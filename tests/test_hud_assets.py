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
        self.assertIn('url("mission-starfield.png")', html)
        self.assertTrue((ROOT / "assets" / "visual-hub" / "mission-starfield.png").exists())
        self.assertIn('url("mission-fleet-bridge-background.png")', html)
        self.assertTrue((ROOT / "assets" / "visual-hub" / "mission-fleet-bridge-background.png").exists())

    def test_hud_keeps_task_and_runtime_entities_separate(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('data-entity-kind="task"', html)
        self.assertIn('data-entity-kind="runtime-agent"', html)
        self.assertIn("FLEET COMMAND PLOT", html)
        self.assertIn("LIVE AGENTS", html)
        self.assertIn("EVIDENCE / BLOCKED LOG", html)
        self.assertIn("lastValidRuntimeState", html)
        self.assertIn("No connected runtime agents", html)

    def test_hud_uses_compact_attention_capsule_and_accessible_drawer(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('class="attention-capsule"', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('aria-controls="liveAgentsDrawer"', html)
        self.assertIn('.agent:hover .nameplate', html)
        self.assertIn('role="listitem" aria-label=', html)
        self.assertIn('id="liveAgentsDrawer"', html)
        self.assertIn("toggleRuntimeDrawer", html)
        self.assertIn("runtimeDrawer.hidden = !expanded", html)

    def test_hud_uses_neutral_fallback_and_reports_stale_state(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="zh-Hant">', html)
        self.assertIn('id="stateNotice"', html)
        self.assertIn("Task state unavailable · showing fallback", html)
        self.assertIn("Task state stale · showing last valid snapshot", html)
        self.assertIn('id="runtimeNotice"', html)
        self.assertIn("Runtime state stale · showing last valid snapshot", html)
        self.assertIn('id="progressText">0%</strong>', html)
        self.assertIn('id="statusText">Unknown</strong>', html)
        self.assertIn("Waiting for task state", html)

    def test_hud_discloses_runtime_visibility_and_keeps_stale_out_of_done(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn("visible of", html)
        self.assertIn("hidden", html)
        self.assertIn('stale: "Unknown"', html)
        self.assertIn('idle: "Unknown"', html)
        self.assertIn('finished: "Done"', html)
        self.assertIn('id="closeRuntimeDrawer"', html)
        self.assertIn('event.key === "Escape"', html)
        self.assertIn("closeRuntimeDrawer.focus()", html)
        self.assertIn("lastFocusElement.focus()", html)

    def test_hud_has_visible_legend_motion_preference_and_semantic_lists(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('class="map-legend" aria-label="Task status legend"', html)
        for label in ("Intake", "In Progress", "Blocked", "Review", "Done"):
            self.assertIn(f">{label}</span>", html)
        self.assertIn("@media (prefers-reduced-motion: reduce)", html)
        self.assertIn('id="progressBar" role="progressbar"', html)
        self.assertIn('class="agents-layer" data-entity-kind="task" role="list"', html)
        self.assertIn('class="runtime-agents-layer" data-entity-kind="runtime-agent" role="list"', html)
        self.assertIn('role="listitem" data-state=', html)
        self.assertIn('class="agent-title-track" aria-hidden="true"', html)
        self.assertRegex(html, r"\.territory > \.agents-layer \{[^}]*overflow-x: hidden;[^}]*overflow-y: auto;")
        self.assertRegex(html, r"\.territories \{[^}]*overflow-x: auto;")
        self.assertIn('.agent-title[data-marquee="true"] .agent-title-track', html)
        self.assertIn('title.classList.add("is-overflowing")', html)
        self.assertIn('track.getBoundingClientRect().width', html)
        self.assertIn('window.addEventListener("resize", scheduleTaskTitleMarqueeMeasurement', html)
        self.assertIn('id="taskTelemetryIds"', html)
        self.assertIn('id="runtimeTelemetryIds"', html)
        self.assertIn('class="telemetry-rail" aria-hidden="true"', html)
        self.assertIn('@keyframes borderFlow', html)
        self.assertIn('background: conic-gradient(from 90deg, var(--cyan-peak), #fff', html)
        self.assertIn('@property --edge-angle', html)
        self.assertIn('@keyframes borderFlow { from { --edge-angle: 0deg; } to { --edge-angle: 360deg; } }', html)
        self.assertIn('@keyframes panelEdgeFlow', html)
        self.assertNotIn('@keyframes borderFlow { to { transform: rotate', html)
        self.assertNotIn('animation: borderFlow 9s linear infinite; transform:', html)
        self.assertIn('@media (prefers-reduced-motion: reduce)', html)
        self.assertIn('.hud-shell::before { animation: none; opacity: .78;', html)
        self.assertIn('@keyframes activeCardScan', html)
        self.assertNotIn('class="radial-scan"', html)
        self.assertNotIn('class="specular-sweep"', html)
        self.assertNotIn('animation: panelSpecular', html)
        self.assertIn('id="localTime"', html)
        self.assertIn('id="utcTime"', html)
        self.assertIn("updateClockReadouts", html)
        for label in ("BRIEFING", "EXECUTION", "HOLD", "VERIFICATION", "ARCHIVE"):
            self.assertIn(f'class="zone-command">{label}</span>', html)
        self.assertIn('class="broadcast-strip broadcast-top" aria-hidden="true"', html)
        self.assertIn('class="broadcast-waterfall broadcast-left" aria-hidden="true"', html)
        self.assertIn('class="broadcast-waterfall broadcast-right" aria-hidden="true"', html)
        self.assertIn("@keyframes broadcastLtr", html)
        self.assertIn("@keyframes waterfallDown", html)
        self.assertIn("POLL T10S · R2S/H30S", html)
        self.assertNotIn("weather", html.lower())
        self.assertNotIn("sensor feed", html.lower().replace("no sensor feed", ""))
        self.assertIn("rgba(6,22,33,.5)", html)
        self.assertIn("rgba(1,19,32,.58)", html)
        self.assertIn("rgba(1,19,32,.28)", html)
        self.assertIn("rgba(6,22,33,.36)", html)
        self.assertIn("rgba(20,38,50,.66)", html)
        self.assertIn("rgba(0,13,23,.25)", html)
        self.assertIn("rgba(4,22,34,.5)", html)
        self.assertIn('class="territory-doctrine" aria-hidden="true"', html)
        for doctrine in (
            "TASK ORDER / FILE SNAPSHOT / READ ONLY",
            "ACTIVE WORK / COMMAND LINK / TASK TRUTH",
            "CONSTRAINT HOLD / HUMAN INTERVENTION",
            "VERIFICATION QUEUE / TASK TRUTH",
            "MISSION RECORD / SNAPSHOT ARCHIVE",
        ):
            self.assertIn(doctrine, html)
        self.assertIn("width: 13px; writing-mode: vertical-rl", html)
        self.assertIn("opacity: .46;", html)
        self.assertIn(".broadcast-right { right: 6px; writing-mode: vertical-lr; opacity: .42;", html)
        self.assertNotIn("backdrop-filter", html)
        self.assertNotIn("blur(", html)

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
