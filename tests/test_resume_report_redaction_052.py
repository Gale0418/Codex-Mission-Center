"""Focused regressions for resume validation/report redaction boundaries."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from verify_upgrade_052 import (  # noqa: E402
    _bounded_resume_string_bytes,
    _redact_report_paths,
    invoke,
    resume_contract_valid,
)


def _resume_packet(files_read: list[str]) -> dict:
    data = {
        "schemaVersion": "1.1",
        "route": "resume",
        "sourceFresh": True,
        "dateFresh": True,
        "staleReasons": [],
        "filesRead": files_read,
        "content": {
            "handoff": None,
            "brief": "brief",
            "workingSet": "work",
            "activeCriticalLessons": "",
            "snapshot": None,
        },
        "handoff": None,
        "ledgerStatus": "missing",
        "ledgerError": None,
        "context": {"includedBytes": {"brief": 5, "workingSet": 4}},
        "bytes": 0,
        "maxBytes": 16384,
        "canonicalFallback": False,
        "fallbackReason": None,
        "truncated": False,
        "truncatedMarker": None,
        "readNext": [],
    }
    return {"exitCode": 0, "envelope": {"data": data}, "stderr": ""}


def _set_declared_bytes(result: dict) -> None:
    data = result["envelope"]["data"]
    for _ in range(16):
        measured = _bounded_resume_string_bytes(data)
        if measured is None:
            raise AssertionError("fixture unexpectedly exceeded budget")
        if data["bytes"] == measured:
            return
        data["bytes"] = measured
    raise AssertionError("resume byte declaration did not converge")


class ResumeReportRedactionTests(unittest.TestCase):
    def test_invoke_preserves_raw_fixture_path_for_validation(self):
        with tempfile.TemporaryDirectory(prefix="mc-052-raw-invoke-") as temporary:
            root = Path(temporary)
            binary = root / "fake-cli"
            binary.write_text(
                "#!/usr/bin/env python3\n"
                "import json,sys\n"
                "root=sys.argv[sys.argv.index('--root')+1]\n"
                "print(json.dumps({'data': {'filesRead': [root]}}))\n",
                encoding="utf-8",
            )
            binary.chmod(0o700)
            result = invoke(binary, root, "resume")
            self.assertEqual(result["envelope"]["data"]["filesRead"], [str(root)])

    def test_oversized_raw_path_packet_cannot_pass_after_report_redaction(self):
        with tempfile.TemporaryDirectory(prefix="mc-052-redaction-budget-") as temporary:
            root = Path(temporary)
            raw = _resume_packet([str(root) * 500])

            # Model the old bug: redact first, then make that shrunken copy
            # internally self-consistent. It is valid only after redaction.
            redacted = _redact_report_paths(raw, root)
            _set_declared_bytes(redacted)
            self.assertTrue(resume_contract_valid(redacted))

            # Copy the shrunken declaration back into the actual candidate
            # response. Raw validation must reject the >16 KiB public packet.
            raw["envelope"]["data"]["bytes"] = redacted["envelope"]["data"]["bytes"]
            self.assertFalse(resume_contract_valid(raw))

    def test_report_redaction_removes_fixture_paths_without_changing_source(self):
        with tempfile.TemporaryDirectory(prefix="mc-052-redaction-copy-") as temporary:
            root = Path(temporary)
            source = {"value": str(root), "nested": [f"prefix:{root}:suffix"]}
            redacted = _redact_report_paths(source, root)
            self.assertEqual(source["value"], str(root))
            self.assertNotIn(str(root), str(redacted))
            self.assertIn("<fixture>", str(redacted))


if __name__ == "__main__":
    unittest.main()
