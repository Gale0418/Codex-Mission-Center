"""Pure compatibility/oracle policy for the bounded Rust working-set view.

No file IO, model calls, lifecycle writes, or implicit task promotion occurs
here. The native Rust runtime remains the formal entry point. Preserve the
existing dictionary API so compatibility sync and Doctor use the same policy.
"""
from __future__ import annotations

import re

WORKING_SET_LIMIT = 6


def priority_key(task: dict[str, str]) -> tuple[int, str]:
    """Keep the historical priority/ID order for compatibility callers."""
    priority = task.get("Priority", "").strip().upper()
    value = int(priority[1:]) if re.fullmatch(r"P\d+", priority) else 99
    return value, task.get("ID", "").strip()


def dependency_ids(task: dict[str, str]) -> set[str]:
    """Use the existing compact Depends on cell convention."""
    return set(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*-\d+\b", task.get("Depends on", "")))


def select_working_set(
    tasks: list[dict[str, str]], limit: int = WORKING_SET_LIMIT,
) -> list[dict[str, str]]:
    """Anchor current work, then urgent tasks/dependencies, within six slots.

    There is no explicit active-task-ID parameter in this API. The first
    canonical In Progress row is the anchor. Returned rows are borrowed and
    canonical input order/content is never mutated. Backlog stays unapproved.
    """
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("working-set limit must be an integer")
    bounded_limit = min(max(0, limit), WORKING_SET_LIMIT)
    if bounded_limit == 0:
        return []

    def status(task: dict[str, str]) -> str:
        return task.get("Status", "").strip().casefold()

    anchor = next((task for task in tasks if status(task) == "in progress"), None)
    dependencies = dependency_ids(anchor) if anchor is not None else set()
    categories = (
        (anchor,) if anchor is not None else (),
        (task for task in tasks if task.get("Priority", "").strip().casefold() == "p0"),
        (task for task in tasks if task.get("ID", "").strip() in dependencies),
        (task for task in tasks if status(task) == "in progress"),
        (task for task in tasks if status(task) == "review"),
        (task for task in tasks if status(task) == "blocked"),
        sorted((task for task in tasks if status(task) == "ready"), key=priority_key),
    )
    selected: list[dict[str, str]] = []
    seen: set[str] = set()
    for category in categories:
        for task in category:
            task_id = task.get("ID", "").strip()
            if (task_id and task_id not in seen
                    and status(task) in {"ready", "in progress", "review", "blocked"}):
                seen.add(task_id)
                selected.append(task)
                if len(selected) == bounded_limit:
                    return selected
    return selected
