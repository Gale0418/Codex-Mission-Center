import json
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "skills" / "mission-center" / "scripts"))

from mission_maintenance import run_sync
from steelman_contract import route_steelman, validate_steelman_artifact
from tests.test_mission_maintenance import make_workspace


def artifact(task_id="T1", route="steelman_lite", max_rounds=1):
    return {
        "schemaVersion": "1.0",
        "artifactType": "steelman-evolution",
        "taskId": task_id,
        "trueGoal": "preserve the real goal",
        "currentBest": "small local change",
        "strongestOpposition": "it may hide a durable trade-off",
        "thirdRoute": "defer with a bounded experiment",
        "flipVariables": ["risk evidence", "reversibility"],
        "smallestDiscriminatingTest": "compare the two observable outcomes",
        "materialDissent": [{"position": "keep current best", "impact": "lower churn", "resolution": "test before merge"}],
        "reopenConditions": ["new evidence changes the risk classification"],
        "qualityContract": {"invariants": ["readable", "testable"]},
        "architectureContract": {"invariants": ["tasks remain canonical"]},
        "evidenceRefs": ["tests/test_steelman_contract.py"],
        "unknowns": ["whether the edge case occurs in production"],
        "selectedRoute": route,
        "maxRounds": max_rounds,
        "perspectives": [
            {"id": "sim-a", "kind": "simulated", "observation": "a", "blindSpot": "b", "recommendation": "c"},
            {"id": "sim-b", "kind": "simulated", "observation": "d", "blindSpot": "e", "recommendation": "f"},
            *([{"id": "sim-c", "kind": "simulated", "observation": "g", "blindSpot": "h", "recommendation": "i"}] if route == "steelman_full" else []),
        ],
        "realSubagentsCompleted": False,
    }


def minimal_skip(task_id="T1"):
    return {
        "schemaVersion": "1.0",
        "artifactType": "steelman-evolution",
        "taskId": task_id,
        "selectedRoute": "skip",
        "maxRounds": 0,
        "skipReason": "reversible deterministic low-risk change",
        "perspectives": [],
        "realSubagentsCompleted": False,
    }


class SteelmanContractTests(unittest.TestCase):
    def test_route_is_bounded_and_task_bound(self):
        with workspace_tempdir("steelman-route-") as temporary:
            workspace = make_workspace(Path(temporary))
            tasks_before = (workspace / "MissionCenter/tasks.md").read_bytes()
            self.assertEqual(route_steelman(workspace, "T1", risk="low", deterministic=True)["selectedRoute"], "skip")
            self.assertEqual(route_steelman(workspace, "T1", risk="medium")["selectedRoute"], "steelman_lite")
            full = route_steelman(workspace, "T1", risk="high")
            self.assertEqual(full["selectedRoute"], "steelman_full")
            self.assertEqual(full["maxRounds"], 2)
            self.assertTrue(full["perspectivesAreSimulatedByDefault"])
            with self.assertRaises(ValueError):
                route_steelman(workspace, "UNKNOWN", risk="low", deterministic=True)
            self.assertEqual((workspace / "MissionCenter/tasks.md").read_bytes(), tasks_before)

    def test_required_fields_dissent_reopen_and_round_cap_fail_closed(self):
        record = artifact()
        errors = validate_steelman_artifact({
            "schemaVersion": "1.0", "artifactType": "steelman-evolution", "taskId": "T1",
            "selectedRoute": "steelman_lite", "maxRounds": 1, "perspectives": [],
            "realSubagentsCompleted": False,
        })
        self.assertTrue(any("trueGoal is required" in error for error in errors))
        record["materialDissent"] = []
        record["reopenConditions"] = []
        record["maxRounds"] = 3
        errors = validate_steelman_artifact(record)
        self.assertTrue(any("materialDissent must be a non-empty list" in error for error in errors))
        self.assertTrue(any("reopenConditions must be a non-empty list" in error for error in errors))
        self.assertTrue(any("maxRounds must be an integer" in error for error in errors))

    def test_minimal_skip_is_valid_and_minimal_lite_is_not(self):
        self.assertEqual(validate_steelman_artifact(minimal_skip()), [])
        errors = validate_steelman_artifact({
            "schemaVersion": "1.0", "artifactType": "steelman-evolution", "taskId": "T1",
            "selectedRoute": "steelman_lite", "maxRounds": 1, "perspectives": [],
            "realSubagentsCompleted": False,
        })
        self.assertTrue(any("trueGoal is required for steelman_lite" in error for error in errors))

    def test_empty_unknowns_is_valid_for_complete_artifact(self):
        record = artifact()
        record["unknowns"] = []
        self.assertEqual(validate_steelman_artifact(record), [])

    def test_valid_artifact_and_fake_real_completion_are_distinguished(self):
        with workspace_tempdir("steelman-validate-") as temporary:
            workspace = make_workspace(Path(temporary))
            self.assertEqual(validate_steelman_artifact(artifact(), workspace), [])
            fake = artifact()
            fake["realSubagentsCompleted"] = True
            errors = validate_steelman_artifact(fake, workspace)
            self.assertTrue(any("match completed real_subagent" in error for error in errors))
            real = artifact()
            real["perspectives"] = [
                {"id": "real-a", "kind": "real_subagent", "status": "completed", "observation": "a", "blindSpot": "b", "recommendation": "c", "evidenceRefs": ["output/a"]},
                {"id": "sim-b", "kind": "simulated", "observation": "d", "blindSpot": "e", "recommendation": "f"},
            ]
            real["realSubagentsCompleted"] = True
            errors = validate_steelman_artifact(real, workspace)
            self.assertTrue(any("explicitAuthorization" in error for error in errors))
            self.assertTrue(any("positive total" in error for error in errors))
            real["authorization"] = {"explicitAuthorization": True}
            real["budgets"] = {"total": 10, "perSeat": 5, "tool": 2, "wallClock": 30}
            self.assertEqual(validate_steelman_artifact(real, workspace), [])

    def test_artifact_task_binding_and_tasks_are_not_written(self):
        with workspace_tempdir("steelman-task-binding-") as temporary:
            workspace = make_workspace(Path(temporary))
            run_sync(workspace, date_str="2026-08-09")
            path = workspace / "MissionCenter/tasks.md"
            before = path.read_bytes()
            errors = validate_steelman_artifact(artifact("UNKNOWN"), workspace)
            self.assertTrue(any("canonical tasks.md" in error for error in errors))
            self.assertEqual(path.read_bytes(), before)

    def test_schema_and_python_validator_enforce_route_specific_rounds_and_perspectives(self):
        schema = json.loads((ROOT / "skills/mission-center/schemas/steelman-evolution.schema.json").read_text(encoding="utf-8"))
        route_rules = {
            rule["if"]["properties"]["selectedRoute"].get("const"): rule["then"]["properties"]
            for rule in schema["allOf"]
            if "const" in rule["if"]["properties"]["selectedRoute"]
        }
        self.assertEqual(route_rules["steelman_lite"]["maxRounds"]["const"], 1)
        self.assertEqual(route_rules["steelman_lite"]["perspectives"]["minItems"], 2)
        self.assertEqual(route_rules["steelman_full"]["perspectives"]["minItems"], 3)
        invalid_lite = artifact(max_rounds=2)
        self.assertTrue(any("exactly one round" in error for error in validate_steelman_artifact(invalid_lite)))
    def test_steelman_rejects_secret_injection_and_forbidden_keys(self):
        record = artifact()
        record["strongestOpposition"] = "contains token sk-proj-1234567890abcdef"
        errors = validate_steelman_artifact(record)
        self.assertTrue(any("contains secret-like content" in error for error in errors))

        record_key = artifact()
        record_key["secret"] = "top_secret"
        errors_key = validate_steelman_artifact(record_key)
        self.assertTrue(any("forbidden privacy content" in error for error in errors_key))

        record_normal = artifact()
        record_normal["strongestOpposition"] = "discussing general API key rotation and design trade-offs"
        self.assertEqual(validate_steelman_artifact(record_normal), [])


if __name__ == "__main__":
    unittest.main()
