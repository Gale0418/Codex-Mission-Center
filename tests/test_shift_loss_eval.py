import json
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "skills" / "mission-center" / "scripts"))

from security_scanner import scan_forbidden_content
from shift_loss_eval import aggregate_cases, compare_paired, evaluate_shift_loss, validate_shift_loss
from tests.test_mission_maintenance import make_workspace


def case(case_id, *, recall=False, ignore=False, supersede=False, actual_recall=False, actual_ignore=False, actual_supersede=False, **overrides):
    record = {
        "caseId": case_id,
        "taskId": "T1",
        "variant": "baseline_v0_3",
        "shouldRecall": recall,
        "shouldIgnore": ignore,
        "shouldSupersede": supersede,
        "actualRecall": actual_recall,
        "actualIgnore": actual_ignore,
        "actualSupersede": actual_supersede,
        "firstCorrectActionMs": 12,
        "staleMemoryInjected": False,
        "wrongBranch": False,
        "tokensUsed": 10,
        "verifiedProgress": True,
        "evidenceClaims": 2,
        "evidenceBackedClaims": 2,
        "falseDone": False,
        "recoveryDistance": 1,
        "unverifiedDestructiveAction": False,
        "activeGuardrailWithoutSource": False,
        "multipleWritersSameBranch": False,
    }
    record.update(overrides)
    return record


def result(variant="baseline_v0_3", cases=None):
    cases = cases or [
        case("recall", recall=True, actual_recall=True),
        case("ignore", ignore=True, actual_ignore=True),
        case("supersede", supersede=True, actual_supersede=True),
    ]
    for item in cases:
        item["variant"] = variant
    return {"schemaVersion": "1.0", "artifactType": "shift-loss-eval", "taskId": "T1", "variant": variant, "cases": cases}


class ShiftLossEvalTests(unittest.TestCase):
    def test_aggregate_metrics_and_zero_denominators_are_explicit(self):
        record = evaluate_shift_loss(result())
        self.assertTrue(record["valid"])
        self.assertEqual(record["metrics"]["HRA"], 1.0)
        self.assertEqual(record["metrics"]["TFCA"], 12.0)
        self.assertIsNone(aggregate_cases([case("only", recall=True, actual_recall=True, firstCorrectActionMs=None)])["metrics"]["TFCA"])
        self.assertIsNone(aggregate_cases([case("unknown-distance", recall=True, actual_recall=True, recoveryDistance=None)])["metrics"]["RecoveryDistance"])

    def test_nontrivial_metric_formulas_are_not_cross_wired(self):
        cases = [
            case("multi-target", recall=True, ignore=True, actual_recall=True, actual_ignore=False, firstCorrectActionMs=10, staleMemoryInjected=True, wrongBranch=True, tokensUsed=8, verifiedProgress=True, evidenceClaims=3, evidenceBackedClaims=2, recoveryDistance=2),
            case("supersede", supersede=True, actual_supersede=False, firstCorrectActionMs=30, staleMemoryInjected=False, wrongBranch=False, tokensUsed=12, verifiedProgress=False, evidenceClaims=0, evidenceBackedClaims=0, recoveryDistance=None),
        ]
        metrics = aggregate_cases(cases)["metrics"]
        self.assertAlmostEqual(metrics["HRA"], 1 / 3)
        self.assertEqual(metrics["TFCA"], 20)
        self.assertEqual(metrics["SMIR"], 0.5)
        self.assertEqual(metrics["WBR"], 0.5)
        self.assertEqual(metrics["TVP"], 20)
        self.assertEqual(metrics["EvidenceCoverage"], 2 / 3)
        self.assertEqual(metrics["FalseDone"], 0)
        self.assertEqual(metrics["RecoveryDistance"], 2)

    def test_hard_constraints_override_metrics(self):
        bad = result(cases=[case("bad", recall=True, actual_recall=True, falseDone=True, unverifiedDestructiveAction=True, activeGuardrailWithoutSource=True, multipleWritersSameBranch=True)])
        evaluated = evaluate_shift_loss(bad)
        self.assertEqual(evaluated["overallStatus"], "failed_hard_constraint")
        self.assertFalse(evaluated["hardConstraintsPassed"])
        self.assertEqual(evaluated["metrics"]["FalseDone"], 1)

    def test_paired_comparison_is_incomplete_without_matching_case(self):
        baseline = result()
        newer = result("owo_v0_4", [case("recall", recall=True, actual_recall=True), case("ignore", ignore=True, actual_ignore=True)])
        compared = compare_paired(baseline, newer)
        self.assertFalse(compared["complete"])
        self.assertFalse(compared["improvementClaim"])
        self.assertIn("supersede", compared["missingNew"])
        self.assertNotIn("metricDeltas", compared)

    def test_privacy_forbidden_and_unknown_task_fail_without_writing_tasks(self):
        with workspace_tempdir("shift-loss-privacy-") as temporary:
            workspace = make_workspace(Path(temporary))
            path = workspace / "MissionCenter/tasks.md"
            before = path.read_bytes()
            forbidden = result()
            forbidden["prompt"] = "never persist"
            self.assertTrue(any("forbidden privacy" in error for error in validate_shift_loss(forbidden, workspace)))
            unknown = result()
            unknown["taskId"] = "UNKNOWN"
            for item in unknown["cases"]:
                item["taskId"] = "UNKNOWN"
            self.assertTrue(any("canonical tasks.md" in error for error in validate_shift_loss(unknown, workspace)))
            self.assertEqual(path.read_bytes(), before)

    def test_target_flags_require_one_true(self):
        invalid = result(cases=[case("none")])
        self.assertTrue(any("at least one true" in error for error in validate_shift_loss(invalid)))

    def test_malformed_numeric_and_case_id_values_return_errors_without_crashing(self):
        malformed = result(cases=[case("bad", recall=True, evidenceClaims="two", evidenceBackedClaims=[], recoveryDistance="far")])
        malformed["cases"][0]["caseId"] = []
        errors = validate_shift_loss(malformed)
        self.assertTrue(any("evidenceClaims must be a non-negative integer" in error for error in errors))
        self.assertTrue(any("evidenceBackedClaims must be a non-negative integer" in error for error in errors))
        self.assertTrue(any("recoveryDistance must be a non-negative number" in error for error in errors))
        self.assertTrue(any("caseId must be bounded non-empty text" in error for error in errors))

    def test_security_scanner_handles_deep_input_with_controlled_error(self):
        nested = "leaf"
        for _ in range(1100):
            nested = {"nested": nested}
        errors = scan_forbidden_content(nested)
        self.assertTrue(any("security scanner depth limit" in error for error in errors))

        record = result()
        record["metadata"] = nested
        errors = validate_shift_loss(record)
        self.assertTrue(any("security scanner depth limit" in error for error in errors))

    def test_shift_loss_schema_has_anyof_and_python_validator_rejects_all_false(self):
        schema_path = ROOT / "skills" / "mission-center" / "schemas" / "shift-loss-eval.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        case_def = schema["$defs"]["case"]
        self.assertIn("anyOf", case_def)
        any_of = case_def["anyOf"]
        self.assertEqual(len(any_of), 3)
        expected_fields = {"shouldRecall", "shouldIgnore", "shouldSupersede"}
        found_fields = {list(opt["properties"].keys())[0] for opt in any_of}
        self.assertEqual(found_fields, expected_fields)
        for opt in any_of:
            field_name = list(opt["properties"].keys())[0]
            self.assertTrue(opt["properties"][field_name]["const"])
        invalid = result(cases=[case("all_false", recall=False, ignore=False, supersede=False)])
        errors = validate_shift_loss(invalid)
        self.assertTrue(any("at least one true" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
