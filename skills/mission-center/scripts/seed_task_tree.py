#!/usr/bin/env python3
"""Seed a MissionCenter task tree from a goal."""

from __future__ import annotations

import argparse
from pathlib import Path


TASK_LABELS = {
    "en": {
        "project_title": "Project",
        "tasks_title": "Tasks",
        "smoke_title": "Smoke Tests",
        "goal": "Goal",
        "cycle": "Cycle",
        "labels": "Labels",
        "activity_log": "Activity log",
        "seeded": "Seeded from goal.",
        "open_comments": "Open comments",
        "none": "None",
        "columns": [
            "ID",
            "Title",
            "Type",
            "Parent",
            "Priority",
            "Status",
            "Owner",
            "Depends on",
            "Next action",
            "Verification",
            "SmokeTest",
            "Review",
            "Estimate",
            "Labels",
            "Comments",
        ],
        "folder_check": "MissionCenter folder created",
        "hub": "Visual hub link",
        "tree": "Task tree and dependencies",
        "bugloop": "Repeat bug-fix loop",
        "smoke": "Smoke tests",
        "intake": "Intake and clarification",
        "workspace": "Workspace setup",
        "slices": "Execution slices",
        "closeout": "Closeout and retro",
        "clarify": "Clarify scope",
        "acceptance": "define acceptance",
        "ask": "Ask questions until scope is clear",
        "checklist": "intake checklist complete",
        "create": "Create MissionCenter files",
        "bootstrap": "bootstrap script run",
        "seed": "Seed initial child tasks",
        "visible": "task tree visible",
        "split": "Split into bounded slices",
        "each": "each slice has smoke test",
        "add": "Add reproducible verifications",
        "recorded": "smoke tests recorded",
        "summarize": "Summarize outcomes",
        "written": "closeout written",
        "smoke_columns": [
            "Date",
            "Linked task ID",
            "What was tested",
            "How it was tested",
            "Expected result",
            "Observed result",
            "Pass / fail",
            "Run type",
        ],
    },
    "zh-TW": {
        "project_title": "專案",
        "tasks_title": "任務",
        "smoke_title": "Smoke Tests",
        "goal": "目標",
        "cycle": "週期",
        "labels": "標籤",
        "activity_log": "活動紀錄",
        "seeded": "已依目標建立初始任務樹。",
        "open_comments": "開放問題",
        "none": "無",
        "columns": [
            "ID",
            "標題",
            "類型",
            "父層",
            "優先級",
            "狀態",
            "負責人",
            "依賴",
            "下一步",
            "驗證方式",
            "SmokeTest",
            "Review",
            "估時",
            "標籤",
            "備註",
        ],
        "folder_check": "MissionCenter 資料夾建立",
        "hub": "視覺 HUB 連結",
        "tree": "任務樹與依賴關係",
        "bugloop": "重複除 BUG 流程",
        "smoke": "Smoke tests",
        "intake": "需求訪談與釐清",
        "workspace": "任務中心初始化",
        "slices": "執行切片",
        "closeout": "收尾與回顧",
        "clarify": "釐清範圍",
        "acceptance": "定義驗收標準",
        "ask": "持續提問直到範圍清楚",
        "checklist": "需求訪談清單完成",
        "create": "建立 MissionCenter 檔案",
        "bootstrap": "bootstrap 腳本已執行",
        "seed": "建立初始子任務",
        "visible": "任務樹可讀且可追蹤",
        "split": "拆成可執行的小切片",
        "each": "每個切片都有 smoke test",
        "add": "加入可重複驗證方式",
        "recorded": "smoke tests 已記錄",
        "summarize": "整理成果與剩餘風險",
        "written": "收尾文件已完成",
        "smoke_columns": [
            "日期",
            "對應任務 ID",
            "測試內容",
            "測試方式",
            "預期結果",
            "實際結果",
            "通過 / 失敗",
            "類型",
        ],
    },
}


def table_header(columns: list[str]) -> list[str]:
    return [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--project", default="MissionCenter")
    parser.add_argument("--cycle", default="Unassigned")
    parser.add_argument("--prefix", default="MC")
    parser.add_argument("--language", choices=("en", "zh-TW"), default="en")
    args = parser.parse_args()
    labels = TASK_LABELS[args.language]

    root = Path(args.workspace).resolve() / "MissionCenter"
    root.mkdir(parents=True, exist_ok=True)

    project = root / "project.md"
    if not project.exists():
        project.write_text(
            f"# {labels['project_title']}\n\n"
            f"- {labels['goal']}: {args.goal}\n"
            f"- {labels['cycle']}: {args.cycle}\n"
            f"- {labels['labels']}: intake, plan, execution, verification\n"
            f"- {labels['activity_log']}:\n"
            f"  - {labels['seeded']}\n"
            f"- {labels['open_comments']}:\n"
            f"  - {labels['none']}\n",
            encoding="utf-8",
        )

    tasks = root / "tasks.md"
    lines = [
        f"# {labels['tasks_title']}",
        "",
        *table_header(labels["columns"]),
        f"| {args.prefix}-E1 | {args.goal} | Epic |  | P0 | Backlog |  |  | {labels['clarify']} | {labels['acceptance']} | NO | NO | 8 | intake, plan |  |",
        f"| {args.prefix}-P0-1 | {labels['folder_check']} | Task | {args.prefix}-E1 | P0 | Ready |  |  | {labels['create']} | bootstrap script run | NO | NO | 1 | intake |  |",
        f"| {args.prefix}-P0-2 | {labels['hub']} | Task | {args.prefix}-E1 | P0 | Ready |  | {args.prefix}-P0-1 | {labels['create']} | hub file visible | NO | NO | 1 | plan |  |",
        f"| {args.prefix}-P0-3 | {labels['tree']} | Task | {args.prefix}-E1 | P0 | Ready |  | {args.prefix}-P0-2 | {labels['seed']} | task tree visible | NO | NO | 2 | plan |  |",
        f"| {args.prefix}-P0-4 | {labels['bugloop']} | Task | {args.prefix}-E1 | P0 | Ready |  | {args.prefix}-P0-3 | {labels['split']} | fixed after review | NO | NO | 2 | execution |  |",
        f"| {args.prefix}-P0-5 | {labels['smoke']} | Task | {args.prefix}-E1 | P0 | Ready |  | {args.prefix}-P0-4 | {labels['add']} | smoke tests recorded | NO | NO | 2 | verification |  |",
        f"| {args.prefix}-T1 | {labels['intake']} | Task | {args.prefix}-E1 | P1 | Backlog |  | {args.prefix}-P0-5 | {labels['ask']} | {labels['checklist']} | NO | NO | 2 | intake |  |",
        f"| {args.prefix}-T2 | {labels['workspace']} | Task | {args.prefix}-E1 | P2 | Backlog |  | {args.prefix}-T1 | {labels['create']} | {labels['bootstrap']} | NO | NO | 2 | plan |  |",
        f"| {args.prefix}-T3 | {labels['tree']} | Task | {args.prefix}-E1 | P2 | Backlog |  | {args.prefix}-T2 | {labels['seed']} | {labels['visible']} | NO | NO | 3 | plan |  |",
        f"| {args.prefix}-T4 | {labels['slices']} | Task | {args.prefix}-E1 | P1 | Backlog |  | {args.prefix}-T3 | {labels['split']} | {labels['each']} | NO | NO | 5 | execution |  |",
        f"| {args.prefix}-T5 | {labels['smoke']} | Task | {args.prefix}-E1 | P1 | Backlog |  | {args.prefix}-T4 | {labels['add']} | {labels['recorded']} | NO | NO | 3 | verification |  |",
        f"| {args.prefix}-T6 | {labels['closeout']} | Task | {args.prefix}-E1 | P2 | Backlog |  | {args.prefix}-T5 | {labels['summarize']} | {labels['written']} | NO | NO | 2 | closeout |  |",
    ]
    tasks.write_text("\n".join(lines) + "\n", encoding="utf-8")

    smoke_tests = root / "smoke-tests.md"
    if not smoke_tests.exists():
        smoke_tests.write_text(
            f"# {labels['smoke_title']}\n\n"
            + "\n".join(table_header(labels["smoke_columns"]))
            + "\n|  |  |  |  |  |  |  | manual |\n",
            encoding="utf-8",
        )

    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
