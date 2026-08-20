#!/usr/bin/env python3
"""Maintain compact MissionCenter hot-context views without model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from common.markdown_table import parse_table_blocks, parse_table_rows
from security_scanner import SECRET_PATTERN
from sync_mission_center import TEXT, _find_summary_value
from visual_state import normalize_tasks


SCHEMA_VERSION = "1.0"
FINGERPRINT_FORMAT = "sha256-v2-lf"
DEFAULT_BRIEF_MAX_BYTES = 4096
BRIEF_HARD_MAX_BYTES = 16384
DERIVED_WARNING = "Generated materialized view. Do not edit directly; rebuild from canonical MissionCenter files."
FOCUS_DEPRECATION = "Deprecated compatibility view: focus.md is generated from tasks.md only and must never be edited or treated as a second lifecycle source."
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


def atomic_write_if_changed(
    path: Path,
    content: str,
    *,
    force: bool = False,
    replace_unreadable: bool = False,
) -> bool:
    """Atomically write UTF-8 text, optionally replacing equal content too."""
    path = Path(path)
    try:
        if not force and path.read_text(encoding="utf-8") == content:
            return False
    except FileNotFoundError:
        pass
    except (OSError, UnicodeDecodeError):
        if not replace_unreadable:
            raise
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


def canonicalize_hash_bytes(content: str | bytes) -> bytes:
    """Normalize UTF-8 text line endings before cross-platform content hashing."""
    raw = content.encode("utf-8") if isinstance(content, str) else content
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def compute_content_hash(content: str | bytes) -> str:
    return hashlib.sha256(canonicalize_hash_bytes(content)).hexdigest()


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
            limit = CANONICAL_READ_LIMITS.get(name, 256 * 1024)
            raw = canonicalize_hash_bytes(_read_bounded_bytes(path, limit))
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
    path = Path(tasks_path)
    if not path.is_file():
        return []
    text = _read_bounded_text(path, CANONICAL_READ_LIMITS["tasks.md"])
    rows, errors = parse_table_rows(text.splitlines(), table_name=path.name, strict=True)
    if errors:
        raise ValueError(errors[0])
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
    path = Path(path)
    if not path.is_file():
        return []
    text = _read_bounded_text(path, CANONICAL_READ_LIMITS["guardrails.md"])
    rows, errors = parse_table_rows(text.splitlines(), table_name=path.name, strict=True)
    if errors:
        raise ValueError(errors[0])
    return normalize_guardrail_rows(rows)


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
    with _daily_log_lock(root):
        return _organize_daily_log_unlocked(root, day, message)


def _organize_daily_log_unlocked(root: Path, day: date, message: str | None = None) -> tuple[bool, list[str]]:
    language = _detect_language_bounded(root)
    path = root / "daily-log.md"
    existing = _read_bounded_text(path, CANONICAL_READ_LIMITS["daily-log.md"]) if path.is_file() else daily_log_template(language, day.isoformat())
    _, entries = parse_daily_log(existing)
    day_key = day.isoformat()
    if message:
        cleaned = " ".join(message.split())
        if cleaned and cleaned not in entries.setdefault(day_key, []):
            entries[day_key].append(cleaned)
    content = render_daily_log(language, day_key, entries)
    return atomic_write_if_changed(path, content), entries.get(day_key, [])


def append_daily_log(daily_log_path: Path, message: str, date_str: str | None = None) -> bool:
    """Append one normalized event to the explicit canonical daily-log.md path."""
    path = Path(daily_log_path)
    if path.name != "daily-log.md":
        raise ValueError("append_daily_log requires the canonical daily-log.md path")
    with _daily_log_lock(path.parent):
        before = path.read_text(encoding="utf-8") if path.is_file() else None
        _organize_daily_log_unlocked(path.parent, local_date(date_str), message)
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
    path = root / "project.md"
    text = _read_bounded_text(path, CANONICAL_READ_LIMITS["project.md"]) if path.is_file() else ""
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
        f"<!-- {FOCUS_DEPRECATION} -->",
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
    language = _detect_language_bounded(root)
    day = day or local_date()
    fingerprint = fingerprint or compute_workspace_fingerprint(root)
    daily_entries = daily_entries or []
    guardrails = guardrails if guardrails is not None else read_guardrails(root / "guardrails.md")
    project, goal, cycle = project_identity(root, language)
    none_label = "無" if language == "zh-TW" else "None"
    working_set_count = len(extract_working_set_tasks(tasks))
    active_guardrails = active_guardrail_ids(guardrails)

    labels = {
        "title": "任務簡報" if language == "zh-TW" else "Mission Brief",
        "project": "專案" if language == "zh-TW" else "Project",
        "goal": "北極星" if language == "zh-TW" else "North Star",
        "cycle": "週期" if language == "zh-TW" else "Cycle",
        "organized": "最後整理" if language == "zh-TW" else "Last organized",
        "fingerprint": "來源指紋" if language == "zh-TW" else "Source fingerprint",
        "truth": "唯一真實來源" if language == "zh-TW" else "Source of truth",
        "working_set": "當前工作集" if language == "zh-TW" else "Active working set",
        "today": "今日摘要" if language == "zh-TW" else "Today's Summary",
        "guardrails": "重要護欄" if language == "zh-TW" else "Relevant Guardrails",
        "route": "需要時再讀" if language == "zh-TW" else "Read Next Only When Needed",
    }
    header_lines = [
        f"<!-- {DERIVED_WARNING} -->",
        f"<!-- mission-center-derived schema={SCHEMA_VERSION} fingerprint-format={FINGERPRINT_FORMAT} source-fingerprint={fingerprint['value']} -->",
        f"# {labels['title']}",
        "",
        f"- {labels['organized']}: {day.isoformat()}",
        f"- {labels['fingerprint']}: `{fingerprint['value']}`",
        f"- {labels['truth']}: `tasks.md`",
        f"- {labels['project']}: {project}",
        f"- {labels['goal']}: {goal or none_label}",
        f"- {labels['cycle']}: {cycle or none_label}",
    ]
    lines = [
        *header_lines,
        "",
        f"## {labels['today']} · {day.isoformat()}",
        *_bounded_lines(daily_entries, 8, none_label),
        "",
        f"## {labels['guardrails']} ({len(active_guardrails)})",
        *_bounded_lines(active_guardrails, 20, none_label),
        "",
        f"## {labels['route']}",
        *(
            [
                f"- 目前工作（{working_set_count} 項）→ `working-set.md`",
                "- 修改任務生命週期／順序 → `tasks.md`",
                "- 查閱理由／證據 → `decisions.md`、`notes.md`、`smoke-tests.md`",
                "- 簡報／工作集過期或截斷 → 執行 `mission_maintenance.py sync` 後再讀 canonical files",
            ]
            if language == "zh-TW"
            else [
                f"- Current work ({working_set_count} items) → `working-set.md`",
                "- Modify task lifecycle/order → `tasks.md`",
                "- Need rationale/evidence → `decisions.md`, `notes.md`, `smoke-tests.md`",
                "- Brief/working set stale or truncated → run `mission_maintenance.py sync` and open canonical files",
            ]
        ),
    ]
    content = "\n".join(lines).rstrip() + "\n"
    if len(content.encode("utf-8")) <= max_bytes:
        return content
    minimal = header_lines + [
        "",
        "## Context counts",
        f"- Working set: {working_set_count}",
        f"- Guardrails: {len(active_guardrails)}",
        "- [TRUNCATED] Brief exceeded its byte budget; read `working-set.md` and canonical files.",
    ]
    content = "\n".join(minimal).rstrip() + "\n"
    if len(content.encode("utf-8")) > max_bytes:
        raise ValueError("brief byte budget is too small for required metadata")
    return content


WORKING_SET_FINGERPRINT_SOURCES = ("tasks.md",)
WORKING_SET_MAX_BYTES = 4096
CRITICAL_LESSONS_MAX_BYTES = 6144
RESUME_MAX_BYTES = 16384
EXECUTION_LEDGER_FILENAME = "execution-ledger.jsonl"
EXECUTION_LEDGER_MAX_BYTES = 262144
EXECUTION_PULSE_MAX_BYTES = 4096
HANDOFF_MAX_BYTES = 8192
PULSE_FIELDS = {
    "pulseId",
    "taskId",
    "phase",
    "outcome",
    "nextAction",
    "evidenceRef",
    "budgetRemaining",
    "causalParent",
}
PULSE_FORBIDDEN_KEY = re.compile(
    r"(?:prompt|reasoning|chain[-_ ]?of[-_ ]?thought|full[-_ ]?command|command|secret|password|token|api[-_ ]?key|credential)",
    re.IGNORECASE,
)
PULSE_STRING_LIMITS = {
    "pulseId": 128,
    "taskId": 128,
    "phase": 128,
    "outcome": 1024,
    "nextAction": 1024,
    "evidenceRef": 512,
    "causalParent": 128,
}
CANONICAL_TASK_FIELDS = ("ID", "Title", "Priority", "Status", "Depends on", "Next action", "Verification")

# These bounds apply to files consumed by status/resume and sync.  They keep a
# malformed workspace from turning a read-only command into an unbounded read.
CANONICAL_READ_LIMITS = {
    "project.md": 64 * 1024,
    "tasks.md": 256 * 1024,
    "guardrails.md": 64 * 1024,
    "daily-log.md": 128 * 1024,
    "critical-lessons.md": 64 * 1024,
}
DERIVED_READ_LIMITS = {
    "brief.md": BRIEF_HARD_MAX_BYTES,
    "working-set.md": WORKING_SET_MAX_BYTES,
    "focus.md": WORKING_SET_MAX_BYTES,
}


def _read_bounded_bytes(path: Path, max_bytes: int) -> bytes:
    """Read at most max_bytes plus one sentinel byte from a stable descriptor."""
    path = Path(path)
    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"{path.name} exceeds its bounded byte limit")
    return raw


def _read_bounded_text(path: Path, max_bytes: int) -> str:
    """Read one bounded UTF-8 file; callers choose fail-open policy."""
    raw = _read_bounded_bytes(path, max_bytes)
    return raw.decode("utf-8")


def _detect_language_bounded(root: Path) -> str:
    markers = ("# 專案", "# 進度", "# 任務", "- 目標:", "- 目標：")
    for name in ("project.md", "progress.md", "tasks.md"):
        path = Path(root) / name
        if path.is_file():
            limit = CANONICAL_READ_LIMITS.get(name, 64 * 1024)
            try:
                text = _read_bounded_text(path, limit)
            except (OSError, UnicodeDecodeError, ValueError):
                if name == "progress.md":
                    continue
                raise
            if any(marker in text for marker in markers):
                return "zh-TW"
    return "en"


def _validate_canonical_inputs(root: Path) -> None:
    """Reject unreadable/oversized canonical inputs before any derived write."""
    for name, limit in CANONICAL_READ_LIMITS.items():
        path = root / name
        if path.is_file():
            _read_bounded_text(path, limit)


def _read_derived_text(path: Path) -> tuple[str, str | None]:
    """Derived files are disposable: unreadable/oversized content is stale."""
    try:
        if not path.is_file():
            return "", None
        return _read_bounded_text(path, DERIVED_READ_LIMITS[path.name]), None
    except UnicodeDecodeError:
        return "", "derived_unreadable"
    except OSError:
        return "", "derived_unreadable"
    except ValueError:
        return "", "derived_oversized"


def _pulse_text(value: Any, field: str, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"execution pulse {field} must be a string")
    if required and not value.strip():
        raise ValueError(f"execution pulse {field} must not be empty")
    if len(value) > PULSE_STRING_LIMITS[field]:
        raise ValueError(f"execution pulse {field} exceeds its length bound")
    if any(ord(character) < 32 and character not in "\t" for character in value):
        raise ValueError(f"execution pulse {field} contains a control character")
    if SECRET_PATTERN.search(value):
        raise ValueError(f"execution pulse {field} contains secret-like content")
    return value.strip()


def _validate_pulse_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("execution pulse must be an object")
    for key in payload:
        if PULSE_FORBIDDEN_KEY.search(str(key)):
            raise ValueError(f"execution pulse field is forbidden: {key}")
        if key not in PULSE_FIELDS:
            raise ValueError(f"execution pulse field is not allowed: {key}")

    required = ("taskId", "phase", "outcome", "nextAction", "evidenceRef", "budgetRemaining")
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"execution pulse is missing required fields: {', '.join(missing)}")

    normalized: dict[str, Any] = {
        "taskId": _pulse_text(payload["taskId"], "taskId"),
        "phase": _pulse_text(payload["phase"], "phase"),
        "outcome": _pulse_text(payload["outcome"], "outcome"),
        "nextAction": _pulse_text(payload["nextAction"], "nextAction"),
        "evidenceRef": _pulse_text(payload["evidenceRef"], "evidenceRef", required=False),
    }
    budget = payload["budgetRemaining"]
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        raise ValueError("execution pulse budgetRemaining must be a non-negative integer")
    normalized["budgetRemaining"] = budget
    parent = payload.get("causalParent")
    if parent is not None:
        normalized["causalParent"] = _pulse_text(parent, "causalParent")
    else:
        normalized["causalParent"] = None
    pulse_id = payload.get("pulseId")
    if pulse_id is not None:
        normalized["pulseId"] = _pulse_text(pulse_id, "pulseId")
    else:
        identity = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        normalized["pulseId"] = "pulse-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return normalized


def _execution_ledger_path(workspace: Path) -> Path:
    return mission_root(workspace) / EXECUTION_LEDGER_FILENAME


def _canonical_task(workspace: Path, task_id: str) -> dict[str, str] | None:
    """Read one task row from the sole lifecycle source; never infer from pulse data."""
    root = mission_root(workspace)
    tasks_path = root / "tasks.md"
    if not tasks_path.is_file():
        raise ValueError("canonical tasks.md is missing")
    wanted = task_id.strip().casefold()
    for task in parse_tasks(tasks_path):
        if task.get("ID", "").strip().casefold() == wanted:
            return {field: task.get(field, "") for field in CANONICAL_TASK_FIELDS}
    return None


def _read_execution_ledger(workspace: Path) -> list[dict[str, Any]]:
    """Read only the named, bounded pulse ledger; malformed input fails closed."""
    path = _execution_ledger_path(workspace)
    if not path.is_file():
        return []
    if path.stat().st_size > EXECUTION_LEDGER_MAX_BYTES:
        raise ValueError("execution ledger exceeds its bounded byte limit")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError) as exc:
        raise ValueError("execution ledger is unreadable") from exc
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    parsed_times: dict[str, datetime] = {}
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > EXECUTION_PULSE_MAX_BYTES:
            raise ValueError(f"execution ledger line {number} exceeds its byte limit")
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"execution ledger line {number} is malformed") from exc
        if not isinstance(record, dict) or record.get("schemaVersion") != "1.0" or record.get("kind") != "execution-pulse":
            raise ValueError(f"execution ledger line {number} has an invalid envelope")
        allowed_record_fields = PULSE_FIELDS | {"schemaVersion", "kind", "recordedAt"}
        for key in record:
            if key not in allowed_record_fields or PULSE_FORBIDDEN_KEY.search(str(key)):
                raise ValueError(f"execution ledger line {number} contains a forbidden field: {key}")
        payload = {field: record.get(field) for field in PULSE_FIELDS if field in record}
        normalized = _validate_pulse_payload(payload)
        if record.get("pulseId") != normalized["pulseId"]:
            raise ValueError(f"execution ledger line {number} has an invalid pulseId")
        if record["pulseId"] in seen:
            raise ValueError(f"execution ledger contains duplicate pulseId: {record['pulseId']}")
        seen.add(record["pulseId"])
        recorded_at = record.get("recordedAt")
        if not isinstance(recorded_at, str) or not recorded_at.strip():
            raise ValueError(f"execution ledger line {number} is missing recordedAt")
        try:
            parsed_recorded_at = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"execution ledger line {number} has an invalid recordedAt") from exc
        if parsed_recorded_at.tzinfo is None or parsed_recorded_at.utcoffset() is None:
            raise ValueError(f"execution ledger line {number} recordedAt must include a timezone")
        normalized["schemaVersion"] = "1.0"
        normalized["kind"] = "execution-pulse"
        normalized["recordedAt"] = recorded_at
        records.append(normalized)
        parsed_times[normalized["pulseId"]] = parsed_recorded_at
    ids = {record["pulseId"] for record in records}
    by_id = {record["pulseId"]: record for record in records}
    prior_ids: set[str] = set()
    for record in records:
        parent = record.get("causalParent")
        if parent is not None and parent not in ids:
            raise ValueError(f"execution ledger has an unknown causalParent: {parent}")
        if parent is not None and by_id.get(parent, {}).get("taskId", "").strip().casefold() != record.get("taskId", "").strip().casefold():
            raise ValueError(
                f"execution ledger causalParent must belong to the same task: {parent}"
            )
        if parent is not None and parent not in prior_ids:
            raise ValueError(f"execution ledger causalParent must precede its child: {parent}")
        if parent is not None and parsed_times[parent] > parsed_times[record["pulseId"]]:
            raise ValueError(f"execution ledger causalParent recordedAt must precede or equal its child: {parent}")
        prior_ids.add(record["pulseId"])
    for record in records:
        visited: set[str] = set()
        current: dict[str, Any] | None = record
        while current is not None:
            pulse_id = current["pulseId"]
            if pulse_id in visited:
                raise ValueError("execution ledger contains a causal cycle")
            visited.add(pulse_id)
            parent = current.get("causalParent")
            current = by_id.get(parent) if parent else None
    return records


@contextmanager
def _path_keyed_interprocess_lock(path: Path):
    """Serialize one path's read-modify-write section across Windows/Linux processes."""
    path_identity = os.path.normcase(str(Path(path).resolve()))
    lock_key = hashlib.sha256(path_identity.encode("utf-8")).hexdigest()
    lock_root = Path(tempfile.gettempdir()) / "mission-center-locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / f"{lock_key}.lock"
    with lock_path.open("a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _execution_ledger_lock(workspace: Path):
    """Serialize ledger writers across processes without adding workspace files."""
    with _path_keyed_interprocess_lock(_execution_ledger_path(workspace)):
        yield


@contextmanager
def _daily_log_lock(root: Path):
    """Serialize complete daily-log read-modify-write operations."""
    with _path_keyed_interprocess_lock(Path(root) / "daily-log.md"):
        yield


def append_execution_pulse(workspace: Path, pulse: dict[str, Any]) -> dict[str, Any]:
    """Append one restricted execution pulse without changing task lifecycle files."""
    root = mission_root(workspace)
    if not root.is_dir():
        raise FileNotFoundError(f"MissionCenter directory not found: {root}")
    normalized = _validate_pulse_payload(pulse)
    if _canonical_task(root, normalized["taskId"]) is None:
        raise ValueError(f"execution pulse taskId not found in canonical tasks.md: {normalized['taskId']}")
    with _execution_ledger_lock(workspace):
        existing = _read_execution_ledger(workspace)
        existing_by_id = {record["pulseId"]: record for record in existing}
        if normalized.get("causalParent") is not None and normalized["causalParent"] not in existing_by_id:
            raise ValueError(f"execution pulse has an unknown causalParent: {normalized['causalParent']}")
        if (
            normalized.get("causalParent") is not None
            and existing_by_id[normalized["causalParent"]].get("taskId", "").strip().casefold()
            != normalized["taskId"].strip().casefold()
        ):
            raise ValueError("execution pulse causalParent must belong to the same task")
        prior = existing_by_id.get(normalized["pulseId"])
        if prior is not None:
            candidate = {field: prior.get(field) for field in PULSE_FIELDS}
            if candidate != normalized:
                raise ValueError(f"execution pulse id already exists with different content: {normalized['pulseId']}")
            return {"schemaVersion": "1.0", "appended": False, "duplicate": True, "pulse": prior, "ledger": EXECUTION_LEDGER_FILENAME}

        record = dict(normalized)
        record.update({
            "schemaVersion": "1.0",
            "kind": "execution-pulse",
            "recordedAt": datetime.now(timezone.utc).isoformat(),
        })
        line = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        if len(line.encode("utf-8")) > EXECUTION_PULSE_MAX_BYTES:
            raise ValueError("execution pulse exceeds its byte limit")
        path = _execution_ledger_path(workspace)
        prior_text = path.read_text(encoding="utf-8") if path.is_file() else ""
        content = prior_text
        if content and not content.endswith("\n"):
            content += "\n"
        content += line
        if len(content.encode("utf-8")) > EXECUTION_LEDGER_MAX_BYTES:
            raise ValueError("execution ledger would exceed its bounded byte limit")
        atomic_write_if_changed(path, content)
        return {"schemaVersion": "1.0", "appended": True, "duplicate": False, "pulse": record, "ledger": EXECUTION_LEDGER_FILENAME}


def _handoff_packet(
    records: list[dict[str, Any]],
    task_id: str | None,
    max_bytes: int,
    canonical_task: dict[str, str] | None = None,
) -> dict[str, Any]:
    selected = [record for record in records if task_id is None or record["taskId"].casefold() == task_id.strip().casefold()]
    if not selected:
        return {"schemaVersion": "1.0", "route": "handoff", "taskId": task_id, "found": False, "pulses": [], "bytes": 0, "maxBytes": max_bytes, "truncated": False, "content": None}
    latest = selected[-1]
    if canonical_task is None:
        raise ValueError(f"execution ledger latest task is missing from canonical tasks.md: {latest['taskId']}")
    by_id = {record["pulseId"]: record for record in records}
    chain: list[dict[str, Any]] = []
    current = latest
    while current is not None:
        chain.append(current)
        parent = current.get("causalParent")
        current = by_id.get(parent) if parent else None
    chain.reverse()
    packet = {
        "schemaVersion": "1.0",
        "route": "handoff",
        "taskId": latest["taskId"],
        "found": True,
        "lifecycleSource": "tasks.md",
        "canonicalTask": canonical_task,
        "latestPulse": latest,
        "nextAction": latest["nextAction"],
        "executionNextAction": latest["nextAction"],
        "nextActionSource": "execution-pulse",
        "executionOnly": True,
        "budgetRemaining": latest["budgetRemaining"],
        "evidenceRef": latest["evidenceRef"],
        "causalParent": latest.get("causalParent"),
        "causalChain": chain,
        "truncated": False,
    }
    while True:
        encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) <= max_bytes:
            packet["bytes"] = len(encoded.encode("utf-8"))
            packet["maxBytes"] = max_bytes
            packet["content"] = encoded
            return packet
        if len(packet["causalChain"]) > 1:
            packet["causalChain"] = packet["causalChain"][1:]
            packet["truncated"] = True
            continue
        packet["causalChain"] = []
        packet["latestPulse"] = {"pulseId": latest["pulseId"], "taskId": latest["taskId"], "nextAction": latest["nextAction"], "budgetRemaining": latest["budgetRemaining"], "causalParent": latest.get("causalParent")}
        packet["truncated"] = True
        encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) <= max_bytes:
            packet["bytes"] = len(encoded.encode("utf-8"))
            packet["maxBytes"] = max_bytes
            packet["content"] = encoded
            return packet
        if max_bytes <= 0:
            packet["bytes"] = 0
            packet["maxBytes"] = max_bytes
            packet["content"] = None
            return packet
        raise ValueError("handoff byte budget is too small for required metadata")


def run_handoff(workspace: Path, task_id: str | None = None, max_bytes: int = HANDOFF_MAX_BYTES) -> dict[str, Any]:
    """Return the latest bounded causal pulse chain; no task status is derived here."""
    root = mission_root(workspace)
    if not root.is_dir():
        raise FileNotFoundError(f"MissionCenter directory not found: {root}")
    bounded = min(max(0, int(max_bytes)), HANDOFF_MAX_BYTES)
    records = _read_execution_ledger(root)
    requested_task = _canonical_task(root, task_id) if task_id is not None else None
    selected = [record for record in records if task_id is None or record["taskId"].casefold() == task_id.strip().casefold()]
    latest_task = _canonical_task(root, selected[-1]["taskId"]) if selected else requested_task
    return _handoff_packet(records, task_id, bounded, latest_task)


def _priority_key(task: dict[str, str]) -> tuple[int, str]:
    priority = task.get("Priority", "").strip().upper()
    value = int(priority[1:]) if re.fullmatch(r"P\d+", priority) else 99
    return value, task.get("ID", "").strip()


def _dependency_ids(task: dict[str, str]) -> set[str]:
    """Extract task IDs from a compact Depends on cell without a second parser."""
    return set(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*-\d+\b", task.get("Depends on", "")))


def _dependencies_satisfied(task: dict[str, str], done_ids: set[str]) -> bool:
    return _dependency_ids(task).issubset(done_ids)


def extract_working_set_tasks(tasks: list[dict[str, str]], limit: int = 6) -> list[dict[str, str]]:
    """Select the bounded derived view; tasks.md remains lifecycle truth."""
    unfinished = [t for t in tasks if t.get("Status", "").strip().casefold() != DONE_STATUS]
    done_ids = {
        t.get("ID", "").strip()
        for t in tasks
        if t.get("Status", "").strip().casefold() == DONE_STATUS
    }
    status = lambda task: task.get("Status", "").strip().casefold()
    p0 = [t for t in unfinished if t.get("Priority", "").strip().casefold() == "p0" and status(t) != "backlog"]
    categories = (
        [t for t in unfinished if status(t) == "blocked"],
        [t for t in unfinished if status(t) == "in progress"],
        [t for t in unfinished if status(t) == "review"],
        p0,
        sorted((t for t in unfinished if status(t) == "ready"), key=_priority_key),
    )
    selected: list[dict[str, str]] = []
    seen: set[str] = set()
    for category in categories:
        for task in category:
            task_id = task.get("ID", "").strip()
            if task_id and task_id not in seen:
                seen.add(task_id)
                selected.append(task)
                if len(selected) >= limit:
                    return selected
    return selected


def extract_next_candidates(tasks: list[dict[str, str]], limit: int = 2) -> list[dict[str, str]]:
    """List dependency-ready Backlog work without granting execution permission."""
    done_ids = {
        task.get("ID", "").strip()
        for task in tasks
        if task.get("Status", "").strip().casefold() == DONE_STATUS
    }
    candidates = (
        task for task in tasks
        if task.get("Status", "").strip().casefold() == "backlog"
        and _dependencies_satisfied(task, done_ids)
    )
    return sorted(candidates, key=_priority_key)[:max(0, limit)]


def render_working_set(tasks: list[dict[str, str]], fingerprint: dict[str, Any], language: str) -> str:
    items = extract_working_set_tasks(tasks, limit=6)
    candidates = extract_next_candidates(tasks, limit=2)
    title = "當前工作集" if language == "zh-TW" else "Active Working Set"
    source_label = "唯一真實來源" if language == "zh-TW" else "Source of truth"
    count_label = "可執行項目數" if language == "zh-TW" else "Unfinished working set count"
    headers = (
        "| ID | 標題 | 優先級 | 狀態 | 下一步 | 依賴 | 驗證方式 | 阻塞原因 |"
        if language == "zh-TW"
        else "| ID | Title | Priority | Status | Next action | Depends on | Verification | Blocker reason |"
    )
    header_lines = [
        f"<!-- {DERIVED_WARNING} -->",
        f"<!-- mission-center-derived schema={SCHEMA_VERSION} fingerprint-format={FINGERPRINT_FORMAT} source-fingerprint={fingerprint['value']} -->",
        f"# {title}",
        "",
        f"- {source_label}: `tasks.md`",
        f"- {count_label}: {len(items)}",
    ]
    candidate_lines = []
    if candidates:
        candidate_lines = ["", "## 下一步候選" if language == "zh-TW" else "## Next Candidates", ""]
        candidate_lines.extend(
            f"- {task.get('ID', '').strip()} — {task.get('Title', '').strip()}"
            for task in candidates
        )
        candidate_lines.append(
            "- 以上僅為候選，開始前仍須在 `tasks.md` 升格為 Ready。"
            if language == "zh-TW"
            else "- Candidates only; promote to Ready in `tasks.md` before starting."
        )
    if not items:
        all_done = all(t.get("Status", "").strip().casefold() == DONE_STATUS for t in tasks) if tasks else True
        statuses = {t.get("Status", "").strip().casefold() for t in tasks}
        if all_done:
            reason = "all work complete"
        elif "blocked" in statuses:
            reason = "blocked"
        elif "awaiting approval" in statuses:
            reason = "awaiting approval"
        else:
            reason = "dependency unresolved"
        header_lines.extend([f"- Status: {reason}", *candidate_lines, ""])
        return "\n".join(header_lines).rstrip() + "\n"

    header_lines.extend([
        "",
        headers,
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    lines = list(header_lines)
    for task in items:
        blocker = task.get("Blocker reason", "") or (task.get("Comments", "") if task.get("Status", "").strip().casefold() == "blocked" else "")
        lines.append(
            "| " + " | ".join(
                _escape_cell(task.get(field, ""))
                for field in ("ID", "Title", "Priority", "Status", "Next action", "Depends on", "Verification")
            ) + f" | {_escape_cell(blocker)} |"
        )
    lines.extend(candidate_lines)
    content = "\n".join(lines).rstrip() + "\n"
    if len(content.encode("utf-8")) <= WORKING_SET_MAX_BYTES:
        return content

    marker = "- [TRUNCATED] Working set exceeded its byte budget; rebuild from `tasks.md`."
    bounded_lines = list(header_lines)
    bounded_lines.extend(["", headers, "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    for line in lines[len(bounded_lines):]:
        candidate = "\n".join([*bounded_lines, line, marker]).rstrip() + "\n"
        if len(candidate.encode("utf-8")) > WORKING_SET_MAX_BYTES:
            break
        bounded_lines.append(line)
    bounded_lines.append(marker)
    return "\n".join(bounded_lines).rstrip() + "\n"


def critical_lessons_template(language: str) -> str:
    if language == "zh-TW":
        return (
            "# 重大教訓\n\n"
            "> 只收錄已發生、具有再次發生價值，且解法已有證據支持的重大問題。\n"
            "> 詳細事故資料位於 incidents/。\n"
            "> 此文件必須保持精簡。\n\n"
            "## 主動教訓\n\n"
            "| ID | 適用情境 | 症狀 | 根因 | 正確處理 | 禁止重犯 | 驗證方式 | Incident | 最後確認 |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n\n"
            "## 已解決索引\n\n"
            "| ID | 狀態 | Resolved by | Incident |\n"
            "| --- | --- | --- | --- |\n"
        )
    return (
        "# Critical Lessons\n\n"
        "> Only recorded issues that have occurred, are likely to recur, and have verified solutions.\n"
        "> Detailed evidence is stored in incidents/.\n"
        "> Keep this file compact.\n\n"
        "## Active Lessons\n\n"
        "| ID | Applies when | Symptoms | Root cause | Correct action | Avoid | Verification | Incident | Last confirmed |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n\n"
        "## Resolved Index\n\n"
        "| ID | Status | Resolved by | Incident |\n"
        "| --- | --- | --- | --- |\n"
    )


INCIDENTS_README = """# Incidents

Only create an `INC-xxx.md` record for a significant, evidenced event. Keep it bounded: summary, impact, symptoms, reproduction, root cause, rejected fixes, final fix, verification evidence, related task/decision/commit links, promoted lessons, and status. Do not store raw logs, secrets, or a second task lifecycle here.
"""


def validate_critical_lessons(path: Path, incidents_dir: Path | None = None) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        errors.append("critical-lessons.md is missing")
        return errors

    content = path.read_text(encoding="utf-8")
    byte_count = len(content.encode("utf-8"))
    if byte_count > CRITICAL_LESSONS_MAX_BYTES:
        errors.append(f"critical-lessons.md exceeds hard limit ({byte_count} > {CRITICAL_LESSONS_MAX_BYTES} bytes)")

    tables, table_errors = parse_table_blocks(
        content.splitlines(), table_name="critical-lessons.md", include_indented=True, strict=False
    )
    errors.extend(table_errors)
    if not tables:
        return errors

    seen_ids: set[str] = set()
    valid_resolved_statuses = {"Resolved", "Resolved-by-design", "Superseded", "已解決", "已由設計解決", "已取代"}
    for table_idx, table_rows in enumerate(tables):
        for number, row in enumerate(table_rows, start=1):
            lesson_id = (row.get("ID") or "").strip()
            if not lesson_id:
                continue
            if not re.fullmatch(r"CL-\d{3}", lesson_id):
                errors.append(f"critical-lessons.md row {number} has invalid ID: {lesson_id}")
                continue
            if lesson_id in seen_ids:
                errors.append(f"critical-lessons.md contains duplicate ID: {lesson_id}")
            seen_ids.add(lesson_id)

            symptoms = row.get("Symptoms") or row.get("症狀")
            root_cause = row.get("Root cause") or row.get("根因")
            correct_action = row.get("Correct action") or row.get("正確處理")
            verification = row.get("Verification") or row.get("驗證方式")

            is_active_lesson = symptoms is not None or "Applies when" in row or "適用情境" in row
            if is_active_lesson:
                applies_when = row.get("Applies when") or row.get("適用情境")
                if not (symptoms and symptoms.strip()):
                    errors.append(f"critical-lessons.md {lesson_id} is missing Symptoms")
                if not (applies_when and applies_when.strip()):
                    errors.append(f"critical-lessons.md {lesson_id} is missing Applies when")
                if not (root_cause and root_cause.strip()):
                    errors.append(f"critical-lessons.md {lesson_id} is missing Root cause")
                if not (correct_action and correct_action.strip()):
                    errors.append(f"critical-lessons.md {lesson_id} is missing Correct action")
                if not (verification and verification.strip()):
                    errors.append(f"critical-lessons.md {lesson_id} is missing Verification")

            incident = (row.get("Incident") or "").strip()
            if is_active_lesson and not incident:
                errors.append(f"critical-lessons.md {lesson_id} is missing Incident evidence pointer")
            if incident and incident not in {"-", "None", "無"} and incidents_dir is not None:
                norm_incident = incident.replace("\\", "/")
                match = re.fullmatch(r"(?:incidents/)?(INC-\d{3})\.md|(?:INC-\d{3})", norm_incident)
                if not match:
                    errors.append(f"critical-lessons.md {lesson_id} has invalid Incident pointer: {incident}")
                    continue
                incident_id = match.group(1) or norm_incident
                target_path = (incidents_dir / f"{incident_id}.md").resolve()
                if incidents_dir.resolve() not in target_path.parents or not target_path.is_file():
                    errors.append(f"critical-lessons.md {lesson_id} references missing incident file: {incident}")
            if not is_active_lesson:
                resolved_status = (row.get("Status") or row.get("狀態") or "").strip()
                if resolved_status and resolved_status not in valid_resolved_statuses:
                    errors.append(f"critical-lessons.md {lesson_id} has invalid resolved status: {resolved_status}")

    return errors


def ensure_memory_files(root: Path, day: date) -> list[str]:
    language = _detect_language_bounded(root)
    changed = []
    if not (root / "guardrails.md").is_file() and atomic_write_if_changed(root / "guardrails.md", guardrails_template(language)):
        changed.append("guardrails.md")
    if not (root / "daily-log.md").is_file() and atomic_write_if_changed(root / "daily-log.md", daily_log_template(language, day.isoformat())):
        changed.append("daily-log.md")
    if not (root / "critical-lessons.md").is_file() and atomic_write_if_changed(root / "critical-lessons.md", critical_lessons_template(language)):
        changed.append("critical-lessons.md")
    incidents_dir = root / "incidents"
    incidents_dir.mkdir(parents=True, exist_ok=True)
    if not (incidents_dir / "README.md").is_file() and atomic_write_if_changed(incidents_dir / "README.md", INCIDENTS_README):
        changed.append("incidents/README.md")
    return changed


STATUS_REQUIRED_FILES = ("brief.md", "working-set.md", "guardrails.md", "daily-log.md", "critical-lessons.md")


def run_sync(
    workspace: Path,
    force: bool = False,
    date_str: str | None = None,
    max_bytes: int = DEFAULT_BRIEF_MAX_BYTES,
    *,
    _daily_lock_held: bool = False,
) -> dict[str, Any]:
    root = mission_root(workspace)
    if not root.is_dir():
        raise FileNotFoundError(f"MissionCenter directory not found: {root}")
    if not _daily_lock_held:
        with _daily_log_lock(root):
            return run_sync(
                root,
                force=force,
                date_str=date_str,
                max_bytes=max_bytes,
                _daily_lock_held=True,
            )
    max_bytes = min(max(0, int(max_bytes)), BRIEF_HARD_MAX_BYTES)
    _validate_canonical_inputs(root)
    day = local_date(date_str)
    current_before = compute_workspace_fingerprint(root)
    ws_before = compute_workspace_fingerprint(root, WORKING_SET_FINGERPRINT_SOURCES)
    focus_before = compute_workspace_fingerprint(root, FOCUS_FINGERPRINT_SOURCES)
    brief_before, _ = _read_derived_text(root / "brief.md")
    ws_before_text, _ = _read_derived_text(root / "working-set.md")
    cached_before = parse_derived_fingerprint(brief_before)
    cached_ws_before = parse_derived_fingerprint(ws_before_text)
    stale_before = (
        is_fingerprint_stale(current_before, cached_before)
        or is_fingerprint_stale(ws_before, cached_ws_before)
    )
    # The caller holds the daily lock across this complete sync transaction.
    changed = ensure_memory_files(root, day)
    daily_changed, today_entries = _organize_daily_log_unlocked(root, day)
    if daily_changed:
        changed.append("daily-log.md")
    tasks = parse_tasks(root / "tasks.md")
    guardrails = read_guardrails(root / "guardrails.md")
    fingerprint = compute_workspace_fingerprint(root)
    ws_fingerprint = compute_workspace_fingerprint(root, WORKING_SET_FINGERPRINT_SOURCES)
    focus_fingerprint = compute_workspace_fingerprint(root, FOCUS_FINGERPRINT_SOURCES)

    language = _detect_language_bounded(root)
    working_set = render_working_set(tasks, ws_fingerprint, language)
    focus = render_focus(tasks, focus_fingerprint, language)
    brief = render_brief(root, tasks, fingerprint, day, today_entries, guardrails, max_bytes)

    def write_derived(path: Path, content: str) -> bool:
        # --force is an explicit atomic materialized-view rebuild, even if equal.
        return atomic_write_if_changed(path, content, force=force, replace_unreadable=True)

    if write_derived(root / "working-set.md", working_set):
        changed.append("working-set.md")
    if force or (root / "focus.md").is_file():
        if write_derived(root / "focus.md", focus):
            changed.append("focus.md")
    if write_derived(root / "brief.md", brief):
        changed.append("brief.md")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "workspace": str(root.parent),
        "organizedDate": day.isoformat(),
        "fingerprint": fingerprint,
        "staleBeforeSync": stale_before,
        "forced": force,
        "changed": sorted(set(changed)),
        "focusCount": len(extract_focus_tasks(tasks)),
        "workingSetCount": len(extract_working_set_tasks(tasks)),
        "briefBytes": len(brief.encode("utf-8")),
    }


def run_daily(workspace: Path, message: str | None = None, date_str: str | None = None, max_bytes: int = DEFAULT_BRIEF_MAX_BYTES) -> dict[str, Any]:
    root = mission_root(workspace)
    if not root.is_dir():
        raise FileNotFoundError(f"MissionCenter directory not found: {root}")
    day = local_date(date_str)
    with _daily_log_lock(root):
        _validate_canonical_inputs(root)
        changed = ensure_memory_files(root, day)
        daily_changed, _ = _organize_daily_log_unlocked(root, day, message)
        if daily_changed:
            changed.append("daily-log.md")
        result = run_sync(
            root,
            date_str=day.isoformat(),
            max_bytes=max_bytes,
            _daily_lock_held=True,
        )
    result["changed"] = sorted(set(result["changed"] + changed))
    result["eventAdded"] = bool(message and daily_changed)
    return result


def run_status(workspace: Path, date_str: str | None = None) -> dict[str, Any]:
    root = mission_root(workspace)
    _validate_canonical_inputs(root)
    current = compute_workspace_fingerprint(root)
    current_ws = compute_workspace_fingerprint(root, WORKING_SET_FINGERPRINT_SOURCES)

    brief_text, brief_error = _read_derived_text(root / "brief.md")
    ws_text, ws_error = _read_derived_text(root / "working-set.md")
    _, focus_error = _read_derived_text(root / "focus.md")

    brief_fp = parse_derived_fingerprint(brief_text)
    ws_fp = parse_derived_fingerprint(ws_text)

    missing = [name for name in STATUS_REQUIRED_FILES if not (root / name).is_file()]

    source_fresh = (
        not bool(missing)
        and brief_error is None
        and ws_error is None
        and focus_error is None
        and not is_fingerprint_stale(current, brief_fp)
        and not is_fingerprint_stale(current_ws, ws_fp)
    )

    target_date = local_date(date_str)
    daily_text = _read_bounded_text(root / "daily-log.md", CANONICAL_READ_LIMITS["daily-log.md"]) if (root / "daily-log.md").is_file() else ""
    last_organized, _ = parse_daily_log(daily_text) if daily_text else (None, {})
    date_fresh = (last_organized == target_date.isoformat())

    stale_reasons: list[str] = []
    if missing:
        stale_reasons.append("missing_required_files")
    if not source_fresh and "missing_required_files" not in stale_reasons:
        stale_reasons.append(
            brief_error or ws_error or focus_error or "source_fingerprint_mismatch"
        )
    if not date_fresh:
        stale_reasons.append("organized_date_mismatch")

    stale = not (source_fresh and date_fresh)
    tasks = parse_tasks(root / "tasks.md") if (root / "tasks.md").is_file() else []
    ws_tasks = extract_working_set_tasks(tasks, limit=6)
    focus_tasks = extract_focus_tasks(tasks)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "workspace": str(root.parent),
        "date": target_date.isoformat(),
        "fingerprint": current,
        "sourceFresh": source_fresh,
        "dateFresh": date_fresh,
        "stale": stale,
        "staleReasons": stale_reasons,
        "missing": missing,
        "workingSetTasks": [task.get("ID", "") for task in ws_tasks],
        "focusTasks": [task.get("ID", "") for task in focus_tasks],
        "briefBytes": len(brief_text.encode("utf-8")),
    }


def _active_lessons_text(content: str) -> str:
    """Keep resolved history out of the permanently loaded resume packet."""
    marker = re.search(r"^## (?:Resolved Index|已解決索引)\s*$", content, re.MULTILINE)
    return content[:marker.start()] if marker else content


def _truncate_utf8(text: str, max_bytes: int, marker: str = "[TRUNCATED]") -> tuple[str, bool]:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False
    marker_bytes = marker.encode("utf-8")
    if max_bytes < len(marker_bytes):
        return "", True
    prefix = encoded[: max_bytes - len(marker_bytes)]
    while prefix:
        try:
            return prefix.decode("utf-8") + marker, True
        except UnicodeDecodeError:
            prefix = prefix[:-1]
    return marker, True


def _bounded_resume_content(
    sections: list[tuple[str, str | None]], max_bytes: int
) -> tuple[dict[str, str | None], dict[str, int], list[str]]:
    remaining = max(0, max_bytes)
    content: dict[str, str | None] = {}
    included: dict[str, int] = {}
    read_next: list[str] = []
    truncated_section = False
    for name, value in sections:
        if value is None:
            content[name] = None
            included[name] = 0
            continue
        if name == "handoff":
            value_bytes = len(value.encode("utf-8"))
            if value_bytes <= remaining:
                content[name] = value
                included[name] = value_bytes
                remaining -= value_bytes
            else:
                content[name] = None
                included[name] = 0
                read_next.append(name)
            continue
        if truncated_section:
            content[name] = ""
            included[name] = 0
            if value:
                read_next.append(name)
            continue
        bounded, truncated = _truncate_utf8(value, remaining)
        content[name] = bounded
        size = len(bounded.encode("utf-8"))
        included[name] = size
        remaining -= size
        if truncated:
            read_next.append(name)
            truncated_section = True
    return content, included, read_next


def run_resume(workspace: Path, date_str: str | None = None, max_bytes: int = RESUME_MAX_BYTES) -> dict[str, Any]:
    root = mission_root(workspace)
    status_res = run_status(root, date_str=date_str)
    bounded_max_bytes = min(max(0, int(max_bytes)), RESUME_MAX_BYTES)
    derived_read_errors: list[str] = []

    files_read = [
        "MissionCenter/brief.md",
        "MissionCenter/working-set.md",
        "MissionCenter/critical-lessons.md",
    ]

    snapshot_path = root / "snapshot.md"
    snapshot_text = None
    if snapshot_path.is_file():
        # Snapshot is canonical recovery evidence, not a disposable view.
        # Corruption or oversize must fail closed instead of being hidden.
        snapshot_text = _read_bounded_text(snapshot_path, 64 * 1024)
        if snapshot_text and re.search(r"^\s*-\s*State:\s*active\b", snapshot_text, re.MULTILINE | re.IGNORECASE):
            files_read.append("MissionCenter/snapshot.md")

    ledger_path = root / EXECUTION_LEDGER_FILENAME
    handoff: dict[str, Any] | None = None
    ledger_error: str | None = None
    if ledger_path.is_file():
        files_read.append(f"MissionCenter/{EXECUTION_LEDGER_FILENAME}")
        try:
            # Build the bounded handoff independently; the resume packet applies the
            # single 16 KiB fuse (or a caller's smaller budget) to all sections.
            handoff = run_handoff(root, max_bytes=HANDOFF_MAX_BYTES)
        except (ValueError, OSError) as exc:
            # Do not expose partially parsed evidence or fall back to a directory scan.
            ledger_error = str(exc)

    brief_text, brief_error = _read_derived_text(root / "brief.md")
    ws_text, ws_error = _read_derived_text(root / "working-set.md")
    if brief_error:
        derived_read_errors.append("brief")
    if ws_error:
        derived_read_errors.append("workingSet")
    brief_bytes = len(brief_text.encode("utf-8"))
    ws_bytes = len(ws_text.encode("utf-8"))
    cl_text = (
        _read_bounded_text(root / "critical-lessons.md", CANONICAL_READ_LIMITS["critical-lessons.md"])
        if (root / "critical-lessons.md").is_file()
        else ""
    )
    cl_bytes = len(_active_lessons_text(cl_text).encode("utf-8"))
    snap_text = snapshot_text if "MissionCenter/snapshot.md" in files_read else None
    snap_bytes = len(snap_text.encode("utf-8")) if snap_text is not None else 0
    sections = [
        ("brief", brief_text),
        ("workingSet", ws_text),
        ("activeCriticalLessons", _active_lessons_text(cl_text)),
        ("snapshot", snap_text),
    ]
    if handoff and handoff.get("content"):
        sections.insert(0, ("handoff", handoff["content"]))
    content, included_bytes, read_next = _bounded_resume_content(sections, bounded_max_bytes)
    for name in derived_read_errors:
        if name not in read_next:
            read_next.append(name)
    total_bytes = sum(included_bytes.values())

    canonical_fallback = False
    fallback_reason = None

    if not status_res["sourceFresh"] or not status_res["dateFresh"]:
        canonical_fallback = True
        fallback_reason = "derived view stale"
    elif ledger_error:
        canonical_fallback = True
        fallback_reason = "execution ledger corrupt"
    # Budget overflow remains a bounded hot packet, not a canonical fallback.

    return {
        "schemaVersion": "1.1",
        "route": "resume",
        "sourceFresh": status_res["sourceFresh"],
        "dateFresh": status_res["dateFresh"],
        "staleReasons": status_res["staleReasons"],
        "filesRead": files_read,
        "content": content,
        "handoff": handoff,
        "ledgerStatus": "corrupt" if ledger_error else ("ready" if handoff is not None else "missing"),
        "ledgerError": ledger_error,
        "context": {
            "briefBytes": brief_bytes,
            "workingSetBytes": ws_bytes,
            "criticalLessonsBytes": cl_bytes,
            "snapshotBytes": snap_bytes,
            "totalBytes": total_bytes,
            "includedBytes": included_bytes,
        },
        "bytes": total_bytes,
        "maxBytes": bounded_max_bytes,
        "canonicalFallback": canonical_fallback,
        "fallbackReason": fallback_reason,
        "truncated": bool(read_next),
        "truncatedMarker": "[TRUNCATED]" if read_next else None,
        "readNext": read_next,
    }


def run_task_info(workspace: Path, task_id: str) -> dict[str, Any]:
    root = mission_root(workspace)
    tasks = parse_tasks(root / "tasks.md") if (root / "tasks.md").is_file() else []
    matched = [t for t in tasks if t.get("ID", "").strip().casefold() == task_id.strip().casefold()]
    if matched:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "route": "task",
            "taskId": task_id,
            "found": True,
            "task": matched[0],
            "canonicalFallback": False,
            "fallbackReason": None,
        }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "route": "task",
        "taskId": task_id,
        "found": False,
        "task": None,
        "canonicalFallback": True,
        "fallbackReason": "requested task not present",
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

    resume = commands.add_parser("resume")
    resume.add_argument("--json", action="store_true", default=True)
    resume.add_argument("--date")
    resume.add_argument("--max-bytes", type=int, default=RESUME_MAX_BYTES)

    pulse = commands.add_parser("pulse")
    pulse.add_argument("--task-id", required=True)
    pulse.add_argument("--phase", required=True)
    pulse.add_argument("--outcome", required=True)
    pulse.add_argument("--next-action", required=True)
    pulse.add_argument("--evidence-ref", default="")
    pulse.add_argument("--budget-remaining", required=True, type=int)
    pulse.add_argument("--causal-parent")
    pulse.add_argument("--pulse-id")

    handoff = commands.add_parser("handoff")
    handoff.add_argument("--task-id")
    handoff.add_argument("--max-bytes", type=int, default=HANDOFF_MAX_BYTES)

    task_cmd = commands.add_parser("task")
    task_cmd.add_argument("task_id")
    task_cmd.add_argument("--json", action="store_true", default=True)

    args = parser.parse_args(argv)
    workspace = Path(args.workspace)
    if args.command == "sync":
        result = run_sync(workspace, args.force, args.date, args.max_brief_bytes)
    elif args.command == "daily":
        result = run_daily(workspace, args.message, args.date, args.max_brief_bytes)
    elif args.command == "status":
        result = run_status(workspace, args.date)
    elif args.command == "resume":
        result = run_resume(workspace, args.date, args.max_bytes)
    elif args.command == "pulse":
        result = append_execution_pulse(workspace, {
            "pulseId": args.pulse_id,
            "taskId": args.task_id,
            "phase": args.phase,
            "outcome": args.outcome,
            "nextAction": args.next_action,
            "evidenceRef": args.evidence_ref,
            "budgetRemaining": args.budget_remaining,
            "causalParent": args.causal_parent,
        })
    elif args.command == "handoff":
        result = run_handoff(workspace, args.task_id, args.max_bytes)
    elif args.command == "task":
        result = run_task_info(workspace, args.task_id)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "status":
        return 1 if result["stale"] else 0
    if args.command == "task":
        return 0 if result["found"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
