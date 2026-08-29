import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCHEMAS = ROOT / "skills" / "mission-center" / "schemas"


class MachineContractTests(unittest.TestCase):
    def test_versioned_json_schemas_exist_and_parse(self):
        expected = {
            "project-profile.schema.json",
            "optimization-decision.schema.json",
            "experiment-manifest.schema.json",
            "experiment-result.schema.json",
            "agent-event.schema.json",
            "runtime-state.schema.json",
            "provider-capabilities.schema.json",
            "execution-pulse.schema.json",
            "steelman-evolution.schema.json",
            "research-portfolio.schema.json",
            "shift-loss-eval.schema.json",
            "evidence-envelope.schema.json",
            "project-map.schema.json",
            "hud-side-panel.schema.json",
        }
        self.assertEqual({path.name for path in SCHEMAS.glob("*.json")}, expected)
        for path in SCHEMAS.glob("*.json"):
            with self.subTest(path=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(schema["type"], "object")

    def test_core_does_not_import_optional_websocket_dependency(self):
        core = (ROOT / "skills/mission-center/scripts/runtime_protocol.py").read_text(encoding="utf-8")
        adapter = (ROOT / "skills/mission-center/scripts/mission_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("import websockets", core)
        self.assertIn("from websockets.asyncio.client import connect", adapter)
        self.assertIn("except ImportError", adapter)

    def test_runtime_schema_exposes_privacy_safe_activity_kind_without_location(self):
        runtime = json.loads((SCHEMAS / "runtime-state.schema.json").read_text(encoding="utf-8"))
        agent_properties = runtime["properties"]["agents"]["items"]["properties"]
        self.assertIn("activityKind", agent_properties)
        self.assertNotIn("location", agent_properties)
        self.assertEqual(agent_properties["startedAt"]["format"], "date-time")
        self.assertEqual(agent_properties["lastSeenAt"]["format"], "date-time")
        self.assertEqual(agent_properties["sequence"]["minimum"], 0)
        event = json.loads((SCHEMAS / "agent-event.schema.json").read_text(encoding="utf-8"))
        self.assertIn("activityKind", event["properties"])
        self.assertNotIn("location", event["properties"])


if __name__ == "__main__":
    unittest.main()
