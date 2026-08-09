import json
import subprocess
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from optimization_core import build_profile, evaluate_observations, route_profile, validate_manifest


class OptimizationTests(unittest.TestCase):
    def profile(self, **changes):
        base = {"taskType": "optimization", "parameterShape": "discrete", "measurement": "repeatable", "noise": "low", "reversibility": "easy", "risk": "low", "factorCount": 2, "budget": {"trials": 8, "tokens": 8000, "wallClockSeconds": 60}}
        base.update(changes)
        return build_profile(base)

    def test_routes_four_modes_and_research_fallback(self):
        self.assertEqual(route_profile(self.profile(taskType="deterministic", parameterShape="none"))["mode"], "skip")
        self.assertEqual(route_profile(self.profile())["mode"], "decision")
        self.assertEqual(route_profile(self.profile(risk="high"))["mode"], "hybrid")
        self.assertEqual(route_profile(self.profile(parameterShape="continuous", differentiable=True))["mode"], "experimental")
        self.assertEqual(route_profile(self.profile(measurement="none"))["mode"], "research_spike")

    def test_strategy_routing(self):
        cases = [
            ({"parameterShape": "categorical"}, "tpe"),
            ({"parameterShape": "mixed"}, "tpe"),
            ({"parameterShape": "continuous", "differentiable": True}, "gradient_method"),
            ({"parameterShape": "continuous", "measurement": "expensive", "factorCount": 3}, "bayesian_optimization"),
            ({"noise": "high"}, "robust_doe_taguchi"),
            ({"factorCount": 8}, "screening_doe"),
            ({"parameterShape": "multi_objective", "objectives": ["quality", "cost"], "budget": {"trials": 30, "tokens": 1000, "wallClockSeconds": 10}}, "pareto_nsga2"),
        ]
        for changes, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(route_profile(self.profile(**changes))["strategy"], expected)

    def test_hard_constraints_win_and_unknowns_are_not_scored(self):
        manifest = json.loads((ROOT / "tests/fixtures/optimization/routing.json").read_text(encoding="utf-8"))
        observations = [
            {"candidate": "rules", "metrics": {"accuracy": 0.7, "cost": 100}},
            {"candidate": "hybrid", "metrics": {"accuracy": 0.4, "cost": 1}},
            {"candidate": "unknown", "metrics": {"cost": 10}},
        ]
        result = evaluate_observations(manifest, observations)
        self.assertEqual(result["paretoCandidates"], ["rules"])
        self.assertIsNone(result["compositeLoss"])
        self.assertIn("unknown:accuracy", result["unknowns"])
        self.assertEqual(result["promotionRecommendation"], "insufficient_evidence")

    def test_composite_requires_explicit_normalization_and_weights(self):
        manifest = json.loads((ROOT / "tests/fixtures/optimization/evaluator.json").read_text(encoding="utf-8"))
        observations = [{"candidate": "independent", "metrics": {"agreement": 0.9}}]
        self.assertIsNone(evaluate_observations(manifest, observations)["compositeLoss"])
        manifest["normalization"] = {"agreement": {"min": 0, "max": 1}}
        manifest["weights"] = {"agreement": 1}
        self.assertEqual(evaluate_observations(manifest, observations)["compositeLoss"]["independent"], 0.1)

    def test_budget_retry_and_fixture_contracts(self):
        fixture_dir = ROOT / "tests/fixtures/optimization"
        self.assertEqual(len(list(fixture_dir.glob("*.json"))), 5)
        for path in fixture_dir.glob("*.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(path=path.name):
                self.assertEqual(validate_manifest(manifest), [])
                self.assertLessEqual(manifest["budget"]["maxConcurrency"], 2)
                self.assertLessEqual(manifest["budget"]["retriesPerTrial"], 1)
                self.assertEqual(manifest["promotionState"], "shadow")

    def test_manifest_rejects_non_numeric_concurrency_without_raising(self):
        manifest = json.loads((ROOT / "tests/fixtures/optimization/evaluator.json").read_text(encoding="utf-8"))
        manifest["budget"]["maxConcurrency"] = "two"
        manifest["budget"]["retriesPerTrial"] = None
        errors = validate_manifest(manifest)
        self.assertIn("invalid_budget:maxConcurrency", errors)
        self.assertIn("invalid_budget:retriesPerTrial", errors)

    def test_manifest_rejects_bool_budget_and_malformed_metrics(self):
        manifest = json.loads((ROOT / "tests/fixtures/optimization/evaluator.json").read_text(encoding="utf-8"))
        manifest["budget"]["trials"] = True
        manifest["metrics"] = [{"name": "agreement"}]
        result = evaluate_observations(manifest, [])
        self.assertEqual(result["status"], "invalid")
        self.assertIn("invalid_budget:trials", result["unknowns"])
        self.assertIn("invalid:metrics", result["unknowns"])
        self.assertEqual(result["budgetUsed"]["trials"], 0)

    def test_shadow_rejects_unsafe_experiment_id(self):
        with workspace_tempdir() as temp:
            workspace = Path(temp)
            manifest = json.loads((ROOT / "tests/fixtures/optimization/evaluator.json").read_text(encoding="utf-8"))
            manifest["experimentId"] = "../escape"
            manifest_path = workspace / "manifest.json"
            observations = workspace / "observations.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            observations.write_text("[]", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "mission_optimizer.py"), "shadow", "--manifest", str(manifest_path), "--observations", str(observations), "--workspace", str(workspace)],
                capture_output=True, text=True, timeout=20,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((workspace / "output/escape-result.json").exists())

    def test_token_time_trial_budget_and_retry_are_enforced(self):
        manifest = json.loads((ROOT / "tests/fixtures/optimization/evaluator.json").read_text(encoding="utf-8"))
        manifest["budget"].update(trials=4, tokens=10, wallClockSeconds=5, retriesPerTrial=1)
        observations = [
            {"candidate": "a", "case": "c", "metrics": {"agreement": 0.4}, "tokens": 3, "wallClockSeconds": 1},
            {"candidate": "a", "case": "c", "metrics": {"agreement": 0.5}, "tokens": 3, "wallClockSeconds": 1},
            {"candidate": "a", "case": "c", "metrics": {"agreement": 0.6}, "tokens": 1, "wallClockSeconds": 1},
            {"candidate": "b", "case": "c", "metrics": {"agreement": 0.9}, "tokens": 8, "wallClockSeconds": 1},
        ]
        result = evaluate_observations(manifest, observations)
        self.assertEqual(result["status"], "budget_exhausted")
        self.assertEqual(result["sampleCount"], 2)
        self.assertEqual(result["budgetUsed"]["tokens"], 6)

    def test_shadow_cli_writes_review_only_result(self):
        with workspace_tempdir() as temp:
            workspace = Path(temp)
            observations = workspace / "observations.json"
            observations.write_text(json.dumps([{"candidate": "independent", "metrics": {"agreement": 0.9}}]), encoding="utf-8")
            command = [sys.executable, str(SCRIPTS / "mission_optimizer.py"), "shadow", "--manifest", str(ROOT / "tests/fixtures/optimization/evaluator.json"), "--observations", str(observations), "--workspace", str(workspace)]
            completed = subprocess.run(command, text=True, capture_output=True, timeout=20)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads((workspace / "output/mission-center-optimization/core-evaluator-result.json").read_text(encoding="utf-8"))
            self.assertIn(result["promotionState"], {"shadow", "review"})
            self.assertNotEqual(result["promotionState"], "adopted")


if __name__ == "__main__":
    unittest.main()
