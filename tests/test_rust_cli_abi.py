"""Execute every representative CLI envelope against the checked-in JSON schema."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "rust" / "mission-center-cli" / "schemas" / "cli-envelope.schema.json"


def _binary() -> Path | None:
    configured = os.environ.get("MISSION_CENTER_RUST_BIN")
    if configured and Path(configured).is_file():
        return Path(configured)
    for candidate in (
        ROOT / "rust" / "target" / "debug" / "mission-center.exe",
        ROOT / "rust" / "target" / "debug" / "mission-center",
    ):
        if candidate.is_file():
            return candidate
    return None


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
                    "0.5.1",
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
