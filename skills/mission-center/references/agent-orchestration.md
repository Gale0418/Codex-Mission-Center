# Agent Orchestration

## Default: Simulated Perspectives

Creative and Dynamic Expert Council participants are simulated perspectives used by the main agent to transfer principles, challenge assumptions, and expose trade-offs. They do not imply real subagent processes, consume separate runtime-agent quota, or control HUD helper count.

## Real Subagent Gate

Use real subagents only when all conditions hold:

- the work is independent from the current slice
- it can be described with a bounded file or research scope
- independent validation adds material value
- it does not depend on shared mutable state
- explicit user approval has been given

## Wave Discipline

Before opening a new wave:

1. Close completed subagents.
2. Review their evidence against the mission, task tree, blockers, and verification plan.
3. Inspect the current Git diff.
4. Update MissionCenter task state.
5. Decide whether another wave is still necessary.

Keep the active set small. Do not dispatch a pile of overlapping experts or use subagents merely to make the process look busy.

## Task Packet

Every dispatched subagent receives exact scope, goal, constraints, expected evidence, and acceptance criteria. The main agent remains responsible for integration and verification.
