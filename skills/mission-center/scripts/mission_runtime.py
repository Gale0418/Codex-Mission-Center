#!/usr/bin/env python3
"""Optional local Runtime Adapter and Mission Control HUD companion."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from optimization_core import atomic_write_json
from runtime_protocol import age_runtime_state, empty_runtime_state, load_last_valid, normalize_codex_message, reduce_event, validate_initialize_response, write_runtime_state


def runtime_path(workspace: Path) -> Path:
    return workspace / "output" / "mission-center-runtime" / "runtime-state.json"


def load_links(workspace: Path) -> dict[str, list[str]]:
    path = workspace / "output" / "mission-center-runtime" / "task-links.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value.get("links", {}) if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def replay(workspace: Path, input_path: Path) -> dict:
    state = empty_runtime_state("replay")
    links = load_links(workspace)
    for sequence, line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        message = json.loads(line)
        for event in normalize_codex_message(message, sequence, links):
            state = reduce_event(state, event)
    write_runtime_state(runtime_path(workspace), state)
    return state


def task_ids_from_workspace(workspace: Path) -> set[str]:
    path = workspace / "MissionCenter" / "tasks.md"
    if not path.is_file():
        return set()
    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells and cells[0] not in {"ID", "---"} and not set(cells[0]) <= {"-", ":"}:
                ids.add(cells[0])
    return ids


def link_task(workspace: Path, agent_id: str, task_ids: list[str]) -> dict:
    valid = task_ids_from_workspace(workspace)
    unknown = sorted(set(task_ids) - valid)
    if unknown:
        raise ValueError(f"Unknown MissionCenter task IDs: {', '.join(unknown)}")
    links = load_links(workspace)
    links[agent_id] = sorted(set(task_ids))
    payload = {"schemaVersion": "1.0", "links": links, "source": "explicit_cli"}
    atomic_write_json(workspace / "output" / "mission-center-runtime" / "task-links.json", payload)
    return payload


class HudHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, session_token: str, **kwargs):
        self.session_token = session_token
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if not is_loopback_host_header(self.headers.get("Host", "")):
            self.send_error(403)
            return
        if self.path in {"/", "/index.html"}:
            self.path = "/mission-center-assets/visual-summary.html"
        super().do_GET()

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
        return urlparse(f"//{value}").hostname in {"127.0.0.1", "localhost", "::1"}
    except ValueError:
        return False


class LoopbackHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def loopback_server_type(host: str) -> type[LoopbackHTTPServer]:
    return type(
        "BoundLoopbackHTTPServer",
        (LoopbackHTTPServer,),
        {"address_family": socket.AF_INET6 if host == "::1" else socket.AF_INET},
    )


def serve(workspace: Path, host: str, port: int) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("HUD companion must bind to loopback")
    output = workspace / "output"
    output.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    handler = partial(HudHandler, directory=str(output), session_token=token)
    server_type = loopback_server_type(host)
    server = server_type((host, port), handler)
    print(f"Mission Control HUD: http://{host}:{server.server_port}/")
    print(f"Session token (controls remain read-only): {token}")
    server.serve_forever()


def validate_websockets_version(version: str) -> None:
    try:
        parts = tuple(int(part) for part in version.split(".")[:2])
    except ValueError as exc:
        raise RuntimeError(f"Unsupported websockets version: {version}") from exc
    if parts < (16, 1) or parts >= (17, 0):
        raise RuntimeError(f"Live runtime requires websockets>=16.1,<17; found {version}")


async def connect_live(workspace: Path, url: str, token_env: str | None) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"ws", "wss"}:
        raise ValueError("--url must use ws:// or wss://")
    if parsed.scheme == "ws" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Plain ws:// is allowed only for loopback")
    try:
        import websockets
        from websockets.asyncio.client import connect
    except ImportError as exc:
        raise RuntimeError("Live runtime requires optional dependency: pip install -r requirements-runtime.txt") from exc
    validate_websockets_version(websockets.__version__)
    headers = None
    if token_env:
        token = os.environ.get(token_env)
        if not token:
            raise ValueError(f"Environment variable {token_env} is empty")
        headers = {"Authorization": f"Bearer {token}"}
    state = empty_runtime_state("connected")
    links = load_links(workspace)
    sequence = 0
    socket_client = await asyncio.wait_for(
        connect(url, additional_headers=headers, origin=None), timeout=10
    )
    initialized = False
    try:
        socket = socket_client
        await socket.send(json.dumps({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "mission-center-runtime", "version": "0.2.0"}}}))
        initialize_response = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        validate_initialize_response(initialize_response, 1)
        await socket.send(json.dumps({"method": "initialized", "params": {}}))
        initialized = True
        while True:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=10)
            except asyncio.TimeoutError:
                state = age_runtime_state(state)
                write_runtime_state(runtime_path(workspace), state)
                continue
            sequence += 1
            message = json.loads(raw)
            events = normalize_codex_message(message, sequence, links)
            for event in events:
                state = reduce_event(state, event)
            if events:
                write_runtime_state(runtime_path(workspace), state)
    finally:
        if initialized:
            write_runtime_state(runtime_path(workspace), age_runtime_state(state, socket_closed=True))
        await socket_client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    serve_cmd = commands.add_parser("serve")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=0)
    replay_cmd = commands.add_parser("replay")
    replay_cmd.add_argument("input")
    connect_cmd = commands.add_parser("connect")
    connect_source = connect_cmd.add_mutually_exclusive_group(required=True)
    connect_source.add_argument("--url")
    connect_source.add_argument("--file", help="One-shot JSONL file fallback.")
    connect_cmd.add_argument("--token-env")
    link_cmd = commands.add_parser("link")
    link_cmd.add_argument("--agent", required=True)
    link_cmd.add_argument("--task", action="append", required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    if args.command == "serve":
        serve(workspace, args.host, args.port)
    elif args.command == "replay":
        print(json.dumps(replay(workspace, Path(args.input)), ensure_ascii=False, indent=2))
    elif args.command == "connect":
        if args.file:
            print(json.dumps(replay(workspace, Path(args.file)), ensure_ascii=False, indent=2))
        else:
            asyncio.run(connect_live(workspace, args.url, args.token_env))
    else:
        print(json.dumps(link_task(workspace, args.agent, args.task), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
