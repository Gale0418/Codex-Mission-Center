#!/usr/bin/env python3
"""Seed a MissionCenter task tree from a goal."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", nargs="?", default=".")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--project", default="MissionCenter")
    parser.add_argument("--cycle", default="Unassigned")
    parser.add_argument("--prefix", default="MC")
    args = parser.parse_args()

    root = Path(args.workspace).resolve() / "MissionCenter"
    root.mkdir(parents=True, exist_ok=True)

    project = root / "project.md"
    if not project.exists():
        project.write_text(
            f"# Project\n\n- Goal: {args.goal}\n- Cycle: {args.cycle}\n- Labels: intake, plan, execution, verification\n- Activity log:\n  - Seeded from goal.\n- Open comments:\n  - None\n",
            encoding="utf-8",
        )

    tasks = root / "tasks.md"
    lines = [
        "# Tasks",
        "",
        "| ID | Title | Type | Parent | Priority | Status | Owner | Depends on | Next action | Verification | Estimate | Labels | Comments |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        f"| {args.prefix}-E1 | {args.goal} | Epic |  | P1 | Backlog |  |  | Clarify scope | define acceptance | 8 | intake, plan |  |",
        f"| {args.prefix}-T1 | Intake and clarification | Task | {args.prefix}-E1 | P1 | Ready |  |  | Ask questions until scope is clear | intake checklist complete | 2 | intake |  |",
        f"| {args.prefix}-T2 | Workspace setup | Task | {args.prefix}-E1 | P2 | Backlog |  | {args.prefix}-T1 | Create MissionCenter files | bootstrap script run | 2 | plan |  |",
        f"| {args.prefix}-T3 | Task tree and dependencies | Task | {args.prefix}-E1 | P2 | Backlog |  | {args.prefix}-T2 | Seed initial child tasks | task tree visible | 3 | plan |  |",
        f"| {args.prefix}-T4 | Execution slices | Task | {args.prefix}-E1 | P1 | Backlog |  | {args.prefix}-T3 | Split into bounded slices | each slice has smoke test | 5 | execution |  |",
        f"| {args.prefix}-T5 | Smoke tests | Task | {args.prefix}-E1 | P1 | Backlog |  | {args.prefix}-T4 | Add reproducible verifications | smoke tests recorded | 3 | verification |  |",
        f"| {args.prefix}-T6 | Closeout and retro | Task | {args.prefix}-E1 | P2 | Backlog |  | {args.prefix}-T5 | Summarize outcomes | closeout written | 2 | closeout |  |",
    ]
    tasks.write_text("\n".join(lines) + "\n", encoding="utf-8")

    smoke_tests = root / "smoke-tests.md"
    if not smoke_tests.exists():
        smoke_tests.write_text(
            "# Smoke Tests\n\n| Date | Linked task ID | What was tested | How it was tested | Expected result | Observed result | Pass / fail | Run type |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n|  |  |  |  |  |  |  | manual |\n",
            encoding="utf-8",
        )

    print(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
