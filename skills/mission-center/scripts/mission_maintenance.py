#!/usr/bin/env python3
"""Maintain compact MissionCenter hot-context views without model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sync_mission_center import TEXT, _find_summary_value, detect_language, parse_table
from visual_state import normalize_tasks


SCHEMA_VERSION = "1.0"
FINGERPRINT_FORMAT = "sha256-v1"
DEFAULT_BRIEF_MAX_BYTES = 4096
DERIVED_WARNING = "Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files."
FINGERPRINT_SOURCES = ("project.md", "tasks.md", "guardrails.md", "daily-log.md")
FOCUS_FINGERPRINT_SOURCES = ("tasks.md",)
DONE_STATUS = "done"
GUARDRAIL_HEADER_ALIASES = {
    "嚴重度": "Severity",
    "適用情境": "Applies when",
    "曾踩過的坑": "Pitfall",
    "必須遵守": "Must follow",
    "驗證方式": "Verification",
    "來源": "Source",
    "最後確認": "Last confirmed",
    "狀態": "Status",
}
GUARDRAIL_REQUIRED = (
    "ID",
    "Severity",
    "Applies when",
    "Pitfall",
    "Must follow",
    "Verification",
    "Source",
    "Last confirmed",
    "Status",
)
GUARDRAIL_SEVERITIES = {"Critical", "High", "Medium", "Low"}
GUARDRAIL_STATUSES = {"Active", "Superseded"}
GUARDRAIL_VALUE_ALIASES = {
    "Severity": {"關鍵": "Critical", "嚴重": "Critical", "高": "High", "中": "Medium", "低": "Low"},
    "Status": {"啟用": "Active", "有效": "Active", "已取代": "Superseded", "已替代": "Superseded"},
}


def mission_root(workspace: Path) -> Path:
    candidate = Path(workspace).expanduser().resolve()
    return candidate if candidate.name.casefold() == "missioncenter" else candidate / "MissionCenter"


def local_date(value: str | date | None = None) -> date:
    if value is None:
        return datetime.now().astimezone().date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def atomic_write_if_changed(path: Path, content: str) -> bool:
    """Atomically write UTF-8 text only when bytes changed."""
    path = Path(path)
    try:
        if path.read_text(encoding="utf-8") == content:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


# Backward-compatible name used by the first implementation slice.
atomic_write = atomic_write_if_changed


def compute_content_hash(content: str | bytes) -> str:
    raw = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(raw).hexdigest()


def compute_workspace_fingerprint(
    workspace: Path, sources_to_hash: tuple[str, ...] = FINGERPRINT_SOURCES
) -> dict[str, Any]:
    """Hash canonical inputs that affect one materialized view."""
    root = mission_root(workspace)
    digest = hashlib.sha256()
    sources: dict[str, str] = {}
    digest.update(f"mission-center-hot-context:{SCHEMA_VERSION}\0".encode())
    for name in sources_to_hash:
        path = root / name
        if path.is_file():
            raw = path.read_bytes()
            source_hash = hashlib.sha256(raw).hexdigest()
        else:
            raw = b"<missing>"
            source_hash = "missing"
        sources[name] = source_hash
        digest.update(name.encode("utf-8") + b"\0" + raw + b"\0")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "format": FINGERPRINT_FORMAT,
        "value": digest.hexdigest(),
        "sources": sources,
    }


def is_fingerprint_stale(current_fp: dict[str, Any], cached_fp: dict[str, Any]) -> bool:
    return (
        current_fp.get("format") != cached_fp.get("format")
        or current_fp.get("value") != cached_fp.get("value")
    )


def parse_derived_fingerprint(text: str) -> dict[str, str]:
    match = re.search(
        r"mission-center-derived\s+schema=(\S+)\s+fingerprint-format=(\S+)\s+source-fingerprint=([0-9a-f]{64})",
        text,
    )
    if not match:
        return {}
    return {"schemaVersion": match.group(1), "format": match.group(2), "value": match.group(3)}


def parse_tasks(tasks_path: Path) -> list[dict[str, str]]:
    rows = parse_table(tasks_path)
    return normalize_tasks(rows) if rows else []


def extract_focus_tasks(tasks: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        task
        for task in tasks
        if task.get("Priority", "").strip().casefold() == "p0"
        and task.get("Status", "").strip().casefold() != DONE_STATUS
    ]


def normalize_guardrail_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = []
    for row in rows:
        normalized_row = {}
        for key, value in row.items():
            canonical_key = GUARDRAIL_HEADER_ALIASES.get(str(key).strip(), str(key).strip())
            cleaned = str(value).strip()
            normalized_row[canonical_key] = GUARDRAIL_VALUE_ALIASES.get(canonical_key, {}).get(cleaned, cleaned)
        normalized.append(normalized_row)
    return normalized


def read_guardrails(path: Path) -> list[dict[str, str]]:
    return normalize_guardrail_rows(parse_table(path)) if path.is_file() else []


def active_guardrail_ids(rows: list[dict[str, str]]) -> list[str]:
    return [row.get("ID", "") for row in rows if row.get("Status") == "Active" and row.get("ID")]


def guardrails_template(language: str) -> str:
    if language == "zh-TW":
        return (
            "# 重要護欄\n\n"
            "自動化不得新增、升格或停用護欄；變更必須經人工明確核准。\n\n"
            "| ID | 嚴重度 | 適用情境 | 曾踩過的坑 | 必須遵守 | 驗證方式 | 來源 | 最後確認 | 狀態 |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        )
    return (
        "# Guardrails\n\n"
        "Automation must not add, promote, or retire guardrails without explicit human approval.\n\n"
        "| ID | Severity | Applies when | Pitfall | Must follow | Verification | Source | Last confirmed | Status |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    )


def parse_daily_log(text: str) -> tuple[str | None, dict[str, list[str]]]:
    last_organized = None
    entries: dict[str, list[str]] = {}
    current_date = None
    for line in text.splitlines():
        stripped = line.strip()
        match = re.match(r"^- (?:Last organized|最後整理)[：:]\s*(\d{4}-\d{2}-\d{2})$", stripped)
        if match:
            last_organized = match.group(1)
            continue
        match = re.match(r"^## (\d{4}-\d{2}-\d{2})$", stripped)
        if match:
            current_date = match.group(1)
            entries.setdefault(current_date, [])
            continue
        if current_date and stripped.startswith("- "):
            message = stripped[2:].strip()
            if message and message not in {"None", "無"} and message not in entries[current_date]:
                entries[current_date].append(message)
    return last_organized, entries


def render_daily_log(language: str, organized: str, entries: dict[str, list[str]]) -> str:
    title = "每日紀錄" if language == "zh-TW" else "Daily Log"
    organized_label = "最後整理" if language == "zh-TW" else "Last organized"
    separator = "：" if language == "zh-TW" else ":"
    lines = [f"# {title}", "", f"- {organized_label}{separator} {organized}"]
    for day in sorted(entries, reverse=True):
        lines.extend(["", f"## {day}"])
        messages = entries[day]
        lines.extend(f"- {message}" for message in messages)
        if not messages:
            lines.append("- 無" if language == "zh-TW" else "- None")
    return "\n".join(lines).rstrip() + "\n"


def daily_log_template(language: str, organized: str) -> str:
    return render_daily_log(language, organized, {})


def organize_daily_log(root: Path, day: date, message: str | None = None) -> tuple[bool, list[str]]:
    language = detect_language(root)
    path = root / "daily-log.md"
    existing = path.read_text(encoding="utf-8") if path.is_file() else daily_log_template(language, day.isoformat())
    _, entries = parse_daily_log(existing)
    day_key = day.isoformat()
    if message:
        cleaned = " ".join(message.split())
        if cleaned and cleaned not in entries.setdefault(day_key, []):
            entries[day_key].append(cleaned)
    content = render_daily_log(language, day_key, entries)
    return atomic_write_if_changed(path, content), entries.get(day_key, [])


def append_daily_log(path: Path, message: str, date_str: str | None = None) -> bool:
    root = path.parent
    if path.name != "daily-log.md":
        path = root / "daily-log.md"
    before = path.read_text(encoding="utf-8") if path.is_file() else None
    organize_daily_log(root, local_date(date_str), message)
    after = path.read_text(encoding="utf-8")
    return before != after


def validate_daily_log_text(text: str) -> list[str]:
    """Validate the compact daily journal without changing it."""
    errors: list[str] = []
    organized_matches = re.findall(
        r"^- (?:Last organized|最後整理)[：:]\s*(\S+)$", text, flags=re.MULTILINE
    )
    if len(organized_matches) != 1:
        errors.append("daily-log.md must contain exactly one Last organized field")
    elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", organized_matches[0]):
        errors.append("daily-log.md Last organized must use YYYY-MM-DD")
    else:
        try:
            date.fromisoformat(organized_matches[0])
        except ValueError:
            errors.append("daily-log.md Last organized is not a valid date")

    headings = re.findall(r"^## (\S+)$", text, flags=re.MULTILINE)
    valid_dates: list[str] = []
    for heading in headings:
        try:
            date.fromisoformat(heading)
            valid_dates.append(heading)
        except ValueError:
            errors.append(f"daily-log.md has invalid date heading: {heading}")
    if len(valid_dates) != len(set(valid_dates)):
        errors.append("daily-log.md contains duplicate date sections")
    if valid_dates != sorted(valid_dates, reverse=True):
        errors.append("daily-log.md date sections must be newest first")
    return errors


def validate_guardrails(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for number, row in enumerate(rows, start=1):
        missing = [field for field in GUARDRAIL_REQUIRED if not row.get(field, "").strip()]
        if missing:
            errors.append(f"guardrails.md row {number} is missing: {', '.join(missing)}")
            continue
        identifier = row["ID"]
        if not re.fullmatch(r"GR-\d{3}", identifier):
            errors.append(f"guardrails.md row {number} has invalid ID: {identifier}")
        if identifier in seen:
            errors.append(f"guardrails.md contains duplicate ID: {identifier}")
        seen.add(identifier)
        if row["Severity"] not in GUARDRAIL_SEVERITIES:
            errors.append(f"guardrails.md {identifier} has invalid severity: {row['Severity']}")
        if row["Status"] not in GUARDRAIL_STATUSES:
            errors.append(f"guardrails.md {identifier} has invalid status: {row['Status']}")
        try:
            date.fromisoformat(row["Last confirmed"])
        except ValueError:
            errors.append(f"guardrails.md {identifier} has invalid Last confirmed date")
    return errors


def project_identity(root: Path, language: str) -> tuple[str, str, str]:
    text = (root / "project.md").read_text(encoding="utf-8") if (root / "project.md").is_file() else ""
    labels = TEXT[language]
    project = _find_summary_value(text, [labels["project_label"], "Project", "專案"]) or root.parent.name
    goal = _find_summary_value(text, [labels["goal_label"], "Goal", "目標"]) or ""
    cycle = _find_summary_value(text, [labels["cycle_label"], "Cycle", "週期"]) or ""
    return project, goal, cycle


def _escape_cell(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def _bounded_lines(items: list[str], limit: int, none_label: str) -> list[str]:
    if not items:
        return [f"- {none_label}"]
    visible = items[:limit]
    lines = [f"- {item}" for item in visible]
    if len(items) > limit:
        lines.append(f"- [TRUNCATED] {len(items) - limit} additional items require canonical file access.")
    return lines


def render_focus(tasks: list[dict[str, str]], fingerprint: dict[str, Any], language: str) -> str:
    focus = extract_focus_tasks(tasks)
    title = "P0 焦點" if language == "zh-TW" else "P0 Focus"
    source_label = "唯一真實來源" if language == "zh-TW" else "Source of truth"
    count_label = "未完成 P0" if language == "zh-TW" else "Unfinished P0"
    headers = (
        "| ID | 標題 | 狀態 | 下一步 | 依賴 | 驗證方式 |"
        if language == "zh-TW"
        else "| ID | Title | Status | Next action | Depends on | Verification |"
    )
    header_lines = [
        f"<!-- {DERIVED_WARNING} -->",
        f"<!-- mission-center-derived schema={SCHEMA_VERSION} fingerprint-format={FINGERPRINT_FORMAT} source-fingerprint={fingerprint['value']} -->",
        f"# {title}",
        "",
        f"- {source_label}: `tasks.md`",
        f"- {count_label}: {len(focus)}",
        "",
        headers,
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines = list(header_lines)
    for task in focus:
        lines.append(
            "| " + " | ".join(
                _escape_cell(task.get(field, ""))
                for field in ("ID", "Title", "Status", "Next action", "Depends on", "Verification")
            ) + " |"
        )
    return "\n".join(lines).rstrip() + "\n"


def render_brief(
    workspace: Path,
    tasks: list[dict[str, str]],
    fingerprint: dict[str, Any] | None = None,
    day: date | None = None,
    daily_entries: list[str] | None = None,
    guardrails: list[dict[str, str]] | None = None,
    max_bytes: int = DEFAULT_BRIEF_MAX_BYTES,
) -> str:
    root = mission_root(workspace)
    language = detect_language(root)
    day = day or local_date()
    fingerprint = fingerprint or compute_workspace_fingerprint(root)
    daily_entries = daily_entries or []
    guardrails = guardrails if guardrails is not None else read_guardrails(root / "guardrails.md")
    project, goal, cycle = project_identity(root, language)
    none_label = "無" if language == "zh-TW" else "None"
    p0 = extract_focus_tasks(tasks)
    active = [task for task in tasks if task.get("Status") in {"Ready", "In Progress"}]
    blocked = [task for task in tasks if task.get("Status") == "Blocked"]
    review = [task for task in tasks if task.get("Status") == "Review"]
    active_guardrails = active_guardrail_ids(guardrails)

    def task_lines(rows: list[dict[str, str]], limit: int = 8) -> list[str]:
        return _bounded_lines(
            [f"{_escape_cell(row.get('ID'))} · {_escape_cell(row.get('Title'))} · {row.get('Status')}" for row in rows],
            limit,
            none_label,
        )

    labels = {
        "title": "任務簡報" if language == "zh-TW" else "Mission Brief",
        "project": "專案" if language == "zh-TW" else "Project",
        "goal": "北極星" if language == "zh-TW" else "North Star",
        "cycle": "週期" if language == "zh-TW" else "Cycle",
        "p0": "未完成 P0" if language == "zh-TW" else "Unfinished P0",
        "active": "進行中／就緒" if language == "zh-TW" else "Active / Ready",
        "blocked": "阻塞" if language == "zh-TW" else "Blocked",
        "review": "審查" if language == "zh-TW" else "Review",
        "today": "今日摘要" if language == "zh-TW" else "Today's Summary",
        "guardrails": "重要護欄" if language == "zh-TW" else "Relevant Guardrails",
        "route": "需要時再讀" if language == "zh-TW" else "Read Next Only When Needed",
    }
    header_lines = [
        f"<!-- {DERIVED_WARNING} -->",
        f"<!-- mission-center-derived schema={SCHEMA_VERSION} fingerprint-format={FINGERPRINT_FORMAT} source-fingerprint={fingerprint['value']} -->",
        f"# {labels['title']}",
        "",
        f"- Last organized: {day.isoformat()}",
        f"- Source fingerprint: `{fingerprint['value']}`",
        "- Source of truth: `tasks.md`",
        f"- {labels['project']}: {project}",
        f"- {labels['goal']}: {goal or none_label}",
        f"- {labels['cycle']}: {cycle or none_label}",
    ]
    lines = [
        *header_lines,
        "",
        f"## {labels['p0']} ({len(p0)})",
        *task_lines(p0, 10),
        "",
        f"## {labels['active']} ({len(active)})",
        *task_lines(active),
        "",
        f"## {labels['blocked']} ({len(blocked)})",
        *task_lines(blocked),
        "",
        f"## {labels['review']} ({len(review)})",
        *task_lines(review),
        "",
        f"## {labels['today']} · {day.isoformat()}",
        *_bounded_lines(daily_entries, 8, none_label),
        "",
        f"## {labels['guardrails']} ({len(active_guardrails)})",
        *_bounded_lines(active_guardrails, 20, none_label),
        "",
        f"## {labels['route']}",
        "- Modify task lifecycle/order → `tasks.md`",
        "- Need rationale/evidence → `decisions.md`, `notes.md`, `smoke-tests.md`",
        "- Brief/focus stale or truncated → run `mission_maintenance.py sync` and open canonical files",
    ]
    content = "\n".join(lines).rstrip() + "\n"
    if len(content.encode("utf-8")) <= max_bytes:
        return content
    minimal = header_lines + [
        "",
        "## Context counts",
        f"- P0: {len(p0)}",
        f"- Active: {len(active)}",
        f"- Blocked: {len(blocked)}",
        f"- Review: {len(review)}",
        f"- Guardrails: {len(active_guardrails)}",
        "- [TRUNCATED] Brief exceeded its byte budget; read `focus.md` and canonical files.",
    ]
    content = "\n".join(minimal).rstrip() + "\n"
    if len(content.encode("utf-8")) > max_bytes:
        raise ValueError("brief byte budget is too small for required metadata")
    return content


def ensure_memory_files(root: Path, day: date) -> list[str]:
    language = detect_language(root)
    changed = []
    if not (root / "guardrails.md").is_file() and atomic_write_if_changed(root / "guardrails.md", guardrails_template(language)):
        changed.append("guardrails.md")
    if not (root / "daily-log.md").is_file() and atomic_write_if_changed(root / "daily-log.md", daily_log_template(language, day.isoformat())):
        changed.append("daily-log.md")
    return changed


def run_sync(workspace: Path, force: bool = False, date_str: str | None = None, max_bytes: int = DEFAULT_BRIEF_MAX_BYTES) -> dict[str, Any]:
    root = mission_root(workspace)
    if not root.is_dir():
        raise FileNotFoundError(f"MissionCenter directory not found: {root}")
    day = local_date(date_str)
    current_before = compute_workspace_fingerprint(root)
    focus_before = compute_workspace_fingerprint(root, FOCUS_FINGERPRINT_SOURCES)
    cached_before = parse_derived_fingerprint(
        (root / "brief.md").read_text(encoding="utf-8") if (root / "brief.md").is_file() else ""
    )
    cached_focus_before = parse_derived_fingerprint(
        (root / "focus.md").read_text(encoding="utf-8") if (root / "focus.md").is_file() else ""
    )
    stale_before = (
        force
        or is_fingerprint_stale(current_before, cached_before)
        or is_fingerprint_stale(focus_before, cached_focus_before)
    )
    changed = ensure_memory_files(root, day)
    daily_changed, today_entries = organize_daily_log(root, day)
    if daily_changed:
        changed.append("daily-log.md")
    tasks = parse_tasks(root / "tasks.md")
    guardrails = read_guardrails(root / "guardrails.md")
    fingerprint = compute_workspace_fingerprint(root)
    focus_fingerprint = compute_workspace_fingerprint(root, FOCUS_FINGERPRINT_SOURCES)
    focus = render_focus(tasks, focus_fingerprint, detect_language(root))
    brief = render_brief(root, tasks, fingerprint, day, today_entries, guardrails, max_bytes)
    if atomic_write_if_changed(root / "focus.md", focus):
        changed.append("focus.md")
    if atomic_write_if_changed(root / "brief.md", brief):
        changed.append("brief.md")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "workspace": str(root.parent),
        "organizedDate": day.isoformat(),
        "fingerprint": fingerprint,
        "staleBeforeSync": stale_before,
        "changed": sorted(set(changed)),
        "focusCount": len(extract_focus_tasks(tasks)),
        "briefBytes": len(brief.encode("utf-8")),
    }


def run_daily(workspace: Path, message: str | None = None, date_str: str | None = None, max_bytes: int = DEFAULT_BRIEF_MAX_BYTES) -> dict[str, Any]:
    root = mission_root(workspace)
    if not root.is_dir():
        raise FileNotFoundError(f"MissionCenter directory not found: {root}")
    day = local_date(date_str)
    changed = ensure_memory_files(root, day)
    daily_changed, _ = organize_daily_log(root, day, message)
    if daily_changed:
        changed.append("daily-log.md")
    result = run_sync(root, date_str=day.isoformat(), max_bytes=max_bytes)
    result["changed"] = sorted(set(result["changed"] + changed))
    result["eventAdded"] = bool(message and daily_changed)
    return result


def run_status(workspace: Path, date_str: str | None = None) -> dict[str, Any]:
    root = mission_root(workspace)
    current = compute_workspace_fingerprint(root)
    current_focus = compute_workspace_fingerprint(root, FOCUS_FINGERPRINT_SOURCES)
    brief_text = (root / "brief.md").read_text(encoding="utf-8") if (root / "brief.md").is_file() else ""
    focus_text = (root / "focus.md").read_text(encoding="utf-8") if (root / "focus.md").is_file() else ""
    brief_fp = parse_derived_fingerprint(brief_text)
    focus_fp = parse_derived_fingerprint(focus_text)
    tasks = parse_tasks(root / "tasks.md") if (root / "tasks.md").is_file() else []
    missing = [name for name in ("brief.md", "focus.md", "guardrails.md", "daily-log.md") if not (root / name).is_file()]
    stale = (
        bool(missing)
        or is_fingerprint_stale(current, brief_fp)
        or is_fingerprint_stale(current_focus, focus_fp)
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "workspace": str(root.parent),
        "date": local_date(date_str).isoformat(),
        "fingerprint": current,
        "stale": stale,
        "missing": missing,
        "focusTasks": [task.get("ID", "") for task in extract_focus_tasks(tasks)],
        "briefBytes": len(brief_text.encode("utf-8")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", nargs="?", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync")
    sync.add_argument("--date")
    sync.add_argument("--force", action="store_true")
    sync.add_argument("--max-brief-bytes", type=int, default=DEFAULT_BRIEF_MAX_BYTES)
    daily = commands.add_parser("daily")
    daily.add_argument("--date")
    daily.add_argument("--message", "-m")
    daily.add_argument("--max-brief-bytes", type=int, default=DEFAULT_BRIEF_MAX_BYTES)
    status = commands.add_parser("status")
    status.add_argument("--date")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    if args.command == "sync":
        result = run_sync(workspace, args.force, args.date, args.max_brief_bytes)
    elif args.command == "daily":
        result = run_daily(workspace, args.message, args.date, args.max_brief_bytes)
    else:
        result = run_status(workspace, args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.command == "status" and result["stale"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
