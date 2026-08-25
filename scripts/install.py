#!/usr/bin/env python3
"""Compatibility entry point delegating installation to publish_local.py."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def build_publish_command(repo_root: Path) -> list[str]:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    personal = Path(os.environ.get("MISSION_CENTER_PERSONAL_SKILL", codex_home / "skills" / "mission-center")).expanduser()
    marketplace = Path(os.environ.get("MISSION_CENTER_MARKETPLACE_PLUGIN", codex_home / "local-marketplaces" / "mission-center" / "plugins" / "mission-center")).expanduser()
    command = [
        sys.executable, str(repo_root / "scripts" / "publish_local.py"),
        "--repo", str(repo_root), "--personal-skill", str(personal),
        "--marketplace-plugin", str(marketplace), "--write",
    ]
    if os.environ.get("MISSION_CENTER_PUBLISH_REGISTER", "1") != "0":
        command.append("--register")
    return command


def install() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    completed = subprocess.run(build_publish_command(repo_root), check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(install())
