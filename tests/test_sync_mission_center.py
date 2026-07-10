import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
SYNC = SCRIPTS / "sync_mission_center.py"
FIXTURE = ROOT / "tests" / "fixtures" / "demo-workspace"
sys.path.insert(0, str(SCRIPTS))

from sync_mission_center import compute_progress


class SyncMissionCenterTests(unittest.TestCase):
    def test_sync_writes_visual_state_json(self):
        with workspace_tempdir("sync-state-") as temporary:
            workspace = Path(temporary) / "workspace"
            shutil.copytree(FIXTURE, workspace)
            result = subprocess.run(
                [sys.executable, str(SYNC), str(workspace), "--goal", "Demo"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            state_path = workspace / "output" / "mission-center-assets" / "visual-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["goal"], "Demo")
            self.assertEqual(
                [agent["id"] for agent in state["agents"]],
                ["DEMO-001", "DEMO-002", "DEMO-003"],
            )

    def test_progress_uses_estimates_when_present(self):
        percent, mode, _, _ = compute_progress(
            [
                {"ID": "T1", "Title": "完成", "Status": "Done", "Estimate": "3"},
                {"ID": "T2", "Title": "進行", "Status": "In Progress", "Estimate": "1"},
            ]
        )
        self.assertEqual(percent, 75)
        self.assertEqual(mode, "3/4 estimated")

    def test_progress_falls_back_to_task_count_without_estimates(self):
        percent, mode, _, _ = compute_progress(
            [
                {"ID": "T1", "Title": "完成", "Status": "Done", "Estimate": ""},
                {"ID": "T2", "Title": "待辦", "Status": "Backlog", "Estimate": ""},
            ]
        )
        self.assertEqual(percent, 50)
        self.assertEqual(mode, "1/2 tasks")


if __name__ == "__main__":
    unittest.main()
