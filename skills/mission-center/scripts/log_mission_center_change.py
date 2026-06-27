#!/usr/bin/env python3
"""Append a timestamped activity note to a MissionCenter project file."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


ACTIVITY_HEADERS = ("- Activity log:", "- Activity log：", "- 活動紀錄:", "- 活動紀錄：")


def detect_project_header(text: str) -> str:
    if "# 專案" in text or "- 目標" in text or "- 活動紀錄" in text:
        return "專案"
    return "Project"


def detect_activity_header(text: str) -> str:
    for header in ACTIVITY_HEADERS:
        if header in text:
            return header
    return "- 活動紀錄:" if detect_project_header(text) == "專案" else "- Activity log:"


def append_block(path: Path, line: str) -> None:
    if not path.exists():
        path.write_text("# Project\n\n", encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    text = text.replace("- Activity log：", "- Activity log:")
    text = text.replace("- 活動紀錄：", "- 活動紀錄:")
    activity_header = detect_activity_header(text)
    if activity_header not in text:
        text = text.rstrip() + f"\n{activity_header}\n"
    lines = text.splitlines()
    output: list[str] = []
    inserted = False
    for current in lines:
        output.append(current)
        if current.strip() == activity_header and not inserted:
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
    append_block(path, note)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
