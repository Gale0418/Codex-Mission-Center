import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_plugin_privacy_policy_uses_privacy_document(self):
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        url = manifest["interface"]["privacyPolicyURL"]
        self.assertTrue(url.endswith("/PRIVACY.md"))
        self.assertTrue((ROOT / "PRIVACY.md").is_file())

    def test_plugin_version_is_final_maintenance_patch(self):
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.3.1")

    def test_readme_does_not_end_with_test_marker(self):
        lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
        self.assertNotEqual(lines[-1].strip(), "123")


if __name__ == "__main__":
    unittest.main()
