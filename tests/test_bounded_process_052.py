"""Adversarial local probes for the test runner itself (no CI/provider calls)."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from bounded_process import run_bounded  # noqa: E402
from verify_upgrade_052 import (  # noqa: E402
    check_status,
    collect,
    corrupt_resume_contract_valid,
    resume_contract_valid,
)


def _proc_state(pid: int) -> str | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
        return None
    end = raw.rfind(")")
    return raw[end + 2 :].split()[0] if end >= 0 else None


def _terminated(pid: int) -> bool:
    return _proc_state(pid) in {None, "Z", "X"}


def _child_code(pid_file: Path) -> str:
    return (
        "from pathlib import Path; import time; "
        "status=Path('/proc/self/status').read_text(); "
        "host=next(line.split()[1] for line in status.splitlines() if line.startswith('NSpid:')); "
        f"Path({str(pid_file)!r}).write_text(host); time.sleep(60)"
    )


def _wait_for_file(path: Path) -> str:
    return (
        f"deadline=time.monotonic()+2; path=pathlib.Path({str(path)!r}); "
        "\nwhile not path.exists() and time.monotonic()<deadline: time.sleep(0.01)\n"
        "\nif not path.exists(): raise SystemExit(9)\n"
    )


def _public_packet_bytes(value) -> int:
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, dict):
        return sum(
            len(str(key).encode("utf-8")) + _public_packet_bytes(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return sum(_public_packet_bytes(item) for item in value)
    if value is None:
        return 4
    if isinstance(value, bool):
        return 4 if value else 5
    if isinstance(value, int):
        return len(str(value).encode("ascii"))
    raise TypeError(f"unsupported packet scalar: {type(value).__name__}")


def _legacy_string_key_bytes(value) -> int:
    """The pre-round-7 metric: useful only to prove the scalar bypass stays closed."""
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, dict):
        return sum(
            len(str(key).encode("utf-8")) + _legacy_string_key_bytes(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return sum(_legacy_string_key_bytes(item) for item in value)
    return 0


def _set_self_consistent_bytes(payload: dict) -> int:
    """Solve the small decimal-length fixed point for the public `bytes` field."""
    payload["bytes"] = 0
    for _ in range(16):
        measured = _public_packet_bytes(payload)
        if payload["bytes"] == measured:
            return measured
        payload["bytes"] = measured
    raise AssertionError("resume bytes declaration did not converge")


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux PID namespaces are required")
class BoundedProcessTests(unittest.TestCase):
    def run_python(self, code: str, *, limit: int = 1024, timeout: float = 5.0):
        return run_bounded(
            [sys.executable, "-c", code],
            timeout=timeout,
            max_output_bytes=limit,
        )

    def assert_terminated(self, pid: int, message: str) -> None:
        deadline = time.monotonic() + 2.0
        while not _terminated(pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(_terminated(pid), message)

    def test_exact_per_stream_limit_is_allowed(self):
        rc, out, err = self.run_python(
            "import os; os.write(1,b'x'*16); os.write(2,b'y'*16)",
            limit=16,
        )
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
            self.run_python(
                "import os\nwhile True:\n os.write(1,b'x'*128)\n os.write(2,b'y'*128)",
                limit=256,
            )

    def test_nonzero_exit_is_not_hidden(self):
        self.assertEqual(
            self.run_python("import sys; print('evidence'); sys.exit(7)"),
            (7, b"evidence\n", b""),
        )

    def test_timeout_kills_silent_child(self):
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_python("import time; time.sleep(10)", timeout=0.2)
        self.assertLess(time.monotonic() - start, 3.0)

    def test_descendant_holding_a_pipe_is_eagerly_contained(self):
        with tempfile.TemporaryDirectory(prefix="mc-bounded-pipe-") as temporary:
            pid_file = Path(temporary) / "child.pid"
            child = _child_code(pid_file)
            code = (
                "import pathlib,subprocess,sys,time; "
                f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
                + _wait_for_file(pid_file)
                + "print('parent done')"
            )
            start = time.monotonic()
            rc, out, err = self.run_python(code, timeout=3.0)
            self.assertEqual((rc, out, err), (0, b"parent done\n", b""))
            self.assertLess(time.monotonic() - start, 3.0)
            self.assert_terminated(
                int(pid_file.read_text(encoding="utf-8")),
                "inherited-pipe descendant survived eager namespace teardown",
            )

    def test_descendant_that_creates_a_new_session_is_reaped(self):
        with tempfile.TemporaryDirectory(prefix="mc-bounded-setsid-") as temporary:
            pid_file = Path(temporary) / "escaped.pid"
            child = _child_code(pid_file)
            code = (
                "import pathlib,subprocess,sys,time; "
                f"subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
                + _wait_for_file(pid_file)
                + "print('parent done')"
            )
            rc, out, err = self.run_python(code, timeout=3.0)
            self.assertEqual((rc, out, err), (0, b"parent done\n", b""))
            self.assert_terminated(
                int(pid_file.read_text(encoding="utf-8")),
                "setsid descendant escaped PID-namespace teardown",
            )

    def test_timeout_reaps_descendant_that_creates_a_new_session(self):
        with tempfile.TemporaryDirectory(prefix="mc-bounded-setsid-timeout-") as temporary:
            pid_file = Path(temporary) / "escaped.pid"
            child = _child_code(pid_file)
            code = (
                "import pathlib,subprocess,sys,time; "
                f"subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
                + _wait_for_file(pid_file)
                + "time.sleep(60)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_python(code, timeout=3.0)
            self.assert_terminated(
                int(pid_file.read_text(encoding="utf-8")),
                "setsid descendant survived timeout namespace teardown",
            )

    def test_candidate_cannot_escape_by_sigkilling_namespace_init(self):
        with tempfile.TemporaryDirectory(prefix="mc-bounded-init-signal-") as temporary:
            pid_file = Path(temporary) / "escaped.pid"
            child = _child_code(pid_file)
            code = (
                "import os,pathlib,signal,subprocess,sys,time; "
                f"subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
                + _wait_for_file(pid_file)
                + "\ntry:\n os.kill(1, signal.SIGKILL)\n"
                "except PermissionError:\n print('protected')\n"
                "else:\n print('unexpected')\n"
            )
            rc, out, err = self.run_python(code, timeout=3.0)
            self.assertEqual(rc, 0, err.decode("utf-8", errors="replace"))
            self.assertIn(out, {b"protected\n", b"unexpected\n"})
            self.assert_terminated(
                int(pid_file.read_text(encoding="utf-8")),
                "setsid descendant survived namespace-init signal test",
            )

    def test_invalid_limits_fail_before_execution(self):
        for invalid in (float("inf"), float("nan"), 0, -1, True, "1"):
            with self.subTest(timeout=invalid), self.assertRaises(ValueError):
                self.run_python("pass", timeout=invalid)  # type: ignore[arg-type]
        for invalid in (-1, True, 1.5):
            with self.subTest(limit=invalid), self.assertRaises(ValueError):
                self.run_python("pass", limit=invalid)  # type: ignore[arg-type]

    def test_setup_popen_failure_closes_both_readiness_descriptors(self):
        fd_root = Path("/proc/self/fd")
        before = len(list(fd_root.iterdir()))
        with patch("bounded_process.subprocess.Popen", side_effect=OSError("injected Popen failure")):
            for _ in range(20):
                with self.assertRaisesRegex(OSError, "injected Popen failure"):
                    self.run_python("pass")
        after = len(list(fd_root.iterdir()))
        self.assertEqual(after, before)


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
    data = {
        'schemaVersion': '1.1', 'route': 'resume', 'sourceFresh': True, 'dateFresh': True,
        'staleReasons': [], 'filesRead': [], 'content': content, 'handoff': None,
        'ledgerStatus': 'corrupt', 'ledgerError': 'bad ledger',
        'context': {'includedBytes': {key: len((value or '').encode('utf-8')) for key, value in content.items()}},
        'maxBytes': 16384, 'canonicalFallback': True,
        'fallbackReason': 'execution ledger corrupt', 'truncated': False,
        'truncatedMarker': None, 'readNext': ['handoff'],
    }
    def packet_bytes(value):
        if isinstance(value, str): return len(value.encode('utf-8'))
        if isinstance(value, dict): return sum(len(str(key).encode('utf-8')) + packet_bytes(item) for key, item in value.items())
        if isinstance(value, list): return sum(packet_bytes(item) for item in value)
        if value is None: return 4
        if isinstance(value, bool): return 4 if value else 5
        if isinstance(value, int): return len(str(value))
        raise TypeError()
    data['bytes'] = 0
    for _ in range(16):
        measured = packet_bytes(data)
        if data['bytes'] == measured: break
        data['bytes'] = measured
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
                item
                for item in report["probes"]
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
        omit: str | None = None,
        schema_version: str = "1.1",
        ledger_status: str = "missing",
        envelope_schema: str = "1.0",
        envelope_command: str = "resume",
        envelope_status: str = "ok",
    ):
        content = {
            "handoff": None,
            "brief": brief,
            "workingSet": working,
            "activeCriticalLessons": "",
            "snapshot": None,
        }
        payload = {
            "schemaVersion": schema_version,
            "route": "resume",
            "sourceFresh": True,
            "dateFresh": True,
            "staleReasons": [],
            "filesRead": ["MissionCenter/brief.md", "MissionCenter/working-set.md"],
            "content": content,
            "handoff": None,
            "ledgerStatus": ledger_status,
            "ledgerError": None,
            "context": {
                "includedBytes": {
                    key: len((value or "").encode("utf-8"))
                    for key, value in content.items()
                }
            },
            "bytes": 0,
            "maxBytes": max_bytes,
            "canonicalFallback": False,
            "fallbackReason": None,
            "truncated": False,
            "truncatedMarker": None,
            "readNext": [] if read_next is None else read_next,
        }
        if declared_bytes is None:
            _set_self_consistent_bytes(payload)
        else:
            payload["bytes"] = declared_bytes
        if omit is not None:
            payload.pop(omit, None)
        return {
            "exitCode": exit_code,
            "envelope": {
                "schemaVersion": envelope_schema,
                "command": envelope_command,
                "status": envelope_status,
                "data": payload,
            },
        }

    def test_malformed_status_is_not_treated_as_verified(self):
        result = {
            "envelope": {
                "data": {"checks": [{"name": "ledger", "status": ["pass"]}]}
            }
        }
        self.assertIsNone(check_status(result, "ledger"))

    def test_resume_contract_accepts_exact_success_packet(self):
        self.assertTrue(
            resume_contract_valid(
                self.resume_result(brief="繁體內容", working="工作集")
            )
        )

    def test_resume_contract_rejects_invalid_top_level_envelope(self):
        self.assertFalse(
            resume_contract_valid(self.resume_result(envelope_schema="2.0"))
        )
        self.assertFalse(
            resume_contract_valid(self.resume_result(envelope_command="status"))
        )
        self.assertFalse(
            resume_contract_valid(self.resume_result(envelope_status="error"))
        )
        result = self.resume_result()
        result["envelope"]["unexpected"] = True
        self.assertFalse(resume_contract_valid(result))
        result = self.resume_result()
        del result["envelope"]["status"]
        self.assertFalse(resume_contract_valid(result))

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

    def test_resume_contract_counts_mapping_keys_in_shared_budget(self):
        result = self.resume_result()
        payload = result["envelope"]["data"]
        payload["context"]["includedBytes"] = {"k" * 20_000: 0}
        _set_self_consistent_bytes(payload)
        self.assertFalse(resume_contract_valid(result))

    def test_resume_contract_counts_nested_integer_metadata(self):
        result = self.resume_result()
        payload = result["envelope"]["data"]
        numbers = [int("9" * 101) for _ in range(1000)]
        payload["handoff"] = {"numbers": numbers}
        payload["bytes"] = _legacy_string_key_bytes(payload)
        self.assertLess(payload["bytes"], payload["maxBytes"])
        self.assertFalse(resume_contract_valid(result))

    def test_resume_contract_rejects_unsupported_ledger_status(self):
        self.assertFalse(
            resume_contract_valid(self.resume_result(ledger_status="banana"))
        )

    def test_resume_contract_requires_exact_included_bytes(self):
        result = self.resume_result()
        included = result["envelope"]["data"]["context"]["includedBytes"]
        included.pop("workingSet")
        _set_self_consistent_bytes(result["envelope"]["data"])
        self.assertFalse(resume_contract_valid(result))

        result = self.resume_result()
        result["envelope"]["data"]["context"]["includedBytes"]["brief"] = 0
        _set_self_consistent_bytes(result["envelope"]["data"])
        self.assertFalse(resume_contract_valid(result))

    def test_resume_contract_compares_workspace_content_and_truncation(self):
        result = self.resume_result(brief="real brief", working="real work")
        self.assertTrue(
            resume_contract_valid(
                result, {"brief": "real brief", "workingSet": "real work"}
            )
        )
        self.assertFalse(
            resume_contract_valid(
                result, {"brief": "different", "workingSet": "real work"}
            )
        )

        truncated = self.resume_result(
            brief="real [TRUNCATED]", working="real work", read_next=["brief"]
        )
        self.assertTrue(
            resume_contract_valid(
                truncated,
                {"brief": "real full source", "workingSet": "real work"},
            )
        )

    def test_corrupt_resume_requires_fail_closed_invariants(self):
        result = self.resume_result(ledger_status="corrupt", read_next=["handoff"])
        data = result["envelope"]["data"]
        data["ledgerError"] = "malformed ledger"
        data["canonicalFallback"] = True
        data["fallbackReason"] = "execution ledger corrupt"
        _set_self_consistent_bytes(data)
        self.assertTrue(corrupt_resume_contract_valid(result))

        for mutation in ("handoff", "content_handoff", "ledger_error", "fallback", "read_next"):
            with self.subTest(mutation=mutation):
                candidate = self.resume_result(ledger_status="corrupt", read_next=["handoff"])
                payload = candidate["envelope"]["data"]
                payload["ledgerError"] = "malformed ledger"
                payload["canonicalFallback"] = True
                payload["fallbackReason"] = "execution ledger corrupt"
                if mutation == "handoff":
                    payload["handoff"] = {"trusted": True}
                elif mutation == "content_handoff":
                    payload["content"]["handoff"] = "trusted"
                    payload["context"]["includedBytes"]["handoff"] = len(b"trusted")
                elif mutation == "ledger_error":
                    payload["ledgerError"] = None
                elif mutation == "fallback":
                    payload["canonicalFallback"] = False
                else:
                    payload["readNext"] = []
                _set_self_consistent_bytes(payload)
                self.assertFalse(corrupt_resume_contract_valid(candidate))

    def test_resume_contract_requires_supported_schema_version(self):
        self.assertFalse(
            resume_contract_valid(self.resume_result(schema_version="not-a-version"))
        )
        self.assertFalse(
            resume_contract_valid(self.resume_result(schema_version="1.0"))
        )

    def test_resume_contract_rejects_every_missing_public_field(self):
        fields = (
            "schemaVersion",
            "route",
            "sourceFresh",
            "dateFresh",
            "staleReasons",
            "filesRead",
            "content",
            "handoff",
            "ledgerStatus",
            "ledgerError",
            "context",
            "bytes",
            "maxBytes",
            "canonicalFallback",
            "fallbackReason",
            "truncated",
            "truncatedMarker",
            "readNext",
        )
        for field in fields:
            with self.subTest(field=field):
                self.assertFalse(
                    resume_contract_valid(self.resume_result(omit=field))
                )


if __name__ == "__main__":
    unittest.main()
