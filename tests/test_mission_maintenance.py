import json
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from tests import workspace_tempdir

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mission_maintenance import (
    append_daily_log,
    atomic_write_if_changed,
    compute_workspace_fingerprint,
    extract_focus_tasks,
    extract_next_candidates,
    extract_working_set_tasks,
    parse_daily_log,
    run_daily,
    append_execution_pulse,
    run_handoff,
    run_status,
    run_resume,
    run_sync,
    validate_critical_lessons,
    validate_daily_log_text,
    validate_guardrails,
    normalize_guardrail_rows,
)


def make_workspace(base: Path, language: str = "en") -> Path:
    root = base / "workspace"
    mission = root / "MissionCenter"
    mission.mkdir(parents=True)
    if language == "zh-TW":
        project = "# 專案\n\n- 專案: 測試\n- 目標: 省額度\n- 週期: 今日\n"
        tasks = (
            "# 任務\n\n"
            "| ID | 標題 | 類型 | 父層 | 優先級 | 狀態 | 負責人 | 依賴 | 下一步 | 驗證方式 | 估時 | 標籤 | 備註 |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| T1 | 重要修正 | Task | | P0 | Ready | Codex | | 實作 | unittest | 1 | | |\n"
            "| T2 | 已完成 | Task | | P0 | Done | Codex | | 無 | unittest | 1 | | |\n"
            "| T3 | 次要阻塞 | Task | | P1 | Blocked | Codex | | 等待 | unittest | 1 | | |\n"
        )
    else:
        project = "# Project\n\n- Project: Test\n- Goal: Save tokens\n- Cycle: Today\n"
        tasks = (
            "# Tasks\n\n"
            "| ID | Title | Type | Parent | Priority | Status | Owner | Depends on | Next action | Verification | Estimate | Labels | Comments |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            "| T1 | Critical fix | Task | | P0 | Ready | Codex | | Implement | unittest | 1 | | |\n"
            "| T2 | Finished | Task | | P0 | Done | Codex | | None | unittest | 1 | | |\n"
            "| T3 | Lesser block | Task | | P1 | Blocked | Codex | | Wait | unittest | 1 | | |\n"
        )
    (mission / "project.md").write_text(project, encoding="utf-8")
    (mission / "tasks.md").write_text(tasks, encoding="utf-8")
    return root


class MissionMaintenanceTests(unittest.TestCase):
    def test_execution_pulses_are_idempotent_causal_and_resume_bounded(self):
        with workspace_tempdir("memory-pulse-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            tasks_before = (mission / "tasks.md").read_bytes()
            first = append_execution_pulse(workspace, {
                "pulseId": "pulse-a",
                "taskId": "T1",
                "phase": "implement",
                "outcome": "A complete",
                "nextAction": "continue",
                "evidenceRef": "tests/A",
                "budgetRemaining": 100,
                "causalParent": None,
            })
            duplicate = append_execution_pulse(workspace, {
                "pulseId": "pulse-a",
                "taskId": "T1",
                "phase": "implement",
                "outcome": "A complete",
                "nextAction": "continue",
                "evidenceRef": "tests/A",
                "budgetRemaining": 100,
                "causalParent": None,
            })
            append_execution_pulse(workspace, {
                "pulseId": "pulse-b",
                "taskId": "T1",
                "phase": "verify",
                "outcome": "B complete",
                "nextAction": "resume focused tests",
                "evidenceRef": "tests/B",
                "budgetRemaining": 42,
                "causalParent": "pulse-a",
            })
            handoff = run_handoff(workspace, "T1")
            self.assertTrue(first["appended"])
            self.assertTrue(duplicate["duplicate"])
            self.assertEqual([pulse["pulseId"] for pulse in handoff["causalChain"]], ["pulse-a", "pulse-b"])
            self.assertEqual(handoff["nextAction"], "resume focused tests")
            self.assertEqual(handoff["executionNextAction"], "resume focused tests")
            self.assertEqual(handoff["nextActionSource"], "execution-pulse")
            self.assertTrue(handoff["executionOnly"])
            self.assertEqual(handoff["lifecycleSource"], "tasks.md")
            self.assertEqual(handoff["canonicalTask"], {
                "ID": "T1", "Title": "Critical fix", "Priority": "P0", "Status": "Ready",
                "Depends on": "", "Next action": "Implement", "Verification": "unittest",
            })
            self.assertEqual(handoff["budgetRemaining"], 42)
            packet = run_resume(workspace, "2026-08-09")
            self.assertEqual(packet["ledgerStatus"], "ready")
            self.assertIn("handoff", packet["content"])
            self.assertLessEqual(packet["bytes"], 16384)
            self.assertEqual((mission / "tasks.md").read_bytes(), tasks_before)

    def test_pulse_requires_canonical_task_and_missing_latest_task_fails_closed(self):
        with workspace_tempdir("memory-pulse-task-binding-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            pulse = {
                "pulseId": "pulse-bound",
                "taskId": "T1",
                "phase": "implement",
                "outcome": "bound",
                "nextAction": "verify",
                "evidenceRef": "tests/bound",
                "budgetRemaining": 7,
                "causalParent": None,
            }
            with self.assertRaises(ValueError):
                append_execution_pulse(workspace, {**pulse, "taskId": "UNKNOWN"})
            append_execution_pulse(workspace, pulse)
            run_sync(workspace, date_str="2026-08-09")
            (mission / "tasks.md").write_text(
                (mission / "tasks.md").read_text(encoding="utf-8").replace(
                    "| T1 | Critical fix |", "| TX | Removed task |"
                ),
                encoding="utf-8",
            )
            tasks_after_delete = (mission / "tasks.md").read_bytes()
            with self.assertRaises(ValueError):
                run_handoff(workspace)
            packet = run_resume(workspace, "2026-08-09")
            self.assertEqual(packet["ledgerStatus"], "corrupt")
            self.assertIsNone(packet["handoff"])
            self.assertEqual((mission / "tasks.md").read_bytes(), tasks_after_delete)

    def test_execution_pulse_rejects_sensitive_fields_and_corrupt_ledger_fails_closed(self):
        with workspace_tempdir("memory-pulse-reject-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            for forbidden in ("prompt", "reasoning", "command", "secret"):
                with self.assertRaises(ValueError):
                    append_execution_pulse(workspace, {
                        "taskId": "T1", "phase": "x", "outcome": "x", "nextAction": "x",
                        "evidenceRef": "x", "budgetRemaining": 1, "causalParent": None,
                        forbidden: "do not persist this",
                    })
            run_sync(workspace, date_str="2026-08-09")
            tasks_before = (mission / "tasks.md").read_bytes()
            (mission / "execution-ledger.jsonl").write_text("{not json}\n", encoding="utf-8")
            packet = run_resume(workspace, "2026-08-09")
            self.assertEqual(packet["ledgerStatus"], "corrupt")
            self.assertEqual(packet["fallbackReason"], "execution ledger corrupt")
            self.assertIsNone(packet["handoff"])
            self.assertNotIn("handoff", packet["content"])
            self.assertEqual((mission / "tasks.md").read_bytes(), tasks_before)

    def test_execution_pulse_uses_shared_secret_scanner_and_serializes_writers(self):
        with workspace_tempdir("memory-pulse-lock-") as temporary:
            workspace = make_workspace(Path(temporary))
            secret = {
                "taskId": "T1", "phase": "verify", "outcome": "ghp_123456789012345678901234567890123456",
                "nextAction": "continue", "evidenceRef": "tests/lock", "budgetRemaining": 1,
                "causalParent": None,
            }
            with self.assertRaisesRegex(ValueError, "secret-like"):
                append_execution_pulse(workspace, secret)

            def append(index):
                return append_execution_pulse(workspace, {
                    "pulseId": f"parallel-{index}", "taskId": "T1", "phase": "verify",
                    "outcome": f"result-{index}", "nextAction": "continue",
                    "evidenceRef": f"tests/parallel-{index}", "budgetRemaining": 1,
                    "causalParent": None,
                })

            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(append, range(16)))
            self.assertTrue(all(result["appended"] for result in results))
            ledger = workspace / "MissionCenter/execution-ledger.jsonl"
            records = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
            self.assertEqual({record["pulseId"] for record in records}, {f"parallel-{index}" for index in range(16)})

    def test_resume_treats_ledger_oserror_as_corrupt_without_aborting(self):
        with workspace_tempdir("memory-pulse-oserror-") as temporary:
            workspace = make_workspace(Path(temporary))
            run_sync(workspace, date_str="2026-08-09")
            (workspace / "MissionCenter/execution-ledger.jsonl").write_text("{}\n", encoding="utf-8")
            with patch("mission_maintenance.run_handoff", side_effect=OSError("read denied")):
                packet = run_resume(workspace, "2026-08-09")
            self.assertEqual(packet["ledgerStatus"], "corrupt")
            self.assertEqual(packet["fallbackReason"], "execution ledger corrupt")
            self.assertIsNone(packet["handoff"])

    def test_execution_ledger_rejects_invalid_time_and_forward_parent(self):
        with workspace_tempdir("memory-pulse-envelope-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            append_execution_pulse(workspace, {
                "pulseId": "pulse-a", "taskId": "T1", "phase": "implement",
                "outcome": "A", "nextAction": "continue", "evidenceRef": "tests/A",
                "budgetRemaining": 1, "causalParent": None,
            })
            ledger = mission / "execution-ledger.jsonl"
            original = ledger.read_text(encoding="utf-8")
            record = json.loads(original)
            record["recordedAt"] = "not-a-date"
            ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid recordedAt"):
                run_handoff(workspace)

            child = dict(record)
            child.update({"pulseId": "pulse-child", "causalParent": "pulse-parent", "recordedAt": "2026-08-20T12:00:00Z"})
            parent = dict(record)
            parent.update({"pulseId": "pulse-parent", "causalParent": None, "recordedAt": "2026-08-20T11:00:00+00:00"})
            ledger.write_text(
                json.dumps(child) + "\n" + json.dumps(parent) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "must precede its child"):
                run_handoff(workspace)

            parent_later = dict(parent)
            parent_later["recordedAt"] = "2026-08-20T15:00:00Z"
            ledger.write_text(
                json.dumps(parent_later) + "\n" + json.dumps(child) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "must precede or equal"):
                run_handoff(workspace)

    def test_resume_budget_is_hard_capped_at_sixteen_kib(self):
        with workspace_tempdir("memory-pulse-budget-") as temporary:
            workspace = make_workspace(Path(temporary))
            run_sync(workspace, date_str="2026-08-09")
            packet = run_resume(workspace, "2026-08-09", max_bytes=999999)
            self.assertEqual(packet["maxBytes"], 16384)
            self.assertLessEqual(packet["bytes"], 16384)
            append_execution_pulse(workspace, {
                "taskId": "T1", "phase": "verify", "outcome": "bounded",
                "nextAction": "continue", "evidenceRef": "tests/budget",
                "budgetRemaining": 1, "causalParent": None,
            })
            bounded = run_resume(workspace, "2026-08-09", max_bytes=512)
            self.assertEqual(bounded["ledgerStatus"], "ready")
            self.assertLessEqual(bounded["bytes"], 512)
            self.assertIsNone(bounded["content"]["handoff"])
            self.assertIn("handoff", bounded["readNext"])
            self.assertTrue(bounded["content"]["brief"])
            self.assertGreater(bounded["context"]["includedBytes"]["brief"], 0)
            self.assertIsNotNone(bounded["content"]["brief"])

    def test_critical_lessons_rejects_non_incident_paths(self):
        with workspace_tempdir("memory-incidents-") as temporary:
            root = Path(temporary)
            incidents = root / "incidents"
            incidents.mkdir()
            (incidents / "INC-123.md").write_text("evidence", encoding="utf-8")
            (root / "README.md").write_text("not incident evidence", encoding="utf-8")
            lessons = root / "critical-lessons.md"
            header = (
                "# Critical Lessons\n\n## Active Lessons\n\n"
                "| ID | Applies when | Symptoms | Root cause | Correct action | Avoid | Verification | Incident | Last confirmed |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            )
            def validate(incident):
                lessons.write_text(header + f"| CL-001 | general | s | r | c | a | v | {incident} | 2026-08-13 |\n", encoding="utf-8")
                return validate_critical_lessons(lessons, incidents)

            self.assertEqual(validate("INC-123"), [])
            self.assertEqual(validate("incidents/INC-123.md"), [])
            self.assertEqual(validate(r"incidents\INC-123.md"), [])
            self.assertTrue(any("invalid Incident pointer" in error for error in validate("../README.md")))
            self.assertTrue(any("invalid Incident pointer" in error for error in validate(r"..\README.md")))
            self.assertTrue(any("invalid Incident pointer" in error for error in validate("README.md")))

    def test_focus_contains_only_unfinished_p0_in_both_languages(self):
        for language in ("en", "zh-TW"):
            with workspace_tempdir(f"memory-{language}-") as temporary:
                workspace = make_workspace(Path(temporary), language)
                result = run_sync(workspace, date_str="2026-08-09")
                self.assertEqual(result["focusCount"], 1)
                ws = (workspace / "MissionCenter" / "working-set.md").read_text(encoding="utf-8")
                self.assertIn("| T1 |", ws)
                brief = (workspace / "MissionCenter" / "brief.md").read_text(encoding="utf-8")
                self.assertNotIn("| T1 |", brief)
                self.assertIn("working-set.md", brief)

    def test_extract_focus_uses_priority_column_not_labels(self):
        tasks = [
            {"ID": "T1", "Priority": "P0", "Status": "Ready"},
            {"ID": "T2", "Priority": "P0", "Status": "Done"},
            {"ID": "T3", "Priority": "P1", "Status": "Ready", "Labels": "P0"},
        ]
        self.assertEqual([row["ID"] for row in extract_focus_tasks(tasks)], ["T1"])

    def test_daily_log_groups_dates_and_deduplicates_normalized_messages(self):
        with workspace_tempdir("memory-daily-") as temporary:
            workspace = make_workspace(Path(temporary))
            run_daily(workspace, "  Fixed   parser  ", "2026-08-08")
            result = run_daily(workspace, "Fixed parser", "2026-08-08")
            run_daily(workspace, "Released", "2026-08-09")
            text = (workspace / "MissionCenter" / "daily-log.md").read_text(encoding="utf-8")
            organized, entries = parse_daily_log(text)
            self.assertFalse(result["eventAdded"])
            self.assertEqual(organized, "2026-08-09")
            self.assertEqual(entries["2026-08-08"], ["Fixed parser"])
            self.assertLess(text.index("## 2026-08-09"), text.index("## 2026-08-08"))
            self.assertEqual(validate_daily_log_text(text), [])

    def test_append_daily_log_requires_the_canonical_path(self):
        with workspace_tempdir("memory-daily-path-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            with self.assertRaises(ValueError):
                append_daily_log(mission / "progress.md", "must not land elsewhere", "2026-08-09")
            self.assertTrue(append_daily_log(mission / "daily-log.md", "recorded", "2026-08-09"))
            self.assertIn("recorded", (mission / "daily-log.md").read_text(encoding="utf-8"))

    def test_daily_placeholders_do_not_become_real_events(self):
        with workspace_tempdir("memory-placeholder-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            (mission / "daily-log.md").write_text(
                "# Daily Log\n\n- Last organized: 2026-08-09\n\n## 2026-08-09\n- None\n",
                encoding="utf-8",
            )
            run_sync(workspace, date_str="2026-08-09")
            self.assertEqual(parse_daily_log((mission / "daily-log.md").read_text(encoding="utf-8"))[1]["2026-08-09"], [])

    def test_daily_missing_workspace_does_not_create_tree(self):
        with workspace_tempdir("memory-missing-") as temporary:
            workspace = Path(temporary) / "missing"
            with self.assertRaises(FileNotFoundError):
                run_daily(workspace, "must not write", "2026-08-09")
            self.assertFalse((workspace / "MissionCenter").exists())

    def test_second_sync_same_day_is_idempotent_and_focus_ignores_unrelated_changes(self):
        with workspace_tempdir("memory-idempotent-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            run_sync(workspace, date_str="2026-08-09")
            mtimes = {name: (mission / name).stat().st_mtime_ns for name in ("brief.md", "working-set.md")}
            time.sleep(0.01)
            second = run_sync(workspace, date_str="2026-08-09")
            self.assertEqual(second["changed"], [])
            self.assertEqual(mtimes, {name: (mission / name).stat().st_mtime_ns for name in mtimes})
            (mission / "project.md").write_text("# Project\n\n- Project: Changed\n", encoding="utf-8")
            time.sleep(0.01)
            run_sync(workspace, date_str="2026-08-09")
            self.assertEqual(mtimes["working-set.md"], (mission / "working-set.md").stat().st_mtime_ns)
            self.assertNotEqual(mtimes["brief.md"], (mission / "brief.md").stat().st_mtime_ns)

    def test_force_requests_a_rebuild_without_claiming_prior_staleness(self):
        with workspace_tempdir("memory-force-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            run_sync(workspace, date_str="2026-08-09")
            mtimes = {name: (mission / name).stat().st_mtime_ns for name in ("brief.md", "working-set.md")}
            time.sleep(0.01)
            result = run_sync(workspace, force=True, date_str="2026-08-09")
            self.assertFalse(result["staleBeforeSync"])
            self.assertTrue(result["forced"])
            self.assertEqual(result["changed"], ["brief.md", "focus.md", "working-set.md"])
            self.assertTrue(all((mission / name).stat().st_mtime_ns > mtime for name, mtime in mtimes.items()))
            self.assertTrue((mission / "focus.md").is_file())

    def test_status_detects_stale_then_sync_repairs_it(self):
        with workspace_tempdir("memory-stale-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            run_sync(workspace, date_str="2026-08-09")
            self.assertFalse(run_status(workspace, "2026-08-09")["stale"])
            (mission / "tasks.md").write_text(
                (mission / "tasks.md").read_text(encoding="utf-8").replace("Critical fix", "Changed fix"),
                encoding="utf-8",
            )
            self.assertTrue(run_status(workspace, "2026-08-09")["stale"])
            run_sync(workspace, date_str="2026-08-09")
            self.assertFalse(run_status(workspace, "2026-08-09")["stale"])

    def test_fingerprint_is_stable_across_lf_and_crlf_inputs(self):
        with workspace_tempdir("memory-line-endings-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            lf_fingerprint = compute_workspace_fingerprint(workspace)
            for path in (mission / "project.md", mission / "tasks.md"):
                lf_bytes = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                path.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))
            self.assertEqual(compute_workspace_fingerprint(workspace)["value"], lf_fingerprint["value"])

    def test_brief_budget_has_explicit_truncation(self):
        with workspace_tempdir("memory-budget-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            tasks = (mission / "tasks.md").read_text(encoding="utf-8")
            rows = "".join(
                f"| X{i} | {'Very long title ' * 8}{i} | Task | | P0 | Ready | Codex | | Work | test | 1 | | |\n"
                for i in range(50)
            )
            (mission / "tasks.md").write_text(tasks + rows, encoding="utf-8")
            result = run_sync(workspace, date_str="2026-08-09", max_bytes=800)
            brief = (mission / "brief.md").read_text(encoding="utf-8")
            self.assertLessEqual(result["briefBytes"], 800)
            self.assertIn("[TRUNCATED]", brief)

    def test_working_set_budget_is_utf8_bounded_and_explicitly_truncated(self):
        with workspace_tempdir("memory-working-set-budget-") as temporary:
            workspace = make_workspace(Path(temporary), "zh-TW")
            mission = workspace / "MissionCenter"
            tasks = (mission / "tasks.md").read_text(encoding="utf-8")
            tasks += "".join(
                f"| X{i} | {'很長的工作內容' * 800}{i} | Task | | P0 | Ready | Codex | | 處理 | unittest | 1 | | |\n"
                for i in range(6)
            )
            (mission / "tasks.md").write_text(tasks, encoding="utf-8")
            run_sync(workspace, date_str="2026-08-09")
            working_set = (mission / "working-set.md").read_text(encoding="utf-8")
            self.assertLessEqual(len(working_set.encode("utf-8")), 4096)
            self.assertIn("[TRUNCATED]", working_set)
            self.assertIn("tasks.md", working_set)
            self.assertFalse(run_status(workspace, "2026-08-09")["stale"])

    def test_atomic_write_preserves_mtime_when_unchanged(self):
        with workspace_tempdir("memory-atomic-") as temporary:
            path = Path(temporary) / "value.txt"
            self.assertTrue(atomic_write_if_changed(path, "same\n"))
            mtime = path.stat().st_mtime_ns
            time.sleep(0.01)
            self.assertFalse(atomic_write_if_changed(path, "same\n"))
            self.assertEqual(mtime, path.stat().st_mtime_ns)

    def test_guardrail_validation_rejects_invalid_values(self):
        errors = validate_guardrails([{
            "ID": "bad", "Severity": "Huge", "Applies when": "always", "Pitfall": "x",
            "Must follow": "y", "Verification": "z", "Source": "human",
            "Last confirmed": "yesterday", "Status": "Candidate",
        }])
        self.assertTrue(any("invalid ID" in error for error in errors))
        self.assertTrue(any("invalid status" in error for error in errors))

    def test_traditional_chinese_guardrail_values_are_canonicalized(self):
        rows = normalize_guardrail_rows([{"ID": "GR-001", "嚴重度": "高", "狀態": "啟用"}])
        self.assertEqual(rows[0]["Severity"], "High")
        self.assertEqual(rows[0]["Status"], "Active")

    def test_traditional_chinese_daily_log_uses_full_width_colon(self):
        with workspace_tempdir("memory-colon-") as temporary:
            workspace = make_workspace(Path(temporary), "zh-TW")
            run_sync(workspace, date_str="2026-08-09")
            daily = (workspace / "MissionCenter/daily-log.md").read_text(encoding="utf-8")
            self.assertIn("- 最後整理： 2026-08-09", daily)

    def test_working_set_prioritizes_blocked_in_progress_review_then_ready(self):
        tasks = [
            {"ID": "T-ready", "Priority": "P1", "Status": "Ready"},
            {"ID": "T-review", "Priority": "P3", "Status": "Review"},
            {"ID": "T-progress", "Priority": "P3", "Status": "In Progress"},
            {"ID": "T-blocked", "Priority": "P3", "Status": "Blocked"},
            {"ID": "T-backlog", "Priority": "P0", "Status": "Backlog"},
        ]
        self.assertEqual(
            [task["ID"] for task in extract_working_set_tasks(tasks)],
            ["T-blocked", "T-progress", "T-review", "T-ready"],
        )

    def test_working_set_lists_at_most_two_backlog_candidates_separately(self):
        tasks = [
            {"ID": "D", "Priority": "P0", "Status": "Done"},
            {"ID": "R", "Title": "Run", "Priority": "P1", "Status": "Ready"},
            {"ID": "B1", "Title": "One", "Priority": "P1", "Status": "Backlog", "Depends on": "D"},
            {"ID": "B2", "Title": "Two", "Priority": "P2", "Status": "Backlog"},
            {"ID": "B3", "Title": "Three", "Priority": "P3", "Status": "Backlog"},
            {"ID": "BX", "Title": "Blocked dependency", "Priority": "P0", "Status": "Backlog", "Depends on": "MISSING-1"},
        ]
        self.assertEqual([row["ID"] for row in extract_next_candidates(tasks)], ["B1", "B2"])
        self.assertEqual([row["ID"] for row in extract_working_set_tasks(tasks)], ["R"])

    def test_resume_includes_p1_ready_when_no_p0_and_honors_budget(self):
        with workspace_tempdir("memory-resume-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            tasks = (mission / "tasks.md").read_text(encoding="utf-8").replace("| P0 | Ready |", "| P1 | Ready |", 1)
            (mission / "tasks.md").write_text(tasks, encoding="utf-8")
            run_sync(workspace, date_str="2026-08-09")
            self.assertIn("T1", run_status(workspace, "2026-08-09")["workingSetTasks"])
            (mission / "critical-lessons.md").write_text("# Critical Lessons\n\n" + ("x" * 7000), encoding="utf-8")
            packet = run_resume(workspace, "2026-08-09", max_bytes=512)
            self.assertLessEqual(packet["bytes"], 512)
            self.assertTrue(packet["truncated"])
            self.assertEqual(packet["truncatedMarker"], "[TRUNCATED]")

    def test_status_is_date_stale_without_source_change(self):
        with workspace_tempdir("memory-date-stale-") as temporary:
            workspace = make_workspace(Path(temporary))
            run_sync(workspace, date_str="2026-08-09")
            result = run_status(workspace, "2026-08-10")
            self.assertTrue(result["sourceFresh"])
            self.assertFalse(result["dateFresh"])
            self.assertEqual(result["staleReasons"], ["organized_date_mismatch"])

    def test_critical_lesson_requires_incident_and_verified_fields(self):
        with workspace_tempdir("memory-lessons-") as temporary:
            path = Path(temporary) / "critical-lessons.md"
            path.write_text(
                "# Critical Lessons\n\n## Active Lessons\n\n"
                "| ID | Applies when | Symptoms | Root cause | Correct action | Avoid | Verification | Incident | Last confirmed |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
                "| CL-001 | resume | lost task | p0-only | use set | none | test | | 2026-08-13 |\n",
                encoding="utf-8",
            )
            self.assertTrue(any("Incident evidence" in error for error in validate_critical_lessons(path, Path(temporary) / "incidents")))

    def test_resume_and_task_info_return_json_structures(self):
        from mission_maintenance import run_resume, run_task_info
        with workspace_tempdir("memory-resume-") as temporary:
            workspace = make_workspace(Path(temporary))
            run_sync(workspace, date_str="2026-08-09")
            res = run_resume(workspace, date_str="2026-08-09")
            self.assertEqual(res["schemaVersion"], "1.1")
            self.assertEqual(res["route"], "resume")
            self.assertTrue(res["sourceFresh"])
            self.assertIn("MissionCenter/working-set.md", res["filesRead"])
            self.assertEqual(set(res["content"]), {"brief", "workingSet", "activeCriticalLessons", "snapshot"})
            self.assertLessEqual(sum(len((value or "").encode("utf-8")) for value in res["content"].values()), 16384)

            task_data = run_task_info(workspace, "T1")
            self.assertEqual(task_data["task"]["ID"], "T1")
            self.assertEqual(task_data["task"]["Priority"], "P0")

    def test_critical_lessons_validation(self):
        from mission_maintenance import validate_critical_lessons
        with workspace_tempdir("memory-lessons-") as temporary:
            workspace = Path(temporary) / "workspace"
            mission = workspace / "MissionCenter"
            mission.mkdir(parents=True)
            lessons_file = mission / "critical-lessons.md"
            inc_dir = mission / "incidents"
            inc_dir.mkdir()

            lessons_file.write_text(
                "# Critical Lessons\n\n"
                "## Active Lessons\n\n"
                "| ID | Applies when | Symptoms | Root cause | Correct action | Avoid | Verification | Incident | Last confirmed |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
                "| BAD | general | s | r | c | a | v | - | 2026-08-09 |\n"
                "| CL-001 | general | s | r | c | a | v | missing-inc.md | 2026-08-09 |\n",
                encoding="utf-8"
            )
            errors = validate_critical_lessons(lessons_file, inc_dir)
            self.assertTrue(any("invalid ID" in err for err in errors))
            self.assertTrue(any("invalid Incident pointer" in err for err in errors))



    def test_critical_lessons_only_accepts_incident_ids_or_incident_paths_inside_directory(self):
        with workspace_tempdir("memory-incidents-") as temporary:
            root = Path(temporary)
            incidents = root / "incidents"
            incidents.mkdir()
            (incidents / "INC-123.md").write_text("evidence", encoding="utf-8")
            (root / "README.md").write_text("not incident evidence", encoding="utf-8")
            lessons = root / "critical-lessons.md"
            header = (
                "# Critical Lessons\n\n## Active Lessons\n\n"
                "| ID | Applies when | Symptoms | Root cause | Correct action | Avoid | Verification | Incident | Last confirmed |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            )
            def validate(incident):
                lessons.write_text(header + f"| CL-001 | general | s | r | c | a | v | {incident} | 2026-08-13 |\n", encoding="utf-8")
                return validate_critical_lessons(lessons, incidents)

            self.assertEqual(validate("INC-123"), [])
            self.assertEqual(validate("incidents/INC-123.md"), [])
            self.assertTrue(any("invalid Incident pointer" in error for error in validate("../README.md")))
            self.assertTrue(any("invalid Incident pointer" in error for error in validate("README.md")))

if __name__ == "__main__":
    unittest.main()
