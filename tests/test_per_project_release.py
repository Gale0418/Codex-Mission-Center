import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class PerProjectReleaseTests(unittest.TestCase):
    def test_repo_dogfood_workspace_is_trackable_and_complete(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertNotIn("MissionCenter/", ignored)
        actual = {
            path.name
            for path in (ROOT / "MissionCenter").iterdir()
            if path.is_file()
        }
        self.assertEqual(
            actual,
            {
                "project.md",
                "progress.md",
                "tasks.md",
                "decisions.md",
                "smoke-tests.md",
                "notes.md",
                "snapshot.md",
                "closeout.md",
                "visual-hub.md",
            },
        )

    def test_readme_declares_per_project_only_contract(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for sentence in (
            "Mission Center is per-project only.",
            "Use it inside the current repo/workspace.",
            "It creates or reads `./MissionCenter/`.",
            "It does not monitor all repositories.",
            "It does not merge tasks across projects.",
        ):
            self.assertIn(sentence, readme)

    def test_documented_layout_matches_canonical_contract(self):
        expected = {
            "project.md",
            "progress.md",
            "tasks.md",
            "decisions.md",
            "smoke-tests.md",
            "notes.md",
            "snapshot.md",
            "closeout.md",
            "visual-hub.md",
        }
        for relative in (
            "README.md",
            "skills/mission-center/references/task-workspace.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for name in expected:
                self.assertIn(name, text, f"{relative} omits {name}")

    def test_ci_runs_unit_and_single_workspace_cli_checks(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for phrase in (
            "push:",
            "pull_request:",
            "python -m unittest discover -s tests -p \"test_*.py\" -v",
            "bootstrap_mission_center.py /tmp/mc-demo --language zh-TW",
            "normalize_mission_center.py /tmp/mc-demo",
            "sync_mission_center.py /tmp/mc-demo",
            "doctor_mission_center.py /tmp/mc-demo",
        ):
            self.assertIn(phrase, workflow)

    def test_release_checklist_repeats_product_boundaries(self):
        checklist = (ROOT / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8").lower()
        for phrase in (
            "publish dry-run",
            "publish verify",
            "global monitoring",
            "merge tasks across repositories",
        ):
            self.assertIn(phrase, checklist)

    def test_skill_has_no_global_overview_route(self):
        skill = (ROOT / "skills" / "mission-center" / "SKILL.md").read_text(encoding="utf-8").lower()
        self.assertNotIn("global-overview", skill)
        self.assertFalse((ROOT / "skills" / "mission-center" / "references" / "global-overview.md").exists())


if __name__ == "__main__":
    unittest.main()
