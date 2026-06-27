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
        "research": "Research and scope",
        "milestone": "First verifiable milestone",
        "verification_closeout": "Verification and closeout",
        "research_next": "Research prior art and clarify scope",
        "research_done": "intake and research decisions approved",
        "milestone_next": "Detail the approved first milestone",
        "milestone_done": "milestone acceptance check passes",
        "verification_next": "Run verification and summarize outcomes",
        "clarify": "Clarify scope",
        "acceptance": "define acceptance",
        "recorded": "smoke tests recorded",
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
            "估時",
            "標籤",
            "備註",
        ],
        "research": "研究與範圍釐清",
        "milestone": "第一個可驗證里程碑",
        "verification_closeout": "驗證與收尾",
        "research_next": "研究既有方案並釐清範圍",
        "research_done": "需求與研究決策已核准",
        "milestone_next": "詳細拆解已核准的第一個里程碑",
        "milestone_done": "里程碑驗收檢查通過",
        "verification_next": "執行驗證並整理成果",
        "clarify": "釐清範圍",
        "acceptance": "定義驗收標準",
        "recorded": "smoke tests 已記錄",
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


def _extract_summary_value(line: str, label: str) -> str | None:
    stripped = line.strip()
    for marker in (f"- {label}:", f"- {label}："):
        if stripped.startswith(marker):
            return stripped.removeprefix(marker).strip()
    return None


def project_goal_is_blank(path: Path) -> bool:
    if not path.exists():
        return True
    for line in path.read_text(encoding="utf-8").splitlines():
        value = _extract_summary_value(line, "Goal")
        if value is not None:
            return not value
        value = _extract_summary_value(line, "目標")
        if value is not None:
            return not value
    return True


def tasks_file_is_placeholder(path: Path) -> bool:
    if not path.exists():
        return True
    non_empty = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(non_empty) != 3:
        return False
    titles = {f"# {TASK_LABELS['en']['tasks_title']}", f"# {TASK_LABELS['zh-TW']['tasks_title']}"}
    return non_empty[0] in titles and non_empty[1].startswith("|") and non_empty[2].startswith("|")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--project", default="MissionCenter")
    parser.add_argument("--cycle", default="Unassigned")
    parser.add_argument("--prefix", default="MC")
    parser.add_argument("--language", choices=("en", "zh-TW"), default="en")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    labels = TASK_LABELS[args.language]

    root = Path(args.workspace).resolve() / "MissionCenter"
    root.mkdir(parents=True, exist_ok=True)

    project = root / "project.md"
    if args.force or project_goal_is_blank(project):
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
        f"| {args.prefix}-E1 | {args.goal} | Epic |  | P0 | Backlog |  |  | {labels['clarify']} | {labels['acceptance']} | 8 | intake, plan |  |",
        f"| {args.prefix}-R1 | {labels['research']} | Task | {args.prefix}-E1 | P0 | Ready |  |  | {labels['research_next']} | {labels['research_done']} | 2 | intake, research |  |",
        f"| {args.prefix}-M1 | {labels['milestone']} | Task | {args.prefix}-E1 | P1 | Backlog |  | {args.prefix}-R1 | {labels['milestone_next']} | {labels['milestone_done']} | 5 | plan, execution |  |",
        f"| {args.prefix}-V1 | {labels['verification_closeout']} | Task | {args.prefix}-E1 | P1 | Backlog |  | {args.prefix}-M1 | {labels['verification_next']} | {labels['recorded']} | 3 | verification, closeout |  |",
    ]
    if args.force or tasks_file_is_placeholder(tasks):
        tasks.write_text("\n".join(lines) + "\n", encoding="utf-8")

    smoke_tests = root / "smoke-tests.md"
    if args.force or not smoke_tests.exists():
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
