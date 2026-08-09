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

Completion Adversarial Critic Council seats additionally require explicit approval of the total budget, per-seat budget, tool budget, and wall-clock budget. These seats are real, read-only subagents: they cannot update `tasks.md`, smoke evidence, guardrails, closeout, runtime state, or the reviewed artifact. Use [completion-critic-council.md](completion-critic-council.md) for its immutable snapshot, routing, and wave limits.

## Wave Discipline

Before opening a new wave:

1. Close completed subagents.
2. Review their evidence against the mission, task tree, blockers, and verification plan.
3. Inspect the current Git diff.
4. Update MissionCenter task state.
5. Decide whether another wave is still necessary.

Keep the active set small. Do not dispatch a pile of overlapping experts or use subagents merely to make the process look busy.

For completion critics, use at most an initial review phase and one delta wave; never continue until clean. When slots are constrained, the initial phase may queue blind critic batches: close each completed seat, seal its draft, and dispatch the separate evidence arbiter only after all critic drafts are sealed. Initial critic drafts are mutually blind. The chair deduplicates, preserves material dissent, and verifies claims against the frozen evidence and available capabilities.

## Task Packet

Every dispatched subagent receives exact scope, goal, constraints, expected evidence, and acceptance criteria. The main agent remains responsible for integration and verification.

For critic seats, the packet also includes the immutable `taskId`, revision/hash, build/platform/capabilities, evidence locators, read-only restriction, finding schema, authorization, and budget. Critic reports are advisory release-quality evidence; they cannot substitute for passing smoke verification or task lifecycle updates.
