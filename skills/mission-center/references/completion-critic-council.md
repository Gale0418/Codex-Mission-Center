# Completion Adversarial Critic Council Gate

## Purpose and Position

This is a release-quality evidence and advisory gate. Run it **after local verification and applicable CodeRabbit review**, and before `Done` or Closeout. It never replaces recorded smoke verification, task disposition, or human approval.

Route each completed slice as follows:

- `skip`: low-risk, non-perceptual work may skip. Record the reason and the verification already performed.
- `critic_lite`: a perceptual result with bounded impact needs targeted independent critique.
- `critic_full`: games, releases, high-impact work, or a materially perceptual result need the full route.

The normal order is: local verification -> applicable CodeRabbit technical review -> verified repairs and local re-verification -> Completion Adversarial Critic Council -> `Done`/Closeout. CodeRabbit remains separately advisory.

## Dispatch Authorization and Snapshot

`critic_lite` and `critic_full` use **real subagents, never simulated perspectives**. Lite requires at least two independent critic subagents; Full requires at least three independent critic subagents plus a separate evidence-arbiter subagent. The main agent remains the integrator. Do not dispatch unless the user has explicitly approved the total budget, per-seat budget, tool budget, and wall-clock budget for this gate. The approval must cover the planned wave and any permitted delta wave. If authorization is missing after Lite or Full was selected, record `not dispatched: approval/budget missing`; the main agent keeps the Task in `Review` or marks a real user-decision impediment `Blocked`. It cannot reach `Done` or a clean Closeout. Do not auto-downgrade to `skip`; only the user may select `skip`, and only when the low-risk non-perceptual eligibility rule is true.

Before dispatch, the chair freezes one immutable snapshot containing:

- `taskId`, revision/hash, scope, build, platform, and available capabilities;
- links to the local verification evidence and the exact artifact under review;
- the authorized total/per-seat/tool/wall-clock budgets and the selected route.

The artifact manifest is content-addressed. Every reviewed file, build, media asset, external snapshot, and declared continuity/reference corpus entry records a stable locator plus SHA-256, immutable version, or archived-copy locator. A mutable URL or working-tree path without version evidence is not an immutable artifact.

Every permitted delta wave freezes a new immutable snapshot with the current revision/hash, exact artifact links, refreshed verification-evidence links, and a `parentSnapshot` reference. Never reuse a pre-repair snapshot after its evidence has been invalidated.

Critics are read-only. They must not change `tasks.md`, smoke evidence, guardrails, closeout, runtime state, or the reviewed artifact. A critique comment can never be represented as passing smoke evidence.

When a game or interactive route must test persistence, progression, first-run state, or destructive recovery, give each critic a disposable isolated runtime profile, save namespace, or equivalent snapshot. Restore or discard it when the route ends. If isolation is unavailable, record the affected coverage as `unknown` and do not mark that route passed.

## Artifact Routing

Choose seats dynamically from the artifact modalities, user journey, audience, acceptance criteria, failure cost, available tools, and observed risk; never dispatch a fixed roster merely because its titles sound relevant. Give every seat one non-overlapping failure-hunting responsibility and a declared non-goal. Split mixed deliverables into independent lanes and give each lane its own evidence locator.

The machine record lists every selected lane with `id`, `kind`, `required`, assigned `seatId`, `evidenceLocator`, and `coverageStatus` (`covered`, `unknown`, or `not_applicable`). `unknown` and `not_applicable` require a capability or applicability reason. Every artifact-manifest entry links to a lane. The route outcome is `passed`, `limited`, or `blocked`; any required lane that is not `covered` prevents `passed`. A replacement critic preserves the seat count but never launders an unobserved modality into covered evidence.

| Artifact lane | `critic_lite` | `critic_full` minimum seats |
| --- | --- | --- |
| game / interactive | journey or player review | independent journey/player; visual/UX/accessibility; audio/feel when capability exists; evidence arbiter |
| visual / audio | perceptual craft review | perceptual craft plus accessibility/context and evidence arbiter |
| article / nonfiction | clarity/structure or fact-evidence review | dynamically select clarity, structure, fact evidence, and audience-fit seats; evidence arbiter |
| fiction / dialogue | voice/continuity or pacing review | dynamically select voice, continuity, pacing, and reader-experience seats; evidence arbiter |
| UI / app | task-flow and UX review | task-flow, visual/UX/accessibility, failure-state review, and evidence arbiter |
| CLI / API / library | integrator or failure-path review | dynamically select integration, misuse/security, reliability/operations, performance/cost, and evidence-arbiter seats |
| non-perceptual | normally `skip` with reason | when risk makes critique valuable, dynamically select architecture, security, reliability, maintainability, or cost seats plus evidence arbitration |

For a full game route, its game lane records journey coverage for first launch, onboarding, core loop, failure/retry, settings, persistence, progression, and ending/exit. Each checkpoint is `covered`, `unknown`, or `not_applicable`, with execution evidence for covered checkpoints and a reason otherwise. Any unknown required checkpoint makes the outcome `limited` or `blocked`, never `passed`. Audio/feel is required only when the available capabilities can actually inspect it; otherwise the chair records the capability gap as an unknown and replaces that seat with another independent applicable critic such as systems/fun, balance/pacing, reliability/persistence, or narrative/continuity. Capability loss never reduces Full below three critic subagents plus the separate evidence arbiter. Article and dialogue routes are dynamic: choose only the relevant clarity, structure, fact evidence, voice, continuity, pacing, or audience seats. Fictional world facts use the declared continuity corpus; external factual claims require source support rather than invented certainty.

## Independent Waves and Findings

All critics receive the same immutable snapshot and submit initial drafts without seeing one another. The initial review phase may use blind sequential batches when capacity cannot host the chair, three critics, and the arbiter concurrently. Close each finished critic seat and seal its draft; only after every critic draft is sealed may the separate arbiter read them. The arbiter is not counted as a critic, and slot limits never reduce the required seat count. The chair then deduplicates findings, preserves material dissent, and checks each claim against capabilities and evidence. Do not manufacture an overall score.

At intake, the chair normalizes UTF-8 category, root-cause summary, and primary stable locator, hashes that tuple with SHA-256, and assigns `CACC-<taskId>-<categorySlug>-<hash8>-<ordinal>`. Use the ordinal only to resolve a real collision. A repaired finding and its delta-wave updates preserve that ID through anchor movement; splits use `parentId`, merges use `replacedBy`, and genuinely new root causes receive new IDs. Every finding includes:

`severity`, `category`, `observation`, `evidence locator`, `repro-or-read-path`, `impact`, `confidence`, `unknown`, `recommendation`, `criticProposedDisposition`, and `chairFinalDisposition`.

Mark subjective preferences as preferences rather than defects. A critic who observes no issue must state the reviewed scope and limits; silence is not clean evidence.

## Repair Loop and Completion

Allow at most an initial wave and one delta wave. Do not run a loop "until clean." Apply only verified, in-scope repairs; repairing a finding invalidates affected evidence, so rerun the relevant local verification before disposition. When a repair changes code, run only the affected focused CodeRabbit review within its separate quota before the critic delta wave. The delta wave reviews only changed areas and unresolved material findings.

Severity controls disposition: unresolved `Critical` findings block `Done`, a shipped release, and clean Closeout and cannot be waived; a blocked/not-shipped checkpoint may only record the unresolved state. `High` findings must be fixed or explicitly accepted by a human. `Medium` and `Low` findings require a chair-final `fixed`, `rejected-with-counterevidence`, or `deferred`; `accepted` is allowed only with the same human-acceptance record. Human acceptance records the approver identity, approval time, task and finding IDs, bounded scope, reason, expiry, and reopen trigger. Agents cannot accept risk for the user. tasks.md remains the only lifecycle truth: critics and runtime agents never update its status. A task reaches `Done` only after recorded smoke verification and every critic finding has a documented disposition; the council itself is advisory release-quality evidence.

## Chair Record

Write the derived/advisory record to `output/mission-center-critique/<taskId>-<snapshotId>.json` and validate it with `scripts/critic_contract.py`; it never becomes a lifecycle source or HUD entity. Record the route or skip reason, immutable snapshot chain, content-addressed artifact manifest, authorization/budgets, lanes/seats/capability gaps, stable finding IDs and dissent, critic-proposed and chair-final dispositions, repairs, invalidated-and-rerun verification, human approver identity/time when applicable, and residual risks. Keep it available to Closeout and to any focused CodeRabbit re-review triggered by critic-driven code repairs, without treating it as smoke-test output.
