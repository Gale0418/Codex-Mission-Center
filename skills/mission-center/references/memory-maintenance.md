# Memory Maintenance Protocol

## Purpose

Reduce repeated context loading without creating a second task truth source. The mechanism is local, deterministic, lazy, and model-free.

## File Roles

- `daily-log.md` is the bounded hot daily journal. After each journal update, run `sync` to keep recent organized entries within 128 KiB; before moving entries out, preserve them verbatim in an immutable, content-addressed archive and verify its bytes and digest. Archives preserve history but never own task lifecycle.
- `guardrails.md` is the canonical set of explicitly approved pitfalls and rules. Automation may reference active guardrails but must never add, promote, supersede, or delete one without human approval.
- `brief.md` is a disposable materialized view of project identity, today's journal, and active guardrail IDs.
- `working-set.md` is the bounded derived execution view: Blocked, In Progress, Review, unfinished P0, then Ready work. It never owns lifecycle state.
- `critical-lessons.md` is the compact, verified experience layer. Active lessons require a symptom, root cause, verified action, verification, and an incident evidence pointer; detailed evidence belongs in `incidents/INC-xxx.md`.
- `focus.md` is a deprecated compatibility view for one migration cycle. It is generated from `tasks.md`, may be deleted after consumers migrate, and is never a second source of truth.
- `execution-ledger.jsonl` is an optional, bounded execution-evidence ledger. It may carry restricted pulse-to-handoff continuity, but never owns task lifecycle or ordering.

`tasks.md` remains the only lifecycle and ordering source. Keep each task row concise and understandable: retain only the goal, status, necessary next action, verification, and necessary blocker. Do not paste chat transcripts or unrelated conversation into it. There is no fixed file-size or word-count cap for `tasks.md`; preserve decisions and evidence through links to the relevant evidence or archive instead of dropping them.

## Progressive Read Route

1. Run `<mission-center> status --root <path> [--date <YYYY-MM-DD>]` for bounded health, then `<mission-center> resume --root <path> [--date <YYYY-MM-DD>]` when a context packet is needed.
2. Prefer only the already bounded `packet.content`. Read another file only when `packet.readNext` or `packet.fallbackReason` explicitly names the need; never scan the whole `MissionCenter/` directory during resume.
3. Read `tasks.md` before changing task lifecycle, ordering, priority, dependencies, or next actions.
4. Read `decisions.md`, `notes.md`, and `smoke-tests.md` when rationale, research, risk, or verification evidence is needed.
5. When stale or truncated, run `<mission-center> sync --root <path> --operation-id <id> --timestamp <RFC3339>`. Use `<mission-center> doctor --root <path>` for task, completion-passport, and writer-lock diagnostics; use `status` or `resume` to surface stale or malformed daily-log/derived state.
6. When handing work across invocations, use the restricted `pulse` command and `handoff` route described in [Execution Pulse／Handoff](execution-pulse-handoff.md). A missing ledger is safe to omit; a corrupt ledger fails closed.

## Maintenance Commands

```text
<mission-center> status --root <path> [--date <YYYY-MM-DD>]
<mission-center> resume --root <path> [--date <YYYY-MM-DD>]
<mission-center> sync --root <path> --operation-id <id> --timestamp <RFC3339>
<mission-center> doctor --root <path>
```

`sync` uses content fingerprints and atomic write-if-changed. All writers must cooperate with the workspace writer lock; do not edit the journal concurrently with rollover. Exact `- Last organized: YYYY-MM-DD` and `- 最後整理： YYYY-MM-DD` lines are reserved metadata. There is no daemon or scheduled model call. A normal sync lazily advances `Last organized` to the current local date, preserves moved daily-log bytes in a verifiable immutable archive before replacing the bounded hot log, and repeated calls on the same day do not rewrite unchanged views.

## Compaction Boundaries

- Keep the recent `daily-log.md` hot window bounded to 128 KiB. Before rollover, preserve moved entries verbatim in an immutable, content-addressed archive and verify its bytes and digest; never discard history and never treat `tasks.md` as a reconstruction of the full journal.
- Keep routine task rows concise and readable: goal, status, necessary next action, verification, and necessary blocker only. Do not impose a fixed byte or word limit on `tasks.md`; link to decisions, evidence, and archived detail instead of copying long conversation or unrelated prose.
- Never auto-summarize away decisions, research provenance, smoke-test evidence, task history, or unresolved blockers.
- Treat `brief.md`, `working-set.md`, and legacy `focus.md` as rebuildable caches. Do not edit them directly.
- Resume packets have a 16 KiB hard budget over their actual UTF-8 `content`. A truncated packet reports `[TRUNCATED]` and `readNext`; consumers must not bypass the fuse by rereading every hot or canonical record.
- A compact brief must mark truncation explicitly and route the reader to canonical files.
- `<mission-center> doctor --root <path>` checks task, completion-passport, and writer-lock health; `status` and `resume` report stale or malformed daily-log/derived state.
