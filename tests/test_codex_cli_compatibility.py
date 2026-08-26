import json
import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MATRIX = ROOT / "skills" / "mission-center" / "references" / "codex-cli-plugin-compatibility-matrix.json"
PUBLISHER = ROOT / "scripts" / "publish_local.py"
sys.path.insert(0, str(ROOT / "skills" / "mission-center" / "scripts"))

from validate_codex_cli_compatibility import validate_matrix


class CodexCliCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
        cls.publisher_source = PUBLISHER.read_text(encoding="utf-8")

    def test_matrix_is_machine_readable_and_covers_mc044_surfaces(self):
        self.assertEqual(validate_matrix(self.matrix), [])
        self.assertEqual(self.matrix["schemaVersion"], "1.0")
        self.assertEqual(self.matrix["spike"], "MC-044")
        surfaces = {entry["surface"] for entry in self.matrix["matrix"]}
        self.assertEqual(
            surfaces,
            {
                "installation",
                "version-and-help",
                "plugin-search-and-list",
                "plugin-install-and-reload",
                "update-and-reinstall",
                "offline-fallback",
            },
        )

    def test_matrix_has_official_sources_and_honest_unverified_states(self):
        self.assertGreaterEqual(len(self.matrix["officialSources"]), 3)
        topics = {source["topic"] for source in self.matrix["officialSources"]}
        self.assertEqual(
            topics,
            {"cli-install-and-update", "plugin-browser", "hooks-and-background-output"},
        )
        for source in self.matrix["officialSources"]:
            self.assertIn(source["url"].split("://", 1)[1].split("/", 1)[0], {"learn.chatgpt.com", "developers.openai.com"})
        statuses = {entry["status"] for entry in self.matrix["matrix"]}
        self.assertIn("blocked-local", statuses)
        self.assertIn("officially-documented-local-unverified", statuses)
        self.assertIn("officially-documented-not-executed", statuses)

    def test_matrix_validator_rejects_missing_probe_fields_and_unknown_status(self):
        missing = copy.deepcopy(self.matrix)
        missing["probeRecords"][0].pop("evidenceLocator")
        self.assertTrue(any("evidenceLocator" in error for error in validate_matrix(missing)))

        invalid = copy.deepcopy(self.matrix)
        invalid["matrix"][0]["status"] = "locally-green"
        self.assertTrue(any("status has an invalid value" in error for error in validate_matrix(invalid)))

    def test_probe_records_are_bounded_and_free_of_sensitive_path_data(self):
        self.assertGreaterEqual(len(self.matrix["probeRecords"]), 4)
        for record in self.matrix["probeRecords"]:
            self.assertLessEqual(len(record["command"]), 256)
            self.assertNotRegex(record["command"].casefold(), r"password|token|secret|api[_-]?key")
            self.assertRegex(record["evidenceLocator"], r"^[^/\\][^\\]*$")
            self.assertIn(record["resultCategory"], {"pass", "blocked", "not-executed", "local-unverified"})

    def test_publisher_preserves_offline_no_cli_fallback_boundary(self):
        self.assertIn('mode.add_argument("--dry-run"', self.publisher_source)
        self.assertIn('mode.add_argument("--verify"', self.publisher_source)
        self.assertIn('parser.add_argument("--register"', self.publisher_source)
        self.assertIn("if register:", self.publisher_source)
        self.assertIn("Codex executable not found", self.publisher_source)
        self.assertIn("if args.register and codex_executable is not None:", self.publisher_source)
        self.assertNotIn("pip install", self.publisher_source.casefold())
        self.assertNotIn("npm install", self.publisher_source.casefold())

    def test_local_probe_records_store_install_and_access_block(self):
        probe = self.matrix["localProbe"]
        self.assertIn("OpenAI.Codex_", probe["observedPath"])
        self.assertEqual(probe["cliExecution"], "blocked")
        self.assertEqual(probe["wslShell"], "available")
        self.assertIn("command -v codex", probe["wslShellEvidence"])
        self.assertEqual(probe["wslExecution"], "cli-permission-denied")
        self.assertIn("Permission denied", probe["wslExecutionEvidence"])
        self.assertIn("publish_local.py --help", probe["nonDestructiveProbe"])


if __name__ == "__main__":
    unittest.main()
