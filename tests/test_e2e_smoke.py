#!/usr/bin/env python3
"""
Python E2E Smoke Integration Test for Codex Mission Center.
"""

import unittest
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parent.parent

class TestMissionCenterE2ESmoke(unittest.TestCase):
    def test_scripts_exist(self):
        scripts_dir = repo_root / "skills" / "mission-center" / "scripts"
        self.assertTrue((scripts_dir / "bootstrap_mission_center.py").exists(),
                        f"bootstrap_mission_center.py not found at {scripts_dir}")
        self.assertTrue((scripts_dir / "normalize_mission_center.py").exists(),
                        f"normalize_mission_center.py not found at {scripts_dir}")
        self.assertTrue((scripts_dir / "sync_mission_center.py").exists(),
                        f"sync_mission_center.py not found at {scripts_dir}")

    def test_hud_assets_exist(self):
        visual_hub = repo_root / "skills" / "mission-center" / "assets" / "visual-hub"
        self.assertTrue((visual_hub / "visual-summary.html").exists(),
                        f"visual-summary.html not found at {visual_hub}")

if __name__ == "__main__":
    unittest.main()
