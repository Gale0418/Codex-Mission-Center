# Visual Hub

## Mission Control HUD v2

The HUD has three explicitly separate surfaces:

- Mission Island summarizes project progress and includes a compact attention capsule.
- Live Agents is a collapsed-by-default drawer for optional `RuntimeState` telemetry.
- Pixel Mission Map shows task lifecycle helpers from `visual-state.json`.

The capsule surfaces only approval, question, blocked, error, and linked finished-awaiting-verification attention. Ordinary activity never raises attention. Mission state refreshes every 10 seconds. Runtime state refreshes every 2 seconds while visible and backs off to 30 seconds while the tab is hidden; it preserves the last valid snapshot across invalid JSON or atomic-write races. Missing runtime data is a normal state and must leave the static Task HUD usable.

Runtime agents and task helpers remain distinct entity types and DOM layers. Runtime map placement is presentation-only: map the verified privacy-safe `activityKind` enum to an existing zone, and never persist inferred coordinates, parse prompt text, or let runtime telemetry edit Task state. Unknown activity stays a generic working presentation rather than inventing a location.

When expanded, Live Agents may group cards by verified `parentAgentId` into a bounded five-generation topology. It may show agent ID, state, explicit Task links, and coarse activity only. Never invent progress percentages or persist model names, token totals, full task text, or a chatty event feed merely to imitate a control-room demo.

An interactive repository Code Map is a separate optional artifact, not Runtime telemetry. If implemented, keep a human HTML view, a machine-readable JSON view, and a fingerprint/lock that marks stale modules after source changes. Caller, dependency, flow, test, and source-evidence edges must come from verified analysis; unsupported languages or ambiguous edges stay unknown. Do not merge this artifact into `RuntimeState` or make it a canonical Task source.

Serve the HUD through `mission_runtime.py serve`, bound to `127.0.0.1`, when live JSON is needed. First-version controls are read-only. Future approve, reject, or focus actions appear only when declared by provider capabilities, require a random session token, `POST`, and Origin validation, and must retain the provider's native permission flow.

## Purpose

Use the HUD as a task-lifecycle board. `MissionCenter/tasks.md` is the only source for helper count, order, names, and zones.

## Task Mapping

- Create exactly one helper for each selected task row.
- Use the task ID as the helper ID and the task short title as its name.
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

Show the first 10 unfinished tasks. Completed tasks do not consume those slots. Keep at most 15 helpers total and retire the oldest completed tasks first.

## Bootstrap Output

Copy the bundled HUD into `output/mission-center-assets/` and create `MissionCenter/visual-hub.md` with a direct link to `visual-summary.html`. Run `scripts/sync_mission_center.py` after task changes so the JSON state and Markdown summaries stay aligned.

If task parsing fails, report the exact error and keep the previous state file. Do not invent tasks to make the HUD look populated.
