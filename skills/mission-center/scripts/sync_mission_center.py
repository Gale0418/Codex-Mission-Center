#!/usr/bin/env python3
"""Sync a MissionCenter workspace summary from tasks and smoke tests."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


def parse_table(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows = [line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()]
    table_lines = [line for line in rows if line.startswith("|")]
    if len(table_lines) < 2:
        return []
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    data = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
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
                total_est += estimate
                if status == "done":
                    done_est += estimate
            if status in {"backlog", "ready", "in progress", "smoketest", "review"} and len(active) < 5:
                active.append(f"{task.get('ID', '').strip()} {title} ({task.get('Status', '').strip()})")
            if status == "blocked" and len(blocked) < 5:
                blocked.append(f"{task.get('ID', '').strip()} {title}")

    if total_est > 0:
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


def update_progress(path: Path, project: str, objective: str, milestone: str, percent: int, mode: str, active: list[str], blocked: list[str]) -> None:
    content = f"""# Progress

- Project: {project}
- Objective: {objective}
- Current status: {mode}
- Milestone: {milestone}
- Progress bar: {render_bar(percent)}
- Active tasks:
{''.join(f'  - {item}\n' for item in active) or '  - None\n'}- Blocked by:
{''.join(f'  - {item}\n' for item in blocked) or '  - None\n'}- Next update: Re-run sync after any task or smoke-test change.
"""
    path.write_text(content, encoding="utf-8")


def update_project(path: Path, project: str, cycle: str, goal: str, labels: str, activity_note: str) -> None:
    content = f"""# Project

- Goal: {goal}
- Cycle: {cycle}
- Labels: {labels}
- Activity log:
  - {activity_note}
- Open comments:
  - None
"""
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--project", default="MissionCenter")
    parser.add_argument("--cycle", default="Unassigned")
    parser.add_argument("--goal", default="MissionCenter workspace")
    parser.add_argument("--labels", default="mission-center")
    parser.add_argument("--milestone", default="Next slice")
    parser.add_argument("--activity", default="Workspace synced from tasks and smoke tests.")
    args = parser.parse_args()

    root = Path(args.workspace).resolve() / "MissionCenter"
    tasks = parse_table(root / "tasks.md")
    smoke_tests = parse_table(root / "smoke-tests.md")
    percent, mode, active, blocked = compute_progress(tasks)
    if smoke_tests:
        activity = f"{args.activity} Smoke tests recorded: {len(smoke_tests)}."
    else:
        activity = args.activity
    update_project(root / "project.md", args.project, args.cycle, args.goal, args.labels, activity)
    update_progress(root / "progress.md", args.project, args.goal, args.milestone, percent, mode, active, blocked)
    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
