#!/usr/bin/env python3
"""Write a MissionCenter closeout file from workspace summaries."""

from __future__ import annotations

import argparse
from pathlib import Path


TEXT = {
    "en": {
        "title": "Closeout",
        "summary": "Summary",
        "completed": "Completed",
        "unfinished": "Unfinished",
        "risks": "Risks",
        "smoke_tests": "Smoke tests",
        "retro": "Retro",
        "none": "None",
    },
    "zh-TW": {
        "title": "收尾",
        "summary": "摘要",
        "completed": "已完成",
        "unfinished": "未完成",
        "risks": "風險",
        "smoke_tests": "冒煙測試",
        "retro": "回顧",
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
    parser.add_argument("--summary", required=True)
    parser.add_argument("--completed", default="")
    parser.add_argument("--unfinished", default="")
    parser.add_argument("--risks", default="")
    parser.add_argument("--smoke-tests", default="")
    parser.add_argument("--retro", default="")
    args = parser.parse_args()

    root = Path(args.workspace).resolve() / "MissionCenter"
    root.mkdir(parents=True, exist_ok=True)
    labels = TEXT[detect_language(root)]
    closeout = root / "closeout.md"
    content = f"""# {labels['title']}

- {labels['summary']}: {args.summary}
- {labels['completed']}: {args.completed or labels['none']}
- {labels['unfinished']}: {args.unfinished or labels['none']}
- {labels['risks']}: {args.risks or labels['none']}
- {labels['smoke_tests']}: {args.smoke_tests or labels['none']}
- {labels['retro']}: {args.retro or labels['none']}
"""
    closeout.write_text(content, encoding="utf-8")
    print(closeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
