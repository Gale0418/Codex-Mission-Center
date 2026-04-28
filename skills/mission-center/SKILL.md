---
name: mission-center
description: "Plan, scaffold, and maintain a local MissionCenter task workspace for vague goals. Use when the user wants an offline Linear-like workflow without app dependencies: keep asking focused questions until the goal is clear, run an intake council before execution, create or reuse a MissionCenter folder in the current workspace, track progress, split work into tasks and checkpoints, and record verified smoke tests."
---

# Mission Center

## Overview

Use this skill to turn a vague request into a local task workspace under `MissionCenter/`.
Keep the workflow offline and file-based: no Linear app, no external project service, only structured files in the current workspace.
All user-facing MissionCenter files should follow the user's conversation language. If the user writes in Traditional Chinese, create headings, table labels, notes, decisions, and task descriptions in Traditional Chinese. Keep only stable workflow tokens such as status values, IDs, and labels in English when consistency is useful.
If the workspace also has a visual MissionCenter HUD, create a visible hub link file during bootstrap so the user can jump to the animated summary that shows helpers moving through the task states.

## Core Workflow

1. Clarify the goal before creating anything.
   - Ask one focused question at a time.
   - Keep going until you know the objective, success criteria, constraints, priority, deadline, ownership, non-goals, and what "done" means.
   - If the user says the goal is still fuzzy, summarize the current understanding and ask the next most important question.
   - Before finalizing the workspace, confirm the top-level deliverable, the first milestone, and the main risk.
   - Compare the request against the Linear-style project model and the Superpowers-style execution model before committing to scope.
   - Use the intake protocol in `references/intake-protocol.md` when the request is underspecified.
   - Run the intake council in `references/intake-council.md` before any execution step, rotating angles for product, technical, verification, risk, operations, and one playful wild-card perspective.

2. Create or reuse `MissionCenter/` in the current workspace root.
   - If the folder does not exist, create it.
   - If it already exists, reuse it and update the existing files.
   - Keep all task state inside that folder.
   - On first creation, seed the standard files from `references/task-workspace.md`.
   - Use `scripts/bootstrap_mission_center.py` for the initial scaffold.
   - Pass `--language zh-TW` when the user is using Traditional Chinese; pass `--language en` for English users.
   - Create `visual-hub.md` during bootstrap so the folder contains a direct link to the animated summary / helper hub.
   - Use `scripts/seed_task_tree.py` when the goal is clear enough to seed the first task tree.
   - When seeding a task tree, pass the same `--language` value used for bootstrap.
   - Prefer updating existing files over creating ad hoc notes elsewhere.
   - If the user resumes later, read the current project context first, then decide whether to update the same project or start a new one.
   - Use `project.md` as the canonical project summary, `progress.md` as the current dashboard, and `tasks.md` as the canonical task tree.
   - Treat the current workspace's `MissionCenter/` as the only source of truth for that workspace.
   - If a global overview exists, use it only as a read-only dashboard unless the user explicitly selects a workspace for editing.
   - Use `scripts/normalize_mission_center.py` when task fields drift from the canonical labels, priorities, or statuses.
   - Use `scripts/log_mission_center_change.py` to append a timestamped activity entry after meaningful updates.

3. Break work into a Linear-like structure.
   - Keep a single top-level `Project` for the goal.
   - Use `Cycle` when work is time-boxed or milestone-based.
   - Use `Epic` for the broad goal.
   - Use `Task` for a deliverable slice.
   - Use `Subtask` for a small executable step.
   - Track `Priority`, `Status`, `Owner`, `Blocked by`, `Next action`, `Due`, `Estimate`, `Labels`, and `Comments` when relevant.
   - Treat `Status` as a workflow: `Backlog` -> `Ready` -> `In Progress` -> `Blocked` -> `Review` -> `Done`.
   - Keep dependencies explicit so blocked work is visible.
   - When a task is too large or too risky, split it before execution and assign a parent/child relationship.

4. Keep the workspace alive while work changes.
   - Update progress whenever new facts appear.
   - Add tasks when scope expands.
   - Remove tasks only after recording why they are obsolete.
   - Move completed items to a finished state instead of deleting them.
   - When the user resumes a thread, read the current `progress.md` and `tasks.md` before changing anything.
   - Do not import, merge, or mutate task rows from another folder's `MissionCenter/`.
   - If the user asks about multiple Codex jobs, read `references/global-overview.md` before proposing a hub design.
   - If progress has changed, recalculate the progress bar and active task list.
   - Maintain a brief activity log for major updates, decisions, and handoffs.
   - Use the execution gates in `references/execution-gates.md` to decide when to move from intake to plan to execution to review.
   - Use the sync script in `scripts/sync_mission_center.py` whenever task state changes enough to affect progress or project summary.
   - Use `scripts/closeout_mission_center_cycle.py` at the end of a project or cycle.

5. Validate with smoke tests.
   - Every meaningful task needs at least one low-cost verification step.
   - Record the command or action, the expected result, the observed result, and the outcome.
   - Prefer tests that can be repeated quickly.
   - Do not mark a task `Done` until the smoke test is recorded.
   - If the goal is implementation work, include at least one reproducible smoke test in the workspace.
   - Use `references/smoke-test-patterns.md` for test selection when the task has multiple possible checks.
   - Use `scripts/snapshot_mission_center.py` before closeout or when you need a reopenable checkpoint.
   - Use `scripts/suggest_smoke_tests.py` when the task tree needs default verification ideas.
   - If the intake is still ambiguous, do not advance past the council gate.

## Task Coordination Style

Use Superpowers-style decomposition and Game Studio-style team slicing.

- Start with broad discovery, then narrow into concrete deliverables.
- Split independent work so it can be tracked and executed separately.
- Treat each branch of work as a bounded slice with its own owner, status, and validation.
- When multiple slices are independent, handle them in parallel if the current session supports it.
- Use the smallest safe unit of work that still lets the workspace stay understandable.
- Revisit the task tree whenever the scope or the risk profile changes.
- Use `references/agent-orchestration.md` when deciding whether to dispatch subagents or keep work local.
- Before spawning more subagents, close out completed ones first; then rotate new subagents carefully, one wave at a time, and compare against prior Git history when needed.
- Before spawning the next expert, review the current Git diff and only then decide whether another wave is actually needed.

## Output Rules

- Keep task files concise and consistent.
- Match the user's language for generated file headings, summaries, task titles, notes, decisions, and smoke-test descriptions.
- Include the visual hub link in the workspace scaffold when the UI summary exists.
- Prefer plain Markdown tables and checklists for progress.
- Make the current state obvious at a glance.
- When the user asks for a change, update the relevant task file first, then summarize the impact.
- Keep the progress bar human-readable, for example `Progress: ####---- 40%`.
- If scope expands, create new tasks instead of hiding them inside notes.
- If a task is blocked, say what is missing and which task or question unblocks it.
- Keep project, cycle, task, and smoke-test data in sync.
- Prefer the sync script over hand-editing summary fields.
- Prefer the seeding script over hand-building the first task tree when the goal is already clear enough.
- Prefer the normalization script when task metadata drifts from the canonical taxonomy.
- Prefer the smoke-test suggester when Verification cells are blank or too vague.
- When discussing installation or Mac support, use `references/platform-support.md`.
- When discussing all-workspace monitoring, use `references/global-overview.md` and keep the hub separate from local task truth.

## References

See [task-workspace.md](references/task-workspace.md) for the folder layout, file formats, and smoke-test conventions.
See [linear-parity.md](references/linear-parity.md) for the Linear-like concepts this skill should mirror.
See [intake-protocol.md](references/intake-protocol.md) for question order and stop criteria.
See [execution-gates.md](references/execution-gates.md) for plan/review/done gates.
See [agent-orchestration.md](references/agent-orchestration.md) for subagent and parallel-work rules.
See [smoke-test-patterns.md](references/smoke-test-patterns.md) for selecting a verification style.
See [project-lifecycle.md](references/project-lifecycle.md) for closeout and archive rules.
See [task-seeding.md](references/task-seeding.md) for the first task tree.
See [closeout-format.md](references/closeout-format.md) for closeout structure.
See [normalization-rules.md](references/normalization-rules.md) for canonical field cleanup.
See [snapshot-format.md](references/snapshot-format.md) for reopenable checkpoints.
See [activity-log-format.md](references/activity-log-format.md) for timestamped change notes.
See [smoke-test-catalog.md](references/smoke-test-catalog.md) for verification templates.
See [intake-council.md](references/intake-council.md) for the pre-execution meeting protocol.
See [visual-hub.md](references/visual-hub.md) for the hub-link and helper-roster bootstrap pattern.
See [global-overview.md](references/global-overview.md) for safe multi-workspace dashboard rules.
See [platform-support.md](references/platform-support.md) for macOS, Linux, and Windows installation notes.
