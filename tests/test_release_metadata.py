import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_rust_stable_manifest_is_explicit_and_installable(self):
        manifest = json.loads(
            (ROOT / ".codex-plugin" / "release.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["schemaVersion"], "1.0")
        self.assertEqual(manifest["kind"], "mission-center-release")
        self.assertEqual(manifest["pluginName"], "mission-center")
        self.assertEqual(manifest["version"], "0.5.1")
        self.assertEqual(manifest["releaseStage"], "stable")
        self.assertEqual(manifest["runtime"], "rust")
        self.assertTrue(manifest["rustOnly"])
        self.assertTrue(manifest["installable"])
        self.assertTrue(manifest["rollback"]["supported"])
        self.assertTrue(manifest["rollback"]["receiptBound"])
        self.assertTrue(manifest["rollback"]["reconcileDeliveryUnknown"])

    def test_rust_stable_selector_is_four_platform_and_fail_closed(self):
        manifest = json.loads(
            (ROOT / ".codex-plugin" / "release.json").read_text(
                encoding="utf-8"
            )
        )
        selector = manifest["selector"]
        self.assertEqual(selector["manifest"], "platform-manifest.json")
        self.assertEqual(len(selector["platforms"]), 4)
        self.assertEqual(
            set(selector["platforms"]),
            {
                "windows-x86_64",
                "linux-x86_64",
                "macos-x86_64",
                "macos-aarch64",
            },
        )
        verification = manifest["verification"]
        self.assertEqual(verification["packageFormat"], "frozen-package-v1")
        self.assertEqual(verification["checksum"], "sha256")
        self.assertEqual(verification["network"], "offline")
        self.assertEqual(verification["fallback"], "none")

    def test_plugin_privacy_policy_uses_privacy_document(self):
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        url = manifest["interface"]["privacyPolicyURL"]
        self.assertTrue(url.endswith("/PRIVACY.md"))
        self.assertTrue((ROOT / "PRIVACY.md").is_file())

    def test_plugin_version_is_v05_release(self):
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.5.1")

    def test_stable_release_identity_matches_root_plugin(self):
        plugin = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        release = json.loads((ROOT / ".codex-plugin" / "release.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], release["version"])
        self.assertFalse((ROOT / ".codex-plugin" / "release-preview.json").exists())

    def test_stable_release_has_sbom_notes_and_rollback_guidance(self):
        sbom = json.loads((ROOT / "docs" / "SBOM.spdx.json").read_text(encoding="utf-8"))
        self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
        self.assertEqual(sbom["name"], "mission-center-0.5.1")
        packages = {(item["name"], item["versionInfo"]) for item in sbom["packages"]}
        lock = tomllib.loads((ROOT / "rust" / "Cargo.lock").read_text(encoding="utf-8"))
        external = {
            (item["name"], item["version"])
            for item in lock["package"]
            if not item["name"].startswith("mission-center-")
        }
        self.assertEqual(external, packages - {("mission-center", "0.5.1")})
        release_notes = (ROOT / "docs" / "releases" / "0.5.1.md").read_text(encoding="utf-8")
        self.assertIn("DELIVERY", release_notes.upper())
        self.assertIn("rollback", release_notes.casefold())
        self.assertTrue((ROOT / "docs" / "rust-maintainability-audit-0.5.1.md").is_file())

    def test_python_oracle_boundary_is_explicit_and_non_runtime(self):
        boundary = json.loads(
            (ROOT / "compat" / "python-oracle" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(boundary["kind"], "mission-center-python-oracle-boundary")
        self.assertFalse(boundary["formalPluginIncluded"])
        self.assertEqual(
            boundary["compatibilityOptIn"],
            {
                "environmentVariable": "MISSION_CENTER_PYTHON_COMPAT",
                "requiredValue": "1",
                "failureMode": "fail-closed",
                "remediation": "Use an already-built and locally verified Rust package/binary for formal installation.",
            },
        )
        self.assertEqual(len(boundary["wrapperEntrypoints"]), 6)
        for entrypoint in boundary["wrapperEntrypoints"]:
            source = (ROOT / entrypoint).read_text(encoding="utf-8").casefold()
            self.assertIn("mission_center_python_compat", source)
            self.assertIn("verified rust package", source)
        self.assertEqual(
            set(boundary["sourceRoots"]),
            {"skills/mission-center/scripts", "scripts"},
        )
        self.assertIn("formal-plugin-runtime", boundary["exclusions"])
        self.assertIn("stable-package", boundary["exclusions"])

    def test_plugin_default_prompt_has_at_most_three_entries(self):
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertLessEqual(len(prompts), 3)
        self.assertTrue(all(isinstance(prompt, str) and prompt.strip() for prompt in prompts))

    def test_readme_does_not_end_with_test_marker(self):
        lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
        self.assertNotEqual(lines[-1].strip(), "123")


if __name__ == "__main__":
    unittest.main()
