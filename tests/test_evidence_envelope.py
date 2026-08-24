import json
import shutil
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "demo-workspace"
sys.path.insert(0, str(SCRIPTS))

from evidence_envelope import envelope_status, scope_digest, validate_envelope
from doctor_mission_center import inspect_workspace
from reconcile_mission_center import reconcile_workspace


class EvidenceEnvelopeTests(unittest.TestCase):
    def copy_fixture(self, root: Path) -> Path:
        workspace = root / "workspace"
        shutil.copytree(FIXTURE, workspace)
        return workspace

    def envelope(
        self,
        workspace: Path,
        task_id: str = "DEMO-003",
        envelope_id: str = "env-demo-003",
        *,
        status: str = "current",
        supersedes: str | None = None,
    ) -> dict:
        scope = ["MissionCenter/tasks.md"]
        artifact = {
            "schemaVersion": "1.0",
            "artifactType": "evidence-envelope",
            "envelopeId": envelope_id,
            "taskId": task_id,
            "checkId": "doctor",
            "scope": scope,
            "scopeDigest": scope_digest(workspace, scope),
            "sourceRevision": "fixture-revision",
            "result": "pass",
            "status": status,
            "artifactLocators": ["MissionCenter/tasks.md"],
            "recordedAt": "2026-08-24T00:00:00Z",
        }
        if supersedes is not None:
            artifact["supersedes"] = supersedes
        return artifact

    def write_envelope(self, workspace: Path, payload: dict, name: str | None = None) -> Path:
        directory = workspace / "output" / "mission-center-evidence"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (name or f"{payload['envelopeId']}.json")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def write_all_task_envelopes(self, workspace: Path) -> None:
        for task_id in ("DEMO-001", "DEMO-002", "DEMO-003"):
            self.write_envelope(
                workspace,
                self.envelope(workspace, task_id, f"env-{task_id.lower()}"),
            )

    def test_versioned_schema_declares_required_envelope_contract(self):
        schema = json.loads(
            (ROOT / "skills" / "mission-center" / "schemas" / "evidence-envelope.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], "1.0")
        self.assertEqual(schema["properties"]["artifactType"]["const"], "evidence-envelope")
        self.assertIn("scopeDigest", schema["required"])
        self.assertIn("supersedes", schema["properties"])

    def test_scope_digest_ignores_unlisted_files(self):
        with workspace_tempdir("envelope-scope-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            payload = self.envelope(workspace)
            (workspace / "README.md").write_text("unlisted\n", encoding="utf-8")
            original = payload["scopeDigest"]
            (workspace / "README.md").write_text("unlisted changed\n", encoding="utf-8")
            self.assertEqual(scope_digest(workspace, payload["scope"]), original)
            self.assertEqual(validate_envelope(payload, workspace), [])

    def test_scoped_change_is_stale_and_malformed_shape_is_corrupt(self):
        with workspace_tempdir("envelope-stale-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            payload = self.envelope(workspace)
            self.assertEqual(envelope_status(payload, workspace), "pass")
            tasks = workspace / "MissionCenter" / "tasks.md"
            tasks.write_text(tasks.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertEqual(envelope_status(payload, workspace), "stale")
            payload.pop("scopeDigest")
            self.assertEqual(envelope_status(payload, workspace), "corrupt")

    def test_reconciler_accepts_complete_envelopes_and_warns_for_legacy(self):
        with workspace_tempdir("envelope-reconcile-valid-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            self.write_all_task_envelopes(workspace)
            checks = {item["name"]: item for item in reconcile_workspace(workspace)["checks"]}
            self.assertEqual(checks["evidence_envelope"]["status"], "pass")

        with workspace_tempdir("envelope-reconcile-legacy-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            checks = {item["name"]: item for item in reconcile_workspace(workspace)["checks"]}
            self.assertEqual(checks["evidence_envelope"]["status"], "unknown")

    def test_reconciler_classifies_duplicate_stale_and_superseded_conflicts(self):
        with workspace_tempdir("envelope-duplicate-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            self.write_envelope(workspace, self.envelope(workspace, envelope_id="env-a"))
            self.write_envelope(workspace, self.envelope(workspace, envelope_id="env-b"))
            checks = {item["name"]: item for item in reconcile_workspace(workspace)["checks"]}
            self.assertEqual(checks["evidence_envelope"]["status"], "conflict")

        with workspace_tempdir("envelope-supersede-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            old = self.envelope(workspace, envelope_id="env-old", status="superseded")
            current = self.envelope(workspace, envelope_id="env-new", supersedes="env-old")
            self.write_envelope(workspace, old)
            self.write_envelope(workspace, current)
            checks = {item["name"]: item for item in reconcile_workspace(workspace)["checks"]}
            self.assertEqual(checks["evidence_envelope"]["status"], "unknown")

        with workspace_tempdir("envelope-stale-reconcile-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            payload = self.envelope(workspace)
            self.write_envelope(workspace, payload)
            tasks = workspace / "MissionCenter" / "tasks.md"
            tasks.write_text(tasks.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            checks = {item["name"]: item for item in reconcile_workspace(workspace)["checks"]}
            self.assertEqual(checks["evidence_envelope"]["status"], "stale")
            self.assertTrue(
                any("reconciliation evidence_envelope" in error for error in inspect_workspace(workspace))
            )

    def test_current_failed_evidence_is_a_reconciliation_conflict(self):
        with workspace_tempdir("evidence-failed-result-") as temporary:
            workspace = self.copy_fixture(Path(temporary))
            payload = self.envelope(workspace)
            payload["result"] = "fail"
            self.write_envelope(workspace, payload)

            checks = {item["name"]: item for item in reconcile_workspace(workspace)["checks"]}
            self.assertEqual(checks["evidence_envelope"]["status"], "conflict")
            self.assertIn("current evidence result is fail", checks["evidence_envelope"]["message"])
            self.assertTrue(
                any("reconciliation evidence_envelope" in error for error in inspect_workspace(workspace))
            )


if __name__ == "__main__":
    unittest.main()
