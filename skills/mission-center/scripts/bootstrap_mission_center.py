#!/usr/bin/env python3
"""Create a MissionCenter workspace scaffold in the current directory."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


FILES_EN = {
    "project.md": """# Project

- Goal:
- Cycle:
- Labels:
- Activity log:
- Open comments:
""",
    "progress.md": """# Progress

- Project:
- Objective:
- Current status:
- Milestone:
- Progress bar: [----------] 0%
- Active tasks:
- Blocked by:
- Next update:
""",
    "tasks.md": """# Tasks

| ID | Title | Type | Parent | Priority | Status | Owner | Depends on | Next action | Verification | Estimate | Labels | Comments |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
""",
    "smoke-tests.md": """# Smoke Tests

| Date | Linked task ID | What was tested | How it was tested | Expected result | Observed result | Pass / fail | Run type |
| --- | --- | --- | --- | --- | --- | --- | --- |
""",
    "decisions.md": """# Decisions

-
""",
    "notes.md": """# Notes

-
""",
    "closeout.md": """# Closeout

- Summary:
- Completed:
- Unfinished:
- Risks:
- Smoke tests:
- Retro:
""",
    "snapshot.md": """# Snapshot

- Captured at:
- Project:
- Cycle:
- Goal:
- Progress:
- Active tasks:
- Blocked tasks:
- Recent decisions:
- Open questions:
""",
    "visual-hub.md": """# Visual Hub

- Open HUD: `output/mission-center-assets/visual-summary.html`
- Current view: active helpers, task states, progress, and blockers
- Helper roster: auto-assigned by the visual panel
""",
}


FILES_ZH_TW = {
    "project.md": """# 專案

- 目標：
- 週期：
- 標籤：
- 活動紀錄：
- 開放問題：
""",
    "progress.md": """# 進度

- 專案：
- 目標：
- 目前狀態：
- 里程碑：
- 進度條：[----------] 0%
- 進行中任務：
- 阻塞原因：
- 下次更新：
""",
    "tasks.md": """# 任務

| ID | 標題 | 類型 | 父層 | 優先級 | 狀態 | 負責人 | 依賴 | 下一步 | 驗證方式 | 估時 | 標籤 | 備註 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
""",
    "smoke-tests.md": """# Smoke Tests

| 日期 | 對應任務 ID | 測試內容 | 測試方式 | 預期結果 | 實際結果 | 通過 / 失敗 | 類型 |
| --- | --- | --- | --- | --- | --- | --- | --- |
""",
    "decisions.md": """# 決策

-
""",
    "notes.md": """# 筆記

-
""",
    "closeout.md": """# 收尾

- 摘要：
- 已完成：
- 未完成：
- 風險：
- Smoke tests：
- 回顧：
""",
    "snapshot.md": """# 快照

- 建立時間：
- 專案：
- 週期：
- 目標：
- 進度：
- 進行中任務：
- 阻塞任務：
- 最近決策：
- 開放問題：
""",
    "visual-hub.md": """# 視覺 HUB

- 開啟 HUD：`output/mission-center-assets/visual-summary.html`
- 目前畫面：小人狀態、任務進度、阻塞項目與 active 清單
- 小人名冊：由視覺面板自動分配
""",
}


def choose_language(value: str) -> str:
    if value != "auto":
        return value
    locale = f"{os.environ.get('MISSION_CENTER_LANGUAGE', '')} {os.environ.get('LANG', '')}".lower()
    if "zh" in locale or "tw" in locale or "taiwan" in locale:
        return "zh-TW"
    return "en"


def copy_visual_assets(workspace_root: Path, force: bool) -> None:
    source = Path(__file__).resolve().parents[1] / "assets" / "visual-hub"
    if not source.exists():
        return

    target = workspace_root / "output" / "mission-center-assets"
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if not item.is_file():
            continue
        destination = target / item.name
        if destination.exists() and not force:
            continue
        shutil.copy2(item, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "workspace",
        nargs="?",
        default=".",
        help="Workspace root where MissionCenter should be created.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files.",
    )
    parser.add_argument(
        "--language",
        choices=("auto", "en", "zh-TW"),
        default="auto",
        help="Template language. Use zh-TW for Traditional Chinese workspaces.",
    )
    args = parser.parse_args()

    root = Path(args.workspace).resolve()
    target = root / "MissionCenter"
    target.mkdir(parents=True, exist_ok=True)
    files = FILES_ZH_TW if choose_language(args.language) == "zh-TW" else FILES_EN

    for name, content in files.items():
        path = target / name
        if path.exists() and not args.force:
            continue
        path.write_text(content, encoding="utf-8")

    copy_visual_assets(root, args.force)

    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
