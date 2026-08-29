"""Static policy checks for the native Windows platform selector."""

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SELECTOR = ROOT / "bin" / "mission-center.ps1"


class WindowsSelectorPolicyTests(unittest.TestCase):
    def setUp(self):
        self.source = SELECTOR.read_text(encoding="utf-8")
        self.code = "\n".join(
            line for line in self.source.splitlines() if not line.lstrip().startswith("#")
        ).lower()

    def test_selector_validates_local_manifests_and_windows_artifact(self):
        for token in (
            "platform-manifest.json",
            ".codex-plugin\\plugin.json",
            "convertfrom-json",
            "windows-x86_64",
            "four artifacts",
            "plugin/manifest version mismatch",
            "selected platform artifact is invalid",
            "selected binary is missing",
            "get-filehash",
            "checksum mismatch",
            "& $binary @args",
        ):
            self.assertIn(token.lower(), self.code)

    def test_selector_fails_closed_without_download_or_alternate_runtime(self):
        for forbidden in ("python", "curl", "wget", "cargo", "pip", "npm", "invoke-webrequest", "start-bitstransfer"):
            self.assertNotIn(forbidden, self.code)
        self.assertNotRegex(self.code, r"(set-content|out-file|add-content|remove-item|copy-item|move-item)")
        hooks = (ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        self.assertIn("mission-center.ps1", hooks)
        self.assertNotIn("windows-x86_64\\\\mission-center.exe\" hook", hooks)


if __name__ == "__main__":
    unittest.main()
