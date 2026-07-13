import shutil
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "demo-workspace"
sys.path.insert(0, str(SCRIPTS))

from doctor_mission_center import inspect_workspace


class DoctorMissionCenterTests(unittest.TestCase):
    def copy_fixture(self, root: Path) -> Path:
        workspace = root / "workspace"
        shutil.copytree(FIXTURE, workspace)
        return workspace

    def test_valid_demo_workspace_has_no_errors(self):
        with workspace_tempdir("doctor-valid-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            self.assertEqual(inspect_workspace(workspace), [])

    def test_missing_required_file_fails(self):
        with workspace_tempdir("doctor-missing-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            (workspace / "MissionCenter" / "decisions.md").unlink()
            self.assertIn("Missing required file: decisions.md", inspect_workspace(workspace))

    def test_invalid_status_fails(self):
        with workspace_tempdir("doctor-status-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            tasks = workspace / "MissionCenter" / "tasks.md"
            tasks.write_text(
                tasks.read_text(encoding="utf-8").replace("In Progress", "Flying"),
                encoding="utf-8",
            )
            self.assertTrue(
                any("Unsupported task status: Flying" in error for error in inspect_workspace(workspace))
            )

    def test_done_task_requires_passing_smoke_test(self):
        with workspace_tempdir("doctor-smoke-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            smoke = workspace / "MissionCenter" / "smoke-tests.md"
            smoke.write_text("# 冒煙測試\n", encoding="utf-8")
            self.assertTrue(
                any("Done task DEMO-003" in error for error in inspect_workspace(workspace))
            )

    def test_stale_progress_fails(self):
        with workspace_tempdir("doctor-progress-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            progress = workspace / "MissionCenter" / "progress.md"
            progress.write_text("# 進度\n\n- 進度條：[----------] 0%\n", encoding="utf-8")
            self.assertTrue(
                any("progress.md is stale" in error for error in inspect_workspace(workspace))
            )

    def test_malformed_task_row_is_reported(self):
        with workspace_tempdir("doctor-malformed-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            tasks = workspace / "MissionCenter" / "tasks.md"
            tasks.write_text(
                tasks.read_text(encoding="utf-8") + "| BROKEN | too few cells |\n",
                encoding="utf-8",
            )
            self.assertTrue(
                any("has 2 cells; expected" in error for error in inspect_workspace(workspace))
            )


if __name__ == "__main__":
    unittest.main()
