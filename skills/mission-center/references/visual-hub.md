# Visual Hub

## Mission Control HUD v2

The HUD has three explicitly separate surfaces:

- Mission Island summarizes project progress and includes a compact attention capsule.
- Live Agents is a collapsed-by-default drawer for optional `RuntimeState` telemetry.
- Pixel Mission Map shows task lifecycle helpers from `visual-state.json`.

The capsule surfaces only approval, question, blocked, error, and linked finished-awaiting-verification attention. Ordinary activity never raises attention. Mission state refreshes every 60 seconds. Runtime state refreshes every 30 seconds while active, 60 seconds while idle, and backs off to 120 seconds while the tab is hidden; WebSocket events remain immediate. It preserves the last valid snapshot across invalid JSON or atomic-write races and labels that snapshot as stale. Missing or malformed runtime data is a normal unavailable state and must leave the static Task HUD usable with a truthful notice.

Runtime agents and task helpers remain distinct entity types and DOM layers. Runtime map placement is presentation-only: map the verified privacy-safe `activityKind` enum to an existing zone, and never persist inferred coordinates, parse prompt text, or let runtime telemetry edit Task state. Unknown, idle, stale, or disconnected activity stays in an explicitly neutral Unknown presentation rather than implying Done or inventing a location.

When expanded, Live Agents may group cards by verified `parentAgentId` into a bounded five-generation topology. It may show agent ID, state, explicit Task links, and coarse activity only. Never invent progress percentages or persist model names, token totals, full task text, or a chatty event feed merely to imitate a control-room demo.

An interactive repository Code Map is a separate optional artifact, not Runtime telemetry. If implemented, keep a human HTML view, a machine-readable JSON view, and a fingerprint/lock that marks stale modules after source changes. Caller, dependency, flow, test, and source-evidence edges must come from verified analysis; unsupported languages or ambiguous edges stay unknown. Do not merge this artifact into `RuntimeState` or make it a canonical Task source.

Serve the HUD through `mission_runtime.py serve`, bound to `127.0.0.1`, when live JSON is needed. First-version controls are read-only. Future approve, reject, or focus actions appear only when declared by provider capabilities, require a random session token, `POST`, and Origin validation, and must retain the provider's native permission flow.

明確呼叫 Mission Center 時可自動開啟本機 HUD；Hook 需由使用者信任，並以缺少工作區資產、無法健康檢查、無頭環境或瀏覽器失敗為正常 fail-safe，不阻塞核心任務。

## Purpose

Use the HUD as a task-lifecycle board. `MissionCenter/tasks.md` is the only source for helper count, order, names, and zones.

## Task Mapping

- Create exactly one helper for each selected task row.
- Use the task ID as the helper ID and the task short title as its name.
- Derive each helper's accent token deterministically from its task ID within the lifecycle color family; refreshes must not recolor a task. Only Blocked/HOLD uses the red family; attention keeps its zone family and adds an amber secondary pulse/glow.
- Keep task order aligned with `tasks.md`.
- Never derive helper count from owners, active agents, processes, or parallel work.
- Do not create a placeholder helper when no valid task exists.

Map task statuses to HUD zones:

| Task status | HUD zone |
| --- | --- |
| `Backlog`, `Ready` | `Intake` |
| `In Progress` | `In Progress` |
| `Blocked` | `Blocked` |
| `Review` | `Review` |
| `Done` | Rest area |

Task card color families are intentionally bounded: `Intake`/`BRIEFING` is yellow, `In Progress`/`EXECUTION` is green, `Blocked`/`HOLD` is red, `Review`/`VERIFICATION` is blue, and `Done`/`ARCHIVE` is low-saturation silver-gray. A deterministic task-ID hash varies hue, saturation, and lightness only inside the selected family; the card may add a static same-color tint at roughly 8% alpha that fades from one corner over the deep surface. The visible task ID and textual status remain in every card, so status is never conveyed by color alone.

Show the first 10 unfinished tasks. Completed tasks do not consume those slots. Keep at most 15 helpers total and retire the oldest completed tasks first. If the source contains more than the visible limit, disclose the visible/total/hidden counts; never present the visible slice as the complete runtime picture.

The static HUD must start from `Unknown`/`0%`/no fabricated tasks. If the task state cannot be loaded, show a fallback notice; after one valid load, show a stale notice while retaining the last valid snapshot. Task and Runtime collections use list/listitem semantics, the Runtime drawer has an explicit close and Escape path, and `prefers-reduced-motion` disables decorative motion.

## Bootstrap Output

Copy the bundled HUD into `output/mission-center-assets/` and create `MissionCenter/visual-hub.md` with a direct link to `visual-summary.html`. Run `scripts/sync_mission_center.py` after task changes so JSON state and materialized views stay aligned. Legacy `project.md` and `progress.md` files without the managed-summary marker are preserved; use `--rewrite-summaries` only for an intentional one-time adoption into generated summaries.

If task parsing fails, report the exact error and keep the previous state file. Do not invent tasks to make the HUD look populated.
