import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "skills" / "mission-center" / "scripts"))

from research_portfolio import (
    default_initial_allocation,
    route_saturation,
    validate_research_portfolio,
)
from tests.test_mission_maintenance import make_workspace


def source(locator="local://evidence", trust="trusted_local", source_type="local", status="verified"):
    return {
        "locator": locator,
        "sourceType": source_type,
        "provenance": "fixture-only; no research executed",
        "trustStatus": trust,
        "licenseStatus": "not_applicable" if trust == "trusted_local" else "unknown",
        "retrievedAt": "2026-08-20T00:00:00Z",
        "status": status,
    }


def hypothesis(identifier, kind, refs=None, status="active"):
    return {
        "id": identifier,
        "kind": kind,
        "question": f"Does {identifier} matter?",
        "mechanism": "bounded mechanism",
        "currentEvidenceRefs": refs or [],
        "smallestDiscriminatingTest": "compare two observable outcomes",
        "expectedObservation": "one outcome changes",
        "falsificationConditions": ["test does not discriminate"],
        "dependencies": ["canonical task"],
        "risks": ["scope drift"],
        "budget": {"token": 0, "tool": 0, "time": 0},
        "successNextAction": "record result",
        "failureKnowledge": "retain the failed premise",
        "revalidateWhen": "new evidence arrives",
        "status": status,
    }


def portfolio(task_id="T1"):
    return {
        "schemaVersion": "1.0",
        "artifactType": "research-portfolio",
        "taskId": task_id,
        "initialHypothesisAllocation": default_initial_allocation(),
        "allocationKind": "initial_hypothesis_allocation",
        "hypotheses": [
            hypothesis("h-exploit", "exploit", ["local://evidence"]),
            hypothesis("h-adjacent", "adjacent_explore", ["local://evidence"]),
            hypothesis("h-moonshot", "moonshot", [], "research_needed"),
        ],
        "sourceLedger": [source()],
        "saturationSignals": {
            "repeatedRootCause": False,
            "renamedHypothesis": False,
            "metricStalled": False,
            "budgetBurning": False,
            "sharedUnverifiedPremise": False,
            "lowMarginalGainCount": 0,
        },
        "selectedAction": "continue",
    }


class ResearchPortfolioTests(unittest.TestCase):
    def test_three_hypothesis_kinds_and_default_allocation_validate(self):
        with workspace_tempdir("research-portfolio-") as temporary:
            workspace = make_workspace(Path(temporary))
            self.assertEqual(validate_research_portfolio(portfolio(), workspace), [])
            self.assertEqual(sum(default_initial_allocation().values()), 100)

    def test_allocation_source_license_and_budget_fail_closed(self):
        record = portfolio()
        record["initialHypothesisAllocation"]["moonshot"] = 11
        self.assertTrue(any("totaling 100" in error for error in validate_research_portfolio(record)))
        record = portfolio()
        record["sourceLedger"] = [source("https://example.invalid", "trusted_local", "external_url")]
        self.assertTrue(any("untrusted_external_evidence" in error for error in validate_research_portfolio(record)))
        record = portfolio()
        record["hypotheses"][0]["budget"]["token"] = -1
        self.assertTrue(any("non-negative" in error for error in validate_research_portfolio(record)))

    def test_missing_hypothesis_kind_is_rejected(self):
        record = portfolio()
        record["hypotheses"] = record["hypotheses"][:2]
        self.assertTrue(any("moonshot" in error for error in validate_research_portfolio(record)))

    def test_empty_evidence_requires_unverified_or_research_needed_and_external_cannot_promote(self):
        record = portfolio()
        record["hypotheses"][2]["status"] = "active"
        self.assertTrue(any("empty evidenceRefs" in error for error in validate_research_portfolio(record)))
        record = portfolio()
        record["sourceLedger"] = [source("https://example.invalid", "untrusted_external_evidence", "external_url", "advisory_only")]
        record["hypotheses"][0]["currentEvidenceRefs"] = ["https://example.invalid"]
        record["hypotheses"][0]["status"] = "promoted"
        self.assertTrue(any("cannot promote" in error for error in validate_research_portfolio(record)))

    def test_empty_source_pre_research_and_empty_dependencies_are_valid(self):
        record = portfolio()
        record["sourceLedger"] = []
        for item in record["hypotheses"]:
            item["currentEvidenceRefs"] = []
            item["status"] = "research_needed"
            item["dependencies"] = []
            item["risks"] = []
        self.assertEqual(validate_research_portfolio(record), [])

    def test_github_and_docs_source_types_are_external(self):
        record = portfolio()
        record["sourceLedger"] = [source("https://example.invalid/docs", "trusted_local", "docs")]
        self.assertTrue(any("untrusted_external_evidence" in error for error in validate_research_portfolio(record)))
        record["sourceLedger"] = [source("https://example.invalid/github", "trusted_local", "github")]
        self.assertTrue(any("untrusted_external_evidence" in error for error in validate_research_portfolio(record)))

    def test_saturation_routes_require_two_signals_and_hard_stops(self):
        base = {"repeatedRootCause": False, "renamedHypothesis": False, "metricStalled": False, "budgetBurning": False, "sharedUnverifiedPremise": False, "lowMarginalGainCount": 0}
        self.assertEqual(route_saturation(base)["selectedAction"], "continue")
        two = dict(base, repeatedRootCause=True, metricStalled=True)
        self.assertEqual(route_saturation(two)["selectedAction"], "broaden_search")
        self.assertEqual(route_saturation(base, budget_exhausted=True)["selectedAction"], "stop")
        record = portfolio()
        record["saturationSignals"] = two
        record["selectedAction"] = "broaden_search"
        self.assertEqual(validate_research_portfolio(record), [])
        record["saturationSignals"] = dict(base, repeatedRootCause=True)
        self.assertTrue(any("deterministic route" in error for error in validate_research_portfolio(record)))
        record["saturationSignals"] = two
        record["selectedAction"] = "continue"
        self.assertTrue(any("deterministic route" in error for error in validate_research_portfolio(record)))

    def test_unknown_task_and_tasks_bytes_are_preserved(self):
        with workspace_tempdir("research-task-binding-") as temporary:
            workspace = make_workspace(Path(temporary))
            path = workspace / "MissionCenter/tasks.md"
            before = path.read_bytes()
            self.assertTrue(any("canonical tasks.md" in error for error in validate_research_portfolio(portfolio("UNKNOWN"), workspace)))
    def test_research_rejects_secret_injection_and_schema_description_locks_total(self):
        schema_path = ROOT / "skills" / "mission-center" / "schemas" / "research-portfolio.schema.json"
        import json
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        desc = schema["properties"]["initialHypothesisAllocation"].get("description", "")
        self.assertIn("Total sum must equal 100", desc)
        self.assertIn("Python semantic validator", desc)

        record = portfolio()
        record["sourceLedger"][0]["provenance"] = "contains token ghp_123456789012345678901234567890123456"
        errors = validate_research_portfolio(record)
        self.assertTrue(any("contains secret-like content" in error for error in errors))

        record_key = portfolio()
        record_key["secret"] = "hidden_value"
        errors_key = validate_research_portfolio(record_key)
        self.assertTrue(any("forbidden privacy content" in error for error in errors_key))


if __name__ == "__main__":
    unittest.main()
