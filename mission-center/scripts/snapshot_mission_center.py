#!/usr/bin/env python3
"""Create a reopenable MissionCenter snapshot."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path


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
    snapshot = root / "snapshot.md"
    now = datetime.now().isoformat(timespec="seconds")
    content = f"""# Snapshot

- Captured at: {now}
- Project: {args.project}
- Cycle: {args.cycle}
- Goal: {args.goal}
- Progress: {args.progress}
- Active tasks:
  - {args.active or 'None'}
- Blocked tasks:
  - {args.blocked or 'None'}
- Recent decisions:
  - {args.decisions or 'None'}
- Open questions:
  - {args.questions or 'None'}
"""
    snapshot.write_text(content, encoding="utf-8")
    print(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
