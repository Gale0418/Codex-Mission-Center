#!/usr/bin/env python3
"""Validate one explicitly selected Mission Center workspace without mutating it."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from sync_mission_center import (
    build_visual_state,
    compute_progress,
    is_managed_summary,
    render_bar,
)
from visual_state import normalize_tasks
from workspace_contract import REQUIRED_FILES
from mission_maintenance import (
    FOCUS_FINGERPRINT_SOURCES,
    GUARDRAIL_REQUIRED,
    compute_workspace_fingerprint,
    extract_focus_tasks,
    is_fingerprint_stale,
    normalize_guardrail_rows,
    parse_derived_fingerprint,
    validate_daily_log_text,
    validate_guardrails,
)


SMOKE_ID_HEADERS = ("Linked task ID", "對應任務 ID")
SMOKE_RESULT_HEADERS = ("Pass / fail", "通過 / 失敗")
PASS_VALUES = {"pass", "passed", "ok", "通過", "成功"}
LEGACY_DONE_AUDIT = "legacy-done-audit.json"


def split_cells(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"): text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"): text = text[:-1]
    cells, current, escaped = [], [], False
    for char in text:
        if escaped:
            if char not in ("|", "\\"): current.append("\\")
            current.append(char); escaped = False
        elif char == "\\": escaped = True
        elif char == "|": cells.append("".join(current).strip()); current = []
        else: current.append(char)
    if escaped: raise ValueError("row ends with an incomplete escape")
    cells.append("".join(current).strip())
    return cells


def parse_table_strict(path: Path, table_name: str) -> tuple[list[dict[str, str]], list[str]]:
    if not path.is_file():
        return [], []

    table_lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("|")
    ]
    if len(table_lines) < 2:
        return [], [f"{table_name} does not contain a Markdown table"]

    try:
        headers = split_cells(table_lines[0])
        separator = split_cells(table_lines[1])
    except ValueError as exc:
        return [], [f"{table_name} has malformed Markdown table: {exc}"]
    if not headers or len(separator) != len(headers):
        return [], [f"{table_name} has an invalid table header"]
    if any(not re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
        return [], [f"{table_name} has an invalid table separator"]

    rows: list[dict[str, str]] = []
    errors: list[str] = []
    for row_number, line in enumerate(table_lines[2:], start=1):
        try:
            cells = split_cells(line)
        except ValueError as exc:
            errors.append(f"{table_name} row {row_number} is malformed: {exc}")
            continue
        if len(cells) != len(headers):
            errors.append(
                f"{table_name} row {row_number} has {len(cells)} cells; expected {len(headers)}"
            )
            continue
        row = dict(zip(headers, cells))
        if any(row.values()):
            rows.append(row)
    return rows, errors


def first_value(row: dict[str, str], headers: tuple[str, ...]) -> str:
    for header in headers:
        if header in row:
            return row[header].strip()
    return ""


def load_legacy_done_audit(root: Path) -> tuple[set[str], list[str]]:
    path = root / LEGACY_DONE_AUDIT
    if not path.is_file():
        return set(), []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return set(), [f"{LEGACY_DONE_AUDIT} is invalid JSON: {exc}"]
    errors: list[str] = []
    if not isinstance(payload, dict):
        return set(), [f"{LEGACY_DONE_AUDIT} must contain a JSON object"]
    if payload.get("schemaVersion") != "1.0":
        errors.append(f"{LEGACY_DONE_AUDIT} schemaVersion must be 1.0")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append(f"{LEGACY_DONE_AUDIT} reason must be non-empty")
    recorded_at = payload.get("recordedAt")
    try:
        if not isinstance(recorded_at, str):
            raise ValueError
        date.fromisoformat(recorded_at)
    except ValueError:
        errors.append(f"{LEGACY_DONE_AUDIT} recordedAt must be an ISO date")
    raw_ids = payload.get("taskIds")
    if not isinstance(raw_ids, list) or not all(
        isinstance(task_id, str) and task_id.strip() for task_id in raw_ids
    ):
        errors.append(f"{LEGACY_DONE_AUDIT} taskIds must be non-empty strings")
        return set(), errors
    normalized = [task_id.strip() for task_id in raw_ids]
    if len(normalized) != len(set(normalized)):
        errors.append(f"{LEGACY_DONE_AUDIT} taskIds must not contain duplicates")
    return set(normalized), errors


def inspect_workspace_report(workspace: Path) -> tuple[list[str], list[str]]:
    workspace = Path(workspace).expanduser().resolve()
    root = workspace / "MissionCenter"
    if not root.is_dir():
        return [f"MissionCenter directory not found: {root}"], []

    errors = [
        f"Missing required file: {name}"
        for name in REQUIRED_FILES
        if not (root / name).is_file()
    ]
    warnings: list[str] = []
    if not (root / "tasks.md").is_file():
        return errors, warnings

    raw_tasks, task_errors = parse_table_strict(root / "tasks.md", "tasks.md")
    errors.extend(task_errors)
    tasks: list[dict[str, str]] = []
    task_normalization_failed = False
    if not task_errors:
        try:
            tasks = normalize_tasks(raw_tasks)
        except ValueError as exc:
            errors.append(str(exc))
            task_normalization_failed = True

    if tasks:
        legacy_done_ids, legacy_errors = load_legacy_done_audit(root)
        errors.extend(legacy_errors)
        tasks_by_id = {task["ID"]: task for task in tasks}
        for task_id in sorted(legacy_done_ids):
            task = tasks_by_id.get(task_id)
            if task is None:
                errors.append(f"{LEGACY_DONE_AUDIT} references unknown task {task_id}")
            elif task["Status"] != "Done":
                errors.append(
                    f"{LEGACY_DONE_AUDIT} task {task_id} is {task['Status']}, not Done"
                )
        smoke_rows, smoke_errors = parse_table_strict(
            root / "smoke-tests.md", "smoke-tests.md"
        )
        errors.extend(smoke_errors)
        passing_task_ids = {
            first_value(row, SMOKE_ID_HEADERS)
            for row in smoke_rows
            if first_value(row, SMOKE_RESULT_HEADERS).casefold() in PASS_VALUES
        }
        for task in tasks:
            if task["Status"] == "Done" and task["ID"] not in passing_task_ids:
                if task["ID"] in legacy_done_ids:
                    warnings.append(
                        f"Done task {task['ID']} is recorded as unverified legacy debt"
                    )
                else:
                    errors.append(
                        f"Done task {task['ID']} has no passing smoke-test record"
                    )

    if tasks or not task_errors:
        try:
            percent, _, _, _ = compute_progress(tasks)
            expected_bar = render_bar(percent)
            progress_path = root / "progress.md"
            if is_managed_summary(progress_path) and expected_bar not in progress_path.read_text(
                encoding="utf-8"
            ):
                errors.append(
                    f"progress.md is stale; expected progress bar {expected_bar}"
                )
            build_visual_state(tasks, "MissionCenter workspace", percent)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"Unable to derive Mission Center state: {exc}")

    current_fingerprint = compute_workspace_fingerprint(root)
    for name in ("brief.md", "focus.md"):
        path = root / name
        if not path.is_file():
            continue
        cached = parse_derived_fingerprint(path.read_text(encoding="utf-8"))
        if not cached:
            errors.append(f"{name} is not a generated MissionCenter view")
        expected_fingerprint = (
            compute_workspace_fingerprint(root, FOCUS_FINGERPRINT_SOURCES)
            if name == "focus.md"
            else current_fingerprint
        )
        if cached and is_fingerprint_stale(expected_fingerprint, cached):
            errors.append(f"{name} is stale; run mission_maintenance.py sync")

    focus_path = root / "focus.md"
    if focus_path.is_file() and not task_errors and not task_normalization_failed:
        focus_rows, focus_errors = parse_table_strict(focus_path, "focus.md")
        errors.extend(focus_errors)
        expected_ids = [task["ID"] for task in extract_focus_tasks(tasks)]
        actual_ids = [row.get("ID", "").strip() for row in focus_rows]
        if not focus_errors and actual_ids != expected_ids:
            errors.append(
                f"focus.md does not match unfinished P0 tasks; expected {expected_ids}, got {actual_ids}"
            )

    guardrail_path = root / "guardrails.md"
    if guardrail_path.is_file():
        guardrail_rows, guardrail_errors = parse_table_strict(guardrail_path, "guardrails.md")
        errors.extend(guardrail_errors)
        if not guardrail_errors:
            normalized_guardrails = normalize_guardrail_rows(guardrail_rows)
            headers = set(normalized_guardrails[0]) if normalized_guardrails else set()
            if guardrail_rows and not set(GUARDRAIL_REQUIRED).issubset(headers):
                errors.append("guardrails.md is missing required columns")
            errors.extend(validate_guardrails(normalized_guardrails))

    daily_path = root / "daily-log.md"
    if daily_path.is_file():
        errors.extend(validate_daily_log_text(daily_path.read_text(encoding="utf-8")))

    return errors, warnings


def inspect_workspace(workspace: Path) -> list[str]:
    errors, _ = inspect_workspace_report(workspace)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate one workspace's local MissionCenter directory."
    )
    parser.add_argument("workspace", nargs="?", default=".")
    args = parser.parse_args(argv)

    errors, warnings = inspect_workspace_report(Path(args.workspace))
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("MissionCenter doctor: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
