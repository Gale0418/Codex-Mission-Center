"""Adversarial local probes for the test runner itself (no CI/provider calls)."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from bounded_process import run_bounded  # noqa: E402
from verify_upgrade_052 import check_status, resume_contract_valid  # noqa: E402


@unittest.skipUnless(os.name == "posix", "POSIX process-tree containment is required")
class BoundedProcessTests(unittest.TestCase):
    def run_python(self, code: str, *, limit: int = 1024, timeout: float = 2.0):
        return run_bounded([sys.executable, "-c", code], timeout=timeout, max_output_bytes=limit)

    def test_exact_per_stream_limit_is_allowed(self):
        rc, out, err = self.run_python("import os; os.write(1,b'x'*16); os.write(2,b'y'*16)", limit=16)
        self.assertEqual((rc, out, err), (0, b"x" * 16, b"y" * 16))

    def test_zero_limit_allows_silent_process(self):
        self.assertEqual(self.run_python("pass", limit=0), (0, b"", b""))

    def test_stdout_overflow_is_stopped(self):
        with self.assertRaisesRegex(RuntimeError, "stdout exceeded"):
            self.run_python("import os\nwhile True: os.write(1,b'x'*8192)", limit=256)

    def test_stderr_overflow_is_stopped(self):
        with self.assertRaisesRegex(RuntimeError, "stderr exceeded"):
            self.run_python("import os\nwhile True: os.write(2,b'x'*8192)", limit=256)

    def test_both_streams_cannot_deadlock(self):
        with self.assertRaisesRegex(RuntimeError, "exceeded"):
            self.run_python("import os\nwhile True:\n os.write(1,b'x'*128)\n os.write(2,b'y'*128)", limit=256)

    def test_nonzero_exit_is_not_hidden(self):
        self.assertEqual(self.run_python("import sys; print('evidence'); sys.exit(7)"), (7, b"evidence\n", b""))

    def test_timeout_kills_silent_child(self):
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_python("import time; time.sleep(10)", timeout=0.2)
        self.assertLess(time.monotonic() - start, 3.0)

    def test_descendant_holding_a_pipe_cannot_evade_timeout(self):
        start = time.monotonic()
        code = "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)']); print('parent done')"
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_python(code, timeout=0.2)
        self.assertLess(time.monotonic() - start, 3.0)

    def test_invalid_limits_fail_before_execution(self):
        for invalid in (float("inf"), float("nan"), 0, -1):
            with self.subTest(timeout=invalid), self.assertRaises(ValueError):
                self.run_python("pass", timeout=invalid)
        for invalid in (-1, True, 1.5):
            with self.subTest(limit=invalid), self.assertRaises(ValueError):
                self.run_python("pass", limit=invalid)


class EnvelopeTests(unittest.TestCase):
    @staticmethod
    def resume_result(*, exit_code: int = 0, brief: str = "brief", working: str = "work",
                      max_bytes: int = 16384, declared_bytes: int | None = None):
        content = {
            "brief": brief,
            "workingSet": working,
            "activeCriticalLessons": "",
            "snapshot": None,
        }
        actual = sum(len(value.encode("utf-8")) for value in content.values() if isinstance(value, str))
        return {
            "exitCode": exit_code,
            "envelope": {"data": {
                "content": content,
                "readNext": [],
                "bytes": actual if declared_bytes is None else declared_bytes,
                "maxBytes": max_bytes,
            }},
        }

    def test_malformed_status_is_not_treated_as_verified(self):
        result = {"envelope": {"data": {"checks": [{"name": "ledger", "status": ["pass"]}]}}}
        self.assertIsNone(check_status(result, "ledger"))

    def test_resume_contract_accepts_exact_success_packet(self):
        self.assertTrue(resume_contract_valid(self.resume_result(brief="繁體內容", working="工作集")))

    def test_resume_contract_rejects_nonzero_exit_even_with_content(self):
        self.assertFalse(resume_contract_valid(self.resume_result(exit_code=7)))

    def test_resume_contract_rejects_oversized_or_false_byte_claims(self):
        self.assertFalse(resume_contract_valid(self.resume_result(brief="x" * 16385)))
        self.assertFalse(resume_contract_valid(self.resume_result(declared_bytes=1)))
        self.assertFalse(resume_contract_valid(self.resume_result(max_bytes=16385)))


if __name__ == "__main__":
    unittest.main()
