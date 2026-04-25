#!/usr/bin/env python3
"""Create a MissionCenter workspace scaffold in the current directory."""

from __future__ import annotations

import argparse
from pathlib import Path


FILES = {
    "project.md": """# Project\n\n- Goal:\n- Cycle:\n- Labels:\n- Activity log:\n- Open comments:\n""",
    "progress.md": """# Progress\n\n- Project:\n- Objective:\n- Current status:\n- Milestone:\n- Progress bar: [----------] 0%\n- Active tasks:\n- Blocked by:\n- Next update:\n""",
    "tasks.md": """# Tasks\n\n| ID | Title | Type | Parent | Priority | Status | Owner | Depends on | Next action | Verification | Estimate | Labels | Comments |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n""",
    "smoke-tests.md": """# Smoke Tests\n\n| Date | Linked task ID | What was tested | How it was tested | Expected result | Observed result | Pass / fail | Run type |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n""",
    "decisions.md": """# Decisions\n\n- \n""",
    "notes.md": """# Notes\n\n- \n""",
    "closeout.md": """# Closeout\n\n- Summary:\n- Completed:\n- Unfinished:\n- Risks:\n- Smoke tests:\n- Retro:\n""",
    "snapshot.md": """# Snapshot\n\n- Captured at:\n- Project:\n- Cycle:\n- Goal:\n- Progress:\n- Active tasks:\n- Blocked tasks:\n- Recent decisions:\n- Open questions:\n""",
}


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
    args = parser.parse_args()

    root = Path(args.workspace).resolve()
    target = root / "MissionCenter"
    target.mkdir(parents=True, exist_ok=True)

    for name, content in FILES.items():
        path = target / name
        if path.exists() and not args.force:
            continue
        path.write_text(content, encoding="utf-8")

    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
