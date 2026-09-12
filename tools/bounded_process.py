"""Bounded Linux child runner for explicit local development probes.

This bounds captured output, wall-clock lifetime, and the complete descendant
process tree.  It is still not a filesystem/network security sandbox.  Linux
is required because the supervisor uses ``PR_SET_CHILD_SUBREAPER`` plus
``/proc`` identities to contain descendants that create a new session.  Other
platforms fail closed until an equivalent native containment primitive exists.
"""
from __future__ import annotations

import ctypes
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Sequence

_SUPERVISOR_FLAG = "--mission-center-bounded-supervise"
_SUPERVISOR_ERROR_EXIT = 125
_SUPERVISOR_ERROR_MARKER = b"__MC_BOUNDED_SUPERVISOR_ERROR__:"
_PR_SET_CHILD_SUBREAPER = 36
_CLEANUP_SECONDS = 2.0


class OutputLimitError(RuntimeError):
    """The candidate exceeded a stream's capture allowance."""


def _linux_required() -> None:
    if not sys.platform.startswith("linux") or not Path("/proc/self/stat").is_file():
        raise RuntimeError(
            "bounded probes require Linux subreaper and /proc process-tree containment; "
            "this platform is unverified"
        )


def _proc_snapshot() -> dict[int, tuple[int, str]]:
    """Return pid -> (ppid, starttime) from one best-effort /proc snapshot."""
    snapshot: dict[int, tuple[int, str]] = {}
    try:
        entries = os.scandir("/proc")
    except OSError:
        return snapshot
    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                raw = Path(entry.path, "stat").read_text(encoding="utf-8")
                end = raw.rfind(")")
                fields = raw[end + 2 :].split()
                # The suffix starts at field 3 (state). PPID is field 4 and
                # starttime is field 22, therefore indexes 1 and 19.
                if end < 0 or len(fields) <= 19:
                    continue
                snapshot[int(entry.name)] = (int(fields[1]), fields[19])
            except (OSError, UnicodeDecodeError, ValueError):
                continue
    return snapshot


def _descendants(roots: set[int], snapshot: dict[int, tuple[int, str]]) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, (ppid, _starttime) in snapshot.items():
        children.setdefault(ppid, []).append(pid)
    found: set[int] = set()
    stack = list(roots)
    while stack:
        parent = stack.pop()
        for child in children.get(parent, ()):  # pragma: no branch - compact traversal
            if child not in found and child not in roots:
                found.add(child)
                stack.append(child)
    return found


def _remember_descendants(root_pid: int, tracked: dict[int, str]) -> None:
    snapshot = _proc_snapshot()
    for pid in _descendants({root_pid}, snapshot):
        tracked.setdefault(pid, snapshot[pid][1])


def _identity_alive(pid: int, starttime: str) -> bool:
    current = _proc_snapshot().get(pid)
    return current is not None and current[1] == starttime


def _kill_identity(pid: int, starttime: str) -> None:
    current = _proc_snapshot().get(pid)
    if current is None or current[1] != starttime:
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _reap_children() -> None:
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _set_child_subreaper() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    prctl.restype = ctypes.c_int
    if prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _cleanup_supervised_tree(root_pid: int, tracked: dict[int, str]) -> bool:
    """Kill and reap the complete supervised tree, including setsid escapees."""
    deadline = time.monotonic() + _CLEANUP_SECONDS
    while True:
        _remember_descendants(root_pid, tracked)
        live = [(pid, start) for pid, start in tracked.items() if _identity_alive(pid, start)]
        for pid, start in reversed(live):
            _kill_identity(pid, start)
        _reap_children()
        _remember_descendants(root_pid, tracked)
        remaining = [
            (pid, start) for pid, start in tracked.items() if _identity_alive(pid, start)
        ]
        if not remaining:
            _reap_children()
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)


def _supervise(argv: list[str]) -> int:
    """Linux subreaper entry point executed in an isolated helper process."""
    try:
        _linux_required()
        _set_child_subreaper()
        if not argv:
            raise ValueError("an explicit executable is required")

        stop_requested = False

        def request_stop(_signum, _frame) -> None:
            nonlocal stop_requested
            stop_requested = True

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        candidate = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            # Inherit the supervisor's bounded pipes. Normal children remain
            # in this session; a child that calls setsid is still contained by
            # the subreaper and /proc identity tracking below.
            stdout=None,
            stderr=None,
            close_fds=True,
            start_new_session=False,
        )
        tracked: dict[int, str] = {}
        identity = _proc_snapshot().get(candidate.pid)
        if identity is not None:
            tracked[candidate.pid] = identity[1]

        return_code: int | None = None
        while return_code is None and not stop_requested:
            _remember_descendants(os.getpid(), tracked)
            return_code = candidate.poll()
            if return_code is None:
                time.sleep(0.01)

        if stop_requested:
            return_code = 128 + signal.SIGTERM
        if not _cleanup_supervised_tree(os.getpid(), tracked):
            raise RuntimeError("supervised process-tree cleanup did not complete")
        if return_code is None:
            return_code = candidate.poll()
        if return_code is None:
            return_code = 128 + signal.SIGKILL
        return return_code if return_code >= 0 else 128 + (-return_code)
    except BaseException as error:  # supervisor must report bounded protocol failure
        message = f"{_SUPERVISOR_ERROR_MARKER.decode()}{type(error).__name__}: {error}\n"
        try:
            os.write(2, message.encode("utf-8", errors="replace")[:4096])
        except OSError:
            pass
        return _SUPERVISOR_ERROR_EXIT


def _signal_supervisor(process: subprocess.Popen[bytes], tracked: dict[int, str]) -> None:
    """Ask the subreaper to clean up, with an identity-checked hard fallback."""
    if process.poll() is not None:
        return
    _remember_descendants(process.pid, tracked)
    try:
        os.kill(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + _CLEANUP_SECONDS
    while process.poll() is None and time.monotonic() < deadline:
        _remember_descendants(process.pid, tracked)
        time.sleep(0.01)
    if process.poll() is None:
        # The helper itself is wedged. Kill every identity observed before
        # reparenting can hide it, then the helper's original process group.
        for pid, start in reversed(list(tracked.items())):
            _kill_identity(pid, start)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=_CLEANUP_SECONDS)
    for pid, start in reversed(list(tracked.items())):
        _kill_identity(pid, start)


def run_bounded(
    argv: Sequence[str], *, timeout: float = 30.0, max_output_bytes: int = 1024 * 1024,
) -> tuple[int, bytes, bytes]:
    """Capture each stream and contain the Linux descendant tree within bounds."""
    _linux_required()
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or max_output_bytes < 0:
        raise ValueError("output limit must be a non-negative integer")
    if not argv or any(not isinstance(item, str) or not item or "\0" in item for item in argv):
        raise ValueError("an explicit string executable and arguments are required")
    if sum(len(item.encode("utf-8")) + 1 for item in argv) > 256 * 1024:
        raise ValueError("candidate argument vector exceeds its byte limit")

    buffers = [bytearray(), bytearray()]
    failures: list[Exception | None] = [None, None]
    done = [threading.Event(), threading.Event()]
    abort = threading.Event()
    supervisor_argv = [sys.executable, str(Path(__file__).resolve()), _SUPERVISOR_FLAG, *argv]
    process = subprocess.Popen(
        supervisor_argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        start_new_session=True,
    )
    assert process.stdout is not None and process.stderr is not None
    tracked: dict[int, str] = {}
    supervisor_identity = _proc_snapshot().get(process.pid)
    if supervisor_identity is not None:
        tracked[process.pid] = supervisor_identity[1]

    def read_pipe(index: int, stream) -> None:
        try:
            while True:
                remaining = max_output_bytes - len(buffers[index])
                chunk = stream.read(min(8192, remaining + 1))
                if not chunk:
                    break
                if len(chunk) > remaining:
                    buffers[index].extend(chunk[:remaining])
                    failures[index] = OutputLimitError(
                        f"candidate {'stdout' if index == 0 else 'stderr'} exceeded {max_output_bytes} bytes"
                    )
                    abort.set()
                    return
                buffers[index].extend(chunk)
        except Exception as error:
            failures[index] = error
            abort.set()
        finally:
            stream.close()
            done[index].set()

    readers = [
        threading.Thread(target=read_pipe, args=(0, process.stdout), daemon=True),
        threading.Thread(target=read_pipe, args=(1, process.stderr), daemon=True),
    ]
    deadline = time.monotonic() + timeout
    started: list[threading.Thread] = []
    try:
        for reader in readers:
            reader.start()
            started.append(reader)
        while True:
            _remember_descendants(process.pid, tracked)
            if abort.is_set():
                failure = next((error for error in failures if error is not None), None)
                raise RuntimeError(str(failure) if failure else "candidate pipe read failed") from failure
            if all(event.is_set() for event in done) and process.poll() is not None:
                stderr = bytes(buffers[1])
                if process.returncode == _SUPERVISOR_ERROR_EXIT and _SUPERVISOR_ERROR_MARKER in stderr:
                    detail = stderr.split(_SUPERVISOR_ERROR_MARKER, 1)[1].decode(
                        "utf-8", errors="replace"
                    ).strip()
                    raise RuntimeError(f"candidate supervisor failed: {detail}")
                return process.returncode, bytes(buffers[0]), stderr
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(list(argv), timeout)
            abort.wait(min(0.02, remaining))
    finally:
        _signal_supervisor(process, tracked)
        try:
            process.wait(timeout=_CLEANUP_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=_CLEANUP_SECONDS)
        for reader in started:
            reader.join(timeout=_CLEANUP_SECONDS)
        for index, stream in enumerate((process.stdout, process.stderr)):
            if readers[index] not in started:
                stream.close()
        if any(reader.is_alive() for reader in started):
            raise RuntimeError("candidate pipe cleanup did not complete")


def _main(argv: list[str]) -> int:
    if argv and argv[0] == _SUPERVISOR_FLAG:
        return _supervise(argv[1:])
    print("bounded_process.py is an internal development helper", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
