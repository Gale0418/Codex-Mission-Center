import hashlib
import json
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "skills" / "mission-center" / "scripts"))

from contextual_recall import preflight, recall_context, validate_context_manifest


def workspace_at(root: Path) -> tuple[Path, bytes]:
    mission = root / "MissionCenter"
    mission.mkdir()
    content = b"# Guardrails\n\n## Deploy\n\nNever retry an unknown external operation.\n"
    (mission / "guardrails.md").write_bytes(content)
    return mission, content


def manifest(content: bytes) -> dict:
    return {
        "schemaVersion": "1.0",
        "artifactType": "context-manifest",
        "manifestId": "fixture",
        "cards": [{
            "id": "CTX-deploy-unknown",
            "context": "before-deploy",
            "reason": "preserve external result ambiguity",
            "scope": {"component": "release"},
            "source": {"locator": "MissionCenter/guardrails.md", "anchor": "## Deploy", "digest": hashlib.sha256(content).hexdigest()},
            "validity": "active",
            "requiredVerification": ["reconcile the original operation id"],
        }],
    }


class ContextualRecallTests(unittest.TestCase):
    def test_source_backed_recall_and_preflight_are_read_only(self):
        with workspace_tempdir("context-recall-") as temporary:
            root = Path(temporary)
            mission, content = workspace_at(root)
            before = (mission / "guardrails.md").read_bytes()
            record = manifest(content)
            self.assertEqual(validate_context_manifest(record, root), [])
            recalled = recall_context(record, root, "before-deploy", {"component": "release"})
            self.assertEqual(recalled["status"], "pass")
            self.assertEqual(recalled["cards"][0]["status"], "covered")
            decision = preflight(record, root, "before-deploy", {"component": "release"})
            self.assertEqual((decision["coverage"], decision["decision"]), ("covered", "advisory-only"))
            self.assertEqual((mission / "guardrails.md").read_bytes(), before)

    def test_digest_anchor_and_missing_coverage_fail_closed(self):
        with workspace_tempdir("context-stale-") as temporary:
            root = Path(temporary)
            _, content = workspace_at(root)
            record = manifest(content)
            record["cards"][0]["source"]["digest"] = "0" * 64
            stale = preflight(record, root, "before-deploy", {"component": "release"})
            self.assertEqual(stale["status"], "stale")
            self.assertEqual(stale["decision"], "blocked")
            fresh = manifest(content)
            self.assertEqual(preflight(fresh, root, "before-migration")["decision"], "unknown")
            fresh["cards"][0]["source"]["anchor"] = "## Missing"
            self.assertEqual(preflight(fresh, root, "before-deploy", {"component": "release"})["decision"], "blocked")

    def test_manifest_rejects_traversal_duplicate_cycle_and_secret(self):
        with workspace_tempdir("context-invalid-") as temporary:
            root = Path(temporary)
            _, content = workspace_at(root)
            record = manifest(content)
            record["cards"][0]["source"]["locator"] = "../outside.md"
            self.assertTrue(validate_context_manifest(record, root))
            duplicate = manifest(content)
            duplicate["cards"].append(json.loads(json.dumps(duplicate["cards"][0])))
            self.assertTrue(any("unique" in error or "duplicates" in error for error in validate_context_manifest(duplicate, root)))
            duplicate["cards"][1]["supersedes"] = "CTX-deploy-unknown"
            self.assertTrue(any("unique" in error for error in validate_context_manifest(duplicate, root)))
            invalid_id = manifest(content)
            valid_target = json.loads(json.dumps(invalid_id["cards"][0]))
            valid_target["id"] = "CTX-valid-target"
            valid_target["validity"] = "superseded"
            invalid_id["cards"].append(valid_target)
            invalid_id["cards"][0]["id"] = "invalid"
            invalid_id["cards"][0]["supersedes"] = "CTX-valid-target"
            self.assertTrue(any("safe CTX-" in error for error in validate_context_manifest(invalid_id, root)))
            secret = manifest(content)
            secret["cards"][0]["reason"] = "ghp_123456789012345678901234567890123456"
            self.assertTrue(any("secret" in error for error in validate_context_manifest(secret, root)))
            bad_manifest_id = manifest(content)
            bad_manifest_id["manifestId"] = "../bad"
            self.assertTrue(any("manifestId" in error for error in validate_context_manifest(bad_manifest_id, root)))

    def test_output_budget_never_splits_utf8(self):
        with workspace_tempdir("context-budget-") as temporary:
            root = Path(temporary)
            mission = root / "MissionCenter"
            mission.mkdir()
            content = ("## 錨點\n" + "兔" * 1000).encode()
            (mission / "lessons.md").write_bytes(content)
            record = manifest(content)
            record["cards"][0]["source"] = {"locator": "MissionCenter/lessons.md", "anchor": "## 錨點", "digest": hashlib.sha256(content).hexdigest()}
            result = recall_context(record, root, "before-deploy", {"component": "release"}, max_bytes=512)
            encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
            self.assertLessEqual(len(encoded), 512)
            self.assertEqual(result["bytes"], len(encoded))

    def test_superseded_card_is_reported_as_stale(self):
        with workspace_tempdir("context-superseded-") as temporary:
            root = Path(temporary)
            _, content = workspace_at(root)
            record = manifest(content)
            record["cards"][0]["validity"] = "superseded"
            result = recall_context(record, root, "before-deploy", {"component": "release"})
            self.assertEqual(result["status"], "stale")
            self.assertEqual(result["cards"][0]["status"], "stale")


if __name__ == "__main__":
    unittest.main()
