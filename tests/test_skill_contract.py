import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1] / "skills" / "mission-center"
SKILL_PATH = SKILL_ROOT / "SKILL.md"


class SkillContractTests(unittest.TestCase):
    def test_frontmatter_description_is_trigger_only(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        match = re.search(r"^description:\s*[\"']?(.+?)[\"']?$", text, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertTrue(match.group(1).startswith("Use when "))

    def test_core_skill_is_concise_and_routes_to_required_protocols(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertLess(len(text.splitlines()), 500)
        normalized = text.casefold()
        for phrase in (
            "north star intake",
            "creative cross-domain council",
            "prior art gate",
            "approved task draft",
            "one helper represents one task",
            "references/research-protocol.md",
        ):
            self.assertIn(phrase, normalized)

    def test_old_roster_and_pseudo_status_rules_are_absent(self):
        text = SKILL_PATH.read_text(encoding="utf-8").lower()
        for phrase in (
            "active agent count",
            "one visible helper per active agent",
            "smoketest",
        ):
            self.assertNotIn(phrase, text)

    def test_all_linked_references_exist(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        linked = re.findall(r"\]\((references/[^)]+)\)", text)
        self.assertGreater(len(linked), 0)
        for relative in linked:
            self.assertTrue((SKILL_ROOT / relative).is_file(), relative)

    def test_intake_and_creative_council_have_stop_and_convergence_rules(self):
        intake = (SKILL_ROOT / "references" / "intake-protocol.md").read_text(
            encoding="utf-8"
        )
        council = (SKILL_ROOT / "references" / "intake-council.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Ask exactly one question", intake)
        self.assertIn("Stop only when", intake)
        self.assertIn("Diverge", council)
        self.assertIn("Converge", council)
        self.assertIn("unexpected but feasible", council)

    def test_research_protocol_has_prior_art_jina_and_clean_room_rules(self):
        research = (
            SKILL_ROOT / "references" / "research-protocol.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "Prior Art Gate",
            "Jina Reader",
            "Jina Search",
            "Clean-room",
            "Pre-search idea | Source | Adopted insight | License status",
            "AGPL",
            "SSPL",
        ):
            self.assertIn(phrase, research)

    def test_real_subagents_require_explicit_user_approval(self):
        orchestration = (
            SKILL_ROOT / "references" / "agent-orchestration.md"
        ).read_text(encoding="utf-8")
        self.assertIn("explicit user approval", orchestration)
        self.assertIn("simulated expert perspectives", orchestration)


if __name__ == "__main__":
    unittest.main()
