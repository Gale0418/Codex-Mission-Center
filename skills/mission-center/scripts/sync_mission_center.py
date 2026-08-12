#!/usr/bin/env python3
"""Sync a MissionCenter workspace summary from tasks and smoke tests."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from visual_state import build_visual_state, normalize_tasks


MANAGED_SUMMARY_MARKER = "<!-- mission-center-managed-summary v=1 -->"


TEXT = {
    "en": {
        "progress_title": "Progress",
        "project_label": "Project",
        "objective_label": "Objective",
        "status_label": "Current status",
        "milestone_label": "Milestone",
        "progress_bar_label": "Progress bar",
        "active_label": "Active tasks",
        "blocked_label": "Blocked by",
        "next_update_label": "Next update",
        "next_update_value": "Re-run sync after any task or smoke-test change.",
        "none": "None",
        "project_title": "Project",
        "goal_label": "Goal",
        "cycle_label": "Cycle",
        "labels_label": "Labels",
        "activity_log_label": "Activity log",
        "open_comments_label": "Open comments",
        "smoke_note": "Smoke tests recorded",
    },
    "zh-TW": {
        "progress_title": "進度",
        "project_label": "專案",
        "objective_label": "目標",
        "status_label": "目前狀態",
        "milestone_label": "里程碑",
        "progress_bar_label": "進度條",
        "active_label": "進行中任務",
        "blocked_label": "阻塞原因",
        "next_update_label": "下次更新",
        "next_update_value": "任務或 smoke-test 有變動後請重新執行 sync。",
        "none": "無",
        "project_title": "專案",
        "goal_label": "目標",
        "cycle_label": "週期",
        "labels_label": "標籤",
        "activity_log_label": "活動紀錄",
        "open_comments_label": "開放問題",
        "smoke_note": "已記錄 Smoke tests",
    },
}


def split_cells(line: str) -> list[str]:
    """Split one Markdown table row, honoring backslash-escaped pipes."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            if char not in ("|", "\\"):
                current.append("\\")
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        raise ValueError("Markdown table row ends with an incomplete escape")
    cells.append("".join(current).strip())
    return cells


def parse_table(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows = [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()]
    table_lines = [line for line in rows if line.startswith("|")]
    if len(table_lines) < 2:
        return []
    try:
        headers = split_cells(table_lines[0])
        separator = split_cells(table_lines[1])
    except ValueError as exc:
        raise ValueError(f"{path.name}: malformed Markdown table: {exc}") from exc
    if not headers or len(separator) != len(headers):
        raise ValueError(f"{path.name}: invalid table header")
    if any(not re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
        raise ValueError(f"{path.name}: invalid table separator")
    data = []
    for row_number, line in enumerate(table_lines[2:], start=1):
        try:
            cells = split_cells(line)
        except ValueError as exc:
            raise ValueError(f"{path.name} row {row_number}: malformed Markdown table: {exc}") from exc
        if len(cells) != len(headers):
            raise ValueError(f"{path.name} row {row_number} has {len(cells)} cells; expected {len(headers)}")
        item = dict(zip(headers, cells))
        if any(value for value in item.values()):
            data.append(item)
    return data


def parse_int(value: str) -> int | None:
    match = re.search(r"\d+", value or "")
    return int(match.group(0)) if match else None


def compute_progress(tasks: list[dict[str, str]]) -> tuple[int, str, list[str], list[str]]:
    total = 0
    done = 0
    total_est = 0
    done_est = 0
    estimated_tasks = 0
    active: list[str] = []
    blocked: list[str] = []

    for task in tasks:
        title = task.get("Title", "").strip()
        status = task.get("Status", "").strip().lower()
        estimate = parse_int(task.get("Estimate", ""))
        if title:
            total += 1
            if status == "done":
                done += 1
            if estimate is not None:
                estimated_tasks += 1
                total_est += estimate
                if status == "done":
                    done_est += estimate
            if status in {"backlog", "ready", "in progress", "review"} and len(active) < 5:
                active.append(f"{task.get('ID', '').strip()} {title} ({task.get('Status', '').strip()})")
            if status == "blocked" and len(blocked) < 5:
                blocked.append(f"{task.get('ID', '').strip()} {title}")

    if total > 0 and estimated_tasks == total and total_est > 0:
        percent = round((done_est / total_est) * 100)
        mode = f"{done_est}/{total_est} estimated"
    elif total > 0:
        percent = round((done / total) * 100)
        mode = f"{done}/{total} tasks"
    else:
        percent = 0
        mode = "0/0 tasks"

    return percent, mode, active, blocked


def render_bar(percent: int) -> str:
    filled = max(0, min(10, round(percent / 10)))
    return f"[{'#' * filled}{'-' * (10 - filled)}] {percent}%"


def detect_language(root: Path) -> str:
    markers = ("# 專案", "# 進度", "# 任務", "- 目標:", "- 目標：")
    for name in ("project.md", "progress.md", "tasks.md"):
        path = root / name
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if any(marker in text for marker in markers):
                return "zh-TW"
    return "en"


def _extract_summary_value(line: str, label: str) -> str | None:
    stripped = line.strip()
    for marker in (f"- {label}:", f"- {label}："):
        if stripped.startswith(marker):
            return stripped.removeprefix(marker).strip()
    return None


def _find_summary_value(text: str, labels: list[str]) -> str | None:
    for line in text.splitlines():
        for label in labels:
            value = _extract_summary_value(line, label)
            if value:
                return value
    return None


def _extract_list_items(text: str, labels: list[str]) -> list[str]:
    lines = text.splitlines()
    for label in labels:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"- {label}:") or stripped.startswith(f"- {label}："):
                items: list[str] = []
                cursor = index + 1
                while cursor < len(lines):
                    candidate = lines[cursor]
                    stripped_candidate = candidate.strip()
                    if candidate.startswith("  - "):
                        value = candidate[4:].strip()
                        if value:
                            items.append(value)
                        cursor += 1
                        continue
                    if not stripped_candidate:
                        cursor += 1
                        continue
                    break
                return items
    return []


def _merge_items(existing: list[str], new_item: str) -> list[str]:
    merged = list(existing)
    candidate = new_item.strip()
    if candidate and candidate not in merged:
        merged.append(candidate)
    return merged


def _extract_custom_bullets(text: str) -> list[str]:
    known_labels = {
        TEXT["en"]["project_label"],
        TEXT["en"]["goal_label"],
        TEXT["en"]["cycle_label"],
        TEXT["en"]["labels_label"],
        TEXT["en"]["activity_log_label"],
        TEXT["en"]["open_comments_label"],
        TEXT["zh-TW"]["project_label"],
        TEXT["zh-TW"]["goal_label"],
        TEXT["zh-TW"]["cycle_label"],
        TEXT["zh-TW"]["labels_label"],
        TEXT["zh-TW"]["activity_log_label"],
        TEXT["zh-TW"]["open_comments_label"],
    }
    custom: list[str] = []
    for line in text.splitlines():
        if not line.startswith("- "):
            continue
        body = line[2:]
        separator_positions = [
            position
            for position in (body.find(":"), body.find("："))
            if position >= 0
        ]
        label = body[: min(separator_positions)] if separator_positions else body
        if label.strip() and label.strip() not in known_labels:
            custom.append(line.rstrip())
    return custom


def _extract_custom_sections(text: str) -> list[str]:
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                sections.append("\n".join(current).rstrip())
            current = [line]
            continue
        if current:
            current.append(line)
    if current:
        sections.append("\n".join(current).rstrip())
    return sections


def update_progress(
    path: Path,
    project: str,
    objective: str,
    milestone: str,
    percent: int,
    mode: str,
    active: list[str],
    blocked: list[str],
    language: str,
) -> None:
    labels = TEXT[language]
    active_lines = "".join(f"  - {item}\n" for item in active) or f"  - {labels['none']}\n"
    blocked_lines = "".join(f"  - {item}\n" for item in blocked) or f"  - {labels['none']}\n"
    content = (
        f"{MANAGED_SUMMARY_MARKER}\n"
        f"# {labels['progress_title']}\n\n"
        f"- {labels['project_label']}: {project}\n"
        f"- {labels['objective_label']}: {objective}\n"
        f"- {labels['status_label']}: {mode}\n"
        f"- {labels['milestone_label']}: {milestone}\n"
        f"- {labels['progress_bar_label']}: {render_bar(percent)}\n"
        f"- {labels['active_label']}:\n"
        f"{active_lines}"
        f"- {labels['blocked_label']}:\n"
        f"{blocked_lines}"
        f"- {labels['next_update_label']}: {labels['next_update_value']}\n"
    )
    path.write_text(content, encoding="utf-8")


def update_project(
    path: Path,
    project: str,
    cycle: str,
    goal: str,
    labels_text: str,
    activity_note: str,
    language: str,
) -> None:
    labels = TEXT[language]
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    activity_labels = [
        labels["activity_log_label"],
        TEXT["en"]["activity_log_label"],
        TEXT["zh-TW"]["activity_log_label"],
    ]
    open_comment_labels = [
        labels["open_comments_label"],
        TEXT["en"]["open_comments_label"],
        TEXT["zh-TW"]["open_comments_label"],
    ]
    activity_items = _merge_items(_extract_list_items(existing_text, activity_labels), activity_note)
    open_comment_items = _extract_list_items(existing_text, open_comment_labels) or [labels["none"]]
    custom_bullets = _extract_custom_bullets(existing_text)
    custom_sections = _extract_custom_sections(existing_text)
    activity_lines = "".join(f"  - {item}\n" for item in activity_items)
    open_comment_lines = "".join(f"  - {item}\n" for item in open_comment_items)
    custom_bullet_lines = "".join(f"{line}\n" for line in custom_bullets)
    custom_section_block = "\n\n".join(section for section in custom_sections if section)
    content = (
        f"{MANAGED_SUMMARY_MARKER}\n"
        f"# {labels['project_title']}\n\n"
        f"- {labels['project_label']}: {project}\n"
        f"- {labels['goal_label']}: {goal}\n"
        f"- {labels['cycle_label']}: {cycle}\n"
        f"- {labels['labels_label']}: {labels_text}\n"
        f"{custom_bullet_lines}"
        f"- {labels['activity_log_label']}:\n"
        f"{activity_lines}"
        f"- {labels['open_comments_label']}:\n"
        f"{open_comment_lines}"
    )
    if custom_section_block:
        content = content.rstrip() + "\n\n" + custom_section_block + "\n"
    path.write_text(content, encoding="utf-8")


def is_managed_summary(path: Path) -> bool:
    if not path.is_file():
        return False
    return MANAGED_SUMMARY_MARKER in path.read_text(encoding="utf-8")


def update_visual_state(workspace_root: Path, state: dict[str, object]) -> None:
    """Atomically write validated task state for the visual HUD."""
    target = workspace_root / "output" / "mission-center-assets" / "visual-state.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--project")
    parser.add_argument("--cycle")
    parser.add_argument("--goal")
    parser.add_argument("--labels")
    parser.add_argument("--milestone")
    parser.add_argument(
        "--rewrite-summaries",
        action="store_true",
        help=(
            "Adopt and rewrite project.md/progress.md as generated summaries. "
            "Without this flag, unmarked legacy summaries are preserved."
        ),
    )
    parser.add_argument(
        "--activity", default="",
        help="Optional event written to daily-log.md, not project.md.",
    )
    args = parser.parse_args()

    root = Path(args.workspace).resolve() / "MissionCenter"
    language = detect_language(root)
    labels = TEXT[language]
    project_text = (root / "project.md").read_text(encoding="utf-8") if (root / "project.md").exists() else ""
    progress_text = (root / "progress.md").read_text(encoding="utf-8") if (root / "progress.md").exists() else ""
    project = args.project or _find_summary_value(project_text, [labels["project_label"], TEXT["en"]["project_label"], TEXT["zh-TW"]["project_label"]]) or "MissionCenter"
    goal = args.goal or _find_summary_value(project_text, [labels["goal_label"], TEXT["en"]["goal_label"], TEXT["zh-TW"]["goal_label"]]) or "MissionCenter workspace"
    cycle = args.cycle or _find_summary_value(project_text, [labels["cycle_label"], TEXT["en"]["cycle_label"], TEXT["zh-TW"]["cycle_label"]]) or "Unassigned"
    labels_text = args.labels or _find_summary_value(project_text, [labels["labels_label"], TEXT["en"]["labels_label"], TEXT["zh-TW"]["labels_label"]]) or "mission-center"
    milestone = args.milestone or _find_summary_value(progress_text, [labels["milestone_label"], TEXT["en"]["milestone_label"], TEXT["zh-TW"]["milestone_label"]]) or "Next slice"
    raw_tasks = parse_table(root / "tasks.md")
    tasks = normalize_tasks(raw_tasks)
    smoke_tests = parse_table(root / "smoke-tests.md")
    percent, mode, active, blocked = compute_progress(tasks)
    project_path = root / "project.md"
    progress_path = root / "progress.md"
    if args.rewrite_summaries or is_managed_summary(project_path):
        update_project(project_path, project, cycle, goal, labels_text, "", language)
    if args.rewrite_summaries or is_managed_summary(progress_path):
        update_progress(
            progress_path,
            project,
            goal,
            milestone,
            percent,
            mode,
            active,
            blocked,
            language,
        )
    update_visual_state(root.parent, build_visual_state(tasks, goal, percent))
    from mission_maintenance import run_daily, run_sync

    if args.activity:
        activity = args.activity
        if smoke_tests:
            activity = f"{activity} {labels['smoke_note']}: {len(smoke_tests)}."
        run_daily(root, activity)
    else:
        run_sync(root)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
