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
            "Estimate",
            "Labels",
            "Comments",
        ],
        "intake": "Intake and clarification",
        "workspace": "Workspace setup",
        "tree": "Task tree and dependencies",
        "slices": "Execution slices",
        "smoke": "Smoke tests",
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
        "seeded": "已依照目標建立初始任務樹。",
        "open_comments": "開放留言",
        "none": "無",
        "columns": [
            "ID",
            "標題",
            "類型",
            "上層",
            "優先級",
            "狀態",
            "負責人",
            "依賴",
            "下一步",
            "驗證方式",
            "估算",
            "標籤",
            "備註",
        ],
        "intake": "需求訪談與釐清",
        "workspace": "任務中心工作區建立",
        "tree": "任務樹與依賴整理",
        "slices": "執行切片",
        "smoke": "Smoke tests",
        "closeout": "收尾與回顧",
        "clarify": "釐清範圍",
        "acceptance": "定義驗收標準",
        "ask": "持續提問直到範圍清楚",
        "checklist": "完成需求訪談檢查",
        "create": "建立 MissionCenter 文件",
        "bootstrap": "已執行 bootstrap 腳本",
        "seed": "建立初始子任務",
        "visible": "任務樹可讀且可追蹤",
        "split": "拆成可執行的小切片",
        "each": "每個切片都有 smoke test",
        "add": "加入可重複驗證方式",
        "recorded": "已記錄 smoke tests",
        "summarize": "整理成果與剩餘事項",
        "written": "已完成收尾文件",
        "smoke_columns": [
            "日期",
            "關聯任務 ID",
            "測試內容",
            "測試方式",
            "預期結果",
            "實際結果",
            "通過 / 失敗",
            "執行類型",
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
        f"| {args.prefix}-E1 | {args.goal} | Epic |  | P1 | Backlog |  |  | {labels['clarify']} | {labels['acceptance']} | 8 | intake, plan |  |",
        f"| {args.prefix}-T1 | {labels['intake']} | Task | {args.prefix}-E1 | P1 | Ready |  |  | {labels['ask']} | {labels['checklist']} | 2 | intake |  |",
        f"| {args.prefix}-T2 | {labels['workspace']} | Task | {args.prefix}-E1 | P2 | Backlog |  | {args.prefix}-T1 | {labels['create']} | {labels['bootstrap']} | 2 | plan |  |",
        f"| {args.prefix}-T3 | {labels['tree']} | Task | {args.prefix}-E1 | P2 | Backlog |  | {args.prefix}-T2 | {labels['seed']} | {labels['visible']} | 3 | plan |  |",
        f"| {args.prefix}-T4 | {labels['slices']} | Task | {args.prefix}-E1 | P1 | Backlog |  | {args.prefix}-T3 | {labels['split']} | {labels['each']} | 5 | execution |  |",
        f"| {args.prefix}-T5 | {labels['smoke']} | Task | {args.prefix}-E1 | P1 | Backlog |  | {args.prefix}-T4 | {labels['add']} | {labels['recorded']} | 3 | verification |  |",
        f"| {args.prefix}-T6 | {labels['closeout']} | Task | {args.prefix}-E1 | P2 | Backlog |  | {args.prefix}-T5 | {labels['summarize']} | {labels['written']} | 2 | closeout |  |",
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
