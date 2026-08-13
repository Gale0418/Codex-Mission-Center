import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "demo-workspace"
sys.path.insert(0, str(SCRIPTS))

from doctor_mission_center import inspect_workspace, inspect_workspace_report


class DoctorMissionCenterTests(unittest.TestCase):
    def copy_fixture(self, root: Path) -> Path:
        workspace = root / "workspace"
        shutil.copytree(FIXTURE, workspace)
        return workspace

    def test_valid_demo_workspace_has_no_errors(self):
        with workspace_tempdir("doctor-valid-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            self.assertEqual(inspect_workspace(workspace), [])

    def test_bootstrap_empty_working_set_without_table_is_valid(self):
        with workspace_tempdir("doctor-empty-working-set-") as temporary:
            workspace = Path(temporary) / "workspace"
            for script, extra_args in (
                ("bootstrap_mission_center.py", ["--language", "zh-TW"]),
                ("normalize_mission_center.py", []),
                ("sync_mission_center.py", []),
            ):
                subprocess.run(
                    [sys.executable, str(SCRIPTS / script), str(workspace), *extra_args],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
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

    def test_explicit_legacy_done_audit_is_warning_not_fabricated_pass(self):
        with workspace_tempdir("doctor-legacy-done-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            mission = workspace / "MissionCenter"
            smoke = mission / "smoke-tests.md"
            smoke.write_text(
                smoke.read_text(encoding="utf-8").replace("| 通過 |", "| 失敗 |"),
                encoding="utf-8",
            )
            (mission / "legacy-done-audit.json").write_text(
                '{\n'
                '  "schemaVersion": "1.0",\n'
                '  "recordedAt": "2026-08-12",\n'
                '  "reason": "Imported before smoke evidence enforcement; no pass was fabricated.",\n'
                '  "taskIds": ["DEMO-003"]\n'
                '}\n',
                encoding="utf-8",
            )

            errors, warnings = inspect_workspace_report(workspace)

            self.assertEqual(errors, [])
            self.assertTrue(any("DEMO-003" in warning for warning in warnings))
            self.assertFalse(any("passing smoke-test" in warning for warning in warnings))

    def test_legacy_done_audit_rejects_unknown_or_non_done_tasks(self):
        with workspace_tempdir("doctor-invalid-legacy-done-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            mission = workspace / "MissionCenter"
            (mission / "legacy-done-audit.json").write_text(
                '{"schemaVersion":"1.0","recordedAt":"2026-08-12",'
                '"reason":"migration","taskIds":["UNKNOWN","DEMO-001"]}\n',
                encoding="utf-8",
            )

            errors, _ = inspect_workspace_report(workspace)

            self.assertTrue(any("UNKNOWN" in error for error in errors))
            self.assertTrue(any("DEMO-001" in error for error in errors))

    def test_stale_progress_fails(self):
        with workspace_tempdir("doctor-progress-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            progress = workspace / "MissionCenter" / "progress.md"
            progress.write_text(
                "<!-- mission-center-managed-summary v=1 -->\n"
                "# 進度\n\n- 進度條：[----------] 0%\n",
                encoding="utf-8",
            )
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

    def test_smoke_rows_require_known_task_and_valid_result(self):
        with workspace_tempdir("doctor-smoke-contract-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            smoke = workspace / "MissionCenter" / "smoke-tests.md"
            smoke.write_text(
                "| Linked task ID | How it was tested | Expected result | Observed result | Pass / fail |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| UNKNOWN | command | succeeds | succeeds | maybe |\n",
                encoding="utf-8",
            )
            errors = inspect_workspace(workspace)
            self.assertTrue(any("unknown task UNKNOWN" in error for error in errors))
            self.assertTrue(any("invalid pass/fail result" in error for error in errors))

    def test_passing_smoke_row_requires_action_expected_and_observed(self):
        with workspace_tempdir("doctor-smoke-evidence-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            smoke = workspace / "MissionCenter" / "smoke-tests.md"
            smoke.write_text(
                "| Linked task ID | How it was tested | Expected result | Observed result | Pass / fail |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| DEMO-003 |  |  |  | pass |\n",
                encoding="utf-8",
            )
            errors = inspect_workspace(workspace)
            self.assertTrue(any("passing result requires" in error for error in errors))

    def test_legacy_empty_seed_smoke_row_is_a_warning(self):
        with workspace_tempdir("doctor-smoke-legacy-row-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            smoke = workspace / "MissionCenter" / "smoke-tests.md"
            smoke.write_text(
                "| Linked task ID | How it was tested | Expected result | Observed result | Pass / fail | Run type |\n"
                "| --- | --- | --- | --- | --- | --- |\n"
                "|  |  |  |  |  | manual |\n",
                encoding="utf-8",
            )
            _, warnings = inspect_workspace_report(workspace)
            self.assertTrue(any("legacy empty seed row" in warning for warning in warnings))

if __name__ == "__main__":
    unittest.main()
