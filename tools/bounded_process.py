"""Bounded POSIX child runner for explicit local development probes.

This controls captured output and process lifetime, not arbitrary filesystem
or network access. It is not a security sandbox. Windows execution fails
closed until equivalent process-tree cleanup is implemented with Job Objects.
"""
from __future__ import annotations

import math
import os
import signal
import subprocess
import threading
import time
from typing import Sequence


class OutputLimitError(RuntimeError):
    """The candidate exceeded a stream's capture allowance."""


def run_bounded(
    argv: Sequence[str], *, timeout: float = 30.0, max_output_bytes: int = 1024 * 1024,
) -> tuple[int, bytes, bytes]:
    """Capture each pipe within its limit; kill the process group on failure.

    Output is consumed concurrently and never spooled to an unbounded file.
    The allowance is per stream. Timeouts include pipe draining, so a child
    cannot evade the deadline by leaving a descendant holding a pipe open.
    """
    if os.name != "posix":
        raise RuntimeError("bounded probes require POSIX process-group cleanup; Windows is unverified")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if isinstance(max_output_bytes, bool) or not isinstance(max_output_bytes, int) or max_output_bytes < 0:
        raise ValueError("output limit must be a non-negative integer")
    if not argv:
        raise ValueError("an explicit executable is required")

    buffers = [bytearray(), bytearray()]
    failures: list[Exception | None] = [None, None]
    done = [threading.Event(), threading.Event()]
    abort = threading.Event()
    process = subprocess.Popen(
        list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, bufsize=0, start_new_session=True,
    )
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
    try:
        for reader in readers:
            reader.start()
            started.append(reader)
        while True:
            if abort.is_set():
                failure = next((error for error in failures if error is not None), None)
                raise RuntimeError(str(failure) if failure else "candidate pipe read failed") from failure
            if all(event.is_set() for event in done) and process.poll() is not None:
                return process.returncode, bytes(buffers[0]), bytes(buffers[1])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(list(argv), timeout)
            abort.wait(min(0.02, remaining))
    finally:
        # The child leads a new session/group. Also stop descendants left behind
        # after a normal direct-child exit; none may keep writing after a probe.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2.0)
        for reader in started:
            reader.join(timeout=2.0)
        for index, stream in enumerate((process.stdout, process.stderr)):
            if readers[index] not in started:
                stream.close()
        if any(reader.is_alive() for reader in started):
            raise RuntimeError("candidate pipe cleanup did not complete")
