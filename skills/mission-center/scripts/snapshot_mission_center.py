#!/usr/bin/env python3
"""Create a reopenable MissionCenter snapshot."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


TEXT = {
    "en": {
        "title": "Snapshot",
        "captured_at": "Captured at",
        "project": "Project",
        "cycle": "Cycle",
        "goal": "Goal",
        "progress": "Progress",
        "active": "Active tasks",
        "blocked": "Blocked tasks",
        "decisions": "Recent decisions",
        "questions": "Open questions",
        "none": "None",
    },
    "zh-TW": {
        "title": "快照",
        "captured_at": "建立時間",
        "project": "專案",
        "cycle": "週期",
        "goal": "目標",
        "progress": "進度",
        "active": "進行中任務",
        "blocked": "阻塞任務",
        "decisions": "近期決策",
        "questions": "開放問題",
        "none": "無",
    },
}


def detect_language(root: Path) -> str:
    markers = ("# 專案", "# 進度", "# 任務", "- 目標:", "- 目標：")
    for name in ("project.md", "progress.md", "tasks.md"):
        path = root / name
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if any(marker in text for marker in markers):
                return "zh-TW"
    return "en"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--project", default="MissionCenter")
    parser.add_argument("--cycle", default="Unassigned")
    parser.add_argument("--goal", default="MissionCenter workspace")
    parser.add_argument("--progress", default="Unknown")
    parser.add_argument("--active", default="")
    parser.add_argument("--blocked", default="")
    parser.add_argument("--decisions", default="")
    parser.add_argument("--questions", default="")
    args = parser.parse_args()

    root = Path(args.workspace).resolve() / "MissionCenter"
    root.mkdir(parents=True, exist_ok=True)
    labels = TEXT[detect_language(root)]
    snapshot = root / "snapshot.md"
    now = datetime.now().isoformat(timespec="seconds")
    content = f"""# {labels['title']}

- {labels['captured_at']}: {now}
- {labels['project']}: {args.project}
- {labels['cycle']}: {args.cycle}
- {labels['goal']}: {args.goal}
- {labels['progress']}: {args.progress}
- {labels['active']}:
  - {args.active or labels['none']}
- {labels['blocked']}:
  - {args.blocked or labels['none']}
- {labels['decisions']}:
  - {args.decisions or labels['none']}
- {labels['questions']}:
  - {args.questions or labels['none']}
"""
    snapshot.write_text(content, encoding="utf-8")
    print(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
