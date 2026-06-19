import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT_ROOT = ROOT / "skills" / "mission-center" / "scripts"
BOOTSTRAP = SCRIPT_ROOT / "bootstrap_mission_center.py"
SEED = SCRIPT_ROOT / "seed_task_tree.py"


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
        with tempfile.TemporaryDirectory() as temporary:
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
        with tempfile.TemporaryDirectory() as temporary:
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
            self.assertIn("Create a better hair dryer", project)
            self.assertIn("First experiment", project)

    def test_bootstrap_without_force_preserves_existing_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "en")
            notes = workspace / "MissionCenter" / "notes.md"
            notes.write_text("keep me\n", encoding="utf-8")
            run_script(BOOTSTRAP, workspace, "--language", "en")
            self.assertEqual(notes.read_text(encoding="utf-8"), "keep me\n")

    def test_seed_preserves_an_existing_project_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            run_script(BOOTSTRAP, workspace, "--language", "en")
            project = workspace / "MissionCenter" / "project.md"
            project.write_text("# Project\n\n- Goal: Keep this goal\n", encoding="utf-8")
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
        with tempfile.TemporaryDirectory() as temporary:
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
            self.assertIn("- Goal: Recovered goal", content)
            self.assertIn("- Cycle: Recovered cycle", content)



if __name__ == "__main__":
    unittest.main()
