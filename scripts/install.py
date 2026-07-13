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
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    target_dir = codex_home / "skills" / "mission-center"

    print(f"Installing Codex Mission Center to: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    src_dir = repo_root / "skills" / "mission-center"

    if not src_dir.exists():
        print(f"Error: Required source directory {src_dir} does not exist.")
        sys.exit(1)

    shutil.copytree(src_dir, target_dir, dirs_exist_ok=True)
    print("Codex Mission Center installed successfully!")

if __name__ == "__main__":
    install()
