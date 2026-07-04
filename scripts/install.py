#!/usr/bin/env python3
"""
Installer script for Codex Mission Center.
"""

import os
import shutil
import sys
from pathlib import Path

def install():
    repo_root = Path(__file__).resolve().parent.parent
    target_dir = Path.home() / ".codex" / "skills" / "mission-center"

    print(f"Installing Codex Mission Center to: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    items_to_copy = [
        "SKILL.md",
        ".codex-plugin",
        "assets",
        "docs",
        "notes",
        "scripts",
        "skills",
    ]

    for item_name in items_to_copy:
        src = repo_root / item_name
        if src.exists():
            dst = target_dir / item_name
            print(f"  Copying {item_name} -> {dst}")
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

    print("Codex Mission Center installed successfully!")

if __name__ == "__main__":
    install()
