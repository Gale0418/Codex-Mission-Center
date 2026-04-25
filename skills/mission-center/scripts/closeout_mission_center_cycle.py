#!/usr/bin/env python3
"""Write a MissionCenter closeout file from workspace summaries."""

from __future__ import annotations

import argparse
from pathlib import Path


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
    closeout = root / "closeout.md"
    content = f"""# Closeout

- Summary: {args.summary}
- Completed: {args.completed or 'None'}
- Unfinished: {args.unfinished or 'None'}
- Risks: {args.risks or 'None'}
- Smoke tests: {args.smoke_tests or 'None'}
- Retro: {args.retro or 'None'}
"""
    closeout.write_text(content, encoding="utf-8")
    print(closeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
