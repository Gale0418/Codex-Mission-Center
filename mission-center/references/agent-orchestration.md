# Agent Orchestration

## When to Use Subagents

Use subagents when a task is:

- independent from the current slice
- small enough to describe clearly
- useful to validate in parallel
- not blocked by shared state

Do not use subagents when the next step depends on their answer immediately.

If the session has already used subagents, close completed ones before opening a new wave. Rotate new subagents deliberately instead of spawning a pile at once. Before calling the next expert, review the current Git diff and compare against previous Git history when you need to verify whether a change is new or already solved.

## Task Packet

Give each subagent:

- the exact file or scope
- the goal
- constraints
- expected output
- acceptance criteria

## Parallelism Rule

Parallelize only when tasks do not overlap in file ownership or decision making.

## Review Rule

Each subagent result must be checked against:

- the current project goal
- the task tree
- the smoke-test plan
- the active blockers

## Handoff Rule

When a subagent finishes, update `project.md`, `progress.md`, and `tasks.md` before dispatching the next one.

## Anti-Queue Rule

If Codex agent slots feel crowded:

- close finished subagents first
- wait for the current wave to settle
- then spawn the next wave
- keep the active set small enough to reason about
- inspect the Git diff before launching another expert wave
