import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
SCRIPT_DIR = ROOT / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import prompt_router as router  # noqa: E402


def payload(prompt: str, cwd: Path | None = None) -> dict:
    return {
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
        "cwd": str(cwd or Path("does-not-exist")),
    }


class PromptRouterTests(unittest.TestCase):
    def test_explicit_invocation_routes_but_quotes_and_negation_do_not(self):
        self.assertIn(
            "additionalContext",
            router.route(payload("$mission-center"))["hookSpecificOutput"],
        )
        for prompt in (
            "Explain `$mission-center`",
            '引用 "$mission-center"',
            "不要規劃高影響多步驟專案",
            "不要用 $mission-center",
            "Do not invoke @Mission Center",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(router.route(payload(prompt)), {})
        for prompt in (
            "不要用一般 plan；請用 $mission-center",
            "Do not use generic plan; please use @Mission Center",
        ):
            with self.subTest(prompt=prompt):
                self.assertIn("hookSpecificOutput", router.route(payload(prompt)))

    def test_semantic_route_requires_high_impact_or_multistep_plus_planning(self):
        for prompt in (
            "請規劃一個高影響的多步驟專案",
            "规划一个高风险多步骤项目",
            "Create a project plan for a high-impact multi-step migration",
            "高リスクの複数ステップのプロジェクト計画",
            "고위험 다단계 프로젝트 계획",
        ):
            with self.subTest(prompt=prompt):
                self.assertIn(
                    "additionalContext",
                    router.route(payload(prompt))["hookSpecificOutput"],
                )
        for prompt in ("plan this", "goal", "continue", "請解釋高影響專案規劃"):
            with self.subTest(prompt=prompt):
                self.assertEqual(router.route(payload(prompt)), {})

    def test_resume_routes_only_for_existing_mission_center_workspace(self):
        with self.subTest("missing workspace"):
            self.assertEqual(router.route(payload("resume Mission Center work")), {})
            self.assertEqual(router.route(payload("GO!")), {})
        with self.subTest("existing workspace"):
            with patch.object(router.Path, "is_file", return_value=True):
                result = router.route(payload("resume Mission Center work", Path("workspace")))
                go = router.route(payload(" G\n O！", Path("workspace")))
                ok = router.route(payload("OK…", Path("workspace")))
            self.assertIn("additionalContext", result["hookSpecificOutput"])
            self.assertEqual(go, result)
            self.assertEqual(ok, result)
        for prompt in ("go ahead", "okay", "引用 `GO`", "don't go", "GO now"):
            with self.subTest(prompt=prompt):
                with patch.object(router.Path, "is_file", return_value=True):
                    self.assertEqual(router.route(payload(prompt, Path("workspace"))), {})

    def test_router_is_bounded_fail_closed_and_cli_has_no_output_for_noop(self):
        self.assertEqual(router.route({"hook_event_name": "Stop", "prompt": "$mission-center"}), {})
        self.assertEqual(router.route(payload("x" * (router.MAX_PROMPT_CHARS + 1))), {})
        stream = type("Input", (), {"read": lambda *args: io.BytesIO(json.dumps(payload("goal")).encode()).read()})()
        with patch.object(sys, "stdin", type("Stdin", (), {"buffer": stream})()), patch.object(
            sys, "stdout", io.StringIO()
        ) as stdout:
            self.assertEqual(router.main(), 0)
            self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
