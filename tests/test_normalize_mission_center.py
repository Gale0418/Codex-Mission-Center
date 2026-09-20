import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_mission_center import normalize_labels, normalize_priority, normalize_status, normalize_tasks


class NormalizeMissionCenterTests(unittest.TestCase):
    def test_common_statuses_are_normalized(self):
        self.assertEqual(normalize_status("todo"), "Backlog")
        self.assertEqual(normalize_status("doing"), "In Progress")
        self.assertEqual(normalize_status("done"), "Done")

    def test_common_priorities_are_normalized(self):
        self.assertEqual(normalize_priority("high"), "P1")
        self.assertEqual(normalize_priority("medium"), "P2")
        self.assertEqual(normalize_priority("low"), "P3")

    def test_labels_are_lowercase_and_deduplicated(self):
        self.assertEqual(normalize_labels("Alpha; beta, ALPHA"), "alpha, beta")

    def test_normalized_rows_reescape_pipes_and_backslashes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(
                "| Name | Priority | Status | Labels |\n"
                "| --- | --- | --- | --- |\n"
                r"| keep \\path \| pipe | high | todo | Alpha |"
                "\n",
                encoding="utf-8",
            )

            self.assertTrue(normalize_tasks(path))
            normalized = path.read_text(encoding="utf-8")

            self.assertIn(r"keep \\path \| pipe", normalized)
            self.assertEqual(normalize_tasks(path), False)


if __name__ == "__main__":
    unittest.main()
