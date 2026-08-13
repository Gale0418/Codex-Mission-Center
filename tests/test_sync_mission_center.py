import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
SYNC = SCRIPTS / "sync_mission_center.py"
SUGGEST_SMOKE = SCRIPTS / "suggest_smoke_tests.py"
FIXTURE = ROOT / "tests" / "fixtures" / "demo-workspace"
sys.path.insert(0, str(SCRIPTS))

from common.markdown_table import parse_table_blocks, parse_table_rows
from sync_mission_center import compute_progress, parse_table


class SyncMissionCenterTests(unittest.TestCase):
    def test_smoke_suggester_preserves_escaped_pipes_and_crlf(self):
        with workspace_tempdir("suggest-smoke-") as temporary:
            workspace = Path(temporary)
            mission = workspace / "MissionCenter"
            mission.mkdir()
            tasks = mission / "tasks.md"
            tasks.write_bytes(
                b"| ID | Title | Type | Labels | Verification |\r\n"
                b"| --- | --- | --- | --- | --- |\r\n"
                b"| T-1 | a\\|b | Task | execution | |\r\n"
            )
            result = subprocess.run(
                [sys.executable, str(SUGGEST_SMOKE), str(workspace), "--apply"],
                capture_output=True, text=True, encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("a\\|b", tasks.read_text(encoding="utf-8"))

    def test_common_table_parser_handles_multiple_crlf_tables_and_escaped_pipes(self):
        tables, errors = parse_table_blocks(
            "| ID | Note |\r\n| --- | --- |\r\n| A-1 | a\\|b |\r\n\r\n| ID | Status |\r\n| --- | --- |\r\n| B-1 | Ready |\r\n".splitlines(),
            table_name="tables.md",
        )
        self.assertEqual(errors, [])
        self.assertEqual([[row["ID"] for row in table] for table in tables], [["A-1"], ["B-1"]])
        self.assertEqual(tables[0][0]["Note"], "a|b")

    def test_common_table_parser_reports_malformed_escape(self):
        _, errors = parse_table_rows(
            ["| ID |", "| --- |", "| A-1 \\"], table_name="tasks.md"
        )
        self.assertTrue(any("malformed" in error for error in errors))

    def test_sync_preserves_unmanaged_legacy_summaries_by_default(self):
        with workspace_tempdir("sync-legacy-") as temporary:
            workspace = Path(temporary) / "workspace"
            shutil.copytree(FIXTURE, workspace)
            project = workspace / "MissionCenter" / "project.md"
            progress = workspace / "MissionCenter" / "progress.md"
            project.write_text("# Legacy project\n\nKeep every historical line.\n", encoding="utf-8")
            progress.write_text("# Legacy progress\n\nKeep the curated current lane.\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SYNC), str(workspace)],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(project.read_text(encoding="utf-8"), "# Legacy project\n\nKeep every historical line.\n")
            self.assertEqual(progress.read_text(encoding="utf-8"), "# Legacy progress\n\nKeep the curated current lane.\n")
            self.assertTrue(
                (workspace / "output" / "mission-center-assets" / "visual-state.json").is_file()
            )

    def test_rewrite_summaries_marks_files_as_managed(self):
        with workspace_tempdir("sync-managed-") as temporary:
            workspace = Path(temporary) / "workspace"
            shutil.copytree(FIXTURE, workspace)

            result = subprocess.run(
                [sys.executable, str(SYNC), str(workspace), "--rewrite-summaries"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("project.md", "progress.md"):
                text = (workspace / "MissionCenter" / name).read_text(encoding="utf-8")
                self.assertIn("<!-- mission-center-managed-summary v=1 -->", text)

    def test_sync_writes_visual_state_json(self):
        with workspace_tempdir("sync-state-") as temporary:
            workspace = Path(temporary) / "workspace"
            shutil.copytree(FIXTURE, workspace)
            result = subprocess.run(
                [sys.executable, str(SYNC), str(workspace), "--goal", "Demo"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            state_path = workspace / "output" / "mission-center-assets" / "visual-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["goal"], "Demo")
            self.assertEqual(
                [agent["id"] for agent in state["agents"]],
                ["DEMO-001", "DEMO-002", "DEMO-003"],
            )

    def test_progress_uses_estimates_when_present(self):
        percent, mode, _, _ = compute_progress(
            [
                {"ID": "T1", "Title": "完成", "Status": "Done", "Estimate": "3"},
                {"ID": "T2", "Title": "進行", "Status": "In Progress", "Estimate": "1"},
            ]
        )
        self.assertEqual(percent, 75)
        self.assertEqual(mode, "3/4 estimated")

    def test_progress_falls_back_to_task_count_without_estimates(self):
        percent, mode, _, _ = compute_progress(
            [
                {"ID": "T1", "Title": "完成", "Status": "Done", "Estimate": ""},
                {"ID": "T2", "Title": "待辦", "Status": "Backlog", "Estimate": ""},
            ]
        )
        self.assertEqual(percent, 50)
        self.assertEqual(mode, "1/2 tasks")

    def test_progress_falls_back_to_task_count_for_mixed_estimates(self):
        percent, mode, _, _ = compute_progress(
            [
                {"ID": "T1", "Title": "完成", "Status": "Done", "Estimate": "1"},
                {"ID": "T2", "Title": "進行", "Status": "In Progress", "Estimate": ""},
            ]
        )
        self.assertEqual(percent, 50)
        self.assertEqual(mode, "1/2 tasks")

    def test_parse_table_preserves_escaped_pipe(self):
        with workspace_tempdir("sync-pipe-") as temporary:
            tasks = Path(temporary) / "tasks.md"
            tasks.write_text(
                "| ID | Title | Status | Estimate |\n"
                "| --- | --- | --- | --- |\n"
                "| T1 | A \\| B | Done | 1 |\n",
                encoding="utf-8",
            )
            self.assertEqual(parse_table(tasks)[0]["Title"], "A | B")

    def test_parse_table_rejects_malformed_rows(self):
        with workspace_tempdir("sync-malformed-") as temporary:
            tasks = Path(temporary) / "tasks.md"
            tasks.write_text(
                "| ID | Title | Status |\n"
                "| --- | --- | --- |\n"
                "| T1 | missing status |\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "expected 3"):
                parse_table(tasks)

    def test_progress_uses_only_leaf_tasks_and_ignores_orphan_parent(self):
        percent, mode, active, blocked = compute_progress(
            [
                {"ID": "E1", "Title": "Epic", "Status": "Done", "Estimate": "100"},
                {"ID": "T1", "Title": "Child", "Parent": "E1", "Status": "Done", "Estimate": "3"},
                {"ID": "T2", "Title": "Orphan parent", "Parent": "MISSING", "Status": "In Progress", "Estimate": "1"},
            ]
        )
        self.assertEqual((percent, mode), (75, "3/4 estimated"))
        self.assertEqual(active, ["T2 Orphan parent (In Progress)"])
        self.assertEqual(blocked, [])

    def test_progress_excludes_childless_epics_but_keeps_parent_filtering(self):
        percent, mode, active, blocked = compute_progress(
            [
                {"ID": "E-empty", "Title": "Empty Epic", "Type": "Epic", "Status": "Done", "Estimate": "100"},
                {"ID": "E-parent", "Title": "Parent Epic", "Type": "Epic", "Status": "Done", "Estimate": "100"},
                {"ID": "T1", "Title": "Child", "Type": "Task", "Parent": "E-parent", "Status": "Done", "Estimate": "3"},
                {"ID": "T2", "Title": "Open", "Type": "Task", "Status": "Ready", "Estimate": "1"},
            ]
        )
        self.assertEqual((percent, mode), (75, "3/4 estimated"))
        self.assertEqual(active, ["T2 Open (Ready)"])
        self.assertEqual(blocked, [])

    def test_progress_does_not_hide_self_parent_task(self):
        tasks = [
            {"ID": "T1", "Title": "Self parent", "Type": "Task", "Parent": "T1", "Status": "Ready", "Estimate": "1"},
        ]
        percent, mode, active, blocked = compute_progress(tasks)
        self.assertEqual((percent, mode), (0, "0/1 estimated"))
        self.assertEqual(active, ["T1 Self parent (Ready)"])
        self.assertEqual(blocked, [])

    def test_sync_creates_each_missing_summary_without_rewriting_existing_legacy_file(self):
        with workspace_tempdir("sync-missing-summary-") as temporary:
            workspace = Path(temporary)
            mission = workspace / "MissionCenter"
            mission.mkdir()
            (mission / "tasks.md").write_text(
                "| ID | Title | Status |\n| --- | --- | --- |\n| T1 | Work | Ready |\n",
                encoding="utf-8",
            )
            (mission / "smoke-tests.md").write_text(
                "| ID | Result |\n| --- | --- |\n", encoding="utf-8"
            )
            legacy = mission / "project.md"
            legacy.write_text("# Legacy project\n\nKeep this.\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SYNC), str(workspace)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(legacy.read_text(encoding="utf-8"), "# Legacy project\n\nKeep this.\n")
            self.assertTrue((mission / "progress.md").is_file())

    def test_shared_parser_uses_first_top_level_table_and_can_read_indented_table(self):
        lines = [
            "| ID | Title |", "| --- | --- |", "| A | first |", "",
            "| ID | Title |", "| --- | --- |", "| B | second |",
        ]
        rows, errors = parse_table_rows(lines, table_name="tables.md")
        self.assertEqual(errors, [])
        self.assertEqual(rows, [{"ID": "A", "Title": "first"}])
        indented = ["  | ID | Title |", "  | --- | --- |", "  | A | nested |"]
        rows, errors = parse_table_rows(indented, table_name="nested.md", include_indented=True)
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["Title"], "nested")

    def test_shared_parser_non_strict_skips_malformed_row(self):
        rows, errors = parse_table_rows(
            ["| ID | Title |", "| --- | --- |", "| A | ok |", "| B |"],
            table_name="rows.md",
            strict=False,
        )
        self.assertEqual(rows, [{"ID": "A", "Title": "ok"}])
        self.assertEqual(len(errors), 1)

if __name__ == "__main__":
    unittest.main()
