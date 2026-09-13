"""Execute every representative CLI envelope against the checked-in JSON schema."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import native_binary_matches_host


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "rust" / "mission-center-cli" / "schemas" / "cli-envelope.schema.json"


def _binary() -> Path | None:
    configured = os.environ.get("MISSION_CENTER_RUST_BIN")
    if configured and native_binary_matches_host(Path(configured)):
        return Path(configured)
    for candidate in (
        ROOT / "rust" / "target" / "debug" / "mission-center.exe",
        ROOT / "rust" / "target" / "debug" / "mission-center",
    ):
        if native_binary_matches_host(candidate):
            return candidate
    return None


class NativeBinaryMagicTests(unittest.TestCase):
    def test_selector_rejects_cross_platform_binary_magic(self):
        with tempfile.TemporaryDirectory(prefix="mission-center-binary-magic-") as temporary:
            root = Path(temporary)
            pe = bytearray(128)
            pe[:2] = b"MZ"
            pe[0x3C:0x40] = (64).to_bytes(4, "little")
            pe[64:68] = b"PE\0\0"
            pe[68:70] = (0x8664).to_bytes(2, "little")
            windows = root / "mission-center.exe"
            windows.write_bytes(pe)
            elf = bytearray(128)
            elf[:6] = b"\x7fELF\x02\x01"
            elf[18:20] = (62).to_bytes(2, "little")
            linux = root / "mission-center"
            linux.write_bytes(elf)
            macho = bytearray(128)
            macho[:4] = b"\xcf\xfa\xed\xfe"
            macho[4:8] = (0x01000007).to_bytes(4, "little")
            macos = root / "mission-center-macos"
            macos.write_bytes(macho)

            fat = bytearray(8 + 40)
            fat[:4] = b"\xca\xfe\xba\xbe"
            fat[4:8] = (2).to_bytes(4, "big")
            fat[8:12] = (0x01000007).to_bytes(4, "big")
            fat[28:32] = (0x0100000C).to_bytes(4, "big")
            universal = root / "mission-center-universal"
            universal.write_bytes(fat)

            self.assertTrue(native_binary_matches_host(windows, "win32", "x86_64"))
            self.assertFalse(native_binary_matches_host(windows, "win32", "aarch64"))
            self.assertFalse(native_binary_matches_host(linux, "win32", "x86_64"))
            self.assertTrue(native_binary_matches_host(linux, "linux", "x86_64"))
            self.assertFalse(native_binary_matches_host(linux, "linux", "aarch64"))
            self.assertFalse(native_binary_matches_host(windows, "linux", "x86_64"))
            self.assertTrue(native_binary_matches_host(macos, "darwin", "x86_64"))
            self.assertFalse(native_binary_matches_host(macos, "darwin", "aarch64"))
            self.assertTrue(native_binary_matches_host(universal, "darwin", "x86_64"))
            self.assertTrue(native_binary_matches_host(universal, "darwin", "aarch64"))


@unittest.skipUnless(_binary() is not None, "Rust CLI binary unavailable")
class RustCliSchemaTests(unittest.TestCase):
    def test_representative_envelopes_validate_with_jsonschema(self):
        try:
            import jsonschema
        except ImportError as exc:  # pragma: no cover - environment dependent
            self.skipTest(f"jsonschema unavailable: {exc}")
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        binary = _binary()
        assert binary is not None
        with tempfile.TemporaryDirectory(prefix="mission-center-cli-abi-") as temporary:
            root = Path(temporary)
            mission = root / "MissionCenter"
            mission.mkdir()
            (mission / "tasks.md").write_text(
                "| ID | Title | Status |\n| --- | --- | --- |\n| ABI-1 | ABI | Ready |\n",
                encoding="utf-8",
            )
            commands = [
                ["status", "--root", str(root)],
                ["resume", "--root", str(root)],
                ["reconcile", "--root", str(root)],
                ["doctor", "--root", str(root)],
                [
                    "transition",
                    "ABI-1",
                    "In Progress",
                    "--operation-id",
                    "abi-transition",
                    "--timestamp",
                    "2026-08-29T13:40:00Z",
                    "--root",
                    str(root),
                ],
                ["runtime", "capability"],
                ["hud", "capability"],
                ["publish", "--operation-id", "abi"],
                [
                    "publish",
                    "verify",
                    "--version",
                    "0.5.2",
                    "--platform",
                    "windows-x86_64",
                ],
            ]
            for argv in commands:
                completed = subprocess.run(
                    [os.fspath(binary), *argv],
                    cwd=os.fspath(ROOT),
                    input=b"",
                    capture_output=True,
                    check=False,
                    timeout=15,
                )
                self.assertEqual(completed.stderr, b"", argv)
                payload = json.loads(completed.stdout.decode("utf-8"))
                validator.validate(payload)
                self.assertIn(completed.returncode, (0, 1, 2), argv)
