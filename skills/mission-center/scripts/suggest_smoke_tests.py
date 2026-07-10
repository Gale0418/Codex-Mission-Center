#!/usr/bin/env python3
"""Suggest or apply default smoke tests for MissionCenter tasks."""

from __future__ import annotations

import argparse
from pathlib import Path


def split_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def join_cells(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def suggest(type_: str, labels: str, title: str) -> str:
    label_set = {item.strip().lower() for item in labels.replace(";", ",").split(",") if item.strip()}
    type_lower = (type_ or "").strip().lower()
    if "verification" in label_set:
        return "automated smoke test"
    if "execution" in label_set or type_lower in {"task", "subtask"}:
        return "reproducible smoke test"
    if "plan" in label_set or type_lower == "epic":
        return "checklist review"
    if "intake" in label_set:
        return "scope confirmation checklist"
    if "closeout" in label_set:
        return "closeout file review"
    return f"manual smoke test for {title}".strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    root = Path(args.workspace).resolve() / "MissionCenter"
    path = root / "tasks.md"
    if not path.exists():
        print("no tasks.md")
        return 1

    lines = path.read_text(encoding="utf-8").splitlines()
    header_index = next((i for i, line in enumerate(lines) if line.startswith("| ID ")), None)
    if header_index is None:
        print("no table")
        return 1
    headers = split_cells(lines[header_index])
    try:
        verification_idx = headers.index("Verification")
        type_idx = headers.index("Type")
        title_idx = headers.index("Title")
        labels_idx = headers.index("Labels")
    except ValueError:
        print("missing columns")
        return 1

    changed = False
    output = lines[: header_index + 2]
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            output.append(line)
            continue
        cells = split_cells(line)
        if len(cells) != len(headers):
            output.append(line)
            continue
        if not cells[verification_idx].strip():
            cells[verification_idx] = suggest(cells[type_idx], cells[labels_idx], cells[title_idx])
            changed = True
        output.append(join_cells(cells))

    if args.apply and changed:
        path.write_text("\n".join(output) + "\n", encoding="utf-8")
    print("applied" if args.apply and changed else "suggested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
