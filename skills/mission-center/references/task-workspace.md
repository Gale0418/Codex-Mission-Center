# MissionCenter Task Workspace

## Folder Layout

Create this structure under the current workspace root:

```text
MissionCenter/
  project.md
  progress.md
  tasks.md
  decisions.md
  smoke-tests.md
  notes.md
  snapshot.md
  visual-hub.md
```

Add extra files only when they clearly improve traceability.

## File Roles

### `project.md`

Track the top-level project, current cycle, labels, activity notes, and comment-style updates.

Recommended sections:

- `Project`
- `Cycle`
- `Goal`
- `Labels`
- `Activity log`
- `Open comments`

### `progress.md`

Track the current state at a glance.

Recommended sections:

- `Project`
- `Objective`
- `Current status`
- `Milestone`
- `Progress bar`
- `Active tasks`
- `Blocked by`
- `Next update`

Use a simple text bar or checklist-based progress indicator. Keep the top of the file readable in one screen.
Recompute the bar from the current task set whenever tasks are added, removed, blocked, or completed.
If estimates exist, you may compute progress from completed estimate total divided by total estimate total; otherwise use completed leaf tasks divided by total leaf tasks.

### `tasks.md`

Track the task tree.

Recommended fields:

- `ID`
- `Title`
- `Type` (`Epic`, `Task`, `Subtask`)
- `Parent`
- `Priority`
- `Status`
- `Owner`
- `Depends on`
- `Next action`
- `Verification`
- `Estimate`
- `Labels`
- `Comments`

Suggested task hierarchy:

- `Epic` = broad outcome
- `Task` = shippable slice
- `Subtask` = small executable step

Suggested statuses:

- `Backlog`
- `Ready`
- `In Progress`
- `Blocked`
- `Review`
- `Done`

### `decisions.md`

Record major choices, assumptions, and reversals.

### `notes.md`

Keep open questions and a concise research log:

```text
Pre-search idea | Source | Adopted insight | License status
```

Do not paste full search results or long source summaries.

### `smoke-tests.md`

Record verified checks only.

Each entry should include:

- `What was tested`
- `How it was tested`
- `Expected result`
- `Observed result`
- `Pass / fail`
- `Date`
- `Linked task ID`
- `Run type` (`manual` or `automated`)

## Update Rules

- Update the workspace whenever the goal changes.
- Add a task when a new deliverable appears.
- Mark a task blocked when it depends on missing information or another task.
- Promote a task to done only after a smoke test or equivalent verification exists.
- If a task becomes obsolete, move the reason into `decisions.md` or `notes.md` before removing it.
- If a new task appears during execution, assign it an ID immediately and link it to its parent.
- If a task is reopened, append the new work to the existing entry instead of creating a duplicate.
- Keep `project.md`, `progress.md`, and `tasks.md` aligned when scope or cycle changes.

## Smoke Test Standard

Prefer checks that are:

- fast
- repeatable
- low-risk
- directly tied to the user goal

If a real automated smoke test is available, prefer it.
If not, write the closest reproducible manual check and label it clearly as manual.

## First-Run Bootstrap

When the workspace is created for a new goal, seed these starting files:

- `project.md` with the project title, cycle, goal, and labels
- `progress.md` with the current objective and empty progress bar
- `tasks.md` with one top-level epic and initial child tasks
- `smoke-tests.md` with at least one placeholder row for the first verification
- `decisions.md` with any assumptions made during intake
- `notes.md` for open questions and the concise research log
- `snapshot.md` for the latest reopenable checkpoint
- `visual-hub.md` for a short link to the animated MissionCenter HUD

## Sync Expectations

The workspace should be able to recompute progress and active-task summaries from `tasks.md` and `smoke-tests.md`.
If a helper script exists, prefer it over manual recalculation.

## Activity and Comments

Use terse, timestamped entries for updates:

- what changed
- why it changed
- what remains open

If a user-facing comment is needed, write it as a short entry in `project.md` or under the relevant task in `tasks.md`.

## Related Protocols

- `intake-protocol.md` defines mission completeness and one-question intake.
- `intake-council.md` defines creative cross-domain divergence and convergence.
- `research-protocol.md` defines Prior Art, Jina fallback, Clean-room, and licensing.
- `execution-gates.md` defines when a project may move from intake to plan to execute to review.
- `agent-orchestration.md` defines when to dispatch subagents.
- `smoke-test-patterns.md` defines how to choose a verification check.
