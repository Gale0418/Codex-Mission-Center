"""Adversarial local probes for the test runner itself (no CI/provider calls)."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from bounded_process import run_bounded  # noqa: E402
from verify_upgrade_052 import check_status, collect, resume_contract_valid  # noqa: E402


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux subreaper containment is required")
class BoundedProcessTests(unittest.TestCase):
    def run_python(self, code: str, *, limit: int = 1024, timeout: float = 5.0):
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

    def test_descendant_that_creates_a_new_session_is_reaped(self):
        with tempfile.TemporaryDirectory(prefix="mc-bounded-setsid-") as temporary:
            pid_file = Path(temporary) / "escaped.pid"
            child = "import time; time.sleep(60)"
            code = (
                "import pathlib,subprocess,sys; "
                f"p=subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
                f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); "
                "print('parent done')"
            )
            rc, out, err = self.run_python(code, timeout=2.0)
            self.assertEqual((rc, out, err), (0, b"parent done\n", b""))
            escaped_pid = int(pid_file.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 2.0
            while Path(f"/proc/{escaped_pid}").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(
                Path(f"/proc/{escaped_pid}").exists(),
                "setsid descendant escaped the bounded supervisor",
            )

    def test_timeout_reaps_descendant_that_creates_a_new_session(self):
        with tempfile.TemporaryDirectory(prefix="mc-bounded-setsid-timeout-") as temporary:
            pid_file = Path(temporary) / "escaped.pid"
            child = "import time; time.sleep(60)"
            code = (
                "import pathlib,subprocess,sys,time; "
                f"p=subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
                f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); "
                "time.sleep(60)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_python(code, timeout=2.0)
            escaped_pid = int(pid_file.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 2.0
            while Path(f"/proc/{escaped_pid}").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(
                Path(f"/proc/{escaped_pid}").exists(),
                "setsid descendant survived the timeout cleanup",
            )

    def test_supervisor_sigkill_still_reaps_tracked_setsid_descendants(self):
        with tempfile.TemporaryDirectory(prefix="mc-bounded-supervisor-death-") as temporary:
            pid_file = Path(temporary) / "pids"
            child = "import time; time.sleep(60)"
            code = (
                "import os,pathlib,signal,subprocess,sys,time; "
                f"p=subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
                f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())+' '+str(p.pid)); "
                "time.sleep(0.5); os.kill(os.getppid(), signal.SIGKILL); time.sleep(60)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_python(code, timeout=1.5)
            candidate_pid, escaped_pid = map(int, pid_file.read_text(encoding="utf-8").split())
            for pid in (candidate_pid, escaped_pid):
                deadline = time.monotonic() + 2.0
                while Path(f"/proc/{pid}").exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertFalse(
                    Path(f"/proc/{pid}").exists(),
                    f"tracked descendant {pid} survived supervisor death",
                )

    def test_invalid_limits_fail_before_execution(self):
        for invalid in (float("inf"), float("nan"), 0, -1):
            with self.subTest(timeout=invalid), self.assertRaises(ValueError):
                self.run_python("pass", timeout=invalid)
        for invalid in (-1, True, 1.5):
            with self.subTest(limit=invalid), self.assertRaises(ValueError):
                self.run_python("pass", limit=invalid)


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux bounded runner is required")
class HarnessMutationTests(unittest.TestCase):
    def test_collect_detects_mutation_by_the_first_resume(self):
        with tempfile.TemporaryDirectory(prefix="mc-052-fake-cli-") as temporary:
            binary = Path(temporary) / "fake-mission-center"
            binary.write_text(
                """#!/usr/bin/env python3
import json
from pathlib import Path
import sys

args = sys.argv[1:]
command = args[0]
root = Path(args[args.index('--root') + 1])
mission = root / 'MissionCenter'
mission.mkdir(parents=True, exist_ok=True)
exit_code = 0
if command == 'sync':
    tasks = (mission / 'tasks.md').read_text(encoding='utf-8')
    (mission / 'working-set.md').write_text(tasks, encoding='utf-8')
    (mission / 'brief.md').write_text('brief', encoding='utf-8')
    data = {}
elif command == 'resume':
    path = mission / 'tasks.md'
    path.write_text(path.read_text(encoding='utf-8') + '# mutated by resume\\n', encoding='utf-8')
    content = {'handoff': None, 'brief': 'brief', 'workingSet': 'work', 'activeCriticalLessons': '', 'snapshot': None}
    routing = {'route': 'resume', 'ledgerStatus': 'corrupt', 'readNext': [], 'filesRead': [], 'staleReasons': []}
    used = sum(len(value.encode('utf-8')) for value in content.values() if isinstance(value, str))
    used += sum(len(value.encode('utf-8')) for value in routing.values() if isinstance(value, str))
    data = {'content': content, **routing, 'bytes': used, 'maxBytes': 16384}
elif command == 'reconcile':
    data = {'checks': [
        {'name': 'ledger', 'status': 'error'},
        {'name': 'evidence_envelope', 'status': 'unknown'},
    ]}
elif command == 'doctor':
    data = {'checks': [{'name': 'completion_passport', 'status': 'error'}]}
    exit_code = 1
else:
    data = {}
print(json.dumps({'schemaVersion': '1.0', 'command': command, 'status': 'ok', 'data': data}))
raise SystemExit(exit_code)
""",
                encoding="utf-8",
            )
            binary.chmod(0o700)
            report = collect(binary)
            probe = next(
                item for item in report["probes"]
                if item["name"] == "read_only_commands_preserve_canonical_tasks"
            )
            self.assertFalse(probe["passed"])


class EnvelopeTests(unittest.TestCase):
    @staticmethod
    def resume_result(
        *,
        exit_code: int = 0,
        brief: str = "brief",
        working: str = "work",
        max_bytes: int = 16384,
        declared_bytes: int | None = None,
        read_next: list[str] | None = None,
    ):
        content = {
            "handoff": None,
            "brief": brief,
            "workingSet": working,
            "activeCriticalLessons": "",
            "snapshot": None,
        }
        payload = {
            "route": "resume",
            "ledgerStatus": "missing",
            "ledgerError": None,
            "fallbackReason": None,
            "truncatedMarker": None,
            "readNext": [] if read_next is None else read_next,
            "filesRead": ["MissionCenter/brief.md", "MissionCenter/working-set.md"],
            "staleReasons": [],
            "content": content,
        }
        actual = sum(
            len(value.encode("utf-8"))
            for value in content.values()
            if isinstance(value, str)
        )
        actual += sum(
            len(payload[name].encode("utf-8"))
            for name in ("route", "ledgerStatus")
        )
        actual += sum(
            len(item.encode("utf-8"))
            for name in ("readNext", "filesRead", "staleReasons")
            for item in payload[name]
        )
        payload["bytes"] = actual if declared_bytes is None else declared_bytes
        payload["maxBytes"] = max_bytes
        return {"exitCode": exit_code, "envelope": {"data": payload}}

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

    def test_resume_contract_rejects_oversized_routing_metadata(self):
        self.assertFalse(
            resume_contract_valid(self.resume_result(read_next=["x" * 16385]))
        )


if __name__ == "__main__":
    unittest.main()
