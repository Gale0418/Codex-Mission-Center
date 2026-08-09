import sys
import time
import unittest
from pathlib import Path

from tests import workspace_tempdir

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mission_maintenance import (
    append_daily_log,
    atomic_write_if_changed,
    compute_workspace_fingerprint,
    extract_focus_tasks,
    parse_daily_log,
    run_daily,
    run_status,
    run_sync,
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
    def test_focus_contains_only_unfinished_p0_in_both_languages(self):
        for language in ("en", "zh-TW"):
            with workspace_tempdir(f"memory-{language}-") as temporary:
                workspace = make_workspace(Path(temporary), language)
                result = run_sync(workspace, date_str="2026-08-09")
                self.assertEqual(result["focusCount"], 1)
                focus = (workspace / "MissionCenter" / "focus.md").read_text(encoding="utf-8")
                self.assertIn("| T1 |", focus)
                self.assertNotIn("| T2 |", focus)
                self.assertNotIn("| T3 |", focus)
                brief = (workspace / "MissionCenter" / "brief.md").read_text(encoding="utf-8")
                self.assertIn("T1", brief)
                self.assertNotIn("T2", brief)
                self.assertNotIn("T3", brief)

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
            mtimes = {name: (mission / name).stat().st_mtime_ns for name in ("brief.md", "focus.md")}
            time.sleep(0.01)
            second = run_sync(workspace, date_str="2026-08-09")
            self.assertEqual(second["changed"], [])
            self.assertEqual(mtimes, {name: (mission / name).stat().st_mtime_ns for name in mtimes})
            (mission / "project.md").write_text("# Project\n\n- Project: Changed\n", encoding="utf-8")
            time.sleep(0.01)
            run_sync(workspace, date_str="2026-08-09")
            self.assertEqual(mtimes["focus.md"], (mission / "focus.md").stat().st_mtime_ns)
            self.assertNotEqual(mtimes["brief.md"], (mission / "brief.md").stat().st_mtime_ns)

    def test_force_requests_a_rebuild_without_claiming_prior_staleness(self):
        with workspace_tempdir("memory-force-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            run_sync(workspace, date_str="2026-08-09")
            mtimes = {name: (mission / name).stat().st_mtime_ns for name in ("brief.md", "focus.md")}
            time.sleep(0.01)
            result = run_sync(workspace, force=True, date_str="2026-08-09")
            self.assertFalse(result["staleBeforeSync"])
            self.assertTrue(result["forced"])
            self.assertEqual(result["changed"], [])
            self.assertEqual(mtimes, {name: (mission / name).stat().st_mtime_ns for name in mtimes})

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


if __name__ == "__main__":
    unittest.main()
