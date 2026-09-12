"""Bounded Linux child runner for explicit local development probes.

The candidate runs below a dedicated Linux PID namespace init.  Namespace-init
semantics make descendant containment atomic: when the supervisor exits, the
kernel terminates every process in that PID namespace, including descendants
that called ``setsid``.  ``unshare --kill-child`` also tears the namespace down
if its outer helper is killed.  Captured stdout/stderr and wall-clock lifetime
are bounded, but this remains development tooling rather than a filesystem,
network, CPU, memory, or process-count security sandbox.

Linux, util-linux ``unshare``, unprivileged user namespaces, and PID namespaces
are required.  Unsupported hosts fail closed instead of silently weakening the
containment contract.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Sequence

_SUPERVISOR_FLAG = "--mission-center-bounded-supervise"
_SUPERVISOR_ERROR_EXIT = 125
_SUPERVISOR_ERROR_MARKER = b"__MC_BOUNDED_SUPERVISOR_ERROR__:"
_READY_ENV = "MC_BOUNDED_READY_FD"
_READY_BYTE = b"R"
_CLEANUP_SECONDS = 2.0
_SETUP_GRACE_SECONDS = 5.0


class OutputLimitError(RuntimeError):
    """The candidate exceeded a stream's capture allowance."""


def _unshare_path() -> str:
    if not sys.platform.startswith("linux"):
        raise RuntimeError("bounded probes require Linux PID namespaces")
    executable = shutil.which("unshare")
    if executable is None:
        raise RuntimeError("bounded probes require util-linux unshare")
    return executable


def _notify_ready() -> None:
    raw = os.environ.pop(_READY_ENV, None)
    if raw is None:
        raise RuntimeError("supervisor readiness descriptor is missing")
    try:
        descriptor = int(raw)
    except ValueError as error:
        raise RuntimeError("supervisor readiness descriptor is invalid") from error
    try:
        if os.write(descriptor, _READY_BYTE) != len(_READY_BYTE):
            raise RuntimeError("supervisor readiness handshake was incomplete")
    finally:
        os.close(descriptor)


def _supervise(argv: list[str]) -> int:
    """PID-namespace init: run one candidate and let kernel teardown contain descendants."""
    try:
        if os.getpid() != 1:
            raise RuntimeError("supervisor is not PID 1 in its containment namespace")
        if not argv:
            raise ValueError("an explicit executable is required")

        stop_requested = False

        def request_stop(_signum, _frame) -> None:
            nonlocal stop_requested
            stop_requested = True

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        _notify_ready()
        candidate = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=None,
            stderr=None,
            close_fds=True,
            start_new_session=False,
        )
        return_code: int | None = None
        while return_code is None and not stop_requested:
            return_code = candidate.poll()
            if return_code is None:
                time.sleep(0.01)
        if stop_requested:
            return 128 + signal.SIGTERM
        if return_code is None:
            return_code = candidate.poll()
        if return_code is None:
            return 128 + signal.SIGKILL
        return return_code if return_code >= 0 else 128 + (-return_code)
    except BaseException as error:  # fixed bounded protocol failure
        message = f"{_SUPERVISOR_ERROR_MARKER.decode()}{type(error).__name__}: {error}\n"
        try:
            os.write(2, message.encode("utf-8", errors="replace")[:4096])
        except OSError:
            pass
        return _SUPERVISOR_ERROR_EXIT


def _terminate_namespace(process: subprocess.Popen[bytes]) -> None:
    """Terminate the outer unshare helper; --kill-child atomically kills namespace PID 1."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=_CLEANUP_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=_CLEANUP_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("candidate namespace cleanup did not complete") from error


def _wait_ready(
    descriptor: int,
    process: subprocess.Popen[bytes],
    abort: threading.Event,
    failures: list[Exception | None],
    deadline: float,
    timeout: float,
) -> None:
    """Require a private readiness byte before treating any exit as candidate output."""
    setup_deadline = min(deadline, time.monotonic() + _SETUP_GRACE_SECONDS)
    while True:
        if abort.is_set():
            failure = next((error for error in failures if error is not None), None)
            raise RuntimeError(str(failure) if failure else "candidate pipe read failed") from failure
        remaining = setup_deadline - time.monotonic()
        if remaining <= 0:
            if deadline <= setup_deadline:
                raise subprocess.TimeoutExpired("candidate namespace setup", timeout)
            raise RuntimeError("candidate namespace setup did not become ready")
        readable, _, _ = select.select([descriptor], [], [], min(0.02, remaining))
        if readable:
            value = os.read(descriptor, 1)
            if value == _READY_BYTE:
                return
            raise RuntimeError("candidate namespace setup failed before readiness")
        if process.poll() is not None:
            raise RuntimeError("candidate namespace setup failed before readiness")


def run_bounded(
    argv: Sequence[str], *, timeout: float = 30.0, max_output_bytes: int = 1024 * 1024,
) -> tuple[int, bytes, bytes]:
    """Capture each stream and contain the complete Linux PID-namespace tree."""
    unshare = _unshare_path()
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("timeout must be a finite positive number")
    timeout = float(timeout)
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
    ready_read, ready_write = os.pipe()
    os.set_inheritable(ready_write, True)
    environment = os.environ.copy()
    environment[_READY_ENV] = str(ready_write)
    supervisor_argv = [
        unshare,
        "--user",
        "--map-root-user",
        "--pid",
        "--fork",
        "--kill-child=SIGKILL",
        sys.executable,
        str(Path(__file__).resolve()),
        _SUPERVISOR_FLAG,
        *argv,
    ]
    try:
        process = subprocess.Popen(
            supervisor_argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
            close_fds=True,
            pass_fds=(ready_write,),
            env=environment,
        )
    finally:
        os.close(ready_write)
    assert process.stdout is not None and process.stderr is not None

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
    primary_error: BaseException | None = None
    try:
        for reader in readers:
            reader.start()
            started.append(reader)
        _wait_ready(ready_read, process, abort, failures, deadline, timeout)
        while True:
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
    except BaseException as error:
        primary_error = error
        raise
    finally:
        os.close(ready_read)
        cleanup_error: BaseException | None = None
        try:
            _terminate_namespace(process)
        except BaseException as error:
            cleanup_error = error
        for reader in started:
            reader.join(timeout=_CLEANUP_SECONDS)
        for index, stream in enumerate((process.stdout, process.stderr)):
            if readers[index] not in started:
                stream.close()
        if any(reader.is_alive() for reader in started):
            cleanup_error = cleanup_error or RuntimeError("candidate pipe cleanup did not complete")
        if cleanup_error is not None:
            raise cleanup_error


def _main(argv: list[str]) -> int:
    if argv and argv[0] == _SUPERVISOR_FLAG:
        return _supervise(argv[1:])
    print("bounded_process.py is an internal development helper", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
