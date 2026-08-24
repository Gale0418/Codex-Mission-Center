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
from reconcile_mission_center import reconcile_workspace


class ReconcileMissionCenterTests(unittest.TestCase):
    def copy_fixture(self, root: Path) -> Path:
        workspace = root / "workspace"
        shutil.copytree(FIXTURE, workspace)
        return workspace

    @staticmethod
    def checks(result: dict) -> dict[str, dict]:
        return {check["name"]: check for check in result["checks"]}

    def test_valid_workspace_reconciles_without_writing(self):
        with workspace_tempdir("reconcile-valid-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            before = {
                path: path.read_bytes()
                for path in (workspace / "MissionCenter").iterdir()
                if path.is_file()
            }
            result = reconcile_workspace(workspace)
            after = {path: path.read_bytes() for path in before}

            checks = self.checks(result)
            self.assertEqual(checks["ledger"]["status"], "unknown")
            self.assertEqual(checks["progress"]["status"], "pass")
            self.assertEqual(checks["closeout"]["status"], "pass")
            self.assertEqual(checks["derived_source"]["status"], "pass")
            self.assertEqual(before, after)
            self.assertEqual(result["readOnly"], True)

    def test_corrupt_ledger_is_reported_and_doctor_hard_fails(self):
        with workspace_tempdir("reconcile-ledger-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            (workspace / "MissionCenter" / "execution-ledger.jsonl").write_text(
                "{not json}\n", encoding="utf-8"
            )

            result = reconcile_workspace(workspace)
            self.assertEqual(self.checks(result)["ledger"]["status"], "corrupt")
            self.assertTrue(
                any("reconciliation ledger" in error for error in inspect_workspace(workspace))
            )

    def test_progress_and_closeout_conflicts_are_hard_gated(self):
        with workspace_tempdir("reconcile-summaries-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            mission = workspace / "MissionCenter"
            mission.joinpath("progress.md").write_text(
                mission.joinpath("progress.md").read_text(encoding="utf-8").replace(
                    "5/10 estimated", "1/1 estimated"
                ),
                encoding="utf-8",
            )
            mission.joinpath("closeout.md").write_text(
                mission.joinpath("closeout.md").read_text(encoding="utf-8").replace(
                    "DEMO-001, DEMO-002", "DEMO-001, DEMO-003"
                ),
                encoding="utf-8",
            )

            checks = self.checks(reconcile_workspace(workspace))
            self.assertEqual(checks["progress"]["status"], "conflict")
            self.assertEqual(checks["closeout"]["status"], "conflict")
            errors = inspect_workspace(workspace)
            self.assertTrue(any("reconciliation progress" in error for error in errors))
            self.assertTrue(any("reconciliation closeout" in error for error in errors))

    def test_historical_closeout_scope_does_not_require_all_tasks(self):
        with workspace_tempdir("reconcile-closeout-history-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            closeout = workspace / "MissionCenter" / "closeout.md"
            closeout.write_text(
                closeout.read_text(encoding="utf-8").replace(
                    "DEMO-003", "DEMO-003; historical slice only"
                ),
                encoding="utf-8",
            )
            checks = self.checks(reconcile_workspace(workspace))
            self.assertEqual(checks["closeout"]["status"], "pass")

    def test_closeout_catches_completed_non_done_task(self):
        with workspace_tempdir("reconcile-closeout-status-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            closeout = workspace / "MissionCenter" / "closeout.md"
            closeout.write_text(
                closeout.read_text(encoding="utf-8").replace(
                    "DEMO-003", "DEMO-001"
                ),
                encoding="utf-8",
            )
            checks = self.checks(reconcile_workspace(workspace))
            self.assertEqual(checks["closeout"]["status"], "conflict")

    def test_derived_source_fingerprint_staleness_is_reported(self):
        with workspace_tempdir("reconcile-derived-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            tasks = workspace / "MissionCenter" / "tasks.md"
            tasks.write_text(
                tasks.read_text(encoding="utf-8").replace("DEMO-001", "DEMO-004"),
                encoding="utf-8",
            )

            checks = self.checks(reconcile_workspace(workspace))
            self.assertEqual(checks["derived_source"]["status"], "stale")


if __name__ == "__main__":
    unittest.main()
