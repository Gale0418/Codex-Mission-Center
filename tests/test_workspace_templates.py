import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
SCRIPT_ROOT = ROOT / "skills" / "mission-center" / "scripts"
BOOTSTRAP = SCRIPT_ROOT / "bootstrap_mission_center.py"
SEED = SCRIPT_ROOT / "seed_task_tree.py"
NORMALIZE = SCRIPT_ROOT / "normalize_mission_center.py"
SYNC = SCRIPT_ROOT / "sync_mission_center.py"
LOG = SCRIPT_ROOT / "log_mission_center_change.py"
SNAPSHOT = SCRIPT_ROOT / "snapshot_mission_center.py"
CLOSEOUT = SCRIPT_ROOT / "closeout_mission_center_cycle.py"


def run_script(script: Path, *args: str) -> None:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"{script.name} failed ({result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


class WorkspaceTemplateTests(unittest.TestCase):
    def test_bootstrap_creates_concise_research_log_in_both_languages(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            root = Path(temporary)
            english = root / "english"
            chinese = root / "chinese"
            run_script(BOOTSTRAP, english, "--language", "en")
            run_script(BOOTSTRAP, chinese, "--language", "zh-TW")

            english_notes = (english / "MissionCenter" / "notes.md").read_text(
                encoding="utf-8"
            )
            chinese_notes = (chinese / "MissionCenter" / "notes.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "| Pre-search idea | Source | Adopted insight | License status |",
                english_notes,
            )
            self.assertIn(
                "| 搜尋前構想 | 參考來源 | 採納內容 | 授權狀態 |",
                chinese_notes,
            )

            english_hub = (
                english / "MissionCenter" / "visual-hub.md"
            ).read_text(encoding="utf-8")
            chinese_hub = (
                chinese / "MissionCenter" / "visual-hub.md"
            ).read_text(encoding="utf-8")
            self.assertIn("one helper represents one task", english_hub)
            self.assertIn("一個小人代表一個任務", chinese_hub)
            self.assertNotIn("active agent", english_hub.lower())
            self.assertNotIn("active agent", chinese_hub.lower())

    def test_seed_creates_a_small_rolling_plan_with_canonical_statuses(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "en")
            run_script(
                SEED,
                workspace,
                "--goal",
                "Create a better hair dryer",
                "--project",
                "Hair Dryer",
                "--cycle",
                "First experiment",
                "--language",
                "en",
            )

            tasks = (workspace / "MissionCenter" / "tasks.md").read_text(
                encoding="utf-8"
            )
            project = (workspace / "MissionCenter" / "project.md").read_text(
                encoding="utf-8"
            )
            rows = [
                line
                for line in tasks.splitlines()
                if line.startswith("| MC-")
            ]
            self.assertEqual(len(rows), 4)
            self.assertIn("MC-E1", rows[0])
            self.assertIn("MC-R1", rows[1])
            self.assertIn("MC-M1", rows[2])
            self.assertIn("MC-V1", rows[3])
            self.assertIn("| Ready |", rows[1])
            self.assertIn("| Backlog |", rows[2])
            self.assertNotIn("SmokeTest", tasks)
            task_lines = tasks.splitlines()
            self.assertGreater(len(task_lines), 2, "tasks.md should have a header")
            self.assertNotIn("| Review |", task_lines[2])
            self.assertIn("Hair Dryer", project)
            self.assertIn("Create a better hair dryer", project)
            self.assertIn("First experiment", project)

    def test_bootstrap_without_force_preserves_existing_files(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "en")
            notes = workspace / "MissionCenter" / "notes.md"
            notes.write_text("keep me\n", encoding="utf-8")
            run_script(BOOTSTRAP, workspace, "--language", "en")
            self.assertEqual(notes.read_text(encoding="utf-8"), "keep me\n")

    def test_seed_preserves_an_existing_project_summary(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "en")
            project = workspace / "MissionCenter" / "project.md"
            project.write_text(
                "# Project\n\n- Goal: Keep this goal\n",
                encoding="utf-8",
            )
            run_script(
                SEED,
                workspace,
                "--goal",
                "Replacement goal",
                "--language",
                "en",
            )
            self.assertEqual(
                project.read_text(encoding="utf-8"),
                "# Project\n\n- Goal: Keep this goal\n",
            )

    def test_seed_fills_summary_when_goal_field_is_missing(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            project = workspace / "MissionCenter" / "project.md"
            project.parent.mkdir(parents=True)
            project.write_text("# Project\n\nNo summary fields yet.\n", encoding="utf-8")
            run_script(
                SEED,
                workspace,
                "--goal",
                "Recovered goal",
                "--project",
                "Recovered project",
                "--cycle",
                "Recovered cycle",
                "--language",
                "en",
            )
            content = project.read_text(encoding="utf-8")
            self.assertIn("- Project: Recovered project", content)
            self.assertIn("- Goal: Recovered goal", content)
            self.assertIn("- Cycle: Recovered cycle", content)

    def test_seed_without_force_preserves_existing_tasks(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "en")
            tasks = workspace / "MissionCenter" / "tasks.md"
            tasks.write_text("keep tasks\n", encoding="utf-8")
            run_script(SEED, workspace, "--goal", "Keep tasks", "--language", "en")
            self.assertEqual(tasks.read_text(encoding="utf-8"), "keep tasks\n")

    def test_sync_keeps_traditional_chinese_project_and_progress_labels(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "zh-TW")
            run_script(SEED, workspace, "--goal", "照護計畫", "--project", "照護專案", "--cycle", "本週", "--language", "zh-TW", "--force")
            run_script(SYNC, workspace, "--project", "照護專案", "--cycle", "本週", "--goal", "照護計畫", "--labels", "照護, 家庭", "--milestone", "第一階段", "--activity", "同步完成。")

            project = (workspace / "MissionCenter" / "project.md").read_text(encoding="utf-8")
            progress = (workspace / "MissionCenter" / "progress.md").read_text(encoding="utf-8")
            self.assertIn("# 專案", project)
            self.assertIn("- 目標: 照護計畫", project)
            self.assertIn("- 活動紀錄:", project)
            self.assertIn("# 進度", progress)
            self.assertIn("- 專案: 照護專案", progress)
            self.assertIn("- 進度條:", progress)
            smoke_tests = (workspace / "MissionCenter" / "smoke-tests.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("# 冒煙測試", smoke_tests)

    def test_normalize_and_log_scripts_support_traditional_chinese_headers(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "zh-TW")
            tasks = workspace / "MissionCenter" / "tasks.md"
            tasks.write_text(
                "# 任務\n\n"
                "| ID | 標題 | 類型 | 父層 | 優先級 | 狀態 | 負責人 | 依賴 | 下一步 | 驗證方式 | 估時 | 標籤 | 備註 |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
                "| MC-T1 | 修正同步 | Task |  | high | doing | Codex |  | 更新腳本 | 測試通過 | 2 | Alpha; Beta |  |\n",
                encoding="utf-8",
            )
            run_script(NORMALIZE, workspace)
            run_script(LOG, workspace, "--change", "修正同步腳本")

            normalized = tasks.read_text(encoding="utf-8")
            project = (workspace / "MissionCenter" / "project.md").read_text(encoding="utf-8")
            self.assertIn("| P1 | In Progress |", normalized)
            self.assertIn("alpha, beta", normalized)
            self.assertIn("- 活動紀錄:", project)


    def test_sync_preserves_existing_activity_log_and_open_comments(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "en")
            run_script(
                SEED,
                workspace,
                "--goal",
                "Keep the paper trail",
                "--project",
                "Mission Archive",
                "--cycle",
                "Cycle 7",
                "--language",
                "en",
                "--force",
            )
            project = workspace / "MissionCenter" / "project.md"
            project.write_text(
                "# Project\n\n"
                "- Project: Mission Archive\n"
                "- Goal: Keep the paper trail\n"
                "- Cycle: Cycle 7\n"
                "- Labels: archive, verification\n"
                "- Activity log:\n"
                "  - Existing note\n"
                "- Open comments:\n"
                "  - Existing question\n",
                encoding="utf-8",
            )
            run_script(
                SYNC,
                workspace,
                "--project",
                "Mission Archive",
                "--cycle",
                "Cycle 7",
                "--goal",
                "Keep the paper trail",
                "--labels",
                "archive, verification",
                "--activity",
                "Fresh sync note.",
            )

            content = project.read_text(encoding="utf-8")
            self.assertIn("  - Existing note", content)
            self.assertIn("  - Existing question", content)
            self.assertIn("  - Fresh sync note.", content)


    def test_sync_preserves_custom_project_fields_and_sections(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "en")
            run_script(
                SEED,
                workspace,
                "--goal",
                "Keep custom context",
                "--project",
                "Mission Archive",
                "--cycle",
                "Cycle 8",
                "--language",
                "en",
                "--force",
            )
            project = workspace / "MissionCenter" / "project.md"
            project.write_text(
                "# Project\n\n"
                "- Project: Mission Archive\n"
                "- Goal: Keep custom context\n"
                "- Cycle: Cycle 8\n"
                "- Labels: archive, verification\n"
                "- Custom field: Preserve me\n"
                "- Activity log:\n"
                "  - Existing note\n"
                "- Open comments:\n"
                "  - Existing question\n\n"
                "## Custom section\n\n"
                "Do not delete this section.\n",
                encoding="utf-8",
            )
            run_script(
                SYNC,
                workspace,
                "--project",
                "Mission Archive",
                "--cycle",
                "Cycle 8",
                "--goal",
                "Keep custom context",
                "--labels",
                "archive, verification",
                "--activity",
                "Fresh sync note.",
            )

            content = project.read_text(encoding="utf-8")
            self.assertIn("- Custom field: Preserve me", content)
            self.assertIn("## Custom section", content)
            self.assertIn("Do not delete this section.", content)

    def test_log_uses_workspace_language_when_project_file_is_missing(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "zh-TW")
            project = workspace / "MissionCenter" / "project.md"
            project.unlink()

            run_script(LOG, workspace, "--change", "補上活動紀錄")

            content = project.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("# 專案"))
            self.assertIn("- 活動紀錄:", content)

    def test_snapshot_and_closeout_support_traditional_chinese(self):
        with workspace_tempdir("workspace-templates-") as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "zh-TW")
            run_script(
                SNAPSHOT,
                workspace,
                "--project",
                "照護專案",
                "--cycle",
                "本週",
                "--goal",
                "照護計畫",
                "--progress",
                "2/3 tasks",
                "--active",
                "MC-T1 修正同步",
                "--blocked",
                "無",
                "--decisions",
                "改用保留式同步",
                "--questions",
                "是否需要第二輪驗證",
            )
            run_script(
                CLOSEOUT,
                workspace,
                "--summary",
                "本輪完成同步與驗證",
                "--completed",
                "修正 summary 與 sync",
                "--unfinished",
                "整理文件",
                "--risks",
                "仍需真機驗證",
                "--smoke-tests",
                "2 項通過",
                "--retro",
                "下次先補回歸測試",
            )

            snapshot = (workspace / "MissionCenter" / "snapshot.md").read_text(
                encoding="utf-8"
            )
            closeout = (workspace / "MissionCenter" / "closeout.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("# 快照", snapshot)
            self.assertIn("- 專案: 照護專案", snapshot)
            self.assertIn("- 近期決策:", snapshot)
            self.assertIn("# 收尾", closeout)
            self.assertIn("- 摘要: 本輪完成同步與驗證", closeout)
            self.assertIn("- 冒煙測試: 2 項通過", closeout)


if __name__ == "__main__":
    unittest.main()
