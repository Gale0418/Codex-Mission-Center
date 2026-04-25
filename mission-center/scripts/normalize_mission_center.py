#!/usr/bin/env python3
"""Normalize MissionCenter task metadata."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


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

LABEL_CORE = {"intake", "plan", "execution", "verification", "blocked", "closeout"}


def split_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


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


def normalize_tasks(path: Path) -> bool:
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    table_indexes = [i for i, line in enumerate(lines) if line.startswith("|")]
    if len(table_indexes) < 3:
        return False
    header_index = table_indexes[0]
    separator_index = table_indexes[1]
    headers = split_cells(lines[header_index])
    changed = False
    new_lines = lines[: separator_index + 1]
    for line in lines[separator_index + 1 :]:
        if not line.startswith("|"):
            new_lines.append(line)
            continue
        cells = split_cells(line)
        if len(cells) != len(headers):
            new_lines.append(line)
            continue
        row = dict(zip(headers, cells))
        if "Priority" in row:
            normalized = normalize_priority(row["Priority"])
            changed |= normalized != row["Priority"]
            row["Priority"] = normalized
        if "Status" in row:
            normalized = normalize_status(row["Status"])
            changed |= normalized != row["Status"]
            row["Status"] = normalized
        if "Labels" in row:
            normalized = normalize_labels(row["Labels"])
            changed |= normalized != row["Labels"]
            row["Labels"] = normalized
        rebuilt = "| " + " | ".join(row.get(h, "") for h in headers) + " |"
        new_lines.append(rebuilt)
    if changed:
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
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
