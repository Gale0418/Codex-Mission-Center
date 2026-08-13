# Memory Maintenance Protocol

## Purpose

Reduce repeated context loading without creating a second task truth source. The mechanism is local, deterministic, lazy, and model-free.

## File Roles

- `daily-log.md` is the canonical append-only daily journal. Keep one `## YYYY-MM-DD` section per local calendar day and one `Last organized` field.
- `guardrails.md` is the canonical set of explicitly approved pitfalls and rules. Automation may reference active guardrails but must never add, promote, supersede, or delete one without human approval.
- `brief.md` is a disposable materialized view of project identity, today's journal, and active guardrail IDs.
- `working-set.md` is the bounded derived execution view: Blocked, In Progress, Review, unfinished P0, then Ready work. It never owns lifecycle state.
- `critical-lessons.md` is the compact, verified experience layer. Active lessons require a symptom, root cause, verified action, verification, and an incident evidence pointer; detailed evidence belongs in `incidents/INC-xxx.md`.
- `focus.md` is a deprecated compatibility view for one migration cycle. It is generated from `tasks.md`, may be deleted after consumers migrate, and is never a second source of truth.

`tasks.md` remains the only lifecycle and ordering source. Never infer or write Task status from runtime state, the daily journal, brief, or focus.

## Progressive Read Route

1. Run `python skills/mission-center/scripts/mission_maintenance.py . status`.
2. When fresh, read `brief.md`, then `working-set.md`, then the Active Lessons section of `critical-lessons.md`. Read `snapshot.md` only for an active checkpoint; open `guardrails.md` when the work matches a listed situation.
3. Read `tasks.md` before changing task lifecycle, ordering, priority, dependencies, or next actions.
4. Read `decisions.md`, `notes.md`, and `smoke-tests.md` when rationale, research, risk, or verification evidence is needed.
5. When stale or truncated, run `mission_maintenance.py . sync`. Canonical fallback is explicit and limited to a stale/corrupt derived view, requested missing task, lifecycle mutation, verification evidence, or an explicit request.

## Maintenance Commands

```bash
python skills/mission-center/scripts/mission_maintenance.py . status
python skills/mission-center/scripts/mission_maintenance.py . resume --json
python skills/mission-center/scripts/mission_maintenance.py . task MC-038 --json
python skills/mission-center/scripts/mission_maintenance.py . daily --message "Implemented parser guard"
python skills/mission-center/scripts/mission_maintenance.py . sync
```

`sync` uses content fingerprints and atomic write-if-changed. There is no daemon or scheduled model call. A normal sync lazily advances `Last organized` to the current local date; repeated calls on the same day do not rewrite unchanged views.

## Compaction Boundaries

- Organize routine events by day; deduplicate identical normalized messages.
- Never auto-summarize away decisions, research provenance, smoke-test evidence, task history, or unresolved blockers.
- Treat `brief.md`, `working-set.md`, and legacy `focus.md` as rebuildable caches. Do not edit them directly.
- Resume packets have a 16 KiB hard budget. A truncated packet reports `[TRUNCATED]` and `readNext`; it must not silently load every canonical record.
- A compact brief must mark truncation explicitly and route the reader to canonical files.
- `doctor_mission_center.py` must fail on stale derived fingerprints, inconsistent P0 focus, malformed daily dates, or invalid guardrail rows.
