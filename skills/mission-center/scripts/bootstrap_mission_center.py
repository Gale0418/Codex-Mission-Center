#!/usr/bin/env python3
"""Create a MissionCenter workspace scaffold in the current directory."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from workspace_contract import REQUIRED_FILES


FILES_EN = {
    "brief.md": "# Mission Brief\n\nGenerated after bootstrap.\n",
    "working-set.md": "# Active Working Set\n\nGenerated after bootstrap.\n",
    "critical-lessons.md": """# Critical Lessons

> Only recorded issues that have occurred, are likely to recur, and have verified solutions.
> Detailed evidence is stored in incidents/.
> Keep this file compact.

## Active Lessons

| ID | Applies when | Symptoms | Root cause | Correct action | Avoid | Verification | Incident | Last confirmed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Resolved Index

| ID | Status | Resolved by | Incident |
| --- | --- | --- | --- |
""",
    "guardrails.md": """# Guardrails

Automation must not add, promote, or retire guardrails without explicit human approval.

| ID | Severity | Applies when | Pitfall | Must follow | Verification | Source | Last confirmed | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
""",
    "daily-log.md": """# Daily Log

- Last organized: 1970-01-01
""",
    "project.md": """<!-- mission-center-managed-summary v=1 -->
# Project

- Goal:
- Cycle:
- Labels:
- Activity log:
- Open comments:
""",
    "progress.md": """<!-- mission-center-managed-summary v=1 -->
# Progress

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

## Research Log

| Pre-search idea | Source | Adopted insight | License status |
| --- | --- | --- | --- |
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
- Current view: task states, progress, and blockers
- Helper rule: one helper represents one task from `tasks.md`
""",
}


FILES_ZH_TW = {
    "brief.md": "# 任務簡報\n\nBootstrap 後產生。\n",
    "working-set.md": "# 當前工作集\n\nBootstrap 後產生。\n",
    "critical-lessons.md": """# 重大教訓

> 只收錄已發生、具有再次發生價值，且解法已有證據支持的重大問題。
> 詳細事故資料位於 incidents/。
> 此文件必須保持精簡。

## 主動教訓

| ID | 適用情境 | 症狀 | 根因 | 正確處理 | 禁止重犯 | 驗證方式 | Incident | 最後確認 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## 已解決索引

| ID | 狀態 | Resolved by | Incident |
| --- | --- | --- | --- |
""",
    "guardrails.md": """# 重要護欄

自動化不得新增、升格或停用護欄；變更必須經人工明確核准。

| ID | 嚴重度 | 適用情境 | 曾踩過的坑 | 必須遵守 | 驗證方式 | 來源 | 最後確認 | 狀態 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
""",
    "daily-log.md": """# 每日紀錄

- 最後整理：1970-01-01
""",
    "project.md": """<!-- mission-center-managed-summary v=1 -->
# 專案

- 目標：
- 週期：
- 標籤：
- 活動紀錄：
- 開放問題：
""",
    "progress.md": """<!-- mission-center-managed-summary v=1 -->
# 進度

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
    "smoke-tests.md": """# 冒煙測試

| 日期 | 對應任務 ID | 測試內容 | 測試方式 | 預期結果 | 實際結果 | 通過 / 失敗 | 類型 |
| --- | --- | --- | --- | --- | --- | --- | --- |
""",
    "decisions.md": """# 決策

-
""",
    "notes.md": """# 筆記

## 研究紀錄

| 搜尋前構想 | 參考來源 | 採納內容 | 授權狀態 |
| --- | --- | --- | --- |
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
- 目前畫面：任務狀態、進度與阻塞項目
- 小人規則：`tasks.md` 中一個小人代表一個任務
""",
}


if set(FILES_EN) != set(REQUIRED_FILES) or set(FILES_ZH_TW) != set(REQUIRED_FILES):
    raise RuntimeError("Bootstrap templates do not match the canonical workspace contract")


MANAGED_VISUAL_ASSETS = {
    "visual-summary.html",
    "mission-bridge-background.webp",
    "mission-bridge-background.webp.json",
    "mission-fleet-bridge-background.webp",
    "mission-fleet-bridge-background.webp.json",
    "mission-starfield.webp",
    "mission-starfield.webp.json",
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
        if item.name not in MANAGED_VISUAL_ASSETS or not item.is_file() or item.is_symlink():
            continue
        destination = target / item.name
        # Files shipped by the skill are the managed HUD surface.  Keep any
        # workspace-owned extras intact, but always synchronize these names so
        # canonical and served HTML/assets cannot drift after an upgrade.
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
    (target / "incidents").mkdir(parents=True, exist_ok=True)
    files = FILES_ZH_TW if choose_language(args.language) == "zh-TW" else FILES_EN

    for name, content in files.items():
        path = target / name
        if path.exists() and not args.force:
            continue
        path.write_text(content, encoding="utf-8")

    from mission_maintenance import INCIDENTS_README
    incident_readme = target / "incidents" / "README.md"
    if not incident_readme.exists() or args.force:
        incident_readme.write_text(INCIDENTS_README, encoding="utf-8")

    copy_visual_assets(root, args.force)

    # Materialized views are generated from canonical files, never hand-maintained.
    from mission_maintenance import run_sync

    run_sync(target)

    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
