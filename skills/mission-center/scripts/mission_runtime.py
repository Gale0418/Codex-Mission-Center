#!/usr/bin/env python3
"""Optional local Runtime Adapter and Mission Control HUD companion."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import secrets
import shutil
import socket
import threading
import time
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from bootstrap_mission_center import MANAGED_VISUAL_ASSETS
from common.markdown_table import parse_table
from optimization_core import atomic_write_json
from runtime_protocol import MAX_LINK_AGENT_COUNT, MAX_RUNTIME_LINE_BYTES, MAX_TASK_ID_COUNT, age_runtime_state, empty_runtime_state, load_last_valid, normalize_codex_message, reduce_event, touch_runtime_state, validate_initialize_response, validate_task_links, write_runtime_state, is_opaque_id


MAX_REPLAY_FILE_BYTES = 8 * 1024 * 1024
MAX_REPLAY_EVENTS = 10_000
MAX_MALFORMED_FRAMES = 5
MAX_MALFORMED_BYTES = 256 * 1024
MAX_MALFORMED_WINDOW_SECONDS = 30.0
# Descriptive aliases kept for callers/tests that name each budget dimension.
MAX_MALFORMED_FRAME_COUNT = MAX_MALFORMED_FRAMES
MAX_MALFORMED_FRAME_BYTES = MAX_MALFORMED_BYTES
MAX_MALFORMED_FRAME_WINDOW_SECONDS = MAX_MALFORMED_WINDOW_SECONDS
HUD_ALLOWED_ASSETS = frozenset({
    "visual-summary.html", "visual-state.json",
    "mission-starfield.webp", "mission-starfield.webp.json",
    "mission-fleet-bridge-background.webp", "mission-fleet-bridge-background.webp.json",
    "mission-bridge-background.webp", "mission-bridge-background.webp.json",
})


def runtime_path(workspace: Path) -> Path:
    return workspace / "output" / "mission-center-runtime" / "runtime-state.json"


def load_links(workspace: Path) -> dict[str, list[str]]:
    path = workspace / "output" / "mission-center-runtime" / "task-links.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return validate_task_links(value)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def decode_json_frame(raw: str | bytes) -> dict[str, Any]:
    """Decode one bounded JSON object from stdio/WebSocket input."""
    if isinstance(raw, bytes):
        raw_bytes = raw
        text = raw.decode("utf-8")
    elif isinstance(raw, str):
        text = raw
        raw_bytes = raw.encode("utf-8")
    else:
        raise ValueError("Runtime frame must be text or UTF-8 bytes")
    if len(raw_bytes) > MAX_RUNTIME_LINE_BYTES:
        raise RecoverableTransportError("Runtime frame exceeds line byte limit")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Runtime frame is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Runtime frame must be a JSON object")
    return payload


def replay(workspace: Path, input_path: Path) -> dict:
    try:
        if input_path.stat().st_size > MAX_REPLAY_FILE_BYTES:
            raise ValueError("Replay input exceeds file byte limit")
    except OSError as exc:
        raise ValueError(f"Unable to inspect replay input: {input_path}") from exc
    state = empty_runtime_state("replay")
    links = load_links(workspace)
    event_count = 0
    with input_path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if len(raw_line) > MAX_RUNTIME_LINE_BYTES:
                raise ValueError(f"Replay line {line_number} exceeds line byte limit")
            if not raw_line.strip():
                continue
            event_count += 1
            if event_count > MAX_REPLAY_EVENTS:
                raise ValueError("Replay input exceeds event count limit")
            try:
                message = decode_json_frame(raw_line)
            except (UnicodeDecodeError, ValueError, RecoverableTransportError) as exc:
                raise ValueError(f"Replay line {line_number} is invalid") from exc
            for event in normalize_codex_message(message, line_number, links):
                state = reduce_event(state, event)
    write_runtime_state(runtime_path(workspace), state)
    return state


def task_ids_from_workspace(workspace: Path) -> set[str]:
    path = workspace / "MissionCenter" / "tasks.md"
    if not path.is_file():
        return set()
    try:
        return {row.get("ID", "").strip() for row in parse_table(path) if row.get("ID", "").strip()}
    except ValueError:
        return set()


def packaged_runtime_requirements(script_path: Path | None = None) -> Path:
    """Locate the packaged runtime requirements relative to this script."""
    script = (script_path or Path(__file__)).resolve()
    for directory in (script.parent, *script.parents):
        candidate = directory / "requirements-runtime.txt"
        if candidate.is_file():
            return candidate
    return script.parent / "requirements-runtime.txt"


def link_task(workspace: Path, agent_id: str, task_ids: list[str]) -> dict:
    if not is_opaque_id(agent_id):
        raise ValueError("Agent ID must be an opaque allowlisted ID")
    if not isinstance(task_ids, list) or len(task_ids) > MAX_TASK_ID_COUNT or any(not is_opaque_id(task, task=True) for task in task_ids) or len(set(task_ids)) != len(task_ids):
        raise ValueError("Task links exceed type/count limits")
    valid = task_ids_from_workspace(workspace)
    unknown = sorted(set(task_ids) - valid)
    if unknown:
        raise ValueError(f"Unknown MissionCenter task IDs: {', '.join(unknown)}")
    links = load_links(workspace)
    if len(links) >= MAX_LINK_AGENT_COUNT and agent_id not in links:
        raise ValueError("Task links agent limit exceeded")
    links[agent_id] = sorted(set(task_ids))
    payload = {"schemaVersion": "1.0", "links": links, "source": "explicit_cli"}
    validate_task_links(payload)
    atomic_write_json(workspace / "output" / "mission-center-runtime" / "task-links.json", payload)
    return payload


def fingerprint_hud_assets(output: Path) -> str | None:
    """Fingerprint the managed files this server is currently able to serve."""
    if output.is_symlink():
        return None
    target = output / "mission-center-assets"
    if target.is_symlink():
        return None
    digest = hashlib.sha256()
    try:
        for name in sorted(MANAGED_VISUAL_ASSETS):
            asset = target / name
            if asset.is_symlink() or not asset.is_file():
                return None
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(asset.read_bytes())
            digest.update(b"\0")
    except OSError:
        return None
    return digest.hexdigest()


def health_payload(
    workspace_fingerprint: str,
    nonce: str | None = None,
    session_nonce: str | None = None,
    hud_asset_fingerprint: str | None = None,
) -> dict[str, str]:
    payload = {
        "service": "mission-center-hud",
        "workspaceFingerprint": workspace_fingerprint,
    }
    if isinstance(nonce, str) and 0 < len(nonce) <= 128:
        payload["nonce"] = nonce
    if isinstance(session_nonce, str) and 0 < len(session_nonce) <= 128:
        payload["sessionNonce"] = session_nonce
    if isinstance(hud_asset_fingerprint, str) and 0 < len(hud_asset_fingerprint) <= 128:
        payload["hudAssetFingerprint"] = hud_asset_fingerprint
    return payload


class HudHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, session_token: str, workspace_fingerprint: str = "", health_nonce: str | None = None, session_nonce: str | None = None, **kwargs):
        self.session_token = session_token
        self.workspace_fingerprint = workspace_fingerprint
        self.health_nonce = health_nonce
        self.session_nonce = session_nonce
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if not is_loopback_host_header(self.headers.get("Host", "")):
            self.send_error(403)
            return
        path = _safe_request_path(self.path)
        if path is None:
            self.send_error(404)
            return
        if path == "/_mission-center/health":
            payload = health_payload(
                self.workspace_fingerprint,
                self.health_nonce,
                self.session_nonce,
                fingerprint_hud_assets(Path(self.directory)),
            )
            body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in {"/", "/index.html"}:
            self.send_response(302)
            self.send_header("Location", "/mission-center-assets/visual-summary.html")
            self.end_headers()
            return
        if path == "/mission-center-runtime/runtime-state.json":
            root = Path(self.directory)
            candidate = root / "mission-center-runtime" / "runtime-state.json"
            if not _safe_regular_file(root, candidate):
                self.send_error(404)
                return
            self._serve_file(candidate)
            return
        relative = path.removeprefix("/")
        if not relative.startswith("mission-center-assets/") or relative.count("/") != 1:
            self.send_error(404)
            return
        name = relative.split("/", 1)[1]
        if name not in HUD_ALLOWED_ASSETS:
            self.send_error(404)
            return
        root = Path(self.directory)
        candidate = root / relative
        if not _safe_regular_file(root, candidate):
            self.send_error(404)
            return
        self._serve_file(candidate)

    def do_HEAD(self):
        self.do_GET()

    def _serve_file(self, path: Path) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        content_type = "text/html; charset=utf-8" if path.suffix == ".html" else "application/json; charset=utf-8" if path.suffix == ".json" else "image/webp"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if getattr(self, "command", "GET") != "HEAD":
            self.wfile.write(body)

    def do_POST(self):
        if not is_loopback_host_header(self.headers.get("Host", "")):
            self.send_error(403)
            return
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        expected = f"http://{host}"
        if origin != expected or self.headers.get("X-Mission-Token") != self.session_token:
            self.send_error(403)
            return
        self.send_error(501, "Runtime controls are read-only in v1")


def is_loopback_host_header(value: str) -> bool:
    try:
        parsed = urlparse(f"//{value}")
        return not parsed.username and not parsed.password and not parsed.path and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    except ValueError:
        return False


def _safe_request_path(raw_path: str) -> str | None:
    """Canonicalize URL paths and reject traversal before any filesystem lookup."""
    try:
        path = unquote(urlparse(raw_path).path)
    except (TypeError, ValueError):
        return None
    if not path or "\x00" in path or "\\" in path or any(part == ".." for part in path.split("/")):
        return None
    return path if path.startswith("/") and not path.startswith("//") else None


def _safe_regular_file(root: Path, candidate: Path) -> bool:
    try:
        relative = candidate.relative_to(root)
        parents = (root, *(root / parent for parent in relative.parents if parent != Path(".")))
        if any(part.is_symlink() for part in parents):
            return False
        if candidate.is_symlink() or not candidate.is_file():
            return False
        return candidate.resolve() == candidate and candidate.resolve().is_relative_to(root)
    except (OSError, ValueError):
        return False


class LoopbackHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def loopback_server_type(host: str) -> type[LoopbackHTTPServer]:
    return type(
        "BoundLoopbackHTTPServer",
        (LoopbackHTTPServer,),
        {"address_family": socket.AF_INET6 if host == "::1" else socket.AF_INET},
    )


def serve(workspace: Path, host: str, port: int, session_nonce: str | None = None) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("HUD companion must bind to loopback")
    workspace = workspace.resolve()
    output = workspace / "output"
    if output.is_symlink():
        raise OSError("HUD output directory must not be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    asset_fingerprint = fingerprint_hud_assets(output)
    if asset_fingerprint is None:
        raise OSError("HUD managed assets are unavailable")
    token = secrets.token_urlsafe(24)
    fingerprint = fingerprint_workspace(workspace)
    handler = partial(HudHandler, directory=str(output), session_token=token, workspace_fingerprint=fingerprint, session_nonce=session_nonce)
    server_type = loopback_server_type(host)
    server = server_type((host, port), handler)
    print(f"Mission Control HUD: http://{host}:{server.server_port}/")
    print(f"Session token (controls remain read-only): {token}")
    server.serve_forever()


def fingerprint_workspace(workspace: Path) -> str:
    """Return a stable, non-secret identity for this workspace."""
    import hashlib

    identity = os.path.normcase(str(workspace.resolve()))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class TransportAdapter:
    async def connect(self) -> None:
        raise NotImplementedError

    async def recv(self) -> str:
        raise NotImplementedError

    async def send(self, message: dict[str, Any]) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


class RecoverableTransportError(ConnectionError):
    """A malformed transport frame that can be skipped without dropping the session."""


@dataclass
class MalformedFrameBudget:
    """Bound malformed bursts so a peer cannot force an endless parse loop."""

    consecutive: int = 0
    bytes_seen: int = 0
    started_at: float | None = None

    def valid(self) -> None:
        self.consecutive = 0
        self.bytes_seen = 0
        self.started_at = None

    def record(self, raw: str | bytes, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        size = len(raw) if isinstance(raw, bytes) else len(raw.encode("utf-8", "replace")) if isinstance(raw, str) else 0
        if self.started_at is None or now - self.started_at > MAX_MALFORMED_WINDOW_SECONDS:
            self.consecutive = 0
            self.bytes_seen = 0
            self.started_at = now
        self.consecutive += 1
        self.bytes_seen += size
        if self.consecutive > MAX_MALFORMED_FRAMES or self.bytes_seen > MAX_MALFORMED_BYTES or now - self.started_at > MAX_MALFORMED_WINDOW_SECONDS:
            raise ConnectionError("Malformed transport frame budget exceeded")


class StdioTransport(TransportAdapter):
    def __init__(self, command: list[str], reader: asyncio.StreamReader | None = None, writer: Any = None):
        if not command:
            raise ValueError("Stdio command must not be empty")
        self.command = list(command)
        self.reader = reader
        self.writer = writer
        self.process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task | None = None

    async def connect(self) -> None:
        if self.reader is None or self.writer is None:
            try:
                self.process = await asyncio.create_subprocess_exec(
                    *self.command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=1024 * 1024,
                )
            except OSError as exc:
                raise RuntimeError(
                    "Codex executable cannot be launched directly; pass --codex-executable "
                    "pointing to a standalone CLI executable"
                ) from exc
            self.reader = self.process.stdout
            self.writer = self.process.stdin
            if self.process.stderr:
                self._stderr_task = asyncio.create_task(self._drain_stderr(self.process.stderr))

    async def _drain_stderr(self, stderr: asyncio.StreamReader) -> None:
        try:
            while True:
                line = await stderr.readline()
                if not line:
                    break
        except (asyncio.CancelledError, OSError, ValueError):
            return

    async def recv(self) -> str:
        if self.reader is None:
            raise ConnectionError("Transport not connected")
        try:
            line = await self.reader.readline()
        except ValueError as exc:
            raise RecoverableTransportError("Oversized line on stdio transport") from exc
        if not line:
            raise ConnectionError("EOF reached on stdio transport")
        return line.decode("utf-8", "replace").strip()

    async def send(self, message: dict[str, Any]) -> None:
        if self.writer is None:
            raise ConnectionError("Transport not connected")
        data = (json.dumps(message) + "\n").encode("utf-8")
        if hasattr(self.writer, "write"):
            self.writer.write(data)
            if hasattr(self.writer, "drain"):
                await self.writer.drain()

    async def close(self) -> None:
        if self.writer and hasattr(self.writer, "close"):
            with contextlib.suppress(OSError, RuntimeError):
                self.writer.close()
                if hasattr(self.writer, "wait_closed"):
                    await self.writer.wait_closed()
        if self.process:
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=2)
                except asyncio.TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        self.process.kill()
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self.process.wait(), timeout=2)
        if self._stderr_task:
            if not self._stderr_task.done():
                self._stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, OSError, RuntimeError, ValueError):
                await self._stderr_task


def codex_stdio_command(executable: str | None = None) -> list[str]:
    selected = executable or os.environ.get("CODEX_EXECUTABLE") or shutil.which("codex")
    if not selected:
        raise RuntimeError("Codex executable not found; pass --codex-executable")
    if os.name == "nt" and not os.path.splitext(selected)[1]:
        windows_executable = f"{selected}.exe"
        if os.path.isfile(windows_executable):
            selected = windows_executable
    return [selected, "app-server", "--listen", "stdio://"]


class WebSocketTransport(TransportAdapter):
    def __init__(self, url: str, token_env: str | None = None):
        self.url = url
        self.token_env = token_env
        self.socket = None

    async def connect(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"ws", "wss"}:
            raise ValueError("--url must use ws:// or wss://")
        if parsed.scheme == "ws" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Plain ws:// is allowed only for loopback")
        try:
            import websockets
            from websockets.asyncio.client import connect
        except ImportError as exc:
            requirements = packaged_runtime_requirements()
            raise RuntimeError(
                f'Live runtime requires optional dependency: pip install -r "{requirements}"'
            ) from exc
        validate_websockets_version(websockets.__version__)
        headers = None
        if self.token_env:
            token = os.environ.get(self.token_env)
            if not token:
                raise ValueError(f"Environment variable {self.token_env} is empty")
            headers = {"Authorization": f"Bearer {token}"}
        self.socket = await asyncio.wait_for(
            connect(self.url, additional_headers=headers, origin=None), timeout=10
        )

    async def recv(self) -> str:
        if not self.socket:
            raise ConnectionError("WebSocket not connected")
        return await self.socket.recv()

    async def send(self, message: dict[str, Any]) -> None:
        if not self.socket:
            raise ConnectionError("WebSocket not connected")
        await self.socket.send(json.dumps(message))

    async def close(self) -> None:
        if self.socket:
            await self.socket.close()


def validate_websockets_version(version: str) -> None:
    try:
        parts = tuple(int(part) for part in version.split(".")[:2])
    except ValueError as exc:
        raise RuntimeError(f"Unsupported websockets version: {version}") from exc
    if parts < (16, 1) or parts >= (17, 0):
        raise RuntimeError(f"Live runtime requires websockets>=16.1,<17; found {version}")


async def connect_live(workspace: Path, url: str | None = None, token_env: str | None = None, transport: TransportAdapter | None = None) -> None:
    if transport is None:
        if not url:
            raise ValueError("Either url or transport must be specified")
        transport = WebSocketTransport(url, token_env)

    state = empty_runtime_state("connected")
    links = load_links(workspace)
    sequence = 0
    initialized = False
    has_persisted_live_event = False
    malformed_budget = MalformedFrameBudget()
    try:
        await transport.connect()
        await transport.send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "mission-center-runtime", "version": "0.2.0"}}})
        initialize_response = None
        deadline = asyncio.get_running_loop().time() + 10
        while initialize_response is None:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("No initialize response from the Codex app-server")
            try:
                initialize_raw = await asyncio.wait_for(transport.recv(), timeout=remaining)
            except RecoverableTransportError:
                malformed_budget.record(b"")
                continue
            state = touch_runtime_state(state)
            try:
                candidate = decode_json_frame(initialize_raw)
            except (UnicodeDecodeError, ValueError, RecoverableTransportError):
                malformed_budget.record(initialize_raw)
                continue
            malformed_budget.valid()
            if isinstance(candidate, dict) and candidate.get("id") == 1:
                initialize_response = candidate
        validate_initialize_response(initialize_response, 1)
        await transport.send({"method": "initialized", "params": {}})
        initialized = True
        while True:
            try:
                raw = await asyncio.wait_for(transport.recv(), timeout=10)
            except asyncio.TimeoutError:
                state = age_runtime_state(state)
                write_runtime_state(runtime_path(workspace), state)
                continue
            except RecoverableTransportError:
                malformed_budget.record(b"")
                continue
            sequence += 1
            state = touch_runtime_state(state)
            try:
                message = decode_json_frame(raw)
            except (UnicodeDecodeError, ValueError, RecoverableTransportError):
                malformed_budget.record(raw)
                continue
            malformed_budget.valid()
            events = normalize_codex_message(message, sequence, links)
            if not events:
                continue
            for event in events:
                state = reduce_event(state, event)
            write_runtime_state(runtime_path(workspace), state)
            has_persisted_live_event = True
    finally:
        if initialized and has_persisted_live_event:
            write_runtime_state(runtime_path(workspace), age_runtime_state(state, socket_closed=True))
        await transport.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    serve_cmd = commands.add_parser("serve")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=0)
    serve_cmd.add_argument("--session-nonce")
    replay_cmd = commands.add_parser("replay")
    replay_cmd.add_argument("input")
    connect_cmd = commands.add_parser("connect")
    connect_source = connect_cmd.add_mutually_exclusive_group(required=True)
    connect_source.add_argument("--url")
    connect_source.add_argument("--stdio", action="store_true")
    connect_source.add_argument("--file", help="One-shot JSONL file fallback.")
    connect_cmd.add_argument("--token-env")
    connect_cmd.add_argument("--codex-executable")
    link_cmd = commands.add_parser("link")
    link_cmd.add_argument("--agent", required=True)
    link_cmd.add_argument("--task", action="append", required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    if args.command == "serve":
        serve(workspace, args.host, args.port, args.session_nonce)
    elif args.command == "replay":
        print(json.dumps(replay(workspace, Path(args.input)), ensure_ascii=False, indent=2))
    elif args.command == "connect":
        if args.file:
            print(json.dumps(replay(workspace, Path(args.file)), ensure_ascii=False, indent=2))
        elif args.stdio:
            asyncio.run(connect_live(workspace, transport=StdioTransport(codex_stdio_command(args.codex_executable))))
        elif args.url:
            asyncio.run(connect_live(workspace, url=args.url, token_env=args.token_env))
    else:
        print(json.dumps(link_task(workspace, args.agent, args.task), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
