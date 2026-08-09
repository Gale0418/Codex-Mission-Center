# Execution Gates

## Gate 1: Intake

Ask one question at a time until the mission completeness checklist passes. Do not scaffold or publish tasks while the goal is unclear.

## Gate 2: Research, Expert Deliberation, Adaptive Optimization, and Design

Run relevant local research, Prior Art, and early creative cross-domain work. Route consequential decisions through the Dynamic Expert Council Gate as `skip`, `council_lite`, or `council_full`; never force web research or role-play onto deterministic work. Then apply the Adaptive Optimization Gate: route to `skip`, `decision`, `hybrid`, `experimental`, or `research_spike` from the evidence in the current repository. Never invent metrics, bypass hard constraints, or auto-promote a candidate. Present two or three approaches, trade-offs, and a recommendation.

## Gate 3: Task Draft Approval

Present the full Epic map and detailed first milestone as an approved task draft. Do not write `tasks.md` until the user approves that draft.

## Gate 4: Publish

Create or update the local workspace, assign stable IDs and dependencies, and select at least one verification path for each meaningful Task.

## Gate 5: Execute

Implement one bounded slice. Keep changes small, update task state when facts change, and expose blockers rather than hiding them.

## Gate 6: Review

After local verification, run applicable CodeRabbit technical review first, verify its findings, repair real defects, and re-verify locally. Then route the resulting artifact through the [Completion Adversarial Critic Council Gate](completion-critic-council.md) before `Done` or Closeout. Low-risk non-perceptual work may skip only with a recorded reason; perceptual work uses `critic_lite`, while games, releases, and high-impact work use `critic_full`. Critic-driven code repairs receive only the affected focused CodeRabbit review before the one allowed critic delta wave. Before `Done`, require recorded smoke verification, resolved or documented blockers and critic dispositions, and task state that matches reality. The council is advisory evidence, not passing smoke evidence.

## Gate 7: Closeout

After applicable CodeRabbit and Critic Council review, summarize outcomes, preserve smoke-test and advisory evidence separately, record unfinished Backlog work, and capture the next reopenable checkpoint.

## Adaptive Depth

Large or risky missions use the full flow. Small deterministic work may use concise artifacts, but still requires goal understanding, approval for meaningful scope, and verification.
