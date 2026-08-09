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

    def test_cli(self):
        with workspace_tempdir() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(valid_record()), encoding="utf-8")
            self.assertEqual(0, subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, check=False).returncode)
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(1, subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True, check=False).returncode)


if __name__ == "__main__":
    unittest.main()
