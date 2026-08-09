import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skills" / "mission-center"
SKILL_PATH = SKILL_ROOT / "SKILL.md"


class SkillContractTests(unittest.TestCase):
    def test_post_commit_hook_is_explicitly_maintainer_only(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("Maintainer-only", text)
        self.assertIn("not a normal target-workspace command", text)
        self.assertNotIn("In the **Codex-Mission-Center repo root**", text)

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

    def test_all_reference_files_are_routed_from_skill(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        linked = set(re.findall(r"\]\((references/[^)]+)\)", text))
        reference_files = {
            f"references/{path.name}"
            for path in (SKILL_ROOT / "references").glob("*.md")
        }
        self.assertEqual(reference_files, linked)

    def test_dynamic_expert_council_uses_complexity_evidence_and_approval_gates(self):
        council = (
            SKILL_ROOT / "references" / "dynamic-expert-council.md"
        ).read_text(encoding="utf-8")
        normalized = council.casefold()
        for phrase in (
            "`skip`",
            "`council_lite`",
            "`council_full`",
            "at least three dynamically selected professional perspectives",
            "improbable but feasible",
            "confirm and state the current date",
            "primary source",
            "jina reader",
            "do not invent",
            "evidence discipline",
            "exploration variance",
            "explicit approval",
            "agreed budget",
            "do not consume additional runtime-agent quota",
            "receives:",
            "not responsible for:",
            "low-confidence behavior:",
            "confidence plus unknowns",
            "separate from validators",
            "bounded retries",
            "material dissent",
            "next verification",
        ):
            self.assertIn(phrase, normalized)
        self.assertIn(
            "not by claiming different model settings or temperature values", normalized
        )
        self.assertIn("do not draw from a fixed role catalogue", normalized)

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
        self.assertIn("simulated perspectives", orchestration)

    def test_linear_and_execution_references_enforce_rolling_approval(self):
        linear = (SKILL_ROOT / "references" / "linear-parity.md").read_text(
            encoding="utf-8"
        )
        gates = (SKILL_ROOT / "references" / "execution-gates.md").read_text(
            encoding="utf-8"
        )
        workspace = (SKILL_ROOT / "references" / "task-workspace.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Rolling Planning", linear)
        self.assertIn("full Epic map", linear)
        self.assertIn("approved task draft", gates)
        self.assertIn("Do not write `tasks.md`", gates)
        self.assertIn(
            "Pre-search idea | Source | Adopted insight | License status",
            workspace,
        )

    def test_plugin_metadata_uses_current_license_and_repository(self):
        manifest = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        repository = "https://github.com/Gale0418/Codex-Mission-Center"
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["homepage"], repository)
        self.assertEqual(manifest["repository"], repository)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("GPL-3.0", readme)

    def test_agent_prompt_covers_intake_research_and_approved_publish(self):
        agent = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        normalized = agent.casefold()
        for phrase in (
            "one question",
            "prior art",
            "approved task",
            "normalize task state",
            "record verification",
        ):
            self.assertIn(phrase, normalized)

    def test_install_wrappers_delegate_without_mutating_marketplace_metadata(self):
        wrappers = (
            "install-windows.ps1",
            "install-unix.sh",
            "install-plugin-windows.ps1",
            "install-plugin-unix.sh",
        )
        for name in wrappers:
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            normalized = text.casefold()
            with self.subTest(name=name):
                self.assertIn("publish_local.py", normalized)
                self.assertNotIn("marketplace.json", normalized)
                self.assertNotIn("remove-item", normalized)
                self.assertNotIn("rm -rf", normalized)

    def test_install_wrappers_register_plugin_on_write_mode(self):
        wrappers = (
            "install-windows.ps1",
            "install-unix.sh",
            "install-plugin-windows.ps1",
            "install-plugin-unix.sh",
        )
        for name in wrappers:
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8").casefold()
            with self.subTest(name=name):
                self.assertIn("--register", text)

    def test_install_wrappers_report_each_publish_mode_accurately(self):
        wrappers = (
            "install-windows.ps1",
            "install-unix.sh",
            "install-plugin-windows.ps1",
            "install-plugin-unix.sh",
        )
        for name in wrappers:
            text = (ROOT / "scripts" / name).read_text(encoding="utf-8").casefold()
            with self.subTest(name=name):
                self.assertIn("dry-run completed", text)
                self.assertIn("verification completed", text)
                self.assertIn("published mission center", text)

    def test_tests_use_portable_temp_directories_and_subprocess_timeouts(self):
        publish_tests = (ROOT / "tests" / "test_publish_local.py").read_text(
            encoding="utf-8"
        )
        workspace_tests = (
            ROOT / "tests" / "test_workspace_templates.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('dir="C:/tmp"', publish_tests)
        self.assertNotIn('dir="C:/tmp"', workspace_tests)
        self.assertIn("timeout=", workspace_tests)


    def test_coderabbit_gate_is_final_risk_based_and_quota_aware(self):
        skill = SKILL_PATH.read_text(encoding="utf-8")
        gate_path = SKILL_ROOT / "references" / "coderabbit-review-gate.md"
        self.assertIn("references/coderabbit-review-gate.md", skill)
        self.assertTrue(gate_path.is_file())

        gate = gate_path.read_text(encoding="utf-8")
        normalized = gate.casefold()
        for phrase in (
            "after implementation and local verification",
            "explicit consent",
            "risk-based",
            "--dir",
            "--base-commit",
            "-t uncommitted",
            "binary",
            "generated",
            "one full scoped review",
            "one focused re-review",
            "regression test",
            "rate limit",
            "do not claim coderabbit passed",
            "codex-managed plugin cache",
            "completed",
            "skipped",
            "unavailable",
        ):
            self.assertIn(phrase, normalized)



if __name__ == "__main__":
    unittest.main()
