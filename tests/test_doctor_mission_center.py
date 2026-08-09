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
            errors = inspect_workspace(workspace)
            self.assertTrue(any("Unsupported task status: Flying" in error for error in errors))
            self.assertFalse(any("focus.md does not match" in error for error in errors))

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

    def test_stale_materialized_view_fails(self):
        with workspace_tempdir("doctor-memory-stale-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            project = workspace / "MissionCenter" / "project.md"
            project.write_text(project.read_text(encoding="utf-8") + "\n- Changed: yes\n", encoding="utf-8")
            self.assertTrue(any("brief.md is stale" in error for error in inspect_workspace(workspace)))

    def test_focus_must_match_unfinished_p0(self):
        with workspace_tempdir("doctor-focus-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            focus = workspace / "MissionCenter" / "focus.md"
            focus.write_text(
                focus.read_text(encoding="utf-8")
                + "| FAKE | Wrong | Ready | Work | | test |\n",
                encoding="utf-8",
            )
            self.assertTrue(any("focus.md does not match" in error for error in inspect_workspace(workspace)))

    def test_guardrail_and_daily_log_schema_fail_closed(self):
        with workspace_tempdir("doctor-memory-schema-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            mission = workspace / "MissionCenter"
            guardrails = mission / "guardrails.md"
            guardrails.write_text(
                guardrails.read_text(encoding="utf-8")
                + "| bad | Huge | always | x | y | z | human | yesterday | Candidate |\n",
                encoding="utf-8",
            )
            daily = mission / "daily-log.md"
            daily.write_text("# Daily Log\n\n- Last organized: nope\n\n## 2026-99-99\n- bad\n", encoding="utf-8")
            errors = inspect_workspace(workspace)
            self.assertTrue(any("invalid ID" in error for error in errors))
            self.assertTrue(any("invalid status" in error for error in errors))
            self.assertTrue(any("Last organized" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
