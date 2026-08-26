#!/usr/bin/env python3
"""Fail-safe, local-only Mission Center HUD launcher.

The hook deliberately has a narrow invocation matcher and never persists prompt
content.  It is also safe to run directly with ``show --workspace PATH``.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser
from ctypes import wintypes
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bootstrap_mission_center import MANAGED_VISUAL_ASSETS, copy_visual_assets
from mission_runtime import fingerprint_hud_assets


MAX_STDIN_BYTES = 64 * 1024
MAX_METADATA_BYTES = 16 * 1024
MAX_LOCK_BYTES = 4096
# A launch transaction may wait up to five seconds for runtime health.  Wait
# through that bounded transaction so concurrent hooks reuse its result.
LOCK_ACQUIRE_RETRIES = 120
LOCK_RETRY_DELAY_SECONDS = 0.05
# Windows may briefly deny unlink while a concurrent exclusive-create attempt
# is being resolved.  Keep release bounded and only retry an unchanged lock.
LOCK_RELEASE_RETRIES = 20
COOLDOWN_SECONDS = 3.0
HEALTH_TIMEOUT_SECONDS = 0.8
VISUAL_SUMMARY = Path("output/mission-center-assets/visual-summary.html")
TASKS = Path("MissionCenter/tasks.md")
RUNTIME_DIR = Path("output/mission-center-runtime")
METADATA_NAME = "hud-autolaunch.json"
LOCK_NAME = "hud-autolaunch.lock"
HOOK_EVENT_NAME = "UserPromptSubmit"
PERMISSION_MODES = frozenset({"default", "acceptEdits", "plan", "dontAsk", "bypassPermissions"})
METADATA_FIELDS = frozenset(
    {
        "workspaceFingerprint",
        "port",
        "sessionNonce",
        "url",
        "lastLaunchAt",
        "hudAssetFingerprint",
        "lastSessionId",
        "lastTurnId",
    }
)
INVOCATION_PATTERNS = (
    re.compile(r"(?<![\\\w])\$mission-center(?![\w-])", re.IGNORECASE),
    re.compile(r"(?<![\\\w])plugin://mission-center(?:[/?#][^\s]*)?(?![\w-])", re.IGNORECASE),
    re.compile(r"(?<![\\\w])@mission[ \t]+center(?![\w-])", re.IGNORECASE),
)
QUOTED_SPAN_PATTERN = re.compile(
    r"```.*?```|`[^`\r\n]*`|(?<![\w'])'[^'\r\n]*'(?!\w)|\"[^\"\r\n]*\"|「[^」\r\n]*」|『[^』\r\n]*』",
    re.DOTALL,
)
NEGATED_PREFIX_PATTERN = re.compile(
    r"(?:不要|別|勿|不必|禁止)(?:使用|啟動|開啟|執行|呼叫)?\s*$|"
    r"(?:do not|don't|dont|no need to)"
    r"(?:\s+(?:use|invoke|open|launch|run|activate))?\s*$",
    re.IGNORECASE,
)


def invocation_matches(prompt: object) -> bool:
    """Return true for an explicit invocation outside inline code spans."""
    if not isinstance(prompt, str) or not prompt:
        return False
    # Code/quotation spans and an immediate, unambiguous negation are not a
    # request to open the HUD. This is intentionally bounded lexical handling;
    # semantic routing remains in the skill description.
    visible = QUOTED_SPAN_PATTERN.sub(" ", prompt)
    for pattern in INVOCATION_PATTERNS:
        for match in pattern.finditer(visible):
            prefix = visible[max(0, match.start() - 64) : match.start()]
            if not NEGATED_PREFIX_PATTERN.search(prefix):
                return True
    return False


def bounded_hook_input(stream: Any = None) -> dict[str, Any] | None:
    """Read one bounded hook JSON object; malformed/oversized input is a no-op."""
    stream = stream or sys.stdin.buffer
    try:
        raw = stream.read(MAX_STDIN_BYTES + 1)
        if len(raw) > MAX_STDIN_BYTES:
            return None
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def workspace_paths(workspace: Path) -> tuple[Path, Path]:
    return workspace / TASKS, workspace / VISUAL_SUMMARY


def sync_packaged_hud_assets(workspace: Path) -> str | None:
    """Refresh managed HUD files and return their content fingerprint."""
    tasks, visual = workspace_paths(workspace)
    if not tasks.is_file():
        return None
    target = visual.parent
    if any(path.is_symlink() for path in (target.parent, target)):
        return None
    if any((target / name).is_symlink() for name in MANAGED_VISUAL_ASSETS):
        return None
    try:
        copy_visual_assets(workspace, force=True)
        return fingerprint_hud_assets(target.parent)
    except OSError:
        return None


def workspace_fingerprint(workspace: Path) -> str:
    """Return a stable, non-secret identity that survives normal task updates."""
    identity = os.path.normcase(str(workspace.resolve()))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def metadata_path(workspace: Path) -> Path:
    return workspace / RUNTIME_DIR / METADATA_NAME


def lock_path(workspace: Path) -> Path:
    return workspace / RUNTIME_DIR / LOCK_NAME


def read_metadata(workspace: Path) -> dict[str, Any] | None:
    path = metadata_path(workspace)
    try:
        if path.stat().st_size > MAX_METADATA_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return _sanitize_metadata(value)


def _sanitize_metadata(value: object) -> dict[str, Any] | None:
    """Keep only launcher-owned, non-secret metadata fields."""
    if not isinstance(value, dict):
        return None
    return {key: value[key] for key in METADATA_FIELDS if key in value}


def atomic_metadata(workspace: Path, value: dict[str, Any]) -> None:
    path = metadata_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _sanitize_metadata(value)
    if sanitized is None:
        raise TypeError("HUD metadata must be an object")
    encoded = (
        json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError("HUD metadata exceeds byte limit")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
            finally:
                os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class MetadataLock:
    def __init__(self, workspace: Path):
        self.path = lock_path(workspace)
        self.handle = None
        self.contents = ""

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.contents = json.dumps(
            {
                "pid": os.getpid(),
                "processIdentity": _process_creation_identity(os.getpid()),
                "token": secrets.token_hex(16),
            },
            separators=(",", ":"),
        )
        for attempt in range(LOCK_ACQUIRE_RETRIES):
            try:
                self.handle = self.path.open("x", encoding="ascii")
                self.handle.write(self.contents)
                self.handle.flush()
                return self
            except FileExistsError:
                state = _existing_lock_state(self.path)
                if state is None:
                    # A release can unlink the lock between open("x") and
                    # observation. Retry only when the path truly vanished;
                    # an existing malformed/unknown lock remains fail-closed.
                    if not self.path.exists() and not self.path.is_symlink():
                        continue
                    raise TimeoutError("HUD launcher is already running")
                if state is True and not _lock_has_creation_identity(self.path):
                    raise TimeoutError("HUD launcher is already running")
                if _remove_stale_lock(self.path):
                    continue
            if attempt + 1 < LOCK_ACQUIRE_RETRIES:
                time.sleep(LOCK_RETRY_DELAY_SECONDS)
        raise TimeoutError("HUD launcher is already running")

    def __exit__(self, *_exc):
        if self.handle:
            self.handle.close()
        for attempt in range(LOCK_RELEASE_RETRIES):
            try:
                if self.path.read_text(encoding="ascii") != self.contents:
                    return
                self.path.unlink()
                return
            except FileNotFoundError:
                return
            except (OSError, UnicodeDecodeError):
                if attempt + 1 < LOCK_RELEASE_RETRIES:
                    time.sleep(LOCK_RETRY_DELAY_SECONDS)


def _pid_alive(pid: int) -> bool | None:
    """Return whether *pid* is alive; None means the answer is unknown."""
    if os.name == "nt":
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            open_process = kernel32.OpenProcess
            open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            open_process.restype = wintypes.HANDLE
            get_exit_code = kernel32.GetExitCodeProcess
            get_exit_code.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            get_exit_code.restype = wintypes.BOOL
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL

            handle = open_process(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not handle:
                return False if ctypes.get_last_error() == 87 else None  # ERROR_INVALID_PARAMETER
            exit_code = wintypes.DWORD()
            try:
                if not get_exit_code(handle, ctypes.byref(exit_code)):
                    return None
                return exit_code.value == 259  # STILL_ACTIVE
            finally:
                close_handle(handle)
        except (AttributeError, OSError, OverflowError, TypeError, ValueError):
            return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    except (OSError, OverflowError):
        return None
    return True


def _process_creation_identity(pid: int) -> str | None:
    """Return a PID's creation identity where the platform exposes one."""
    if pid <= 0:
        return None
    if os.name == "nt":
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            open_process = kernel32.OpenProcess
            open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            open_process.restype = wintypes.HANDLE
            get_times = kernel32.GetProcessTimes
            get_times.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
            ]
            get_times.restype = wintypes.BOOL
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL
            handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return None
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            try:
                if not get_times(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel_time), ctypes.byref(user_time)):
                    return None
                value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
                return str(value)
            finally:
                close_handle(handle)
        except (AttributeError, OSError, OverflowError, TypeError, ValueError):
            return None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        _, fields = stat.rsplit(")", 1)
        values = fields.split()
        # /proc stat field 22 (starttime), after state (field 3).
        return values[19]
    except (FileNotFoundError, OSError, IndexError, UnicodeDecodeError):
        return None


def _lock_pid(raw: str) -> int | None:
    try:
        if raw.lstrip().startswith("{"):
            value = json.loads(raw)
            pid = value.get("pid") if isinstance(value, dict) else None
        else:
            pid = raw.strip()
        if isinstance(pid, bool):
            return None
        pid = int(pid)
        return pid if pid > 0 else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _lock_has_creation_identity(path: Path) -> bool:
    """Return whether an active lock carries a creation identity."""
    try:
        raw = path.read_text(encoding="ascii")
        if not raw.lstrip().startswith("{"):
            return False
        value = json.loads(raw)
        if not isinstance(value, dict):
            return False
        expected = value.get("processIdentity")
        return isinstance(expected, str) and bool(expected)
    except (FileNotFoundError, OSError, UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _existing_lock_state(path: Path) -> bool | None:
    """Return True for active, False for stale, and None for unknown/malformed."""
    try:
        if path.stat().st_size > MAX_LOCK_BYTES:
            return None
        raw = path.read_text(encoding="ascii")
        pid = _lock_pid(raw)
        value = json.loads(raw) if raw.lstrip().startswith("{") else {}
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return None
    except json.JSONDecodeError:
        value = {}
    if pid is None:
        return None
    expected_identity = value.get("processIdentity") if isinstance(value, dict) else None
    if isinstance(expected_identity, str) and expected_identity:
        observed_identity = _process_creation_identity(pid)
        if observed_identity is None:
            return None
        return observed_identity == expected_identity
    return _pid_alive(pid)


def _remove_stale_lock(path: Path) -> bool:
    """Remove only a lock whose owner was observed dead; races fail closed."""
    try:
        raw = path.read_text(encoding="ascii")
        if _existing_lock_state(path) is not False:
            return False
        # Re-read both contents and owner identity immediately before unlinking.
        if path.read_text(encoding="ascii") != raw or _existing_lock_state(path) is not False:
            return False
        path.unlink()
        return True
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return False


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _validated_port(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        port = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return port if 1 <= port <= 65535 else None


def health_url(port: object) -> str:
    validated = _validated_port(port)
    if validated is None:
        raise ValueError("invalid loopback port")
    return f"http://127.0.0.1:{validated}/_mission-center/health"


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def check_health(port: object, fingerprint: str, session_nonce: object, asset_fingerprint: object) -> bool:
    try:
        url = health_url(port)
        if not isinstance(session_nonce, str) or not session_nonce:
            return False
        if not isinstance(asset_fingerprint, str) or not asset_fingerprint:
            return False
        with _NO_REDIRECT_OPENER.open(url, timeout=HEALTH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read(4096).decode("utf-8"))
        return (
            isinstance(payload, dict)
            and payload.get("service") == "mission-center-hud"
            and payload.get("workspaceFingerprint") == fingerprint
            and payload.get("sessionNonce") == session_nonce
            and payload.get("hudAssetFingerprint") == asset_fingerprint
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError, urllib.error.URLError):
        return False


def detached_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        return {"creationflags": flags, "close_fds": True}
    return {"start_new_session": True, "close_fds": True}


def launch_server(workspace: Path, port: int, session_nonce: str | None = None) -> subprocess.Popen[Any]:
    runtime = Path(__file__).resolve().with_name("mission_runtime.py")
    session_nonce = session_nonce or secrets.token_urlsafe(24)
    command = [
        sys.executable,
        str(runtime),
        "--workspace",
        str(workspace),
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--session-nonce",
        session_nonce,
    ]
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **detached_kwargs(),
    )


def is_headless() -> bool:
    if os.environ.get("MISSION_CENTER_HEADLESS", "").casefold() in {"1", "true", "yes"}:
        return True
    if os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return True
    return False


def open_browser(url: str) -> bool:
    if is_headless():
        return False
    try:
        return bool(webbrowser.open(url, new=0, autoraise=True))
    except Exception:
        return False


def _launch_or_reuse_locked(workspace: Path, *, now: float, open_ui: bool = False) -> dict[str, Any]:
    """Launch/reuse core; caller must hold the workspace's MetadataLock."""
    asset_fingerprint = sync_packaged_hud_assets(workspace)
    if asset_fingerprint is None:
        return {"status": "unavailable", "reason": "workspace-assets-missing"}
    fingerprint = workspace_fingerprint(workspace)
    previous = read_metadata(workspace)
    previous_port = _validated_port(previous.get("port")) if previous else None
    previous_nonce = previous.get("sessionNonce") if previous else None
    if (
        previous
        and previous.get("workspaceFingerprint") == fingerprint
        and previous_port is not None
        and isinstance(previous_nonce, str)
        and previous.get("hudAssetFingerprint") == asset_fingerprint
        and check_health(previous_port, fingerprint, previous_nonce, asset_fingerprint)
    ):
        try:
            last = float(previous.get("lastLaunchAt", 0) or 0)
        except (TypeError, ValueError):
            last = 0
        url = f"http://127.0.0.1:{previous_port}/"
        if now - last < COOLDOWN_SECONDS:
            updated = dict(previous)
            updated["hudAssetFingerprint"] = asset_fingerprint
            atomic_metadata(workspace, updated)
            return {"status": "cooldown", "url": url, "hudAssetFingerprint": asset_fingerprint}
        if open_ui:
            open_browser(url)
        updated = dict(previous)
        updated["port"] = previous_port
        updated["url"] = url
        updated["lastLaunchAt"] = now
        updated["hudAssetFingerprint"] = asset_fingerprint
        atomic_metadata(workspace, updated)
        return {"status": "reused", "url": url, "hudAssetFingerprint": asset_fingerprint}
    port = choose_port()
    session_nonce = secrets.token_urlsafe(24)
    process = launch_server(workspace, port, session_nonce)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not check_health(port, fingerprint, session_nonce, asset_fingerprint):
        time.sleep(0.05)
    if not check_health(port, fingerprint, session_nonce, asset_fingerprint):
        try:
            process.terminate()
        except (OSError, AttributeError):
            pass
        return {"status": "unavailable", "reason": "server-health-timeout"}
    url = f"http://127.0.0.1:{port}/"
    atomic_metadata(
        workspace,
        {
            "schemaVersion": "1.0",
            "service": "mission-center-hud",
            "workspaceFingerprint": fingerprint,
            "port": port,
            "pid": getattr(process, "pid", None),
            "sessionNonce": session_nonce,
            "url": url,
            "lastLaunchAt": now,
            "hudAssetFingerprint": asset_fingerprint,
        },
    )
    if open_ui:
        open_browser(url)
    return {"status": "launched", "url": url, "hudAssetFingerprint": asset_fingerprint}


def launch_or_reuse(workspace: Path, *, now: float | None = None, open_ui: bool = False) -> dict[str, Any]:
    """Reuse a healthy matching server, or launch one; all failures are non-fatal."""
    workspace = workspace.resolve()
    tasks, _visual = workspace_paths(workspace)
    if not tasks.is_file():
        return {"status": "unavailable", "reason": "workspace-assets-missing"}
    try:
        with MetadataLock(workspace):
            return _launch_or_reuse_locked(
                workspace,
                now=time.time() if now is None else now,
                open_ui=open_ui,
            )
    except (OSError, TimeoutError, ValueError, TypeError):
        return {"status": "unavailable", "reason": "launcher-failure"}


def handle_hook(payload: dict[str, Any], *, open_ui: bool = False) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("hook_event_name") != HOOK_EVENT_NAME:
        return {"status": "ignored", "reason": "invalid-hook-event"}
    prompt = payload.get("prompt")
    turn_id = payload.get("turn_id")
    session_id = payload.get("session_id")
    permission_mode = payload.get("permission_mode")
    cwd = payload.get("cwd")
    if not isinstance(prompt, str):
        return {"status": "ignored", "reason": "invalid-prompt"}
    if not isinstance(turn_id, str) or not turn_id.strip():
        return {"status": "ignored", "reason": "missing-turn-id"}
    if not isinstance(session_id, str) or not session_id.strip():
        return {"status": "ignored", "reason": "missing-session-id"}
    if permission_mode not in PERMISSION_MODES:
        return {"status": "ignored", "reason": "invalid-permission-mode"}
    if not isinstance(cwd, str) or not cwd.strip():
        return {"status": "ignored", "reason": "invalid-cwd"}
    if not invocation_matches(prompt):
        return {"status": "ignored", "reason": "no-explicit-invocation"}
    if permission_mode == "plan":
        return {"status": "ignored", "reason": "plan-mode"}
    workspace = Path(cwd)
    workspace = workspace.resolve()
    tasks, _visual = workspace_paths(workspace)
    if not tasks.is_file():
        return {"status": "unavailable", "reason": "workspace-assets-missing"}
    try:
        with MetadataLock(workspace):
            existing = read_metadata(workspace)
            if (
                existing
                and existing.get("lastSessionId") == session_id
                and existing.get("lastTurnId") == turn_id
            ):
                return {"status": "ignored", "reason": "same-turn"}
            result = _launch_or_reuse_locked(workspace, now=time.time(), open_ui=open_ui)
            if result.get("status") in {"launched", "reused", "cooldown"}:
                metadata = read_metadata(workspace) or {}
                metadata["lastSessionId"] = session_id
                metadata["lastTurnId"] = turn_id
                atomic_metadata(workspace, metadata)
            return result
    except (OSError, TimeoutError, ValueError, TypeError):
        return {"status": "unavailable", "reason": "launcher-failure"}


def hook_specific_output(result: object) -> dict[str, Any] | None:
    """Build a formal UserPromptSubmit context for a successful HUD result."""
    if not isinstance(result, dict) or result.get("status") not in {"launched", "reused", "cooldown"}:
        return None
    raw_url = result.get("url")
    if not isinstance(raw_url, str):
        return None
    try:
        parsed = urlparse(raw_url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.path != "/"
        or parsed.params
        or parsed.query
        or parsed.fragment
        or _validated_port(port) is None
    ):
        return None
    url = f"http://127.0.0.1:{port}/"
    context = (
        f"Mission Center HUD ready at {url}. In Codex Desktop, present this loopback URL "
        "in the built-in sidebar or preview surface when supported; otherwise keep this "
        "clickable URL available. This asynchronous UserPromptSubmit hook cannot guarantee "
        "that a sidebar opens during the current turn. Do not rely on Chrome or another "
        "external browser."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "additionalContext": context,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    hook = commands.add_parser("hook")
    hook_browser = hook.add_mutually_exclusive_group()
    hook_browser.add_argument("--open-browser", action="store_true")
    hook_browser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    show = commands.add_parser("show")
    show.add_argument("--workspace", default=".", type=Path)
    show.add_argument("--open-browser", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "hook":
        payload = bounded_hook_input()
        if payload:
            result = handle_hook(payload, open_ui=args.open_browser)
            output = hook_specific_output(result)
            if output:
                print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
        return 0
    else:
        result = launch_or_reuse(args.workspace, open_ui=args.open_browser)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
