#!/usr/bin/env python3
"""Normalize MissionCenter task metadata."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common.markdown_table import first_table_block, split_cells


STATUS_MAP = {
    "todo": "Backlog",
    "backlog": "Backlog",
    "ready": "Ready",
    "in progress": "In Progress",
    "doing": "In Progress",
    "blocked": "Blocked",
    "review": "Review",
    "done": "Done",
}

PRIORITY_MAP = {
    "urgent": "P0",
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "normal": "P2",
    "low": "P3",
}

HEADER_ALIASES = {
    "Priority": "Priority",
    "Status": "Status",
    "Labels": "Labels",
    "優先級": "Priority",
    "狀態": "Status",
    "標籤": "Labels",
}


def normalize_labels(text: str) -> str:
    labels = []
    for raw in re.split(r"[;,]", text or ""):
        label = raw.strip().lower()
        if not label:
            continue
        labels.append(label)
    return ", ".join(dict.fromkeys(labels))


def normalize_priority(value: str) -> str:
    lower = (value or "").strip().lower()
    if lower in {"p0", "p1", "p2", "p3"}:
        return lower.upper()
    return PRIORITY_MAP.get(lower, value.strip() or "P2")


def normalize_status(value: str) -> str:
    lower = (value or "").strip().lower()
    if lower in {"backlog", "ready", "in progress", "blocked", "review", "done"}:
        return lower.title() if lower != "in progress" else "In Progress"
    return STATUS_MAP.get(lower, value.strip() or "Backlog")


def find_header(headers: list[str], canonical: str) -> str | None:
    for header in headers:
        if HEADER_ALIASES.get(header, header) == canonical:
            return header
    return None


def normalize_tasks(path: Path) -> bool:
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    block = first_table_block(lines, include_indented=False)
    if len(block) < 3:
        return False
    header_index = block[0][0] - 1
    separator_index = block[1][0] - 1
    headers = split_cells(lines[header_index])
    priority_header = find_header(headers, "Priority")
    status_header = find_header(headers, "Status")
    labels_header = find_header(headers, "Labels")
    changed = False
    for line_number, line in block[2:]:
        cells = split_cells(line)
        if len(cells) != len(headers):
            continue
        row = dict(zip(headers, cells))
        if priority_header is not None:
            normalized = normalize_priority(row[priority_header])
            changed |= normalized != row[priority_header]
            row[priority_header] = normalized
        if status_header is not None:
            normalized = normalize_status(row[status_header])
            changed |= normalized != row[status_header]
            row[status_header] = normalized
        if labels_header is not None:
            normalized = normalize_labels(row[labels_header])
            changed |= normalized != row[labels_header]
            row[labels_header] = normalized
        lines[line_number - 1] = "| " + " | ".join(row.get(header, "") for header in headers) + " |"
    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.workspace).resolve() / "MissionCenter"
    changed = normalize_tasks(root / "tasks.md")
    print(f"normalized={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
