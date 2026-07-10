import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_mission_center import normalize_labels, normalize_priority, normalize_status


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


if __name__ == "__main__":
    unittest.main()

