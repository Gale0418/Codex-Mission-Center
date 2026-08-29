import json
import re
import shutil
import subprocess
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
        self.assertIn('card.setAttribute("role", "listitem")', html)
        self.assertIn('card.setAttribute("aria-label"', html)
        self.assertIn('id="liveAgentsDrawer"', html)
        self.assertIn("toggleRuntimeDrawer", html)
        self.assertIn("runtimeDrawer.hidden = !expanded", html)

    def test_hud_uses_neutral_fallback_and_reports_stale_state(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="en">', html)
        self.assertIn("document.documentElement.lang = locale", html)
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

    def test_hud_has_bounded_locale_resolver_and_single_dictionary(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn("const dictionary =", html)
        self.assertIn("function t(key, params = {})", html)
        self.assertIn("function resolveLocale", html)
        self.assertIn("new URLSearchParams", html)
        self.assertIn('"zh-tw", "en"', html)
        self.assertIn('["zh", "zh-tw", "zh-hant"]', html)
        self.assertIn("return localeFromLanguageTag(preferred)", html)
        self.assertIn('data-i18n="runtime.liveAgents"', html)
        self.assertIn('data-i18n-aria-label="header.aria"', html)
        for key in ("broadcast.visual", "broadcast.task", "telemetry.taskSignal", "telemetry.runtimeSignal"):
            self.assertIn(f'data-i18n="{key}"', html)
        self.assertNotIn("localStorage", html)
        self.assertNotIn("document.cookie", html)

    def test_hud_zh_tw_preserves_original_mixed_bridge_copy(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('Object.assign(dictionary["zh-TW"], dictionary.en', html)
        self.assertIn('"app.subtitle": "艦隊指揮甲板 · repository task truth"', html)
        self.assertIn('"evidence.description": "只呈現可由目前快照追溯的證據；Runtime 不改寫任務生命週期。"', html)
        self.assertIn('"state.unavailableNotice": "任務狀態不可用 · 顯示備援內容"', html)
        self.assertIn('"state.staleNotice": "任務狀態過期 · 顯示最後有效快照"', html)
        self.assertIn('"app.subtitle": "Fleet command deck · repository task truth"', html)
        self.assertIn('"zone.intakeCommand": "OPERATION"', html)
        self.assertIn('"plot.title": "FLEET COMMAND PLOT"', html)

    def test_hud_uses_text_content_for_dynamic_user_and_system_values(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", html)
        self.assertIn("goal.textContent = state.goal ===", html)
        self.assertIn("nameplate.textContent = String(agent?.task || label)", html)
        self.assertIn('setNotice(stateNotice, t("state.staleNotice"))', html)
        self.assertIn('t("runtime.noIntervention")', html)

    def test_hud_has_visible_legend_motion_preference_and_semantic_lists(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('class="map-legend" aria-label="Task status legend"', html)
        for label in ("Intake", "In Progress", "Blocked", "Review", "Done"):
            self.assertIn(f">{label}</span>", html)
        self.assertIn("@media (prefers-reduced-motion: reduce)", html)
        self.assertIn('id="progressBar" role="progressbar"', html)
        self.assertIn('class="agents-layer" data-entity-kind="task" role="list"', html)
        self.assertIn('class="runtime-agents-layer" data-entity-kind="runtime-agent" role="list"', html)
        self.assertIn('item.setAttribute("role", "listitem")', html)
        self.assertIn('item.dataset.state = state', html)
        self.assertIn('track.className = "agent-title-track"', html)
        self.assertIn('track.setAttribute("aria-hidden", "true")', html)
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

    def test_hud_uses_approved_two_line_headers_in_lifecycle_order(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        pattern = re.compile(
            r'<section class="territory" data-zone="([^"]+)" aria-labelledby="[^"]+">'
            r'<header class="territory-header"><h3 id="[^"]+" aria-label="([^"]+)"[^>]*>'
            r'<span class="zone-command"[^>]*>([^<]+)</span>'
            r'<span class="zone-state[^>]*>([^<]+)</span>'
        )
        self.assertEqual(
            pattern.findall(html),
            [
                ("Intake", "Intake", "OPERATION", "PLANNING"),
                ("In Progress", "In Progress", "FLEET", "DEPLOYED"),
                ("Blocked", "Blocked · Needs Intervention", "TACTICAL", "HOLD"),
                ("Review", "Review", "COMMAND", "VALIDATION"),
                ("Done", "Done", "MISSION", "COMPLETE"),
            ],
        )
        for lifecycle in ("Intake", "In Progress", "Review", "Done"):
            self.assertEqual(html.count(f'aria-label="{lifecycle}"'), 1)
        self.assertEqual(html.count('aria-label="Blocked · Needs Intervention"'), 1)
        self.assertNotIn('class="zone-state">INTAKE</span>', html)
        self.assertNotIn('class="zone-state">IN PROGRESS</span>', html)
        self.assertIn("font-weight: 700", html)
        self.assertRegex(html, r"\.zone-command, \.zone-state \{[^}]*font-weight: 700;[^}]*line-height: 1\.15;")
        self.assertRegex(html, r"\.zone-command \{[^}]*font-size: \.67rem;[^}]*letter-spacing: \.14em;")
        self.assertRegex(html, r"\.zone-state \{[^}]*font-size: \.55rem;[^}]*letter-spacing: \.1em;")
        for zone in ("Intake", "In Progress", "Blocked", "Review", "Done"):
            self.assertIn(f'.territory[data-zone="{zone}"] {{ --territory-family:', html)

    def test_hud_header_responsive_rules_protect_narrow_territories(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn(
            "@media (min-width: 621px) and (max-width: 760px), (min-resolution: 192dpi) and (max-width: 1520px)",
            html,
        )
        self.assertRegex(html, r"\.territory-header \{[^}]*gap: 6px; min-height: 52px; padding-bottom: 7px;")
        self.assertRegex(html, r"\.zone-command \{[^}]*font-size: \.58rem; letter-spacing: \.08em; line-height: 1\.15;")
        self.assertRegex(html, r"\.zone-state \{[^}]*font-size: \.46rem; letter-spacing: \.04em; line-height: 1\.15;")
        self.assertRegex(html, r"\.territory-doctrine \{[^}]*font-size: \.42rem; letter-spacing: \.04em; line-height: 1\.15;")
        self.assertIn("minmax(110px", html)

    def test_hud_attention_is_aggregated_from_the_protocol_allowlist(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn('new Set(["approval", "question", "blocked", "error", "verification"])', html)
        self.assertIn("attentionCount", html)
        self.assertIn("workingCount", html)
        self.assertIn("Awaiting MissionCenter verification", html)

    def test_hud_runtime_truth_contract_is_explicit_and_scoped(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        self.assertIn("const runtimeFreshnessTtlMs = 60000", html)
        self.assertIn("observedAgentCount = agents.length", html)
        self.assertIn("attentionCount = attentionAgentIds.size", html)
        self.assertIn('new Set(["connected", "replay", "file", "file-fallback", "static"])', html)
        self.assertIn('runtime.counts', html)
        self.assertIn('Configured endpoint only', html)
        self.assertIn('不是 Codex 全域 agent census', html)
        self.assertIn("renderRuntimeState(null)", html)
        self.assertNotIn('renderRuntimeState({ sourceStatus: "disconnected", agents: [], attention: [] })', html)

    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable for HUD behavior checks")
    def test_hud_runtime_truth_node_behavior(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        function_lines = {}
        for name in ("parseRuntimeTime", "deriveRuntimeTruth"):
            function_lines[name] = next(
                line.strip() for line in html.splitlines() if f"function {name}(" in line
            )
        node_script = "\n".join(
            [
                'const attentionKinds = new Set(["approval", "question", "blocked", "error", "verification"]);',
                'const runtimeFreshnessTtlMs = 60000;',
                'const runtimeFreshSources = new Set(["connected", "replay", "file", "file-fallback", "static"]);',
                function_lines["parseRuntimeTime"],
                function_lines["deriveRuntimeTruth"],
                'const now = Date.parse("2026-08-29T00:00:00Z");',
                'const agent = (agentId, lastSeenAt) => ({ agentId, lastSeenAt, state: "working" });',
                'const cases = [',
                '  deriveRuntimeTruth({ sourceStatus: "connected", updatedAt: "2026-08-28T23:59:59Z", agents: [agent("a", "2026-08-28T23:59:59Z"), agent("b", "2026-08-28T23:59:59Z")], attention: [{ agentId: "a", kind: "approval" }, { agentId: "a", kind: "error" }, { agentId: "b", kind: "question" }] }, now),',
                '  deriveRuntimeTruth(null, now),',
                '  deriveRuntimeTruth({ sourceStatus: "replay", updatedAt: "2026-08-28T23:00:00Z", agents: [agent("replay-agent", "2026-08-28T23:00:00Z")], attention: [] }, now),',
                '  deriveRuntimeTruth({ sourceStatus: "file", updatedAt: "2026-08-28T23:59:59Z", agents: [agent("file-agent", "2026-08-28T23:59:59Z")], attention: [] }, now)',
                '];',
                'process.stdout.write(JSON.stringify(cases));',
            ]
        )
        completed = subprocess.run(
            [shutil.which("node"), "-e", node_script],
            check=True,
            capture_output=True,
            text=True,
        )
        cases = json.loads(completed.stdout)
        self.assertEqual(cases[0], {"freshness": "VALID", "observedAgentCount": 2, "attentionCount": 2})
        self.assertEqual(cases[1], {"freshness": "UNAVAILABLE", "observedAgentCount": 0, "attentionCount": 0})
        self.assertEqual(cases[2]["freshness"], "STALE")
        self.assertEqual(cases[3]["freshness"], "VALID")

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
        self.assertIn('t("telemetry.hidden", { count: counts.hidden })', html)
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
        self.assertIn('"runtime.parentTopology": "Runtime agent parent-child topology"', html)
        self.assertIn("Math.min(4, 1 + generationFor", html)
        self.assertIn("agent.parentAgentId", html)
        self.assertNotIn("agent.progress", html)
        self.assertNotIn("agent.token", html)

    def test_task_topology_uses_measured_cards_and_bounded_layout_reflow(self):
        html = (ROOT / "assets" / "visual-hub" / "visual-summary.html").read_text(encoding="utf-8")
        topology = html.split("function renderTopology", 1)[1].split(
            "function scheduleTopologyMeasurement", 1
        )[0]
        self.assertIn('card.dataset.taskId = id', html)
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
        self.assertIn('card.dataset.taskColor = String(color.hue)', html)
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
            "Intake": ("OPERATION", "[42, 54]", "[78, 90]", "[58, 70]"),
            "In Progress": ("FLEET", "[132, 150]", "[58, 76]", "[48, 62]"),
            "Blocked": ("TACTICAL", "[350, 359]", "[76, 90]", "[52, 66]"),
            "Review": ("COMMAND", "[198, 222]", "[64, 82]", "[54, 68]"),
            "Done": ("MISSION", "[200, 220]", "[4, 12]", "[62, 76]"),
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
        self.assertIn('card.dataset.taskColorFamily = color.family', html)
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
