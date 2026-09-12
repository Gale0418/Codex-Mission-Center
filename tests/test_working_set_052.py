"""Executable tests of the real compatibility policy, not a copied algorithm."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from common.working_set import dependency_ids, priority_key, select_working_set  # noqa: E402


def task(identifier: str, status: str = "Ready", priority: str = "P1", deps: str = "") -> dict[str, str]:
    return {"ID": identifier, "Status": status, "Priority": priority, "Depends on": deps}


def ids(tasks: list[dict[str, str]], **kwargs) -> list[str]:
    return [item["ID"] for item in select_working_set(tasks, **kwargs)]


class WorkingSetPolicyTests(unittest.TestCase):
    def blockers(self) -> list[dict[str, str]]:
        return [task(f"MC-{index:03}", "Blocked") for index in range(1, 7)]

    def test_active_anchor_survives_six_blockers_without_mutation(self):
        tasks = self.blockers() + [task("MC-007", "In Progress")]
        before = copy.deepcopy(tasks)
        selected = select_working_set(tasks)
        self.assertEqual(selected[0]["ID"], "MC-007")
        self.assertEqual(len(selected), 6)
        self.assertEqual(tasks, before)
        self.assertIs(selected[0], tasks[-1])

    def test_anchor_and_urgent_work_survive_blockers(self):
        tasks = self.blockers() + [task("MC-007", "In Progress"), task("MC-008", priority="p0")]
        self.assertEqual(ids(tasks)[:2], ["MC-007", "MC-008"])

    def test_direct_dependency_precedes_unrelated_blockers(self):
        tasks = self.blockers() + [task("MC-007", "In Progress", deps=" MC-006 ")]
        self.assertEqual(ids(tasks)[:2], ["MC-007", "MC-006"])

    def test_no_done_or_backlog_promotion(self):
        tasks = [task("MC-001", "Done", "P0"), task("MC-002", "Backlog", "P0"),
                 task("MC-003", "In Progress", deps="MC-001, MC-002")]
        self.assertEqual(ids(tasks), ["MC-003"])

    def test_overlapping_categories_are_deduplicated(self):
        tasks = [task("MC-001", "In Progress", "P0", "MC-002"), task("MC-002", "Blocked", "P0")]
        self.assertEqual(ids(tasks), ["MC-001", "MC-002"])

    def test_ready_ties_and_empty_input(self):
        tasks = [task("MC-003", priority="P2"), task("MC-002"), task("MC-001")]
        self.assertEqual(ids(tasks), ["MC-001", "MC-002", "MC-003"])
        self.assertEqual(ids([]), [])

    def test_large_urgent_set_stays_bounded_with_anchor(self):
        tasks = [task(f"MC-{index:03}", priority="P0") for index in range(1, 31)]
        tasks.append(task("MC-031", "In Progress"))
        result = ids(tasks)
        self.assertEqual(result[0], "MC-031")
        self.assertEqual(len(result), 6)
        self.assertEqual(len(set(result)), 6)
        self.assertEqual(result, ids(tasks))

    def test_small_zero_and_oversize_limits(self):
        tasks = self.blockers() + [task("MC-007", "In Progress")]
        self.assertEqual(ids(tasks, limit=0), [])
        self.assertEqual(ids(tasks, limit=-1), [])
        self.assertEqual(ids(tasks, limit=1), ["MC-007"])
        self.assertEqual(len(ids(tasks, limit=100)), 6)
        for invalid in (True, 1.5, "6"):
            with self.subTest(limit=invalid), self.assertRaises(ValueError):
                ids(tasks, limit=invalid)

    def test_status_normalization_and_invalid_rows(self):
        tasks = [task("", "In Progress"), task("MC-001", "Awaiting approval", "P0"),
                 task("MC-002", " in PROGRESS ")]
        self.assertEqual(ids(tasks), ["MC-002"])

    def test_historical_helpers_are_preserved(self):
        self.assertEqual(priority_key(task(" MC-001 ", priority=" p2 ")), (2, "MC-001"))
        self.assertEqual(dependency_ids(task("MC-001", deps="MC-002, MC-003")), {"MC-002", "MC-003"})


if __name__ == "__main__":
    unittest.main()
