import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1] / "skills" / "mission-center"


class HudAssetTests(unittest.TestCase):
    def test_html_has_no_placeholder_roster_or_smoketest_status(self):
        html = (
            ROOT / "assets" / "visual-hub" / "visual-summary.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn('name: "MissionHelper"', html)
        self.assertNotIn('"SmokeTest"', html)
        self.assertIn("const maxVisibleAgents = 15", html)

    def test_hud_keeps_task_and_runtime_entities_separate(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('data-entity-kind="task"', html)
        self.assertIn('data-entity-kind="runtime-agent"', html)
        self.assertIn("Mission Island", html)
        self.assertIn("LIVE AGENTS", html)
        self.assertIn("PIXEL MISSION MAP", html)
        self.assertIn("lastValidRuntimeState", html)
        self.assertIn("No connected runtime agents", html)

    def test_hud_uses_compact_attention_capsule_and_accessible_drawer(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('class="attention-capsule"', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('aria-controls="liveAgentsDrawer"', html)
        self.assertIn('.agent:hover .nameplate', html)
        self.assertIn('tabindex="0" aria-label=', html)
        self.assertIn('id="liveAgentsDrawer"', html)
        self.assertIn("toggleRuntimeDrawer", html)
        self.assertIn("runtimeDrawer.hidden = !expanded", html)

    def test_hud_attention_is_aggregated_from_the_protocol_allowlist(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('new Set(["approval", "question", "blocked", "error", "verification"])', html)
        self.assertIn("needsAttention", html)
        self.assertIn("workingCount", html)
        self.assertIn("Awaiting MissionCenter verification", html)

    def test_hud_adapts_polling_when_hidden(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn("const runtimePollVisibleMs = 2000", html)
        self.assertIn("const runtimePollHiddenMs = 30000", html)
        self.assertIn('document.addEventListener("visibilitychange", updatePollingStrategy)', html)
        self.assertIn("clearInterval(runtimePollTimer)", html)
        self.assertNotIn("setInterval(loadRuntimeState, 2000)", html)

    def test_hud_maps_only_explicit_runtime_activity_kinds(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn("runtimeZoneByActivityKind", html)
        for kind in ("web_search", "file_change", "command_execution", "waiting_input", "verification"):
            self.assertIn(f'"{kind}"', html)
        self.assertIn('data-entity-kind="runtime-agent"', html)
        self.assertIn("Object.hasOwn(runtimeZoneByActivityKind, agent.activityKind)", html)
        self.assertIn("const runtimeAgentPositions = new Map()", html)
        self.assertNotIn("runtimeAgentsLayer.innerHTML = runtimeAgents.map", html)

    def test_live_drawer_renders_bounded_parent_child_topology(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn("renderRuntimeTopology", html)
        self.assertIn('aria-label="Runtime agent parent-child topology"', html)
        self.assertIn("Math.min(4, 1 + generationFor", html)
        self.assertIn("agent.parentAgentId", html)
        self.assertNotIn("agent.progress", html)
        self.assertNotIn("agent.token", html)

    def test_default_state_is_empty(self):
        state = json.loads(
            (ROOT / "assets" / "visual-hub" / "visual-state.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["agents"], [])

    def test_manual_updater_delegates_to_task_sync(self):
        script = (
            ROOT / "assets" / "visual-hub" / "update-visual-state.ps1"
        ).read_text(encoding="utf-8")
        self.assertNotIn("[string[]]$Agents", script)
        self.assertIn("sync_mission_center.py", script)


if __name__ == "__main__":
    unittest.main()
