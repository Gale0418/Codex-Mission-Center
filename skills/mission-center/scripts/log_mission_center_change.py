#!/usr/bin/env python3
"""Append a timestamped activity note to a MissionCenter project file."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


def append_block(path: Path, header: str, line: str) -> None:
    if not path.exists():
        path.write_text(f"# {header}\n\n", encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    if "Activity log:" not in text:
        text = text.rstrip() + "\n- Activity log:\n"
    lines = text.splitlines()
    output: list[str] = []
    inserted = False
    for idx, current in enumerate(lines):
        output.append(current)
        if current.strip() == "- Activity log:" and not inserted:
            output.append(f"  - {line}")
            inserted = True
    if not inserted:
        output.append(f"  - {line}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--file", default="project.md")
    parser.add_argument("--change", required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--impact", default="")
    args = parser.parse_args()

    root = Path(args.workspace).resolve() / "MissionCenter"
    path = root / args.file
    timestamp = datetime.now().isoformat(timespec="seconds")
    note = f"[{timestamp}] {args.change}"
    if args.reason:
        note += f" | reason: {args.reason}"
    if args.impact:
        note += f" | impact: {args.impact}"
    append_block(path, "Project", note)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
