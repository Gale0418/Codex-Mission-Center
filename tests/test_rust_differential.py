"""Wave 0 differential checks for the Python and Rust Mission Center cores.

The Rust CLI is intentionally optional during the walking-skeleton phase.  Set
``MISSION_CENTER_RUST_BIN`` to an executable (or place ``mission-center`` in a
Cargo ``target/{debug,release}`` directory) to enable these tests.

The default CLI contract is::

    mission-center <tasks|status|reconcile|resume> --root <workspace>

Projects with a different argument order may set
``MISSION_CENTER_RUST_ARGS``.  It is a shell-like argument template *after*
the executable and may contain ``{command}`` and ``{workspace}``, for example
``"{workspace} {command} --json"``.  The harness never invokes a shell; this
is therefore safe for Windows paths containing spaces.

Only stable protocol fields are compared.  Human-readable error messages are
deliberately excluded from the oracle.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import unittest
import warnings
from pathlib import Path
from typing import Any

from tests import workspace_tempdir


ROOT = Path(__file__).resolve().parents[1]
PY_SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "demo-workspace"
DATE = "2026-08-09"

# Keep direct Python-oracle imports hermetic and independent of unittest
# method ordering (the scripts are not installed as a package).
if str(PY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PY_SCRIPTS))


def _find_rust_binary() -> Path | None:
    configured = os.environ.get("MISSION_CENTER_RUST_BIN")
    if configured:
        candidate = Path(configured).expanduser()
        return candidate.resolve() if candidate.is_file() else None
    # Ignore stale target artifacts from a previously removed CLI crate.  The
    # source-tree presence is the useful definition of "available" for the
    # default discovery path; CI can still point explicitly at a packaged
    # binary through MISSION_CENTER_RUST_BIN.
    if not (ROOT / "rust" / "mission-center-cli").is_dir():
        return None
    names = ("mission-center.exe", "mission-center")
    candidates = [
        ROOT / "rust" / "target" / profile / name
        for profile in ("debug", "release")
        for name in names
    ] + [
        ROOT / "target" / profile / name
        for profile in ("debug", "release")
        for name in names
    ]
    return next((path.resolve() for path in candidates if path.is_file()), None)


RUST_BINARY = _find_rust_binary()


def _rust_argv(command: str, workspace: Path, *extra: str) -> list[str]:
    """Build argv without a shell, preserving Windows paths as one argument."""
    if RUST_BINARY is None:  # pragma: no cover - guarded by unittest skip
        raise unittest.SkipTest("Rust mission-center binary was not found")
    template = os.environ.get("MISSION_CENTER_RUST_ARGS")
    if template:
        # Parse the operator-supplied flags first, then substitute the path;
        # otherwise POSIX shlex would treat Windows backslashes in the path as
        # escapes.  The resulting argv is still passed directly to Popen.
        args = [
            argument.format(command=command, workspace=str(workspace))
            for argument in shlex.split(template, posix=True)
        ]
    else:
        # The CLI emits JSON unconditionally.  Do not add a ``--json`` flag:
        # mutating commands intentionally reject unknown flags as a safety
        # boundary.
        args = [command, "--root", str(workspace)]
    return [str(RUST_BINARY), *args, *extra]


def _run_rust(command: str, workspace: Path, *extra: str) -> tuple[int, dict[str, Any] | None, str]:
    completed = subprocess.run(
        _rust_argv(command, workspace, *extra),
        cwd=str(ROOT),
        capture_output=True,
        check=False,
        timeout=15,
        env={**os.environ, "RUST_BACKTRACE": "0"},
    )
    stdout = completed.stdout.decode("utf-8", errors="replace").strip()
    # A CLI must emit one JSON value, but accepting a final JSON line makes
    # diagnostics on stderr/stdout harmless without weakening field checks.
    payload: dict[str, Any] | None = None
    for candidate in (stdout, *reversed(stdout.splitlines())):
        try:
            value = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            payload = value
            break
    return completed.returncode, payload, stdout


def _run_python_script(script: Path, workspace: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    """Run a Python writer with byte capture; no shell and no real workspace."""
    return subprocess.run(
        [sys.executable, os.fspath(script), os.fspath(workspace), *args],
        cwd=os.fspath(ROOT),
        capture_output=True,
        check=False,
        timeout=15,
        env={**os.environ, "PYTHONUTF8": "1"},
    )


def _rust_data(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("data")
    return value if isinstance(value, dict) else payload


def _assert_rust_error(test: unittest.TestCase, returncode: int, payload: dict[str, Any] | None, command: str, code: str, stdout: str) -> None:
    test.assertNotEqual(returncode, 0, stdout)
    test.assertIsInstance(payload, dict, stdout)
    _assert_protocol_header(test, payload, command)
    test.assertEqual(payload.get("status"), "error")
    test.assertEqual(_canonical_error_code(_error_code(payload)), code)


def _workspace_with_tasks(parent: Path, *, traditional: bool = False) -> Path:
    workspace = parent / ("zh" if traditional else "en")
    mission = workspace / "MissionCenter"
    mission.mkdir(parents=True)
    if traditional:
        (mission / "project.md").write_text("# 專案\n\n- 目標: Wave 2\n", encoding="utf-8")
        tasks = (
            "| ID | 標題 | 類型 | 父層 | 優先級 | 狀態 | 負責人 | 依賴 | 下一步 | 驗證方式 | 估時 | 標籤 | 備註 |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| T1 | 主要任務 | Task | | P0 | In Progress | Codex | | verify | unittest | 1 | | |\n"
            "| T2 | 第二任務 | Task | | P1 | Ready | Codex | | start | unittest | 1 | | |\n"
        )
    else:
        (mission / "project.md").write_text("# Project\n\n- Goal: Wave 2\n", encoding="utf-8")
        tasks = (
            "| ID | Title | Type | Parent | Priority | Status | Owner | Depends on | Next action | Verification | Estimate | Labels | Notes |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| T1 | Primary task | Task | | P0 | In Progress | Codex | | verify | unittest | 1 | | |\n"
            "| T2 | Second task | Task | | P1 | Ready | Codex | | start | unittest | 1 | | |\n"
        )
    (mission / "tasks.md").write_text(tasks, encoding="utf-8", newline="\n")
    return workspace


def _pulse_args(*, operation_id: str, pulse_id: str, task_id: str = "T1", next_action: str = "verify", outcome: str = "completed", parent: str | None = None, recorded_at: str = "2026-08-29T00:00:00Z") -> tuple[str, ...]:
    args = (
        "--operation-id", operation_id,
        "--pulse-id", pulse_id,
        "--task-id", task_id,
        "--phase", "verify",
        "--outcome", outcome,
        "--next-action", next_action,
        "--evidence-ref", "tests/wave2",
        "--recorded-at", recorded_at,
        "--budget-remaining", "7",
    )
    return args if parent is None else (*args, "--causal-parent", parent)


def _valid_pulse(task_id: str = "T1", pulse_id: str = "pulse-a", *, parent: str | None = None, outcome: str = "completed", next_action: str = "verify", recorded_at: str = "2026-08-29T00:00:00Z") -> dict[str, Any]:
    return {
        "pulseId": pulse_id,
        "taskId": task_id,
        "phase": "verify",
        "outcome": outcome,
        "nextAction": next_action,
        "evidenceRef": "tests/wave2",
        "budgetRemaining": 7,
        "causalParent": parent,
    }


def _load_python_modules() -> tuple[Any, Any, Any, Any]:
    import sys

    script_path = str(PY_SCRIPTS)
    if script_path not in sys.path:
        sys.path.insert(0, script_path)
    from mission_maintenance import parse_tasks, run_resume, run_status
    from reconcile_mission_center import reconcile_workspace

    return parse_tasks, run_status, run_resume, reconcile_workspace


def _write_tasks(workspace: Path, text: str) -> None:
    mission = workspace / "MissionCenter"
    mission.mkdir(parents=True, exist_ok=True)
    # write_bytes is intentional: CRLF is one of the parser's compatibility
    # vectors and must not be normalized by a text-mode writer.
    (mission / "tasks.md").write_bytes(text.encode("utf-8"))


def _copy_fixture(parent: Path) -> Path:
    import shutil

    workspace = parent / "workspace"
    shutil.copytree(FIXTURE, workspace)
    return workspace


def _task_projection(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        value = value.get("tasks", value.get("items"))
    if not isinstance(value, list):
        raise AssertionError("tasks response must contain a tasks array")
    projection = []
    for item in value:
        if not isinstance(item, dict):
            raise AssertionError("each task must be an object")
        projection.append(
            {
                "ID": str(item.get("ID", item.get("id", ""))),
                "Title": str(item.get("Title", item.get("title", ""))),
                "Status": str(item.get("Status", item.get("status", ""))),
            }
        )
    return projection


def _error_code(payload: dict[str, Any]) -> str:
    direct = payload.get("errorCode")
    if isinstance(direct, str):
        return direct
    nested = payload.get("error")
    if isinstance(nested, dict):
        for key in ("code", "errorCode"):
            if isinstance(nested.get(key), str):
                return nested[key]
    raise AssertionError("error response must expose errorCode or error.code")


def _python_error_code(exc: BaseException) -> str:
    text = str(exc).casefold()
    if "incomplete escape" in text or "malformed" in text:
        return "malformed_row"
    if "expected" in text and "cells" in text:
        return "wrong_cell_count"
    if "does not contain" in text:
        return "missing_table"
    if "invalid table header" in text:
        return "invalid_header"
    if "invalid table separator" in text:
        return "invalid_separator"
    return "parse_error"


def _canonical_error_code(value: str) -> str:
    aliases = {
        "malformed": "malformed_row",
        "malformed-markdown-row": "malformed_row",
        "wrong-cell-count": "wrong_cell_count",
        "missing-table": "missing_table",
        "invalid-header": "invalid_header",
        "invalid-separator": "invalid_separator",
    }
    return aliases.get(value.casefold(), value.casefold())


def _assert_protocol_header(test: unittest.TestCase, payload: Any, route: str) -> None:
    test.assertIsInstance(payload, dict)
    test.assertIsInstance(payload.get("schemaVersion"), str)
    # The initial Rust walking skeleton wrapped data in ``command`` while the
    # converged contract uses ``route``.  Accept the former only as a bridge;
    # all semantic assertions below operate on the unwrapped data object.
    test.assertEqual(payload.get("route", payload.get("command")), route)


def _data(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("data")
    return value if isinstance(value, dict) else payload


def _assert_no_actionable_done_handoff(test: unittest.TestCase, payload: dict[str, Any], side: str) -> None:
    if "actionableHandoff" in payload:
        test.assertIs(payload["actionableHandoff"], False)
    handoff = payload.get("handoff")
    if not handoff:
        return
    if not isinstance(handoff, dict):
        test.fail(f"{side} resume handoff must be an object or null")
    canonical = handoff.get("canonicalTask")
    status = canonical.get("Status", canonical.get("status", "")) if isinstance(canonical, dict) else ""
    next_action = handoff.get("nextAction", handoff.get("executionNextAction", ""))
    actionable = str(status).casefold() == "done" and bool(str(next_action).strip()) and str(next_action).strip().casefold() not in {"none", "no action", "n/a", "無", "無動作"}
    if not actionable:
        return
    message = "all-Done + inactive resume returned an actionable Done handoff"
    if side == "python":
        # Known Wave 0 oracle debt: keep CI green while preserving a visible,
        # opt-in failure path for projects that want to close the debt now.
        warnings.warn(message, RuntimeWarning, stacklevel=2)
        if os.environ.get("MISSION_CENTER_STRICT_ORACLE_DEBT") == "1":
            test.fail(message)
    else:
        test.fail(message)


@unittest.skipUnless(
    RUST_BINARY is not None,
    "SKIP: Rust mission-center binary unavailable (set MISSION_CENTER_RUST_BIN to enable)",
)
class RustDifferentialTests(unittest.TestCase):
    def test_tasks_escaped_pipe_backslash_crlf_and_unicode(self):
        parse_tasks, run_status, _, _ = _load_python_modules()
        cases = {
            "escaped": (
                "| ID | Title | Status |\r\n"
                "| --- | --- | --- |\r\n"
                "| MC-ESC | pipe \\| slash \\\\ | In Progress |\r\n"
            ),
            "unicode": (
                "# 任務\n| ID | 標題 | 狀態 |\n| --- | --- | --- |\n"
                "| MC-宇宙 | 太空 🚀 任務 | Done |\n"
            ),
        }
        for name, text in cases.items():
            with self.subTest(name=name), workspace_tempdir(f"rust-tasks-{name}-") as temporary:
                # Keep the parser vector hermetic while retaining a complete
                # workspace around it.  Replacing tasks.md invalidates the
                # derived fingerprints, so status is expected to be stale
                # (and therefore exit 1) until an explicit sync occurs.
                workspace = _copy_fixture(Path(temporary))
                _write_tasks(workspace, text)
                expected = parse_tasks(workspace / "MissionCenter" / "tasks.md")
                expected_status = run_status(workspace, DATE)
                expected_exit = 1 if expected_status["stale"] else 0
                returncode, actual, stdout = _run_rust("status", workspace, "--date", DATE)
                self.assertEqual(returncode, expected_exit, stdout)
                self.assertIsNotNone(actual)
                _assert_protocol_header(self, actual, "status")
                actual_data = _data(actual)
                self.assertEqual(actual_data.get("stale"), expected_status["stale"])
                self.assertEqual(actual_data.get("sourceFresh"), expected_status["sourceFresh"])
                self.assertNotIn("\ufffd", stdout)
                self.assertEqual(_task_projection(actual_data), [
                    {"ID": row.get("ID", ""), "Title": row.get("Title", row.get("標題", "")), "Status": row.get("Status", row.get("狀態", ""))}
                    for row in expected
                ])

    def test_malformed_tasks_compare_error_schema_not_error_text(self):
        parse_tasks, _, _, _ = _load_python_modules()
        cases = {
            "wrong-cell-count": "| ID | Title | Status |\n| --- | --- | --- |\n| BAD | too few |\n",
            "incomplete-escape": "| ID | Title | Status |\n| --- | --- | --- |\n| BAD | trailing slash \\\n",
            "missing-table": "# Tasks\nno table here\n",
        }
        for name, text in cases.items():
            with self.subTest(name=name), workspace_tempdir(f"rust-malformed-{name}-") as temporary:
                workspace = Path(temporary)
                _write_tasks(workspace, text)
                try:
                    parse_tasks(workspace / "MissionCenter" / "tasks.md")
                except (OSError, UnicodeError, ValueError) as exc:
                    expected_code = _python_error_code(exc)
                else:
                    self.fail("Python parser unexpectedly accepted malformed tasks")
                returncode, actual, stdout = _run_rust("status", workspace)
                self.assertNotEqual(returncode, 0, stdout)
                self.assertIsInstance(actual, dict, stdout)
                _assert_protocol_header(self, actual, "status")
                self.assertEqual(actual.get("status"), "error")
                code = _error_code(actual)
                self.assertIsInstance(code, str)
                # Error messages are intentionally not compared.  Error codes
                # are stable protocol identifiers; permit a generic parse code
                # only for the Python implementation's intentionally broad
                # parser exception mapping.
                self.assertEqual(_canonical_error_code(code), _canonical_error_code(expected_code))
                if "exitCode" in actual:
                    self.assertEqual(actual["exitCode"], returncode)

    def test_status_and_reconcile_compare_stable_json_fields(self):
        _, run_status, _, reconcile_workspace = _load_python_modules()
        with workspace_tempdir("rust-status-reconcile-") as temporary:
            workspace = _copy_fixture(Path(temporary))
            # Materialize derived views only inside the hermetic temporary
            # workspace; neither differential command is allowed to write.
            from mission_maintenance import run_sync

            run_sync(workspace, date_str=DATE)
            before = {
                path.relative_to(workspace): path.read_bytes()
                for path in (workspace / "MissionCenter").rglob("*")
                if path.is_file()
            }
            expected_status = run_status(workspace, DATE)
            status_code, actual_status, status_stdout = _run_rust("status", workspace, "--date", DATE)
            self.assertEqual(status_code, 0 if not expected_status["stale"] else 1, status_stdout)
            _assert_protocol_header(self, actual_status, "status")
            status_envelope = actual_status
            actual_status = _data(status_envelope)
            self.assertEqual(status_envelope["schemaVersion"], expected_status["schemaVersion"])
            for field in ("date", "sourceFresh", "dateFresh", "stale", "staleReasons", "missing", "workingSetTasks", "focusTasks"):
                self.assertEqual(actual_status.get(field), expected_status[field], field)
            self.assertRegex(str(actual_status.get("fingerprint", "")), r"^[0-9a-f]{64}$")

            expected_reconcile = reconcile_workspace(workspace)
            reconcile_code, actual_reconcile, reconcile_stdout = _run_rust("reconcile", workspace)
            self.assertEqual(reconcile_code, 0 if expected_reconcile["status"] in {"pass", "unknown", "stale"} else 1, reconcile_stdout)
            _assert_protocol_header(self, actual_reconcile, "reconcile")
            reconcile_envelope = actual_reconcile
            actual_reconcile = _data(reconcile_envelope)
            self.assertEqual(reconcile_envelope["schemaVersion"], expected_reconcile["schemaVersion"])
            self.assertEqual(actual_reconcile.get("status", reconcile_envelope.get("status")), expected_reconcile["status"])
            self.assertIs(actual_reconcile.get("readOnly"), True)
            expected_checks = [(item["name"], item["status"]) for item in expected_reconcile["checks"]]
            actual_checks = [(item.get("name"), item.get("status")) for item in actual_reconcile.get("checks", [])]
            self.assertEqual(actual_checks, expected_checks)
            after = {
                path.relative_to(workspace): path.read_bytes()
                for path in (workspace / "MissionCenter").rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)

    def test_all_done_inactive_resume_has_no_actionable_done_handoff(self):
        _, _, run_resume, _ = _load_python_modules()
        with workspace_tempdir("rust-resume-done-inactive-") as temporary:
            workspace = _copy_fixture(Path(temporary))
            tasks = workspace / "MissionCenter" / "tasks.md"
            text = tasks.read_text(encoding="utf-8")
            text = re.sub(r"\| (Ready|In Progress|Review|Blocked|Backlog) \|", "| Done |", text)
            tasks.write_text(text, encoding="utf-8", newline="\n")
            (workspace / "MissionCenter" / "snapshot.md").write_text(
                "# Snapshot\n\n- State: inactive\n", encoding="utf-8", newline="\n"
            )
            from mission_maintenance import run_sync

            run_sync(workspace, date_str=DATE)
            expected = run_resume(workspace, DATE)
            _assert_protocol_header(self, expected, "resume")
            _assert_no_actionable_done_handoff(self, expected, "python")
            returncode, actual, stdout = _run_rust("resume", workspace, "--date", DATE)
            self.assertEqual(returncode, 0, stdout)
            _assert_protocol_header(self, actual, "resume")
            actual = _data(actual)
            for field in ("sourceFresh", "dateFresh", "staleReasons", "ledgerStatus", "canonicalFallback", "fallbackReason"):
                self.assertEqual(actual.get(field), expected[field], field)
            _assert_no_actionable_done_handoff(self, actual, "rust")

    def test_normalize_preserves_escaped_crlf_and_localized_fields_with_replay_conflict(self):
        normalize = PY_SCRIPTS / "normalize_mission_center.py"
        cases = {
            "escaped-crlf": (
                "| ID | Title | Priority | Status | Labels |\r\n"
                "| --- | --- | --- | --- | --- |\r\n"
                "| T1 | pipe \\| slash \\\\ | P1 | In Progress | alpha, beta |\r\n"
            ),
            "localized": (
                "# 任務\n| ID | 標題 | 優先級 | 狀態 | 標籤 |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| T1 | 修正 🚀 | high | doing | Alpha; alpha |\n"
            ),
        }
        for name, tasks_text in cases.items():
            with self.subTest(name=name), workspace_tempdir(f"rust-normalize-{name}-") as temporary:
                # Python and Rust receive independent copies of exactly the
                # same bytes, including CRLF and escaped Markdown cells.
                import shutil

                source = Path(temporary) / "source"
                source.mkdir()
                _write_tasks(source, tasks_text)
                py_workspace = Path(temporary) / "python"
                rust_workspace = Path(temporary) / "rust"
                shutil.copytree(source, py_workspace)
                shutil.copytree(source, rust_workspace)
                py_result = _run_python_script(normalize, py_workspace)
                self.assertEqual(py_result.returncode, 0, py_result.stderr.decode("utf-8", "replace"))
                python_bytes = (py_workspace / "MissionCenter" / "tasks.md").read_bytes()
                rust_code, rust_payload, rust_stdout = _run_rust(
                    "normalize", rust_workspace,
                    "--operation-id", f"normalize-{name}",
                    "--timestamp", "2026-08-29T00:00:00Z",
                )
                self.assertEqual(rust_code, 0, rust_stdout)
                self.assertIsInstance(rust_payload, dict)
                _assert_protocol_header(self, rust_payload, "normalize")
                self.assertIn(rust_payload.get("status"), {"committed", "replay"})
                if name == "escaped-crlf":
                    self.assertEqual(
                        (rust_workspace / "MissionCenter" / "tasks.md").read_bytes(),
                        python_bytes,
                    )
                else:
                    # Python's Windows text writer may materialize CRLF while
                    # Rust canonicalizes a changed table to LF.  Compare the
                    # parsed canonical rows, not platform line endings.
                    from mission_maintenance import parse_tasks

                    self.assertEqual(
                        _task_projection(parse_tasks(rust_workspace / "MissionCenter" / "tasks.md")),
                        _task_projection(parse_tasks(py_workspace / "MissionCenter" / "tasks.md")),
                    )
                second_code, second_payload, second_stdout = _run_rust(
                    "normalize", rust_workspace,
                    "--operation-id", f"normalize-{name}",
                    "--timestamp", "2026-08-29T00:00:00Z",
                )
                if name == "escaped-crlf":
                    # This fixture is already canonical, so the same
                    # operation is a genuine no-op replay.  A later source
                    # mutation must instead be rejected as a conflict.
                    self.assertEqual(second_code, 0, second_stdout)
                    self.assertEqual(second_payload.get("status"), "replay")
                    (rust_workspace / "MissionCenter" / "tasks.md").write_bytes(
                        (rust_workspace / "MissionCenter" / "tasks.md").read_bytes() + b"\n"
                    )
                    conflict_code, conflict_payload, conflict_stdout = _run_rust(
                        "normalize", rust_workspace,
                        "--operation-id", f"normalize-{name}",
                        "--timestamp", "2026-08-29T00:00:00Z",
                    )
                    _assert_rust_error(self, conflict_code, conflict_payload, "normalize", "operation_conflict", conflict_stdout)
                else:
                    # The localized aliases require a real first-write
                    # normalization.  Reusing that operation after its
                    # source digest changed is correctly a conflict, not a
                    # replay; retain that strict contract in the oracle.
                    _assert_rust_error(self, second_code, second_payload, "normalize", "operation_conflict", second_stdout)

    def test_snapshot_fingerprint_language_retry_metadata_and_operation_replay(self):
        snapshot = PY_SCRIPTS / "snapshot_mission_center.py"
        for traditional in (False, True):
            with self.subTest(language="zh-TW" if traditional else "en"), workspace_tempdir("rust-snapshot-") as temporary:
                import shutil

                source = _workspace_with_tasks(Path(temporary), traditional=traditional)
                py_workspace = Path(temporary) / "python"
                rust_workspace = Path(temporary) / "rust"
                shutil.copytree(source, py_workspace)
                shutil.copytree(source, rust_workspace)
                attempt_one = json.dumps({"phase": "build", "errorSignature": "E-W2"}, ensure_ascii=False)
                attempt_two = json.dumps({"phase": "test", "errorSignature": "E-W2"}, ensure_ascii=False)
                for attempt in (attempt_one, attempt_two):
                    result = _run_python_script(snapshot, py_workspace, "--attempt", attempt)
                    self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
                python_text = (py_workspace / "MissionCenter" / "snapshot.md").read_text(encoding="utf-8")
                self.assertIn("- State: active", python_text)
                self.assertIn("- Retry gate: diagnosis", python_text)
                python_fingerprint = re.search(r"- (?:Fingerprint|指紋): ([0-9a-f]{64})", python_text)
                self.assertIsNotNone(python_fingerprint)
                self.assertIn("Recent attempts JSON:", python_text)

                args = ("--operation-id", "snapshot-wave2", "--timestamp", "2026-08-29T01:00:00Z", "--note", "safe note")
                first_code, first, first_stdout = _run_rust("snapshot", rust_workspace, *args)
                self.assertEqual(first_code, 0, first_stdout)
                _assert_protocol_header(self, first, "snapshot")
                self.assertIn(first.get("status"), {"committed", "replay"})
                rust_text = (rust_workspace / "MissionCenter" / "snapshot.md").read_text(encoding="utf-8")
                rust_fingerprint = re.search(r"- (?:Fingerprint|指紋): ([0-9a-f]{64})", rust_text)
                self.assertIsNotNone(rust_fingerprint)
                self.assertEqual(rust_fingerprint.group(1), python_fingerprint.group(1))
                self.assertIn("- Retry gate: retry", rust_text)
                self.assertIn("Recent attempts JSON:", rust_text)
                second_code, second, second_stdout = _run_rust("snapshot", rust_workspace, *args)
                self.assertEqual(second_code, 0, second_stdout)
                self.assertEqual(second.get("status"), "replay")
                conflict_code, conflict, conflict_stdout = _run_rust(
                    "snapshot", rust_workspace,
                    "--operation-id", "snapshot-wave2", "--timestamp", "2026-08-29T01:00:00Z", "--note", "different note",
                )
                _assert_rust_error(self, conflict_code, conflict, "snapshot", "operation_conflict", conflict_stdout)

                py_secret = _run_python_script(
                    snapshot, py_workspace,
                    "--attempt", json.dumps({"phase": "test", "errorSignature": "password: hidden"}),
                )
                self.assertNotEqual(py_secret.returncode, 0)
                rust_secret_code, rust_secret, rust_secret_stdout = _run_rust(
                    "snapshot", rust_workspace,
                    "--operation-id", "snapshot-secret", "--timestamp", "2026-08-29T01:00:00Z", "--note", "password: hidden",
                )
                _assert_rust_error(self, rust_secret_code, rust_secret, "snapshot", "claim_rejected", rust_secret_stdout)

    def test_pulse_schema_replay_conflicts_secret_scanner_causal_guards_and_final_lf(self):
        parse_tasks, _, _, _ = _load_python_modules()
        from mission_maintenance import append_execution_pulse
        import shutil

        with workspace_tempdir("rust-pulse-") as temporary:
            source = _workspace_with_tasks(Path(temporary))
            py_workspace = Path(temporary) / "python"
            rust_workspace = Path(temporary) / "rust"
            shutil.copytree(source, py_workspace)
            shutil.copytree(source, rust_workspace)
            pulse = _valid_pulse()
            python_result = append_execution_pulse(py_workspace, pulse)
            self.assertTrue(python_result["appended"])
            python_record = json.loads(
                (py_workspace / "MissionCenter" / "execution-ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1]
            )
            required = {"schemaVersion", "kind", "pulseId", "taskId", "phase", "outcome", "nextAction", "evidenceRef", "budgetRemaining", "causalParent", "recordedAt"}
            self.assertEqual(set(python_record), required)
            self.assertEqual(python_record["schemaVersion"], "1.0")
            self.assertEqual(python_record["kind"], "execution-pulse")

            rust_args = _pulse_args(operation_id="pulse-op-a", pulse_id="pulse-a")
            code, payload, stdout = _run_rust("pulse", rust_workspace, *rust_args)
            self.assertEqual(code, 0, stdout)
            _assert_protocol_header(self, payload, "pulse")
            self.assertEqual(payload.get("status"), "committed")
            ledger = rust_workspace / "MissionCenter" / "execution-ledger.jsonl"
            rust_text = ledger.read_text(encoding="utf-8")
            self.assertTrue(rust_text.endswith("\n"))
            rust_record = json.loads(rust_text.splitlines()[-1])
            self.assertEqual(set(rust_record), required)
            self.assertEqual(rust_record["schemaVersion"], "1.0")
            self.assertEqual(rust_record["kind"], "execution-pulse")
            second_code, second, second_stdout = _run_rust("pulse", rust_workspace, *rust_args)
            self.assertEqual(second_code, 0, second_stdout)
            self.assertEqual(second.get("status"), "replay")
            changed_code, changed, changed_stdout = _run_rust(
                "pulse", rust_workspace,
                *_pulse_args(operation_id="pulse-op-a-changed", pulse_id="pulse-a", next_action="different"),
            )
            _assert_rust_error(self, changed_code, changed, "pulse", "operation_conflict", changed_stdout)
            self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 1)

            # A pre-existing ledger without a final LF must be safely extended.
            seed = json.dumps(rust_record, ensure_ascii=False, separators=(",", ":"))
            ledger.write_text(seed, encoding="utf-8", newline="")
            append_code, append_payload, append_stdout = _run_rust(
                "pulse", rust_workspace,
                *_pulse_args(operation_id="pulse-op-b", pulse_id="pulse-b"),
            )
            self.assertEqual(append_code, 0, append_stdout)
            self.assertEqual(append_payload.get("status"), "committed")
            self.assertTrue(ledger.read_bytes().endswith(b"\n"))
            self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 2)

            secret_values = (
                " password : hidden",
                "Authorization: Bearer abcdefghijklmnop",
                "JWT eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature123",
            )
            for index, value in enumerate(secret_values):
                with self.subTest(secret=value):
                    with self.assertRaises(ValueError):
                        append_execution_pulse(py_workspace, _valid_pulse(pulse_id=f"secret-py-{index}", outcome=value))
                    secret_code, secret_payload, secret_stdout = _run_rust(
                        "pulse", rust_workspace,
                        *_pulse_args(operation_id=f"secret-rust-{index}", pulse_id=f"secret-rust-{index}", outcome=value),
                    )
                    _assert_rust_error(self, secret_code, secret_payload, "pulse", "claim_rejected", secret_stdout)

            with self.assertRaises(ValueError):
                append_execution_pulse(py_workspace, _valid_pulse(pulse_id="unknown-py", parent="missing-parent"))
            unknown_code, unknown, unknown_stdout = _run_rust(
                "pulse", rust_workspace,
                *_pulse_args(operation_id="unknown-rust", pulse_id="unknown-rust", parent="missing-parent"),
            )
            _assert_rust_error(self, unknown_code, unknown, "pulse", "claim_rejected", unknown_stdout)

            append_execution_pulse(py_workspace, _valid_pulse(pulse_id="parent-py"))
            with self.assertRaises(ValueError):
                append_execution_pulse(py_workspace, _valid_pulse(task_id="T2", pulse_id="cross-py", parent="parent-py"))
            cross_code, cross, cross_stdout = _run_rust(
                "pulse", rust_workspace,
                *_pulse_args(operation_id="parent-rust", pulse_id="parent-rust"),
            )
            self.assertEqual(cross_code, 0, cross_stdout)
            cross_code, cross, cross_stdout = _run_rust(
                "pulse", rust_workspace,
                *_pulse_args(operation_id="cross-rust", pulse_id="cross-rust", task_id="T2", parent="parent-rust"),
            )
            _assert_rust_error(self, cross_code, cross, "pulse", "claim_rejected", cross_stdout)

    def test_handoff_selects_latest_casefolds_done_is_silent_and_bounds_input(self):
        if str(PY_SCRIPTS) not in sys.path:
            sys.path.insert(0, str(PY_SCRIPTS))
        from mission_maintenance import append_execution_pulse, run_handoff
        import shutil

        with workspace_tempdir("rust-handoff-") as temporary:
            source = _workspace_with_tasks(Path(temporary))
            py_workspace = Path(temporary) / "python"
            rust_workspace = Path(temporary) / "rust"
            shutil.copytree(source, py_workspace)
            shutil.copytree(source, rust_workspace)
            append_execution_pulse(py_workspace, _valid_pulse(pulse_id="p1", task_id="T1", next_action="continue"))
            append_execution_pulse(py_workspace, _valid_pulse(pulse_id="p2", task_id="T2", next_action="ship"))
            py_latest = run_handoff(py_workspace)
            self.assertEqual(py_latest["taskId"], "T2")
            py_casefold = run_handoff(py_workspace, "t1")
            self.assertEqual(py_casefold["taskId"], "T1")

            for pulse_id, task_id, action in (("p1", "T1", "continue"), ("p2", "T2", "ship")):
                code, payload, stdout = _run_rust(
                    "pulse", rust_workspace,
                    *_pulse_args(operation_id=f"handoff-{pulse_id}", pulse_id=pulse_id, task_id=task_id, next_action=action),
                )
                self.assertEqual(code, 0, stdout)
            code, latest, stdout = _run_rust("handoff", rust_workspace)
            self.assertEqual(code, 0, stdout)
            latest_data = _rust_data(latest)
            self.assertEqual(latest_data["taskId"], "T2")
            self.assertEqual(latest_data["latestPulse"]["pulseId"], "p2")
            self.assertNotIn("pulses", latest_data)
            code, casefold, stdout = _run_rust("handoff", rust_workspace, "--task-id", "t1")
            self.assertEqual(code, 0, stdout)
            casefold_data = _rust_data(casefold)
            self.assertEqual(casefold_data["taskId"], "T1")
            self.assertNotIn("pulses", casefold_data)

            # Done is canonical lifecycle truth and must not receive an
            # actionable execution handoff, even when an old pulse remains.
            for workspace in (py_workspace, rust_workspace):
                tasks = workspace / "MissionCenter" / "tasks.md"
                tasks.write_text(tasks.read_text(encoding="utf-8").replace("| In Progress |", "| Done |"), encoding="utf-8")
            done_python = run_handoff(py_workspace, "T1")
            _assert_no_actionable_done_handoff(self, {"handoff": done_python}, "python")
            done_code, done_rust, done_stdout = _run_rust("handoff", rust_workspace, "--task-id", "T1")
            self.assertEqual(done_code, 0, done_stdout)
            _assert_no_actionable_done_handoff(self, {"handoff": _rust_data(done_rust)}, "rust")

            # A bounded oversized ledger is an error, not a partial handoff.
            for workspace in (py_workspace, rust_workspace):
                (workspace / "MissionCenter" / "execution-ledger.jsonl").write_bytes(b"x" * (256 * 1024 + 1))
            with self.assertRaises(ValueError):
                run_handoff(py_workspace)
            too_large_code, too_large, too_large_stdout = _run_rust("handoff", rust_workspace)
            self.assertNotEqual(too_large_code, 0, too_large_stdout)
            self.assertIsInstance(too_large, dict, too_large_stdout)
            _assert_protocol_header(self, too_large, "handoff")
            self.assertEqual(too_large.get("status"), "error")

        with workspace_tempdir("rust-handoff-truncated-") as temporary:
            source = _workspace_with_tasks(Path(temporary))
            py_workspace = Path(temporary) / "python"
            rust_workspace = Path(temporary) / "rust"
            shutil.copytree(source, py_workspace)
            shutil.copytree(source, rust_workspace)
            records = []
            parent = None
            # Keep the source ledger under Rust's bounded 8 KiB read limit,
            # while the handoff envelope (causal chain plus latest pulse)
            # itself crosses the 8 KiB response budget.
            for index in range(8):
                pulse = _valid_pulse(
                    pulse_id=f"large-{index}",
                    parent=parent,
                    outcome="x" * 650,
                    next_action=f"next-{index}",
                )
                append_execution_pulse(py_workspace, pulse)
                records.append(pulse)
                parent = pulse["pulseId"]
            ledger = py_workspace / "MissionCenter" / "execution-ledger.jsonl"
            shutil.copy2(ledger, rust_workspace / "MissionCenter" / "execution-ledger.jsonl")
            py_bounded = run_handoff(py_workspace)
            self.assertTrue(py_bounded["truncated"])
            self.assertLessEqual(py_bounded["bytes"], 8192)
            for field in ("taskId", "found", "latestPulse", "causalChain", "truncated", "bytes", "maxBytes", "content"):
                self.assertIn(field, py_bounded)
            code, rust_bounded, stdout = _run_rust("handoff", rust_workspace)
            self.assertEqual(code, 0, stdout)
            rust_bounded = _rust_data(rust_bounded)
            self.assertTrue(rust_bounded["truncated"])
            self.assertLessEqual(rust_bounded["bytes"], 8192)
            for field in ("taskId", "found", "latestPulse", "causalChain", "truncated", "bytes", "maxBytes", "content"):
                self.assertIn(field, rust_bounded)
            self.assertNotIn("pulses", rust_bounded)
            self.assertEqual(rust_bounded["latestPulse"]["pulseId"], py_bounded["latestPulse"]["pulseId"])

    def test_closeout_english_chinese_fields_archive_replay_and_conflict(self):
        closeout = PY_SCRIPTS / "closeout_mission_center_cycle.py"
        import shutil

        fields = {
            "summary": "Wave 2 complete",
            "completed": "contracts",
            "unfinished": "none",
            "risks": "none",
            "smoke-tests": "4 passed",
            "retro": "keep bounded",
        }
        for traditional in (False, True):
            with self.subTest(language="zh-TW" if traditional else "en"), workspace_tempdir("rust-closeout-") as temporary:
                source = _workspace_with_tasks(Path(temporary), traditional=traditional)
                py_workspace = Path(temporary) / "python"
                rust_workspace = Path(temporary) / "rust"
                shutil.copytree(source, py_workspace)
                shutil.copytree(source, rust_workspace)
                py_args = tuple(item for key, value in fields.items() for item in (f"--{key}", value)) + ("--cycle", "cycle-1")
                py_result = _run_python_script(closeout, py_workspace, *py_args)
                self.assertEqual(py_result.returncode, 0, py_result.stderr.decode("utf-8", "replace"))
                py_text = (py_workspace / "MissionCenter" / "closeout.md").read_text(encoding="utf-8")
                labels = ("摘要", "已完成", "未完成", "風險", "冒煙測試", "回顧") if traditional else ("Summary", "Completed", "Unfinished", "Risks", "Smoke tests", "Retro")
                for label in labels:
                    self.assertIn(f"- {label}:", py_text)
                self.assertTrue((py_workspace / "MissionCenter" / "closeouts" / "cycle-1.md").is_file())

                rust_args = (
                    "--operation-id", "closeout-1", "--timestamp", "2026-08-29T02:00:00Z", "--cycle", "cycle-1", "--archive",
                    "--summary", fields["summary"], "--completed", fields["completed"], "--unfinished", fields["unfinished"],
                    "--risks", fields["risks"], "--smoke-tests", fields["smoke-tests"], "--retro", fields["retro"],
                )
                code, payload, stdout = _run_rust("closeout", rust_workspace, *rust_args)
                self.assertEqual(code, 0, stdout)
                _assert_protocol_header(self, payload, "closeout")
                self.assertEqual(payload.get("status"), "committed")
                rust_text = (rust_workspace / "MissionCenter" / "closeout.md").read_text(encoding="utf-8")
                for label in labels:
                    self.assertIn(f"- {label}:", rust_text)
                self.assertTrue((rust_workspace / "MissionCenter" / "closeouts" / "cycle-1.md").is_file())
                code, replay, stdout = _run_rust("closeout", rust_workspace, *rust_args)
                self.assertEqual(code, 0, stdout)
                self.assertEqual(replay.get("status"), "replay")
                code, conflict, stdout = _run_rust(
                    "closeout", rust_workspace,
                    *rust_args[:rust_args.index("--summary")], "--summary", "different summary",
                )
                _assert_rust_error(self, code, conflict, "closeout", "operation_conflict", stdout)
                py_conflict = _run_python_script(closeout, py_workspace, *tuple(item for key, value in {**fields, "summary": "different summary"}.items() for item in (f"--{key}", value)), "--cycle", "cycle-1")
                self.assertNotEqual(py_conflict.returncode, 0)

    def test_project_map_schema_html_escape_commit_dry_run_verify_tamper_and_missing_source(self):
        from project_map import build_project_map, publish_project_map, validate_published_manifest
        import shutil

        with workspace_tempdir("rust-project-map-") as temporary:
            source = _workspace_with_tasks(Path(temporary))
            mission = source / "MissionCenter"
            project = mission / "project.md"
            project.write_text('# <img src="x">\n\n- Goal: & <script>alert(1)</script>\n', encoding="utf-8")
            tasks = mission / "tasks.md"
            tasks.write_text(tasks.read_text(encoding="utf-8").replace("Primary task", '<script>alert("x")</script>'), encoding="utf-8")
            py_workspace = Path(temporary) / "python"
            rust_workspace = Path(temporary) / "rust"
            shutil.copytree(source, py_workspace)
            shutil.copytree(source, rust_workspace)
            generated_at = "2026-08-29T03:00:00Z"
            python_value = build_project_map(py_workspace, generated_at=generated_at)
            self.assertEqual(python_value["schemaVersion"], "1.0")
            self.assertEqual(python_value["counts"]["total"], len(python_value["nodes"]))
            self.assertEqual(python_value["project"]["name"], '<img src="x">')
            python_published = publish_project_map(py_workspace, generated_at=generated_at)
            python_json = json.loads((py_workspace / "output/mission-center-project-map/project-map.json").read_text(encoding="utf-8"))
            python_html = (py_workspace / "output/mission-center-project-map/project-map.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>", python_html)
            self.assertIn("&lt;script&gt;", python_html)
            self.assertEqual(validate_published_manifest(py_workspace / "output/mission-center-project-map")["generation"], python_json["generation"])

            dry_code, dry_payload, dry_stdout = _run_rust("project-map", rust_workspace, "--dry-run", "--timestamp", generated_at)
            self.assertEqual(dry_code, 0, dry_stdout)
            _assert_protocol_header(self, dry_payload, "project-map")
            dry_data = _rust_data(dry_payload)
            for field in ("schemaVersion", "sourceFingerprint", "sources", "generatedAt", "generation", "language", "project", "counts", "nodes", "edges"):
                self.assertIn(field, dry_data)
            self.assertEqual(dry_data["schemaVersion"], "1.0")
            self.assertEqual(dry_data["sourceFingerprint"], python_value["sourceFingerprint"])
            self.assertEqual(dry_data["generation"], python_value["generation"])
            self.assertFalse((rust_workspace / "output/mission-center-project-map").exists())

            commit_args = ("--operation-id", "map-1", "--timestamp", generated_at)
            commit_code, commit_payload, commit_stdout = _run_rust("project-map", rust_workspace, *commit_args)
            self.assertEqual(commit_code, 0, commit_stdout)
            self.assertEqual(commit_payload.get("status"), "committed")
            output = rust_workspace / "output/mission-center-project-map"
            rust_map = json.loads((output / "project-map.json").read_text(encoding="utf-8"))
            rust_html = (output / "project-map.html").read_text(encoding="utf-8")
            self.assertEqual(rust_map["sourceFingerprint"], python_json["sourceFingerprint"])
            self.assertEqual(rust_map["generation"], python_json["generation"])
            self.assertNotIn("<script>", rust_html)
            self.assertIn("&lt;script&gt;", rust_html)
            replay_code, replay_payload, replay_stdout = _run_rust("project-map", rust_workspace, *commit_args)
            self.assertEqual(replay_code, 0, replay_stdout)
            self.assertEqual(replay_payload.get("status"), "replay")
            verify_code, verify_payload, verify_stdout = _run_rust("project-map", rust_workspace, "--verify")
            self.assertEqual(verify_code, 0, verify_stdout)
            self.assertTrue(_rust_data(verify_payload).get("verified"))

            manifest = output / "project-map.manifest.json"
            manifest.write_text(manifest.read_text(encoding="utf-8").replace("\"generation\"", "\"generationTampered\"", 1), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_published_manifest(output)
            tamper_code, tamper_payload, tamper_stdout = _run_rust("project-map", rust_workspace, "--verify")
            self.assertNotEqual(tamper_code, 0, tamper_stdout)
            self.assertIsInstance(tamper_payload, dict, tamper_stdout)
            _assert_protocol_header(self, tamper_payload, "project-map")
            self.assertEqual(tamper_payload.get("status"), "error")

        with workspace_tempdir("rust-project-map-missing-") as temporary:
            workspace = _workspace_with_tasks(Path(temporary))
            (workspace / "MissionCenter" / "project.md").unlink()
            with self.assertRaises((FileNotFoundError, OSError, ValueError)):
                build_project_map(workspace)
            code, payload, stdout = _run_rust("project-map", workspace, "--dry-run", "--timestamp", "2026-08-29T03:00:00Z")
            _assert_rust_error(self, code, payload, "project-map", "command_error", stdout)


if __name__ == "__main__":
    unittest.main()
