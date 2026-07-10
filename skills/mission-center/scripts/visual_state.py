#!/usr/bin/env python3
"""Build deterministic visual HUD state from MissionCenter task rows."""

from __future__ import annotations

import hashlib


STATUS_TO_ZONE = {
    "backlog": "Intake",
    "ready": "Intake",
    "in progress": "In Progress",
    "blocked": "Blocked",
    "review": "Review",
    "done": "Done",
}

HEADER_ALIASES = {
    "標題": "Title",
    "類型": "Type",
    "父層": "Parent",
    "優先級": "Priority",
    "狀態": "Status",
    "負責人": "Owner",
    "依賴": "Depends on",
    "下一步": "Next action",
    "驗證方式": "Verification",
    "估時": "Estimate",
    "標籤": "Labels",
    "備註": "Comments",
}

REQUIRED_FIELDS = ("ID", "Title", "Status")


def normalize_tasks(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Normalize localized task headers and validate the task lifecycle."""
    tasks: list[dict[str, str]] = []
    for row_number, row in enumerate(rows, start=1):
        task = {
            HEADER_ALIASES.get(str(key).strip(), str(key).strip()): str(value).strip()
            for key, value in row.items()
        }
        missing = [field for field in REQUIRED_FIELDS if not task.get(field)]
        if missing:
            raise ValueError(
                f"Task row {row_number} is missing: {', '.join(missing)}"
            )
        if task["Status"].lower() not in STATUS_TO_ZONE:
            raise ValueError(f"Unsupported task status: {task['Status']}")
        tasks.append(task)
    return tasks


def select_visible_tasks(
    tasks: list[dict[str, str]], limit: int = 15
) -> list[dict[str, str]]:
    """Select up to ten unfinished tasks and newest completed tasks within limit."""
    unfinished_limit = min(10, limit)
    unfinished = [task for task in tasks if task["Status"].lower() != "done"][:unfinished_limit]
    done = [task for task in tasks if task["Status"].lower() == "done"]
    done_slots = max(0, limit - len(unfinished))
    visible_done = done[-done_slots:] if done_slots else []
    return unfinished + visible_done


def _stable_avatar(task_id: str) -> int:
    digest = hashlib.sha256(task_id.encode("utf-8")).digest()
    return (int.from_bytes(digest[:2], "big") % 16) + 1


def _project_status(tasks: list[dict[str, str]]) -> str:
    statuses = [STATUS_TO_ZONE[task["Status"].lower()] for task in tasks]
    if not statuses:
        return "Intake"
    if all(status == "Done" for status in statuses):
        return "Done"
    for candidate in ("Blocked", "In Progress", "Review", "Intake"):
        if candidate in statuses:
            return candidate
    return "Intake"


def build_visual_state(
    tasks: list[dict[str, str]], goal: str, progress: int
) -> dict[str, object]:
    """Create the JSON-serializable state consumed by the visual HUD."""
    visible = select_visible_tasks(tasks)
    active = [
        task["Title"] for task in tasks if task["Status"].lower() != "done"
    ][:5]
    blocked = [
        task["Title"] for task in tasks if task["Status"].lower() == "blocked"
    ][:5]
    agents = []
    for task in visible:
        status = STATUS_TO_ZONE[task["Status"].lower()]
        agents.append(
            {
                "id": task["ID"],
                "name": task["Title"],
                "task": f"{task['ID']} {task['Title']}",
                "status": status,
                "zone": status,
                "avatar": _stable_avatar(task["ID"]),
                "active": task["Status"].lower() != "done",
            }
        )
    return {
        "status": _project_status(tasks),
        "goal": goal,
        "progress": max(0, min(100, int(progress))),
        "active": active,
        "blocked": blocked,
        "agents": agents,
    }
