#!/usr/bin/env python3
"""Create a MissionCenter workspace scaffold in the current directory."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


FILES_EN = {
    "project.md": """# Project\n\n- Goal:\n- Cycle:\n- Labels:\n- Activity log:\n- Open comments:\n""",
    "progress.md": """# Progress\n\n- Project:\n- Objective:\n- Current status:\n- Milestone:\n- Progress bar: [----------] 0%\n- Active tasks:\n- Blocked by:\n- Next update:\n""",
    "tasks.md": """# Tasks\n\n| ID | Title | Type | Parent | Priority | Status | Owner | Depends on | Next action | Verification | Estimate | Labels | Comments |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n""",
    "smoke-tests.md": """# Smoke Tests\n\n| Date | Linked task ID | What was tested | How it was tested | Expected result | Observed result | Pass / fail | Run type |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n""",
    "decisions.md": """# Decisions\n\n- \n""",
    "notes.md": """# Notes\n\n- \n""",
    "closeout.md": """# Closeout\n\n- Summary:\n- Completed:\n- Unfinished:\n- Risks:\n- Smoke tests:\n- Retro:\n""",
    "snapshot.md": """# Snapshot\n\n- Captured at:\n- Project:\n- Cycle:\n- Goal:\n- Progress:\n- Active tasks:\n- Blocked tasks:\n- Recent decisions:\n- Open questions:\n""",
}

FILES_ZH_TW = {
    "project.md": """# 專案\n\n- 目標：\n- 週期：\n- 標籤：\n- 活動紀錄：\n- 開放留言：\n""",
    "progress.md": """# 進度\n\n- 專案：\n- 目前目標：\n- 目前狀態：\n- 里程碑：\n- 進度條：[----------] 0%\n- 進行中任務：\n- 阻塞原因：\n- 下次更新：\n""",
    "tasks.md": """# 任務\n\n| ID | 標題 | 類型 | 上層 | 優先級 | 狀態 | 負責人 | 依賴 | 下一步 | 驗證方式 | 估算 | 標籤 | 備註 |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n""",
    "smoke-tests.md": """# Smoke Tests\n\n| 日期 | 關聯任務 ID | 測試內容 | 測試方式 | 預期結果 | 實際結果 | 通過 / 失敗 | 執行類型 |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n""",
    "decisions.md": """# 決策紀錄\n\n- \n""",
    "notes.md": """# 筆記\n\n- \n""",
    "closeout.md": """# 收尾\n\n- 摘要：\n- 已完成：\n- 未完成：\n- 風險：\n- Smoke tests：\n- 回顧：\n""",
    "snapshot.md": """# 快照\n\n- 建立時間：\n- 專案：\n- 週期：\n- 目標：\n- 進度：\n- 進行中任務：\n- 阻塞任務：\n- 最近決策：\n- 開放問題：\n""",
}


def choose_language(value: str) -> str:
    if value != "auto":
        return value
    locale = f"{os.environ.get('MISSION_CENTER_LANGUAGE', '')} {os.environ.get('LANG', '')}".lower()
    if "zh" in locale or "tw" in locale or "taiwan" in locale:
        return "zh-TW"
    return "en"


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

    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
