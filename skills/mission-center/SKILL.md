---
name: mission-center
description: Use when a user needs to clarify a vague or high-impact goal, research existing solutions, publish an approved direction as a local task workspace, or resume tracked MissionCenter work.
---

# Mission Center

## Overview

Turn an unclear goal into an approved, research-backed task workspace under `MissionCenter/`. Keep each workspace local and file-based. Match the user's conversation language in generated task files and HUD labels.

## Core Contract

- Understand the whole mission before publishing tasks.
- Ask exactly one focused question per intake turn.
- Research existing solutions before proposing custom implementation.
- Present options, trade-offs, and an approved task draft before writing `tasks.md`.
- Treat `tasks.md` as the only task-order and lifecycle source.
- Require recorded verification before moving a task to `Done`.

## Workflow

### 1. Resume or Start

If `MissionCenter/` exists, read `project.md`, `progress.md`, `tasks.md`, `decisions.md`, `notes.md`, and `smoke-tests.md` before changing anything. Otherwise begin North Star Intake and do not scaffold files while the goal is still unclear.

### 2. North Star Intake

Follow [intake-protocol.md](references/intake-protocol.md). Restate the current understanding, identify the highest-value gap, offer a concise recommendation, and end with one question. Continue until the complete mission, boundaries, first milestone, main risks, and verification strategy are clear.

### 3. Creative Cross-Domain Council

Use [intake-council.md](references/intake-council.md) only for open-ended invention, product, experience, system, or architecture work where cross-domain transfer may improve the result. Diverge across mechanisms and distant fields first, then converge on ideas that are unexpected but feasible. Routine fixes and deterministic updates skip this council.

### 4. Prior Art Gate

Use [research-protocol.md](references/research-protocol.md). Inspect local context first, then current primary sources when needed. Compare adopting, adapting, learning from, and independently building solutions. Record only decision-relevant research and respect license, attribution, access-control, and Clean-room rules.

### 5. Propose and Approve

Offer two or three viable approaches with trade-offs and a recommendation. Build a rolling Linear-style draft using `Project -> Cycle -> Epic -> Task -> Subtask`: map the full set of Epics, detail only the first verifiable milestone, and keep later work as a coarse Backlog.

Do not write `tasks.md` until the user accepts the approved task draft. Follow [linear-parity.md](references/linear-parity.md) and [execution-gates.md](references/execution-gates.md).

### 6. Publish the Workspace

Create or reuse `MissionCenter/`. Use `scripts/bootstrap_mission_center.py` for first-run files and `scripts/seed_task_tree.py` only after task-draft approval. Use the user's language consistently. Keep research notes concise and decisions traceable.

### 7. Execute and Maintain

Use Superpowers-style gates: `Brainstorm -> Spec -> Plan -> TDD -> Verify -> Closeout`. Scale document depth with risk, but never skip goal understanding or final verification. Update project, progress, task, decision, and smoke-test files when facts change. Follow [agent-orchestration.md](references/agent-orchestration.md) before using real subagents.

### 8. Sync the HUD

Follow [visual-hub.md](references/visual-hub.md). One helper represents one task. The helper name, order, zone, and count come from `tasks.md`, never owners, processes, active agents, or execution parallelism. Run `scripts/sync_mission_center.py` after task-state changes.

## Task Lifecycle

Use `Backlog -> Ready -> In Progress -> Blocked -> Review -> Done`. `Blocked` means a real impediment. Smoke tests are completion evidence, not a separate task status. Keep dependencies and next actions explicit.

## Validation

- Give every meaningful task a low-cost, repeatable verification.
- Record command or action, expected result, observed result, outcome, date, and linked task ID.
- Keep invalid task data from overwriting the last valid HUD state.
- Use [smoke-test-patterns.md](references/smoke-test-patterns.md) to choose checks.
- Use `scripts/snapshot_mission_center.py` before closeout and `scripts/closeout_mission_center_cycle.py` at project or cycle completion.

## Output Rules

- Keep generated task files concise and readable in one screen where practical.
- Use the user's language for headings, task titles, decisions, notes, and verification descriptions.
- Add scope as explicit tasks instead of hiding it in prose.
- Record why obsolete work was removed.
- Keep unrelated workspaces separate; consult [global-overview.md](references/global-overview.md) only for a read-only multi-workspace dashboard.

## References

- [task-workspace.md](references/task-workspace.md): canonical workspace files and fields.
- [intake-protocol.md](references/intake-protocol.md): intake completeness and question rules.
- [intake-council.md](references/intake-council.md): creative cross-domain transfer.
- [research-protocol.md](references/research-protocol.md): Prior Art, Jina, Clean-room, and licensing.
- [linear-parity.md](references/linear-parity.md): Linear task model and rolling planning.
- [execution-gates.md](references/execution-gates.md): approval and execution gates.
- [agent-orchestration.md](references/agent-orchestration.md): simulated perspectives and real subagents.
- [visual-hub.md](references/visual-hub.md): task-driven HUD contract.
- [smoke-test-patterns.md](references/smoke-test-patterns.md): verification selection.
- [project-lifecycle.md](references/project-lifecycle.md): lifecycle and closeout.
- [global-overview.md](references/global-overview.md): safe global summaries.
- [platform-support.md](references/platform-support.md): installation and platform notes.
