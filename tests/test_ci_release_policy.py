import base64
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def release_job(workflow: str) -> str:
    marker = "  rust-release:\n"
    start = workflow.index(marker)
    end = workflow.find("\n  rust-stable-package:\n", start)
    return workflow[start:] if end == -1 else workflow[start:end]


def stable_package_job(workflow: str) -> str:
    marker = "  rust-stable-package:\n"
    return workflow[workflow.index(marker) :]


class CiReleasePolicyTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")
        self.release = release_job(self.workflow)
        self.stable = stable_package_job(self.workflow)

    def test_release_matrix_covers_real_runner_target_pairs(self):
        expected = {
            "windows-x86_64": ("windows-latest", "x86_64-pc-windows-msvc", "mission-center.exe", "true"),
            "linux-x86_64": ("ubuntu-latest", "x86_64-unknown-linux-gnu", "mission-center", "true"),
            "macos-x86_64": (
                "macos-15-intel",
                "x86_64-apple-darwin",
                "mission-center",
                "true",
            ),
            "macos-aarch64": (
                "macos-15",
                "aarch64-apple-darwin",
                "mission-center",
                "conditional",
            ),
        }
        blocks = re.split(r"(?=          - variant: )", self.release)
        actual = {}
        for block in blocks:
            match = re.search(r"^          - variant: ([^\n]+)", block, re.MULTILINE)
            if not match:
                continue
            variant = match.group(1).strip()
            actual[variant] = tuple(
                re.search(rf"^            {field}: ([^\n]+)", block, re.MULTILINE).group(1).strip()
                for field in ("runner", "target", "binary", "smoke")
            )
        self.assertEqual(actual, expected)
        self.assertIn("runs-on: ${{ matrix.runner }}", self.release)

    def test_test_aggregator_requires_every_release_matrix_job(self):
        self.assertIn("needs: [python, rust, rust-release, rust-stable-package]", self.workflow)
        self.assertIn('needs.rust-release.result', self.workflow)
        self.assertIn('test "${{ needs.rust-release.result }}" = "success"', self.workflow)
        self.assertIn('test "${{ needs.rust-stable-package.result }}" = "success"', self.workflow)

    def test_release_is_pinned_locked_offline_and_has_no_fallback_or_python(self):
        self.assertIn("toolchain install 1.98.0 --profile minimal", self.release)
        self.assertIn("cargo metadata --locked --offline", self.release)
        self.assertIn(
            "cargo build --release --package mission-center-cli --target \"$RELEASE_TARGET\" --locked --offline",
            self.release,
        )
        self.assertNotIn("download-artifact", self.release)
        self.assertNotRegex(self.release, r"\b(curl|wget|python(?:3)?|pip)\b")
        self.assertIn("target list --toolchain 1.98.0 --installed", self.release)
        self.assertIn('echo "available=false"', self.release)
        self.assertIn("cross-build unavailable", self.release)
        self.assertIn("if: always() && steps.target.outputs.available != 'true'", self.release)
        for command in re.findall(r"cargo build[^\n]*", self.release):
            self.assertIn("--locked", command)
            self.assertIn("--offline", command)

    def test_release_checks_magic_checksum_manifest_and_retention(self):
        for phrase in (
            "Check release binary architecture magic",
            'magic=\"$(od -An -tx1 -N4 \"$binary\" | tr -d \' \\n\')\"',
            "hash_file()",
            "sha256sum \"$1\"",
            "shasum -a 256 \"$1\"",
            "checksum-manifest.json",
            "mission-center-smoke",
            '\"smoke\":\"$smoke\"',
            "actions/upload-artifact@",
            "retention-days: 14",
        ):
            self.assertIn(phrase, self.release)
        for magic in ("4d5a", "7f454c46", "cffaedfe", "01000007", "0100000c"):
            self.assertIn(magic, self.release)

    def test_release_and_stable_package_require_clean_checkouts_and_exact_artifacts(self):
        for job in (self.release, self.stable):
            self.assertIn("Require clean source checkout", job)
            self.assertIn("git status --porcelain=v1 --untracked-files=all", job)
            self.assertIn("git diff --cached --quiet", job)
            self.assertIn("git diff --quiet", job)
        self.assertIn(
            "release artifact set is not exactly the four expected platforms",
            self.stable,
        )
        self.assertIn("validate_artifact_layout", self.stable)
        self.assertIn("unexpected files in $variant artifact", self.stable)

    def test_smoke_is_read_only_and_arm_capability_is_explicitly_unknown(self):
        for phrase in (
            '"$binary" runtime capability',
            'runtime_rc=0',
            'test "$runtime_rc" -eq 0',
            'jq -e \'. | type == "object"',
            'jq -e --arg version "$RELEASE_VERSION"',
            'test "$publish_rc" -eq 0',
            'jq -e --arg variant "$RELEASE_VARIANT"',
            '.data.mode == "capability"',
            'publish verify --platform "$RELEASE_VARIANT" --version "$RELEASE_VERSION"',
            "ci/fixtures/publish-verify.json",
            'before=\"$(git status --porcelain)\"',
            'test \"$before\" = \"$(git status --porcelain)\"',
            'smoke=\"unknown\"',
            'echo \"macos-aarch64 smoke=unknown',
            '$(uname -m)',
            "Record unavailable target as explicit unknown",
        ):
            self.assertIn(phrase, self.release)

    def test_stable_gate_assembles_real_matrix_artifacts_and_fails_closed(self):
        self.assertIn("needs: [rust-release]", self.stable)
        self.assertIn("if: always()", self.stable)
        self.assertIn("fetch-depth: 0", self.stable)
        for phrase in (
            "actions/download-artifact@",
            "merge-multiple: false",
            "continue-on-error: true",
            "Require explicit historical replay evidence",
            'historicalReplay.status == "pass"',
            'historicalReplay.status == "unknown"',
            'unknown evidence may not be promoted to pass',
            'git cat-file -e "$revision^{commit}"',
            'status == "unknown"',
            'stable package blocked: missing artifact',
            'stable package blocked: checksum manifest mismatch',
            'frozen-package-v1',
            'publish verify --platform linux-x86_64 --version "$RELEASE_VERSION" --input -',
            'install register apply --plugin-root "$registration_root/plugins/mission-center"',
            'install register reconcile --marketplace-root "$registration_root"',
            'install register rollback --receipt "$registration_receipt"',
            'data.registered == true',
            '.command == "install"',
            '.data.receipt.version == $version',
            'data.receipt.status == "rolledback"',
            'install apply --package "$package_root" --destination "$install_root" --operation-id stable-install-smoke',
            'data.mutationSupported == true',
            'data.receipt.status == "committed"',
            'publish apply --package "$package_root" --destination "$publish_root" --operation-id stable-publish-smoke',
            '.command == "publish"',
            '.data.published == true',
            'install reconcile --root "$RUNNER_TEMP"',
            '.data.reconciled == true',
            'select(.status == "committed")',
            'jq -e --arg version "$RELEASE_VERSION" \'type == "object" and .name == "mission-center" and .version == $version\'',
            'stable package blocked: root plugin manifest must be version $RELEASE_VERSION',
            'mission-center-python-oracle-boundary',
            'stable package blocked: Python oracle boundary manifest is missing or permits formal runtime',
            'sha256sum "$binary_path"',
            '(.artifacts | length == 4)',
            'test "$fail" -eq 0',
            'bin/windows-x86_64/mission-center.exe',
            'bin/linux-x86_64/mission-center',
            'bin/macos-x86_64/mission-center',
            'bin/macos-aarch64/mission-center',
            'add_file bin/mission-center bin/mission-center true',
            'add_file bin/mission-center.ps1 bin/mission-center.ps1 false',
            'any(.files[]; .path == "bin/mission-center.ps1" and .executable == false)',
        ):
            self.assertIn(phrase, self.stable)
        self.assertNotRegex(self.stable, r"\b(curl|wget|pip)\b")
        self.assertNotIn("[.tasks[].historicalReplay.revision] | unique", self.stable)
        self.assertIn("formal plugin inputs still invoke Python runtime", self.stable)
        self.assertIn('if [ "$item" = "scripts" ]; then', self.stable)
        self.assertIn("*.py|*.pyc|*.pyo", self.stable)
        self.assertIn('startswith("scripts/")', self.stable)
        self.assertIn('startswith("compat/")', self.stable)
        self.assertIn('requirements-runtime.txt', self.stable)
        self.assertIn('.codex-plugin/release-preview.json', self.stable)
        self.assertIn('.codex-plugin/release-preview.json) continue', self.stable)
        self.assertIn('for item in README.md LICENSE NOTICE.md PRIVACY.md; do', self.stable)
        self.assertNotRegex(self.stable, r"\n\s*run:\s*python(?:3)?\b")

    def test_publish_policy_has_missing_wrong_arch_corrupt_and_zero_write_gates(self):
        source = (ROOT / "rust" / "mission-center-publish" / "tests" / "wave4_publish.rs").read_text(
            encoding="utf-8"
        )
        for marker in (
            "manifest_is_strict_four_platform_and_semver_two",
            "corrupt_other",
            "missing_other",
            "wrong_arch",
            "preflight_failures_are_zero_write",
        ):
            self.assertIn(marker, source)
        native_install = (ROOT / "rust" / "mission-center-publish" / "tests" / "native_install.rs").read_text(
            encoding="utf-8"
        )
        for marker in ("native_install_replays_and_rolls_back_a_verified_package", "tampered_destination"):
            self.assertIn(marker, native_install)
        publish_source = (ROOT / "rust" / "mission-center-publish" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("native_publish_package", publish_source)
        self.assertIn("native_reconcile_transactions", publish_source)
        self.assertIn("native_register_marketplace", publish_source)
        self.assertIn("native_reconcile_registrations", publish_source)

    def test_publish_fixture_is_four_platform_and_content_is_decodable(self):
        fixture = json.loads(
            (ROOT / "rust" / "ci" / "fixtures" / "publish-verify.json").read_text(encoding="utf-8")
        )
        self.assertEqual(fixture["format"], "frozen-package-v1")
        files = {item["path"]: item for item in fixture["files"]}
        manifest = json.loads(
            base64.b64decode(files["platform-manifest.json"]["contentBase64"]).decode("utf-8")
        )
        self.assertEqual(
            {item["platform"] for item in manifest["artifacts"]},
            {"windows-x86_64", "linux-x86_64", "macos-x86_64", "macos-aarch64"},
        )
        for item in fixture["files"]:
            self.assertTrue(base64.b64decode(item["contentBase64"]))


if __name__ == "__main__":
    unittest.main()
