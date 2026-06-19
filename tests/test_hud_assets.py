import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1] / "skills" / "mission-center"


class HudAssetTests(unittest.TestCase):
    def test_html_has_no_placeholder_roster_or_smoketest_status(self):
        html = (
            ROOT / "assets" / "visual-hub" / "visual-summary.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn('name: "MissionHelper"', html)
        self.assertNotIn('"SmokeTest"', html)
        self.assertIn("const maxVisibleAgents = 15", html)

    def test_default_state_is_empty(self):
        state = json.loads(
            (ROOT / "assets" / "visual-hub" / "visual-state.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["agents"], [])

    def test_manual_updater_delegates_to_task_sync(self):
        script = (
            ROOT / "assets" / "visual-hub" / "update-visual-state.ps1"
        ).read_text(encoding="utf-8")
        self.assertNotIn("[string[]]$Agents", script)
        self.assertIn("sync_mission_center.py", script)


if __name__ == "__main__":
    unittest.main()
