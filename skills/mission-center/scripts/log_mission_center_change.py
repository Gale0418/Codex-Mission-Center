#!/usr/bin/env python3
"""Record one compact MissionCenter activity event."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


ACTIVITY_HEADERS = ("- Activity log:", "- Activity log：", "- 活動紀錄:", "- 活動紀錄：")
ZH_MARKERS = ("# 專案", "# 進度", "# 任務", "# 快照", "- 目標:", "- 目標：")


def detect_workspace_language(root: Path) -> str:
    for name in ("project.md", "tasks.md", "progress.md", "snapshot.md"):
        candidate = root / name
        if not candidate.exists():
            continue
        text = candidate.read_text(encoding="utf-8")
        if any(marker in text for marker in ZH_MARKERS):
            return "zh-TW"
    return "en"


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
        language = detect_workspace_language(path.parent)
        heading = "# 專案\n\n" if language == "zh-TW" else "# Project\n\n"
        path.write_text(heading, encoding="utf-8")
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


def resolve_mission_file(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("--file must stay inside MissionCenter")
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("--file must stay inside MissionCenter") from exc
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--file", default="project.md")
    parser.add_argument("--change", required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--impact", default="")
    args = parser.parse_args()

    root = Path(args.workspace).resolve() / "MissionCenter"
    try:
        path = resolve_mission_file(root, args.file)
    except ValueError as exc:
        parser.error(str(exc))
    timestamp = datetime.now().isoformat(timespec="seconds")
    note = f"[{timestamp}] {args.change}"
    if args.reason:
        note += f" | reason: {args.reason}"
    if args.impact:
        note += f" | impact: {args.impact}"
    if path == (root / "project.md").resolve():
        if not path.exists():
            language = detect_workspace_language(root)
            heading = "# 專案\n\n- 活動紀錄:\n" if language == "zh-TW" else "# Project\n\n- Activity log:\n"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(heading, encoding="utf-8")
        from mission_maintenance import run_daily

        run_daily(root, note)
        print(root / "daily-log.md")
    else:
        append_block(path, note)
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
