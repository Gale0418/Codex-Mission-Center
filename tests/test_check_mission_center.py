import importlib.util
import subprocess
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "check_mission_center.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_mission_center", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckMissionCenterTests(unittest.TestCase):
    def test_normalization_checks_staged_tasks_not_unstaged_worktree(self):
        with workspace_tempdir("check-staged-") as temporary:
            repo = Path(temporary)
            mission = repo / "MissionCenter"
            mission.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            normalized = (
                "| ID | Title | Priority | Status | Labels |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| T1 | Work | P0 | Ready | test |\n"
            )
            tasks = mission / "tasks.md"
            tasks.write_text(normalized, encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "MissionCenter/tasks.md"], check=True)
            tasks.write_text(normalized.replace("| P0 | Ready | test |", "| 0 | todo | Test, TEST |"), encoding="utf-8")
            self.assertFalse(load_module()._normalization_required(repo))


if __name__ == "__main__":
    unittest.main()
