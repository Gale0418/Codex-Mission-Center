#!/usr/bin/env python3
"""Persist a read-only project map separately from RuntimeState.

The map is derived from ``MissionCenter/project.md`` and ``tasks.md`` only.
Run ``py -3 skills/mission-center/scripts/project_map.py .`` (or ``python3``)
to publish ``output/mission-center-project-map/{project-map.json,
project-map.html,project-map.manifest.json}``. The source fingerprint is
line-ending independent and the manifest is the pair's commit marker.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.markdown_table import parse_table_rows
from visual_state import normalize_tasks


SCHEMA_VERSION = "1.0"
MAP_DIR = Path("output/mission-center-project-map")
JSON_NAME = "project-map.json"
HTML_NAME = "project-map.html"
MANIFEST_NAME = "project-map.manifest.json"
LOCK_NAME = "project-map.lock"
SOURCE_NAMES = ("project.md", "tasks.md")
MAX_SOURCE_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 512 * 1024


def _read_source(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(path)
    before = path.stat()
    if before.st_size > MAX_SOURCE_BYTES:
        raise ValueError(f"source exceeds byte limit: {path.name}")
    raw = path.read_bytes()
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise RuntimeError(f"source changed while reading: {path.name}")
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _read_sources(mission_root: Path) -> dict[str, bytes]:
    """Read the bounded canonical inputs once for one consistent build."""
    root = Path(mission_root)
    if root.is_symlink() or not root.is_dir():
        raise OSError("MissionCenter source root must be a real directory")
    return {name: _read_source(root / name) for name in SOURCE_NAMES}


def _fingerprint_sources(sources: dict[str, bytes]) -> str:
    """Hash one already-captured source snapshot in fixed order."""
    digest = hashlib.sha256()
    for name in SOURCE_NAMES:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sources[name])
        digest.update(b"\0")
    return digest.hexdigest()


def canonical_fingerprint(mission_root: Path) -> str:
    """Hash canonical source names and LF-normalized bytes in one snapshot."""
    return _fingerprint_sources(_read_sources(mission_root))


def _language(tasks_text: str, project_text: str) -> str:
    return "zh-TW" if any(marker in f"{tasks_text}\n{project_text}" for marker in ("標題", "狀態", "# 任務")) else "en"


def _first_heading(project_text: str) -> str:
    for line in project_text.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return match.group(1)
    return "MissionCenter"


def _goal(project_text: str, language: str) -> str:
    labels = ("目標", "Goal") if language == "zh-TW" else ("Goal", "目標")
    for line in project_text.splitlines():
        for label in labels:
            match = re.match(rf"^\s*(?:[-*]\s*)?{re.escape(label)}\s*[:：]\s*(.+?)\s*$", line, re.IGNORECASE)
            if match:
                return match.group(1)
    return ""


def _split_dependencies(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return [item.strip() for item in re.split(r"[,，、]", value) if item.strip()]


def _parse_tasks_text(tasks_text: str) -> list[dict[str, str]]:
    rows, errors = parse_table_rows(
        tasks_text.splitlines(), table_name="tasks.md", include_indented=False, strict=True
    )
    if errors:
        raise ValueError(errors[0])
    return rows


def _node(task: dict[str, str]) -> dict[str, Any]:
    dependencies = _split_dependencies(task.get("Depends on", ""))
    parent = task.get("Parent", "").strip()
    return {
        "id": task["ID"],
        "title": task["Title"],
        "type": task.get("Type", ""),
        "parentId": parent or None,
        "priority": task.get("Priority", ""),
        "status": task["Status"],
        "owner": task.get("Owner", ""),
        "dependsOn": dependencies,
    }


def _edges(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for node in nodes:
        if node["parentId"]:
            edges.append({"from": node["parentId"], "to": node["id"], "kind": "parent"})
        edges.extend({"from": dependency, "to": node["id"], "kind": "dependsOn"} for dependency in node["dependsOn"])
    return edges


PROJECT_MAP_STATUSES = frozenset({"Backlog", "Ready", "In Progress", "Blocked", "Review", "Done"})
PROJECT_MAP_NODE_FIELDS = frozenset(
    {"id", "title", "type", "parentId", "priority", "status", "owner", "dependsOn"}
)


def validate_project_map(value: dict[str, Any]) -> None:
    """Validate the public Project Map shape without third-party dependencies."""
    required = {"schemaVersion", "sourceFingerprint", "sources", "generatedAt", "language", "project", "counts", "nodes", "edges", "generation"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("project map is missing required fields")
    if value["schemaVersion"] != SCHEMA_VERSION or not isinstance(value["sourceFingerprint"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["sourceFingerprint"]):
        raise ValueError("project map has invalid schema or source fingerprint")
    if value["sources"] != ["MissionCenter/project.md", "MissionCenter/tasks.md"]:
        raise ValueError("project map has invalid sources")
    if not isinstance(value["generatedAt"], str) or not value["generatedAt"]:
        raise ValueError("project map generatedAt must be a non-empty string")
    if value["language"] not in {"en", "zh-TW"}:
        raise ValueError("project map has unsupported language")
    if not isinstance(value["generation"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["generation"]):
        raise ValueError("project map has invalid generation")
    project = value["project"]
    if not isinstance(project, dict) or set(project) != {"name", "goal"} or not all(isinstance(project.get(key), str) for key in ("name", "goal")):
        raise ValueError("project map project fields must be strings")
    counts = value["counts"]
    nodes = value["nodes"]
    edges = value["edges"]
    if not isinstance(counts, dict) or set(counts) != {"total", "byStatus"} or not isinstance(counts.get("total"), int) or isinstance(counts.get("total"), bool) or counts["total"] < 0:
        raise ValueError("project map counts.total must be a non-negative integer")
    if not isinstance(nodes, list) or counts["total"] != len(nodes):
        raise ValueError("project map counts.total does not match nodes")
    by_status = counts.get("byStatus")
    if not isinstance(by_status, dict) or any(status not in PROJECT_MAP_STATUSES or not isinstance(count, int) or isinstance(count, bool) or count < 0 for status, count in by_status.items()):
        raise ValueError("project map counts.byStatus is invalid")
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) != PROJECT_MAP_NODE_FIELDS:
            raise ValueError("project map node is missing required fields")
        if not all(isinstance(node[key], str) for key in ("id", "title", "type", "priority", "status", "owner")) or not node["id"]:
            raise ValueError("project map node string field is invalid")
        if node["id"] in seen or node["status"] not in PROJECT_MAP_STATUSES:
            raise ValueError("project map has duplicate or invalid node status")
        if node["parentId"] is not None and not isinstance(node["parentId"], str):
            raise ValueError("project map parentId must be string or null")
        if not isinstance(node["dependsOn"], list) or not all(isinstance(item, str) for item in node["dependsOn"]):
            raise ValueError("project map dependsOn must be a string list")
        seen.add(node["id"])
    expected_statuses = {status: sum(node["status"] == status for node in nodes) for status in PROJECT_MAP_STATUSES}
    if {key: value for key, value in expected_statuses.items() if value} != by_status:
        raise ValueError("project map counts.byStatus does not match nodes")
    if not isinstance(edges, list):
        raise ValueError("project map edges must be a list")
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {"from", "to", "kind"}:
            raise ValueError("project map edge shape is invalid")
        if not all(isinstance(edge[key], str) and edge[key] for key in ("from", "to", "kind")) or edge["kind"] not in {"parent", "dependsOn"}:
            raise ValueError("project map edge value is invalid")
        if edge["from"] not in seen or edge["to"] not in seen:
            raise ValueError("project map edge references an unknown node")


def _generation(source_fingerprint: str, generated_at: str) -> str:
    return hashlib.sha256(f"{source_fingerprint}\0{generated_at}".encode("utf-8")).hexdigest()


def validate_published_manifest(output: Path) -> dict[str, Any]:
    """Validate the manifest commit marker and both published file hashes."""
    output = Path(output)
    manifest_path = output / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("project map manifest is unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("project map manifest has an invalid schema")
    generation = manifest.get("generation")
    fingerprint = manifest.get("sourceFingerprint")
    files = manifest.get("files")
    if not isinstance(generation, str) or not re.fullmatch(r"[0-9a-f]{64}", generation):
        raise ValueError("project map manifest has an invalid generation")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("project map manifest has an invalid source fingerprint")
    if not isinstance(files, dict) or set(files) != {JSON_NAME, HTML_NAME} or not all(
        isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) for digest in files.values()
    ):
        raise ValueError("project map manifest file hashes are invalid")
    for name, expected in files.items():
        path = output / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"project map manifest does not match {name}")
    try:
        value = json.loads((output / JSON_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("project map JSON is unreadable") from exc
    validate_project_map(value)
    if value["generation"] != generation or value["sourceFingerprint"] != fingerprint:
        raise ValueError("project map manifest generation does not match JSON")
    return manifest


def build_project_map(workspace: Path, *, generated_at: str | None = None) -> dict[str, Any]:
    """Build a bounded JSON map from canonical MissionCenter task sources."""
    workspace = Path(workspace)
    mission_root = workspace / "MissionCenter"
    sources = _read_sources(mission_root)
    project_bytes = sources["project.md"]
    tasks_bytes = sources["tasks.md"]
    project_text = project_bytes.decode("utf-8")
    tasks_text = tasks_bytes.decode("utf-8")
    tasks = normalize_tasks(_parse_tasks_text(tasks_text))
    ids = [task["ID"] for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task ID in canonical tasks.md")
    nodes = [_node(task) for task in tasks]
    status_counts: dict[str, int] = {}
    for task in tasks:
        status_counts[task["Status"]] = status_counts.get(task["Status"], 0) + 1
    timestamp = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source_fingerprint = _fingerprint_sources(sources)
    value = {
        "schemaVersion": SCHEMA_VERSION,
        "sourceFingerprint": source_fingerprint,
        "sources": [f"MissionCenter/{name}" for name in SOURCE_NAMES],
        "generatedAt": timestamp,
        "generation": _generation(source_fingerprint, timestamp),
        "language": _language(tasks_text, project_text),
        "project": {"name": _first_heading(project_text), "goal": _goal(project_text, _language(tasks_text, project_text))},
        "counts": {"total": len(nodes), "byStatus": status_counts},
        "nodes": nodes,
        "edges": _edges(nodes),
    }
    validate_project_map(value)
    return value


def _json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def render_html(value: dict[str, Any]) -> str:
    """Render a dependency-free, escaped HTML view of the persisted map."""
    project = value["project"]
    rows = []
    for node in value["nodes"]:
        deps = ", ".join(node["dependsOn"]) or "—"
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(node['id'])}</code></td>"
            f"<td>{html.escape(node['title'])}</td>"
            f"<td>{html.escape(node['status'])}</td>"
            f"<td>{html.escape(deps)}</td>"
            "</tr>"
        )
    title = html.escape(str(project.get("name") or "MissionCenter"))
    goal = html.escape(str(project.get("goal") or ""))
    fingerprint = html.escape(str(value["sourceFingerprint"]))
    generation = html.escape(str(value["generation"]))
    return (
        "<!doctype html>\n<html lang=\"" + html.escape(value["language"]) + "\">\n<head>"
        "<meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<meta name=\"project-map-generation\" content=\"{generation}\"><meta name=\"project-map-fingerprint\" content=\"{fingerprint}\">"
        f"<title>{title} · Project Map</title><style>body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd;padding:.5rem;text-align:left}"
        "code{font-family:ui-monospace,monospace}small{color:#52606d}</style></head><body>"
        f"<h1>{title}</h1><p>{goal}</p><small>Source fingerprint: <code>{fingerprint}</code></small>"
        "<table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Depends on</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>\n"
    )


def _atomic_write(path: Path, content: str) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise ValueError(f"project map output exceeds byte limit: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError(f"project map destination must not be a symlink: {path}")
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ProjectMapLock:
    """Small process lock; stale locks fail closed for safe explicit recovery."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._token = secrets.token_urlsafe(18)
        self._owned = False

    def __enter__(self) -> "ProjectMapLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise TimeoutError("project map lock is busy; remove it only after explicit owner recovery") from None
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as stream:
            json.dump({"pid": os.getpid(), "token": self._token}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        self._owned = True
        return self

    def __exit__(self, *_args: object) -> None:
        if not self._owned:
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("pid") == os.getpid() and raw.get("token") == self._token:
                self.path.unlink(missing_ok=True)
        except (OSError, ValueError, json.JSONDecodeError):
            pass


def publish_project_map(workspace: Path, *, generated_at: str | None = None) -> dict[str, str]:
    """Publish per-file atomics plus a manifest commit marker while locked."""
    workspace = Path(workspace).resolve()
    output = workspace / MAP_DIR
    if output.parent.is_symlink() or output.is_symlink():
        raise OSError("project map output must not contain symlinks")
    with ProjectMapLock(output / LOCK_NAME):
        value = build_project_map(workspace, generated_at=generated_at)
        if canonical_fingerprint(workspace / "MissionCenter") != value["sourceFingerprint"]:
            raise RuntimeError("MissionCenter sources changed during project map build")
        json_text = _json_text(value)
        html_text = render_html(value)
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "generation": value["generation"],
            "sourceFingerprint": value["sourceFingerprint"],
            "files": {
                JSON_NAME: hashlib.sha256(json_text.encode("utf-8")).hexdigest(),
                HTML_NAME: hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
            },
        }
        _atomic_write(output / JSON_NAME, json_text)
        _atomic_write(output / HTML_NAME, html_text)
        if canonical_fingerprint(workspace / "MissionCenter") != value["sourceFingerprint"]:
            raise RuntimeError("MissionCenter sources changed during project map publish")
        _atomic_write(output / MANIFEST_NAME, _json_text(manifest))
    return {"json": str(output / JSON_NAME), "html": str(output / HTML_NAME), "manifest": str(output / MANIFEST_NAME), "sourceFingerprint": value["sourceFingerprint"], "generation": value["generation"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(publish_project_map(args.workspace), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
