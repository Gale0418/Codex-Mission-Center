import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "mission-center" / "scripts" / "critic_contract.py"
sys.path.insert(0, str(SCRIPT.parent))

from critic_contract import GAME_CHECKPOINTS, validate_critic_record

def valid_record(route="critic_lite"):
    record = {
        "schemaVersion": "1.0",
        "route": route,
        "taskId": "MC-005",
        "chairRecordLocator": "output/mission-center-critique/MC-005-s1.json",
        "artifactManifest": [
            {"locator": "artifact.zip", "sha256": "a" * 64, "laneId": "main"}
        ],
        "snapshots": [
            {
                "id": "s1",
                "revision": "r1",
                "hash": "h1",
                "evidenceLinks": ["evidence.log"],
            }
        ],
        "findings": [],
    }
    if route != "skip":
        record.update(
            {
                "authorization": {"explicitApproval": True},
                "budgets": {
                    "total": 10,
                    "perSeat": 3,
                    "tool": 2,
                    "wallClock": 60,
                },
                "critics": [{"id": "a"}, {"id": "b"}],
                "outcome": "passed",
                "lanes": [
                    {
                        "id": "main",
                        "kind": "article/nonfiction",
                        "required": True,
                        "seatId": "a",
                        "evidenceLocator": "review.md",
                        "coverageStatus": "covered",
                    }
                ],
            }
        )
    if route == "critic_full":
        record["critics"].append({"id": "c"})
        record["arbiter"] = {"id": "arbiter"}
    return record


class CriticContractTests(unittest.TestCase):
    @staticmethod
    def finding(severity="High", disposition="fixed"):
        return {
            "id": "CACC-MC-005-quality-1234abcd-1",
            "severity": severity,
            "category": "quality",
            "observation": "A reproducible defect",
            "evidenceLocator": "artifact.md:3",
            "reproOrReadPath": "Read line 3",
            "impact": "Breaks the acceptance criterion",
            "confidence": "high",
            "unknown": "none",
            "recommendation": "Repair the defect",
            "criticProposedDisposition": disposition,
            "chairFinalDisposition": disposition,
        }

    @staticmethod
    def closure_reviews(snapshot_id="s1", include_arbiter=False):
        seat_ids = ["a", "b", "c"] if include_arbiter else ["a", "b"]
        if include_arbiter:
            seat_ids.append("arbiter")
        return [
            {
                "seatId": seat_id,
                "snapshotId": snapshot_id,
                "evidenceLocator": f"reviews/{seat_id}.json",
                "sha256": "b" * 64,
            }
            for seat_id in seat_ids
        ]

    def test_valid_skip_lite_and_full(self):
        for route in ("skip", "critic_lite", "critic_full"):
            self.assertEqual([], validate_critic_record(valid_record(route)))

    def test_missing_approval_and_insufficient_seats_are_invalid(self):
        record = valid_record()
        del record["authorization"]
        self.assertTrue(validate_critic_record(record))
        record = valid_record("critic_full")
        record["critics"] = record["critics"][:2]
        self.assertTrue(validate_critic_record(record))

    def test_delta_parent_and_snapshot_boundaries(self):
        record = valid_record()
        record["snapshots"].append({"id": "s2", "parent": "wrong", "revision": "r2", "hash": "h2", "evidenceLinks": ["delta.log"]})
        self.assertTrue(validate_critic_record(record))
        record = valid_record()
        record["snapshots"] *= 3
        self.assertTrue(validate_critic_record(record))

    def test_critical_waiver_and_high_acceptance(self):
        record = valid_record()
        record["findings"] = [self.finding("Critical", "accepted")]
        self.assertTrue(validate_critic_record(record))
        record = valid_record()
        record["findings"] = [self.finding("High", "accepted")]
        self.assertTrue(validate_critic_record(record))
        record["findings"][0]["humanAcceptance"] = {field: "x" for field in ("approverIdentity", "approvalTime", "scope", "reason", "expiry", "reopenTrigger")}
        self.assertEqual([], validate_critic_record(record))

    def test_malformed_and_boolean_budgets_fail_closed(self):
        self.assertTrue(validate_critic_record(None))
        record = valid_record()
        record["budgets"]["total"] = True
        self.assertTrue(validate_critic_record(record))
        record = valid_record()
        record["budgets"]["total"] = float("inf")
        self.assertTrue(validate_critic_record(record))
        record = valid_record("critic_full")
        record["critics"][1]["id"] = record["critics"][0]["id"]
        self.assertTrue(validate_critic_record(record))
        record = valid_record()
        record["smokePassedByCouncil"] = True
        self.assertTrue(validate_critic_record(record))

    def test_required_lane_and_game_journey_fail_closed(self):
        record = valid_record("critic_full")
        record["lanes"] = []
        self.assertTrue(validate_critic_record(record))

        record = valid_record("critic_full")
        record["lanes"][0].update(
            {"coverageStatus": "unknown", "capabilityReason": "no audio device"}
        )
        self.assertTrue(validate_critic_record(record))

        record = valid_record("critic_full")
        record["lanes"][0]["kind"] = "game/interactive"
        self.assertTrue(validate_critic_record(record))

        record["lanes"][0]["journeyCoverage"] = [
            {
                "checkpoint": checkpoint,
                "coverageStatus": "covered",
                "evidenceLocator": f"evidence/{checkpoint}.json",
            }
            for checkpoint in sorted(GAME_CHECKPOINTS)
        ]
        self.assertEqual([], validate_critic_record(record))

    def test_v11_state_machine_allows_honest_non_dispatch_and_requires_completed_contract(self):
        skipped = {"schemaVersion": "1.1", "selectedRoute": "skip", "executionStatus": "skipped", "requiredByPolicy": False, "taskId": "MC-005", "chairRecordLocator": "output/mission-center-critique/MC-005.json", "reason": "not applicable"}
        self.assertEqual([], validate_critic_record(skipped))
        pending = {"schemaVersion": "1.1", "selectedRoute": "critic_full", "executionStatus": "not_dispatched", "requiredByPolicy": False, "taskId": "MC-005", "chairRecordLocator": "output/mission-center-critique/MC-005.json", "reason": "approval and budget absent"}
        self.assertEqual([], validate_critic_record(pending))
        self.assertTrue(validate_critic_record({**pending, "executionStatus": "completed"}))

    def test_v11_enforces_locator_and_required_policy_completion(self):
        record = {"schemaVersion": "1.1", "selectedRoute": "skip", "executionStatus": "skipped", "requiredByPolicy": True, "taskId": "MC-005", "chairRecordLocator": "outside/record.json", "reason": "not applicable"}
        errors = validate_critic_record(record)
        self.assertIn("chairRecordLocator must use output/mission-center-critique/", errors)
        self.assertIn("requiredByPolicy records must be completed", errors)

    def test_high_deferred_needs_human_acceptance(self):
        record = valid_record()
        record["findings"] = [self.finding("High", "deferred")]
        self.assertTrue(validate_critic_record(record))
        record["findings"][0]["humanAcceptance"] = {field: "x" for field in ("approverIdentity", "approvalTime", "scope", "reason", "expiry", "reopenTrigger")}
        self.assertEqual([], validate_critic_record(record))

    def test_converge_allows_arbitrarily_many_parent_linked_snapshots(self):
        record = valid_record()
        record["loopPolicy"] = {
            "mode": "converge",
            "stopCondition": "all_findings_resolved",
            "closure": {
                "snapshotId": "s5",
                "evidenceLocator": "output/mission-center-critique/MC-005-final-coverage.json",
                "reviews": self.closure_reviews("s5"),
            },
        }
        for index in range(2, 6):
            record["snapshots"].append(
                {
                    "id": f"s{index}",
                    "parent": f"s{index - 1}",
                    "revision": f"r{index}",
                    "hash": f"h{index}",
                    "evidenceLinks": [f"evidence-{index}.log"],
                }
            )
        self.assertEqual([], validate_critic_record(record))

        record["snapshots"][3]["parent"] = "s1"
        self.assertTrue(
            any("previous snapshot" in error for error in validate_critic_record(record))
        )

        record["snapshots"][3]["parent"] = "s3"
        record["loopPolicy"]["closure"]["reviews"][0]["sha256"] = "short"
        self.assertTrue(
            any("64-hex sha256" in error for error in validate_critic_record(record))
        )

    def test_converge_full_closure_covers_arbiter_exactly(self):
        record = valid_record("critic_full")
        record["loopPolicy"] = {
            "mode": "converge",
            "stopCondition": "all_findings_resolved",
            "closure": {
                "snapshotId": "s1",
                "evidenceLocator": "coverage.md",
                "reviews": self.closure_reviews("s1", include_arbiter=True),
            },
        }
        self.assertEqual([], validate_critic_record(record))

        record["loopPolicy"]["closure"]["reviews"].pop()
        self.assertTrue(
            any("cover exactly every critic and arbiter" in error for error in validate_critic_record(record))
        )

    def test_converge_passed_requires_final_closure_even_without_findings(self):
        record = valid_record()
        record["loopPolicy"] = {
            "mode": "converge",
            "stopCondition": "all_findings_resolved",
        }
        errors = validate_critic_record(record)
        self.assertIn("converge passed requires closure evidence", errors)

        record["loopPolicy"]["closure"] = {
            "snapshotId": "not-final",
            "evidenceLocator": "coverage.md",
            "reviews": self.closure_reviews("not-final"),
        }
        errors = validate_critic_record(record)
        self.assertIn(
            "loopPolicy.closure.snapshotId must reference the final snapshot", errors
        )

        del record["findings"]
        record["loopPolicy"]["closure"]["snapshotId"] = "s1"
        self.assertIn(
            "converge loopPolicy requires an explicit findings list",
            validate_critic_record(record),
        )

    def test_converge_passed_resolves_low_findings_without_severity_shortcut(self):
        record = valid_record()
        record["loopPolicy"] = {
            "mode": "converge",
            "stopCondition": "all_findings_resolved",
            "closure": {
                "snapshotId": "s1",
                "evidenceLocator": "coverage.md",
                "reviews": self.closure_reviews(),
            },
        }
        record["findings"] = [self.finding("Low", "deferred")]
        self.assertTrue(
            any(
                "convergence passed requires every finding" in error
                for error in validate_critic_record(record)
            )
        )

        record["findings"][0]["chairFinalDisposition"] = "fixed"
        self.assertEqual([], validate_critic_record(record))

    def test_converge_interruption_preserves_unresolved_critical_record(self):
        record = valid_record()
        record["outcome"] = "blocked"
        record["loopPolicy"] = {
            "mode": "converge",
            "stopCondition": "all_findings_resolved",
        }
        record["findings"] = [self.finding("Critical", "deferred")]
        self.assertEqual([], validate_critic_record(record))

        record["findings"] = [self.finding("Critical", "accepted")]
        self.assertTrue(
            any("Critical cannot be human accepted" in error for error in validate_critic_record(record))
        )

        record["findings"] = [self.finding("High", "deferred")]
        self.assertEqual([], validate_critic_record(record))

    def test_skip_cannot_hide_convergence_policy(self):
        record = valid_record("skip")
        record["loopPolicy"] = {
            "mode": "converge",
            "stopCondition": "all_findings_resolved",
        }
        self.assertIn("skip route cannot select converge loopPolicy", validate_critic_record(record))

    def test_v11_non_dispatch_cannot_hide_convergence_policy(self):
        record = {
            "schemaVersion": "1.1",
            "selectedRoute": "skip",
            "executionStatus": "skipped",
            "requiredByPolicy": False,
            "taskId": "MC-005",
            "chairRecordLocator": "output/mission-center-critique/MC-005.json",
            "reason": "not applicable",
            "loopPolicy": {
                "mode": "converge",
                "stopCondition": "all_findings_resolved",
            },
        }
        self.assertIn("skip route cannot select converge loopPolicy", validate_critic_record(record))

    def test_cli(self):
        with workspace_tempdir() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(valid_record()), encoding="utf-8")
            self.assertEqual(0, subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, check=False).returncode)
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(1, subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, check=False).returncode)

    def test_explicit_null_policy_is_not_legacy_omission(self):
        record = valid_record()
        record["loopPolicy"] = None
        self.assertIn("loopPolicy must be an object", validate_critic_record(record))

    def test_converge_rejection_needs_counterevidence(self):
        record = valid_record()
        record["loopPolicy"] = {"mode": "converge", "stopCondition": "all_findings_resolved",
            "closure": {"snapshotId": "s1", "evidenceLocator": "closure.log", "reviews": self.closure_reviews()}}
        record["findings"] = [self.finding("Low", "rejected-with-counterevidence")]
        self.assertTrue(validate_critic_record(record))
        record["findings"][0]["counterevidence"] = "reproduction.log confirms the claim is false"
        self.assertEqual([], validate_critic_record(record))

    def test_bounded_rejection_needs_counterevidence(self):
        record = valid_record()
        record["findings"] = [self.finding("Low", "rejected-with-counterevidence")]
        self.assertTrue(validate_critic_record(record))
        record["findings"][0]["counterevidence"] = "reproduction.log confirms the claim is false"
        self.assertEqual([], validate_critic_record(record))

    def test_converge_non_dispatch_cannot_claim_passed_or_shadow_selected_route(self):
        record = {
            "schemaVersion": "1.1", "selectedRoute": "critic_lite",
            "executionStatus": "not_dispatched", "requiredByPolicy": False,
            "taskId": "MC-005", "chairRecordLocator": "output/mission-center-critique/pending.json",
            "reason": "interrupted", "outcome": "passed",
            "loopPolicy": {"mode": "converge", "stopCondition": "all_findings_resolved",
                "closure": {"snapshotId": "s1", "evidenceLocator": "fake.log"}},
        }
        self.assertIn("incomplete converge execution cannot have passed outcome", validate_critic_record(record))
        del record["outcome"]
        del record["loopPolicy"]["closure"]
        record.update(selectedRoute="skip", route="critic_lite", executionStatus="skipped")
        self.assertIn("skip route cannot select converge loopPolicy", validate_critic_record(record))

    def test_legacy_non_dispatch_cannot_claim_passed(self):
        record = {"schemaVersion": "1.1", "selectedRoute": "skip",
            "executionStatus": "skipped", "requiredByPolicy": False, "taskId": "MC-005",
            "chairRecordLocator": "output/mission-center-critique/pending.json",
            "reason": "not applicable", "outcome": "passed"}
        self.assertIn("incomplete critic records cannot be passed", validate_critic_record(record))

    def test_converge_interruption_records_all_severities_but_not_risk_acceptance(self):
        record = valid_record()
        record["loopPolicy"] = {"mode": "converge", "stopCondition": "all_findings_resolved"}
        record["outcome"] = "blocked"
        for severity in ("Critical", "High", "Medium", "Low"):
            record["findings"] = [self.finding(severity, "deferred")]
            self.assertEqual([], validate_critic_record(record))
            record["findings"][0]["chairFinalDisposition"] = "accepted"
            record["findings"][0]["humanAcceptance"] = {field: "x" for field in (
                "approverIdentity", "approvalTime", "scope", "reason", "expiry", "reopenTrigger")}
            self.assertIn("finding 0: converge findings cannot be accepted", validate_critic_record(record))


if __name__ == "__main__":
    unittest.main()
