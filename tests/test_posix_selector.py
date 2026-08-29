"""Static policy checks for the native POSIX platform selector."""

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SELECTOR = ROOT / "bin" / "mission-center"


class PosixSelectorPolicyTests(unittest.TestCase):
    def setUp(self):
        self.source = SELECTOR.read_text(encoding="utf-8")
        self.code = "\n".join(
            line for line in self.source.splitlines() if not line.lstrip().startswith("#")
        ).lower()

    def test_selector_is_posix_and_covers_supported_host_pairs(self):
        self.assertTrue(self.source.startswith("#!/bin/sh\n"))
        for token in ("linux-x86_64", "macos-x86_64", "macos-aarch64"):
            self.assertIn(token, self.source)
        self.assertIn('selector_platform="$selector_os-$selector_arch"', self.source)
        self.assertIn('bin/" + $platform + "/mission-center', self.source)
        self.assertIn('if $platform == "windows-x86_64" then ".exe"', self.source)

    def test_selector_requires_local_verification_and_fails_closed(self):
        for token in (
            'command -v jq',
            'platform-manifest.json',
            '.codex-plugin/plugin.json',
            'plugin/manifest version mismatch',
            'selected binary is missing',
            'checksum mismatch',
            'exec "$binary" "$@"',
        ):
            self.assertIn(token.lower(), self.code)
        self.assertIn('type != "object"', self.code)
        self.assertNotIn('.type != "object"', self.code)

    def test_selector_has_no_download_build_or_python_fallback(self):
        for forbidden in ("python", "curl", "wget", "cargo", "pip", "npm"):
            self.assertNotIn(forbidden, self.code)
        # No shell file-writing primitive is allowed in the selector; the
        # diagnostic/null redirections above are read-only.
        self.assertNotRegex(self.code, r"(^|[;\n])[ \t]*(rm|mv|cp|mkdir|install)[ \t]")
        self.assertNotRegex(self.code, r">[ \t]*[^/&][^\n]*")


if __name__ == "__main__":
    unittest.main()
