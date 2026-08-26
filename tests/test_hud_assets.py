import json
import re
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
        self.assertIn('url("mission-starfield.webp")', html)
        self.assertTrue((ROOT / "assets" / "visual-hub" / "mission-starfield.webp").exists())
        self.assertIn('url("mission-fleet-bridge-background.webp")', html)
        self.assertTrue((ROOT / "assets" / "visual-hub" / "mission-fleet-bridge-background.webp").exists())
        self.assertIn('url("mission-bridge-background.webp")', html)
        self.assertTrue((ROOT / "assets" / "visual-hub" / "mission-bridge-background.webp").exists())

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
        self.assertIn("POLL T60S · R30S/H120S", html)
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
        self.assertRegex(
            html,
            r"\.territory-header \{[^}]*grid-template-columns: minmax\(0,1fr\) auto;[^}]*min-height: 60px;",
        )
        self.assertIn("@media (max-width: 1080px)", html)
        self.assertIn(".territory-header { min-height: 60px; }", html)
        self.assertIn("@media (max-width: 620px)", html)
        self.assertIn(".territory-header { min-height: auto; }", html)
        self.assertIn('data-rotate="/"', html)
        self.assertIn('data-full-text="TASK ORDER / FILE SNAPSHOT / READ ONLY"', html)
        self.assertIn("@keyframes doctrineSweep", html)
        self.assertIn("startTerritoryPhraseRotation", html)
        self.assertIn("nodeIndex * 700", html)
        self.assertIn("if (!reducedMotionQuery?.matches)", html)
        self.assertIn("document.addEventListener(\"visibilitychange\", updatePollingStrategy)", html)
        self.assertNotIn("loadState(); loadRuntimeState(); updateClockReadouts(); attentionCapsule", html)
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
        self.assertIn("const runtimePollActiveMs = 30000", html)
        self.assertIn("const runtimePollVisibleMs = 60000", html)
        self.assertIn("const runtimePollHiddenMs = 120000", html)
        self.assertIn("const taskPollVisibleMs = 60000", html)
        self.assertIn("const taskPollHiddenMs = 120000", html)
        self.assertIn("function runtimeCadenceMs()", html)
        self.assertIn("if (refresh && !hidden)", html)
        self.assertIn('document.addEventListener("visibilitychange", updatePollingStrategy)', html)
        self.assertIn("clearInterval(runtimePollTimer)", html)
        self.assertNotIn("setInterval(loadRuntimeState, 2000)", html)

    def test_hud_validates_runtime_items_before_committing_last_valid_state(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn("state.agents.some((agent) => !agent || typeof agent !== \"object\"", html)
        self.assertIn("state.attention.some((item) => !item || typeof item !== \"object\"", html)
        self.assertIn("lastValidRuntimeState = state; renderRuntimeState(state)", html)

    def test_hud_discloses_task_visible_total_and_hidden_counts(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('id="taskVisibility"', html)
        self.assertIn('taskCounts: { visible: agents.length, total, hidden }', html)
        self.assertIn("HIDDEN ${counts.hidden}", html)
        self.assertIn("state.taskCounts.hidden", html)

    def test_hud_stops_decorative_rotation_while_hidden_or_reduced_motion(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn("if (document.hidden || reducedMotionQuery?.matches) return", html)
        self.assertIn("reducedMotionQuery?.addEventListener?.(\"change\", resume)", html)

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

    def test_task_topology_uses_measured_cards_and_bounded_layout_reflow(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        topology = html.split("function renderTopology", 1)[1].split(
            "function scheduleTopologyMeasurement", 1
        )[0]
        self.assertIn('data-task-id="${escapeAttr(id)}"', html)
        self.assertIn('id="taskTopology" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"', html)
        self.assertIn('taskPlot = document.querySelector("#taskPlot")', html)
        self.assertIn("function taskCardMap()", html)
        self.assertIn("const cards = new Map()", html)
        self.assertIn("Array.isArray(agent?.dependencies)", topology)
        self.assertIn("dependencyLinks =", topology)
        self.assertIn("dependencyLinks.length > links.length", topology)
        self.assertNotIn("links.length === 24", topology)
        self.assertIn('taskEndpoint(fromCard, "from"', topology)
        self.assertIn('taskEndpoint(toCard, "to"', topology)
        self.assertIn("getBoundingClientRect()", topology)
        self.assertIn("topologyViewBox", topology)
        self.assertIn(" C ${from.x + direction * bend}", topology)
        self.assertIn("Math.max(1.5, Math.min(18", topology)
        self.assertNotIn("Math.max(10, Math.min(30", topology)
        self.assertNotIn("index %", topology)
        self.assertIn("if (!from || !to) return", topology)
        self.assertNotIn("topology-empty", html)
        self.assertIn("const topologySummary = links.length", topology)
        self.assertIn("if (topologyTextSummary.textContent !== topologySummary)", topology)
        self.assertNotIn("topologyTextSummary.textContent = links.length", topology)
        self.assertNotIn('.topology-layer[aria-hidden="true"] path', html)
        self.assertIn('clip = card.closest(".agents-layer")?.getBoundingClientRect()', html)
        self.assertIn("topologyFrame", html)
        self.assertIn("requestAnimationFrame", html)
        self.assertIn("new ResizeObserver", html)
        self.assertIn('querySelectorAll(".territory, .agents-layer")', html)
        self.assertIn('addEventListener("scroll", scheduleTopologyMeasurement', html)
        self.assertIn('window.addEventListener("resize", scheduleTopologyMeasurement', html)
        self.assertIn(".topology-layer, .runtime-agents-layer { display: none; }", html)

    def test_task_cards_use_deterministic_id_color_tokens(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('function stableTaskColor(taskId, status = "Unknown")', html)
        self.assertIn("data-task-color=\"${color.hue}\"", html)
        self.assertIn("--task-accent:${color.accent}", html)
        self.assertIn("--task-accent-soft:${color.soft}", html)
        self.assertIn("--task-tint:${color.tint}", html)
        self.assertIn("tint: `hsl(${hue} ${saturation}% ${lightness}% / .08)`", html)
        self.assertIn("linear-gradient(135deg, var(--task-tint, transparent), transparent 78%)", html)
        self.assertIn("path.dataset.taskColor", html)
        self.assertIn("toCard?.style.getPropertyValue(\"--task-accent\")", html)
        self.assertIn('.agent[data-status="Blocked"], .agent[data-attention="true"]', html)
        self.assertIn("@media (prefers-reduced-motion: reduce)", html)

    def test_task_cards_use_bounded_status_color_families(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        expected_families = {
            "Intake": ("BRIEFING", "[42, 54]", "[78, 90]", "[58, 70]"),
            "In Progress": ("EXECUTION", "[132, 150]", "[58, 76]", "[48, 62]"),
            "Blocked": ("HOLD", "[350, 359]", "[76, 90]", "[52, 66]"),
            "Review": ("VERIFICATION", "[198, 222]", "[64, 82]", "[54, 68]"),
            "Done": ("ARCHIVE", "[200, 220]", "[4, 12]", "[62, 76]"),
        }
        for family, (phase, hue, saturation, lightness) in expected_families.items():
            family_key = rf'(?:"{re.escape(family)}"|{re.escape(family)})'
            self.assertRegex(
                html,
                rf'{family_key}: \{{ phase: "{phase}", hue: {re.escape(hue)}, saturation: {re.escape(saturation)}, lightness: {re.escape(lightness)} \}}',
            )
        self.assertIn('function taskColorFamily(status)', html)
        self.assertIn('function stableTaskColor(taskId, status = "Unknown")', html)
        self.assertIn('color = stableTaskColor(id, zone)', html)
        self.assertNotIn('color = stableTaskColor(id, attention ? "Blocked" : zone)', html)
        self.assertIn('data-task-color-family="${color.family}"', html)
        self.assertIn('((hash >>> shift) & 0xff)', html)
        self.assertIn('@keyframes attentionAmberPulse', html)
        self.assertIn('0 0 16px rgba(255,198,58,.32)', html)
        self.assertIn(
            'background: linear-gradient(135deg, var(--task-tint, transparent), transparent 78%), rgba(56,18,25,.72)',
            html,
        )
        self.assertIn('.agent[data-status="Blocked"], .agent[data-attention="true"] { animation: attentionAmberPulse', html)
        self.assertNotIn('border-color: var(--amber); background: rgba(44,34,12,.7)', html)

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
