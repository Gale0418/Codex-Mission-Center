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

For completion critics, follow the selected loop policy in [completion-critic-council.md](completion-critic-council.md): legacy bounded reviews allow an initial wave and one delta wave; new reviews default to explicit convergence with no fixed wave count, but require all verified in-scope defects repaired and current coverage before success. Budget exhaustion or lack of progress produces an incomplete checkpoint, not a clean result. When slots are constrained, queue blind critic batches: seal each completed draft and dispatch the separate evidence arbiter only after all critic drafts are sealed. Use an available close/release API when supported; interruption alone does not release a slot. Initial critic drafts are mutually blind. The chair deduplicates, preserves material dissent, and verifies claims against the frozen evidence and available capabilities.

## Task Packet

For convergence, stop dispatching new adversarial waves when no unresolved P0/P1 remains. Finish known defects and targeted verification in cleanup; P2/P3 alone cannot trigger another broad review. Reopen only for a P0/P1 revealed during cleanup. Final seat reports confirm repairs and agreed coverage rather than restart discovery.

Every dispatched subagent receives exact scope, goal, constraints, expected evidence, and acceptance criteria. The main agent remains responsible for integration and verification.

For critic seats, the packet also includes the immutable `taskId`, revision/hash, build/platform/capabilities, evidence locators, read-only restriction, finding schema, authorization, and budget. Critic reports are advisory release-quality evidence; they cannot substitute for passing smoke verification or task lifecycle updates.
