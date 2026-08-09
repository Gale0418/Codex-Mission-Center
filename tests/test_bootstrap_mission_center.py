import subprocess
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
BOOTSTRAP = SCRIPTS / "bootstrap_mission_center.py"
sys.path.insert(0, str(SCRIPTS))

from workspace_contract import REQUIRED_FILES


class BootstrapMissionCenterTests(unittest.TestCase):
    def test_workspace_named_missioncenter_still_creates_nested_contract(self):
        with workspace_tempdir("bootstrap-name-") as temporary:
            workspace = Path(temporary) / "MissionCenter"
            result = subprocess.run(
                [sys.executable, str(BOOTSTRAP), str(workspace), "--language", "en"],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            target = workspace / "MissionCenter"
            self.assertTrue((target / "brief.md").is_file())
            self.assertTrue((target / "focus.md").is_file())

    def test_both_languages_create_exact_canonical_file_set(self):
        with workspace_tempdir("bootstrap-contract-") as temporary:
            root = Path(temporary)
            for language in ("en", "zh-TW"):
                workspace = root / language
                result = subprocess.run(
                    [sys.executable, str(BOOTSTRAP), str(workspace), "--language", language],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                actual = {
                    path.name
                    for path in (workspace / "MissionCenter").iterdir()
                    if path.is_file()
                }
                self.assertEqual(actual, set(REQUIRED_FILES))

    def test_language_templates_are_not_silently_interchanged(self):
        with workspace_tempdir("bootstrap-language-") as temporary:
            root = Path(temporary)
            subprocess.run(
                [sys.executable, str(BOOTSTRAP), str(root / "en"), "--language", "en"],
                check=True,
            )
            subprocess.run(
                [sys.executable, str(BOOTSTRAP), str(root / "zh"), "--language", "zh-TW"],
                check=True,
            )
            headings = {
                "en": {
                    "project.md": "# Project",
                    "progress.md": "# Progress",
                    "tasks.md": "# Tasks",
                    "decisions.md": "# Decisions",
                    "smoke-tests.md": "# Smoke Tests",
                    "notes.md": "# Notes",
                    "snapshot.md": "# Snapshot",
                    "closeout.md": "# Closeout",
                    "visual-hub.md": "# Visual Hub",
                },
                "zh": {
                    "project.md": "# 專案",
                    "progress.md": "# 進度",
                    "tasks.md": "# 任務",
                    "decisions.md": "# 決策",
                    "smoke-tests.md": "# 冒煙測試",
                    "notes.md": "# 筆記",
                    "snapshot.md": "# 快照",
                    "closeout.md": "# 收尾",
                    "visual-hub.md": "# 視覺 HUB",
                },
            }
            for language, expected in headings.items():
                for name, heading in expected.items():
                    self.assertTrue(
                        (root / language / "MissionCenter" / name)
                        .read_text(encoding="utf-8")
                        .startswith(heading),
                        f"{language}/{name} should begin with {heading}",
                    )


if __name__ == "__main__":
    unittest.main()
