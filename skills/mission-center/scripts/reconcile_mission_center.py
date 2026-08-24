#!/usr/bin/env python3
"""Read-only reconciliation of MissionCenter lifecycle and evidence views."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from common.markdown_table import parse_table
from mission_maintenance import (
    EXECUTION_LEDGER_FILENAME,
    FINGERPRINT_SOURCES,
    FOCUS_FINGERPRINT_SOURCES,
    WORKING_SET_FINGERPRINT_SOURCES,
    _read_execution_ledger,
    compute_workspace_fingerprint,
    is_fingerprint_stale,
    mission_root,
    parse_derived_fingerprint,
    run_status,
)
from evidence_envelope import (
    ENVELOPE_DIR,
    MAX_ENVELOPE_BYTES,
    envelope_status,
    validate_envelope,
)
from sync_mission_center import compute_progress, render_bar
from visual_state import normalize_tasks


CHECK_STATUS = {"pass", "stale", "conflict", "corrupt", "unknown"}
STATUS_PRIORITY = {"pass": 0, "unknown": 1, "stale": 2, "conflict": 3, "corrupt": 4}
TASK_ID_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*-\d+\b")


def _check(name: str, status: str, message: str, **details: Any) -> dict[str, Any]:
    if status not in CHECK_STATUS:
        raise ValueError(f"unsupported reconciliation status: {status}")
    result: dict[str, Any] = {"name": name, "status": status, "message": message}
    if details:
        result["details"] = details
    return result


def _field(text: str, *labels: str) -> str | None:
    alternatives = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"^\s*-\s*(?:{alternatives})[：:]\s*([^\r\n]*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _section(text: str, start_labels: tuple[str, ...], end_labels: tuple[str, ...]) -> str:
    start = _field_line_start(text, start_labels)
    if start is None:
        return ""
    end = len(text)
    for label in end_labels:
        match = re.search(rf"^\s*-\s*{re.escape(label)}[：:]", text[start:], re.MULTILINE)
        if match:
            end = start + match.start()
            break
    return text[start:end]


def _field_line_start(text: str, labels: tuple[str, ...]) -> int | None:
    alternatives = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"^\s*-\s*(?:{alternatives})[：:]", text, re.MULTILINE)
    return match.start() if match else None


def _task_ids(text: str, known_ids: set[str]) -> set[str]:
    found = set(TASK_ID_PATTERN.findall(text))
    return {task_id for task_id in found if task_id in known_ids}


def _check_ledger(root: Path) -> dict[str, Any]:
    path = root / EXECUTION_LEDGER_FILENAME
    if not path.is_file():
        return _check("ledger", "unknown", "execution ledger is absent", path=str(path))
    try:
        records = _read_execution_ledger(root)
    except (OSError, UnicodeError, ValueError) as exc:
        return _check("ledger", "corrupt", str(exc), path=str(path))
    return _check("ledger", "pass", "execution ledger is readable", records=len(records), path=str(path))


def _check_progress(root: Path, tasks: list[dict[str, str]]) -> dict[str, Any]:
    path = root / "progress.md"
    if not path.is_file():
        return _check("progress", "unknown", "progress.md is absent", path=str(path))
    text = path.read_text(encoding="utf-8")
    percent, mode, active, blocked = compute_progress(tasks)
    expected_bar = render_bar(percent)
    actual_bar = _field(text, "進度條", "Progress bar")
    actual_status = _field(text, "目前狀態", "Current status")
    active_section = _section(text, ("進行中任務", "Active tasks"), ("阻塞原因", "Blocked tasks"))
    known_ids = {task.get("ID", "").strip() for task in tasks if task.get("ID", "").strip()}
    actual_ids = _task_ids(active_section, known_ids)
    expected_ids = _task_ids("\n".join(active), known_ids)
    problems: list[str] = []
    if actual_bar is None or expected_bar not in actual_bar:
        problems.append(f"progress bar expected {expected_bar}")
    if actual_status is None or mode not in actual_status:
        problems.append(f"status expected to include {mode}")
    if actual_ids != expected_ids:
        problems.append(f"active task IDs expected {sorted(expected_ids)}, got {sorted(actual_ids)}")
    if problems:
        return _check(
            "progress",
            "conflict",
            "; ".join(problems),
            expected={"bar": expected_bar, "mode": mode, "activeTaskIds": sorted(expected_ids)},
            actual={"bar": actual_bar, "status": actual_status, "activeTaskIds": sorted(actual_ids)},
        )
    return _check("progress", "pass", "progress.md matches tasks.md", expectedMode=mode, expectedBar=expected_bar, blockedTaskIds=blocked)


def _contains_id(text: str, task_id: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_-]){re.escape(task_id)}(?![A-Za-z0-9_-])", text) is not None


def _check_closeout(root: Path, tasks: list[dict[str, str]]) -> dict[str, Any]:
    path = root / "closeout.md"
    if not path.is_file():
        return _check("closeout", "unknown", "closeout.md is absent", path=str(path))
    text = path.read_text(encoding="utf-8")
    completed = _field(text, "已完成", "Completed")
    unfinished = _field(text, "未完成", "Unfinished")
    if completed is None or unfinished is None:
        return _check("closeout", "unknown", "closeout.md is missing Completed or Unfinished", path=str(path))
    known_ids = {task.get("ID", "").strip() for task in tasks if task.get("ID", "").strip()}
    completed_ids = _task_ids(completed, known_ids)
    unfinished_ids = _task_ids(unfinished, known_ids)
    overlap = sorted(completed_ids & unfinished_ids)
    completed_not_done = sorted(
        task_id
        for task_id in completed_ids
        if next((task.get("Status") for task in tasks if task.get("ID") == task_id), None) != "Done"
    )
    unfinished_done = sorted(
        task_id
        for task_id in unfinished_ids
        if next((task.get("Status") for task in tasks if task.get("ID") == task_id), None) == "Done"
    )
    problems: list[str] = []
    if completed_not_done:
        problems.append(f"Completed contains non-Done task IDs: {completed_not_done}")
    if unfinished_done:
        problems.append(f"Unfinished contains Done task IDs: {unfinished_done}")
    if overlap:
        problems.append(f"task IDs appear in both Completed and Unfinished: {overlap}")
    if problems:
        return _check(
            "closeout",
            "conflict",
            "; ".join(problems),
            completedTaskIds=sorted(completed_ids),
            unfinishedTaskIds=sorted(unfinished_ids),
        )
    return _check(
        "closeout",
        "pass",
        "closeout.md has no contradictory task references",
        completedTaskIds=sorted(completed_ids),
        unfinishedTaskIds=sorted(unfinished_ids),
    )


def _check_derived_source(root: Path) -> dict[str, Any]:
    views = {
        "brief.md": FINGERPRINT_SOURCES,
        "working-set.md": WORKING_SET_FINGERPRINT_SOURCES,
        "focus.md": FOCUS_FINGERPRINT_SOURCES,
    }
    stale: list[str] = []
    corrupt: list[str] = []
    missing: list[str] = []
    for name, sources in views.items():
        path = root / name
        if not path.is_file():
            missing.append(name)
            continue
        try:
            cached = parse_derived_fingerprint(path.read_text(encoding="utf-8"))
            expected = compute_workspace_fingerprint(root, sources)
        except (OSError, UnicodeError, ValueError) as exc:
            corrupt.append(f"{name}: {exc}")
            continue
        if not cached:
            corrupt.append(f"{name} has no generated fingerprint")
        elif is_fingerprint_stale(expected, cached):
            stale.append(name)
    if corrupt:
        return _check("derived_source", "corrupt", "; ".join(corrupt))
    if stale:
        return _check("derived_source", "stale", f"derived source fingerprint is stale: {', '.join(stale)}", staleViews=stale)
    if missing:
        return _check("derived_source", "unknown", f"derived views are absent: {', '.join(missing)}", missingViews=missing)
    return _check("derived_source", "pass", "derived source fingerprints match canonical files")


def _check_derived_date(root: Path) -> dict[str, Any]:
    # Calendar freshness is reported separately from source-fingerprint
    # integrity so an old but internally consistent fixture remains readable.
    try:
        status = run_status(root)
    except (OSError, UnicodeError, ValueError) as exc:
        return _check("derived_date", "unknown", f"could not determine organized date: {exc}")
    if status.get("dateFresh"):
        return _check("derived_date", "pass", "daily organization date is current", date=status.get("date"))
    return _check(
        "derived_date",
        "stale",
        "daily organization date is older than the requested date",
        date=status.get("date"),
        staleReasons=status.get("staleReasons", []),
    )


def _check_evidence_envelopes(root: Path, tasks: list[dict[str, str]]) -> dict[str, Any]:
    """Validate only the bounded, named evidence-envelope directory."""
    workspace = root.parent
    directory = workspace / ENVELOPE_DIR
    task_ids = {task.get("ID", "").strip() for task in tasks if task.get("ID", "").strip()}
    if not directory.is_dir():
        return _check(
            "evidence_envelope",
            "unknown",
            "no evidence envelopes found; existing tasks remain migration debt",
            missingTaskIds=sorted(task_ids),
            directory=str(directory),
        )
    try:
        paths = sorted(directory.glob("*.json"))
    except OSError as exc:
        return _check("evidence_envelope", "corrupt", f"cannot enumerate evidence envelopes: {exc}")
    if not paths:
        return _check(
            "evidence_envelope",
            "unknown",
            "evidence envelope directory is empty; existing tasks remain migration debt",
            missingTaskIds=sorted(task_ids),
            directory=str(directory),
        )

    records: list[tuple[Path, dict[str, Any]]] = []
    errors: list[str] = []
    statuses: list[str] = []
    seen_ids: set[str] = set()
    for path in paths:
        try:
            if path.stat().st_size > MAX_ENVELOPE_BYTES:
                raise ValueError(f"file exceeds {MAX_ENVELOPE_BYTES} bytes")
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{path.name}: corrupt envelope: {exc}")
            statuses.append("corrupt")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.name}: envelope must be an object")
            statuses.append("corrupt")
            continue
        status = envelope_status(payload, workspace)
        statuses.append(status)
        envelope_errors = validate_envelope(payload, workspace)
        if envelope_errors:
            errors.append(f"{path.name}: {'; '.join(envelope_errors)}")
        envelope_id = payload.get("envelopeId")
        if isinstance(envelope_id, str):
            if envelope_id in seen_ids:
                errors.append(f"duplicate envelopeId: {envelope_id}")
                statuses.append("conflict")
            seen_ids.add(envelope_id)
        records.append((path, payload))

    valid_records = [(path, payload) for path, payload in records if not validate_envelope(payload, workspace)]
    by_id = {payload.get("envelopeId"): payload for _, payload in valid_records}
    current_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    covered_task_ids: set[str] = set()
    unknown_results: list[str] = []
    for path, payload in valid_records:
        task_id = payload.get("taskId")
        check_id = payload.get("checkId")
        if task_id not in task_ids:
            errors.append(f"{path.name}: envelope taskId is not present in tasks.md: {task_id}")
            statuses.append("conflict")
        elif isinstance(task_id, str):
            covered_task_ids.add(task_id)
        if payload.get("status") == "current":
            current_by_key.setdefault((str(task_id), str(check_id)), []).append(payload)
            if payload.get("result") == "fail":
                errors.append(f"{path.name}: current evidence result is fail")
                statuses.append("conflict")
            elif payload.get("result") == "unknown":
                unknown_results.append(f"{task_id}/{check_id}")
            supersedes = payload.get("supersedes")
            if supersedes:
                target = by_id.get(supersedes)
                if target is None:
                    errors.append(f"{path.name}: supersedes unknown envelope: {supersedes}")
                    statuses.append("conflict")
                elif target.get("taskId") != task_id or target.get("checkId") != check_id:
                    errors.append(f"{path.name}: supersedes envelope from another task/check")
                    statuses.append("conflict")
                elif target.get("status") != "superseded":
                    errors.append(f"{path.name}: superseded target must have status superseded: {supersedes}")
                    statuses.append("conflict")
        elif payload.get("status") == "superseded":
            if not any(item.get("supersedes") == payload.get("envelopeId") for item in by_id.values()):
                errors.append(f"{path.name}: superseded envelope has no current replacement")
                statuses.append("conflict")

    for (task_id, check_id), current in current_by_key.items():
        if len(current) > 1:
            errors.append(f"multiple current envelopes for task/check: {task_id}/{check_id}")
            statuses.append("conflict")

    missing_task_ids = sorted(task_ids - covered_task_ids)
    if errors:
        if "corrupt" in statuses:
            status = "corrupt"
        elif "stale" in statuses:
            status = "stale"
        else:
            status = "conflict"
        return _check("evidence_envelope", status, "; ".join(errors), missingTaskIds=missing_task_ids)
    if missing_task_ids:
        return _check(
            "evidence_envelope",
            "unknown",
            "some tasks have no evidence envelope; migration warning only",
            missingTaskIds=missing_task_ids,
            envelopeCount=len(valid_records),
        )
    if unknown_results:
        return _check(
            "evidence_envelope",
            "unknown",
            "current evidence results remain unknown",
            unknownChecks=sorted(unknown_results),
            envelopeCount=len(valid_records),
        )
    return _check("evidence_envelope", "pass", "all existing evidence envelopes are valid", envelopeCount=len(valid_records))


def reconcile_workspace(workspace: Path) -> dict[str, Any]:
    """Return bounded read-only evidence reconciliation; never write workspace files."""
    root = mission_root(Path(workspace))
    checks: list[dict[str, Any]] = []
    tasks_path = root / "tasks.md"
    try:
        tasks = normalize_tasks(parse_table(tasks_path))
    except (OSError, UnicodeError, ValueError) as exc:
        checks.append(_check("tasks", "unknown", f"could not read tasks.md: {exc}"))
        tasks = []
    checks.extend(
        (
            _check_ledger(root),
            _check_progress(root, tasks),
            _check_closeout(root, tasks),
            _check_derived_source(root),
            _check_derived_date(root),
            _check_evidence_envelopes(root, tasks),
        )
    )
    status = max((check["status"] for check in checks), key=STATUS_PRIORITY.get, default="unknown")
    return {
        "schemaVersion": "1.0",
        "workspace": str(root.parent),
        "status": status,
        "checks": checks,
        "readOnly": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = reconcile_workspace(Path(args.workspace))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"MissionCenter reconciliation: {result['status']}")
        for check in result["checks"]:
            print(f"{check['status'].upper()}: {check['name']}: {check['message']}")
    return 0 if result["status"] in {"pass", "unknown", "stale"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
