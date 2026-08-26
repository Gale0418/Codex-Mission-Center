import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).parents[1] / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from visual_state import build_visual_state, normalize_tasks, select_visible_tasks


class VisualStateTests(unittest.TestCase):
    def test_empty_tasks_create_no_placeholder_helper(self):
        state = build_visual_state([], goal="空專案", progress=0)
        self.assertEqual(state["agents"], [])
        self.assertEqual(state["taskCounts"], {"visible": 0, "total": 0, "hidden": 0})

    def test_one_helper_per_task_ignores_duplicate_owner(self):
        tasks = normalize_tasks(
            [
                {
                    "ID": "T1",
                    "Title": "風道研究",
                    "Status": "In Progress",
                    "Owner": "Codex",
                },
                {
                    "ID": "T2",
                    "Title": "聲學驗證",
                    "Status": "Review",
                    "Owner": "Codex",
                },
            ]
        )
        state = build_visual_state(tasks, goal="吹風機", progress=50)
        self.assertEqual(
            [agent["name"] for agent in state["agents"]],
            ["風道研究", "聲學驗證"],
        )
        self.assertEqual(
            [agent["status"] for agent in state["agents"]],
            ["In Progress", "Review"],
        )

    def test_first_ten_unfinished_and_newest_done_fill_fifteen_slots(self):
        rows = [
            {"ID": f"T{i}", "Title": f"未完成 {i}", "Status": "Ready"}
            for i in range(12)
        ] + [
            {"ID": f"D{i}", "Title": f"完成 {i}", "Status": "Done"}
            for i in range(7)
        ]
        state = build_visual_state(
            normalize_tasks(rows), goal="大型任務", progress=20
        )
        self.assertEqual(len(state["agents"]), 15)
        self.assertEqual(state["taskCounts"], {"visible": 15, "total": 19, "hidden": 4})
        self.assertEqual(
            [agent["id"] for agent in state["agents"][:10]],
            [f"T{i}" for i in range(10)],
        )
        self.assertEqual(
            [agent["id"] for agent in state["agents"][10:]],
            [f"D{i}" for i in range(2, 7)],
        )

    def test_custom_limit_keeps_ten_unfinished_cap_and_reserves_done_slots(self):
        rows = [
            {"ID": f"T{i}", "Title": f"未完成 {i}", "Status": "Ready"}
            for i in range(15)
        ] + [
            {"ID": f"D{i}", "Title": f"完成 {i}", "Status": "Done"}
            for i in range(5)
        ]

        visible = select_visible_tasks(normalize_tasks(rows), limit=12)

        self.assertEqual([task["ID"] for task in visible[:10]], [f"T{i}" for i in range(10)])
        self.assertEqual([task["ID"] for task in visible[10:]], ["D3", "D4"])
    def test_traditional_chinese_headers_are_normalized(self):
        tasks = normalize_tasks(
            [
                {
                    "ID": "T1",
                    "標題": "研究",
                    "狀態": "Blocked",
                    "負責人": "同一人",
                }
            ]
        )
        self.assertEqual(tasks[0]["Title"], "研究")
        self.assertEqual(tasks[0]["Status"], "Blocked")

    def test_done_blocked_and_in_progress_map_to_expected_zones(self):
        tasks = normalize_tasks(
            [
                {"ID": "T1", "標題": "進行", "狀態": "In Progress", "估時": "2"},
                {"ID": "T2", "標題": "阻塞", "狀態": "Blocked", "估時": "3"},
                {"ID": "T3", "標題": "完成", "狀態": "Done", "估時": "1"},
            ]
        )
        state = build_visual_state(tasks, goal="驗證區域", progress=17)
        self.assertEqual([task["Estimate"] for task in tasks], ["2", "3", "1"])
        self.assertEqual(
            [agent["zone"] for agent in state["agents"]],
            ["In Progress", "Blocked", "Done"],
        )

    def test_unknown_status_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported task status"):
            normalize_tasks(
                [{"ID": "T1", "Title": "壞資料", "Status": "SmokeTest"}]
            )


if __name__ == "__main__":
    unittest.main()
