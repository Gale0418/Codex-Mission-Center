# CodeRabbit Final Review Gate Design

## Goal

Add CodeRabbit as an optional, risk-based independent review gate near Mission Center closeout. CodeRabbit runs only after implementation and local verification are complete. It supplements tests and human judgment; it never replaces them.

## Non-Goals

- Do not run CodeRabbit during intake, research, planning, or routine edit loops.
- Do not require CodeRabbit for trivial, documentation-only, or deterministic low-risk changes.
- Do not upload secrets, generated artifacts, binary assets, caches, vendored code, or unrelated large files.
- Do not let CodeRabbit write Codex-managed plugin cache or automatically apply suggestions.

## Trigger Policy

Run the gate when the user requests it or when a task is large or high risk: cross-module behavior, security or privacy boundaries, release and publishing logic, migration, destructive operations, or broad user-facing workflows. Skip it for low-risk work and record the reason.

CodeRabbit is the final independent review step:

```text
Implement -> Local verification -> CodeRabbit review -> Validate findings -> Fix valid issues -> Focused re-review -> Closeout
```

## Consent And Scope

Before upload, confirm that the user has explicitly allowed the relevant code to be sent to CodeRabbit. Existing explicit consent for the same task is sufficient; do not ask repeatedly.

Inspect the diff before review. Prefer supported CLI scoping such as `--dir`, `--base-commit`, or `-t uncommitted`. Exclude binary images, generated files, caches, lockfiles, vendored dependencies, secrets, unrelated files, and large documents that do not need semantic review. Never invent an unsupported exclusion flag.

## Review Budget

- At most one full scoped review per task.
- At most one focused re-review of the small fix diff.
- Do not repeatedly poll or rerun to chase a clean badge.
- Real subagents remain separately approval-gated and are not required for this flow.

## Finding Handling

Parse CodeRabbit output as external review advice. For each issue:

1. Read the complete issue.
2. Reproduce or verify it against the current code and agreed architecture.
3. Reject incorrect, duplicate, out-of-scope, or unsafe advice with a technical reason.
4. Add a failing regression test before fixing a valid behavior issue.
5. Make the smallest safe fix and rerun local verification.

Never claim CodeRabbit passed when it failed, timed out, was unauthenticated, or hit a rate limit.

## Failure Policy

For ordinary risk-based reviews, CodeRabbit unavailability does not invalidate successful local verification. Record the exact failure and disclose that independent re-review did not complete.

For security-critical, destructive, or release-blocking work where independent review was explicitly required, stop and ask whether to wait, connect a CodeRabbit organization, or proceed without that evidence.

## Skill Integration

- Add `references/coderabbit-review-gate.md` as the detailed runbook.
- Route to it from `SKILL.md` after local verification and before closeout.
- Keep the core Skill concise and dependency-optional.
- Record `completed`, `skipped (reason)`, or `unavailable (exact error)` in Mission Center verification or decision notes.

## Validation

Contract tests must confirm the runbook includes final-only timing, risk triggers, explicit upload consent, supported scope controls, large-file exclusions, the one-plus-one review budget, technical verification of findings, TDD fixes, and truthful rate-limit handling.
