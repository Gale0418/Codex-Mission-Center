# Codex implementation handoff — Mission Center 0.5.2

This document is an executable handoff for the remaining 0.5.2 work. It is not a release claim.

## Immutable delivery constraints

- Work only on `upgrade/0.5.2-executive-memory-20260912` and draft PR #22.
- Never modify, merge, or retarget `main`; never enable auto-merge.
- Do not dispatch, rerun, or modify GitHub Actions/CI. Every commit must contain `[skip ci]` before it is pushed.
- Run local/offline checks where tools exist and record commands, exit codes, test counts, skips, unavailable checks, and pushed SHAs.
- Push incremental source/test/docs checkpoints. Do not leave the only copy in a Codex sandbox.
- Preserve unrelated changes. No force push.
- `MissionCenter/tasks.md` remains the only lifecycle/order truth. Read-only observers must not auto-transition tasks.
- The Rust runtime is formal. Python is an oracle/development harness only, never a runtime fallback.
- No hosted service, daemon, vector database, background model calls, Kubernetes/Temporal/Flink/Drools, live deployment, migration, payment, mail, credential, or provider operation.

## Already implemented on this branch

- Bounded working-set policy reserves current In Progress work, urgent P0 work, direct dependencies, Review/Blocked/Ready work, deduplicates, and stays capped at six.
- Python compatibility policy follows native `Depends on` / `Dependencies` header precedence and complete comma-separated task IDs.
- The offline candidate runner bounds stdout/stderr and process lifetime on POSIX; Windows fails closed.
- The black-box resume probe requires exit code 0 and verifies exact UTF-8 aggregate content within a shared 16 KiB budget.
- Independent review rounds and actual Python evidence are in `docs/evidence/0.5.2/`.

Treat all of those as code to re-verify, not assumptions.

## A — Repair the formal Rust contracts first

### A1. Native `resume` content contract

Current defect: `rust/mission-center-cli/src/main.rs`, the `"resume"` match arm, reports routing/freshness and `actionableHandoff: false` but does not return the documented bounded context.

Implement the public Rust envelope with at least:

```json
{
  "route": "resume",
  "sourceFresh": true,
  "dateFresh": true,
  "staleReasons": [],
  "filesRead": [],
  "content": {
    "brief": "...",
    "workingSet": "...",
    "activeCriticalLessons": "...",
    "snapshot": null,
    "handoff": null
  },
  "ledgerStatus": "missing|ready|corrupt",
  "ledgerError": null,
  "bytes": 0,
  "maxBytes": 16384,
  "truncated": false,
  "readNext": [],
  "canonicalFallback": false,
  "fallbackReason": null
}
```

Requirements:

- Reuse native `MissionWorkspace::handoff_json`; do not reimplement a competing pulse ledger parser in the CLI.
- Add a bounded workspace helper if needed so CLI orchestration is small and testable.
- Apply one shared maximum of 16 KiB to **all included string content and bounded routing metadata**. Count UTF-8 bytes, never split a code point, and make truncation/read-next explicit.
- Priority: valid handoff/current task and approved constraints, then brief, working set, active critical lessons, active snapshot. Do not silently consume the whole budget with one low-priority section.
- Read only named, bounded files. Reject traversal/symlinks through existing workspace guards.
- A present execution ledger is not `ready` unless its complete bounded schema/causal checks pass. Corrupt input must not expose partial evidence or become an all-clear.
- Stale/corrupt derived data gets an explicit canonical fallback route; absence of evidence remains unknown.
- `resume` remains read-only and must not mutate `tasks.md` or other canonical lifecycle files.
- Support a bounded `--max-bytes` override capped at 16384, or document and test the fixed cap consistently.

Update observable CLI integration/differential tests, not source-string assertions. Include multilingual UTF-8 truncation, stale views, missing/corrupt ledger, active snapshot, tiny budget, and canonical task immutability.

### A2. Workspace `reconcile`

Current defect: the CLI marks ledger/progress/closeout/evidence as pass by existence or directory presence.

Replace existence-only checks with explicit dimensions:

- existence;
- readable/bounded UTF-8 or JSON schema;
- causal consistency / revision or source-fingerprint freshness where applicable;
- conflict/supersession state;
- operation readiness.

Requirements:

- Reuse the production execution-ledger parser and existing evidence-envelope validation. Do not create a weaker second parser.
- A malformed ledger is `corrupt/error`; an empty evidence directory is `unknown/empty`, never pass.
- Validate evidence-envelope `scopeDigest`, revision/source freshness, supersedes links, duplicate/conflicting claims, corrupt files, and stale artifacts using the existing policy implementation.
- Preserve the separate native install/register/publish transaction reconciliation paths.
- Keep top-level workspace reconcile read-only and deterministic.
- Overall severity must be monotonic and order independent: pass < unknown < stale < conflict < corrupt/error.

Add black-box tests for corrupt ledger, forward/cross-task parent, empty evidence directory, malformed envelope, stale/superseded evidence, conflicting evidence, and valid evidence.

### A3. Doctor Completion Passport aggregation

Current defect: a later missing passport assigns `unknown` and can overwrite an earlier `error`.

- Implement one explicit severity combiner; do not mutate a string ad hoc.
- Preserve legacy missing-passport warnings as `unknown` only when no error exists.
- Result and exit code must be independent of canonical task row order.
- Add both permutations: corrupt then missing, and missing then corrupt.

## B — Minimal contextual recall and explicit preflight

Use existing `critical-lessons.md`, decisions, incidents, guardrails, and canonical tasks as source content. A small bounded manifest may reference them; it must not duplicate them as another memory truth.

Start with explicit contexts:

- `resume`
- `enter-review`
- `before-deploy`
- `before-migration`
- `after-repeated-failure`

Each returned card must contain:

- stable ID and schema version;
- why it triggered;
- structured scope: workspace/project, optional task, component, phase/operation, optional version/scope digest;
- source locator and source digest;
- active/superseded/incompatible/recheck-required validity;
- required current verification;
- advisory content treated as untrusted data, never executable authority.

Validation must reject duplicates, cycles, traversal/symlinks, missing/corrupt sources, bad digests, unsupported schema/version, excessive card count/size, conflicting active rules, and secret-like content. Superseded or incompatible material must not become an active prescription. Preserve a useful `not-covered/unknown` result.

Expose explicit read-only Rust commands or documented subcommands for context and preflight. Do **not** claim UserPromptSubmit is a global pre-tool interception API and do not claim every shell command is guarded. Required safety checks fail closed; advisory absence is not approval. No implicit side effects or permission bypass.

Use the same shared resume budget when context cards are included. Tests must distinguish actual deploy/migration context from generic text such as a task mentioning a `worker`.

## C — Canonical-task commitment closure

Add a read-only commitment-gap report derived from canonical task requirements and current evidence. Do not add another promise/TODO database.

Per requirement report one of: `satisfied`, `failed`, `missing`, `stale`, `unknown`, with source/evidence references and the next distinguishing verification. Observers must never auto-transition tasks, overwrite canonical `Next action`, or treat execution-pulse `executionNextAction` as lifecycle truth.

Keep overdue checks explicit at resume/checkpoint/preflight boundaries; no daemon. During critical preflight suppress unrelated advisory noise, never safety-critical information.

Regress six unrelated blockers plus current work, deterministic ties, stale evidence, missing evidence, and a read-only check that leaves `tasks.md` byte-identical.

## D — Safe long-run continuity and bounded research exchange

### D1. External-operation result reconciliation

Reuse existing receipts, locks, fencing, operation history, and recovery tombstones. Add a bounded explicit record/command with at least:

- `pending`
- `confirmed`
- `failed`
- `unknown`

On ambiguous interruption, require supplied current evidence to reconcile before replay. Never claim exactly-once external side effects. Fake adapters only in tests; no live production operation.

Validate operation ID, task/scope binding, receipt digest, evidence digest, transition legality, duplicate/conflicting records, restart recovery, size limits, traversal/symlink safety, and secret rejection. Read-only queries must not mutate task lifecycle.

### D2. Research findings exchange

Extend existing advisory Research Portfolio / Shift-Loss contracts with a small source-backed findings exchange, not an automatic dispatcher or new agent platform. Preserve opt-in budgets, provenance, hypotheses vs verified facts, expiry/supersession, counterexamples, and next distinguishing test. Add paired fixtures and deterministic tests.

## Release consistency and documentation

- Update command help, English and Traditional Chinese docs, schemas/templates, and source metadata consistently for a **0.5.2 source candidate**.
- Remove the leftover README `ABC` permission-test marker if it still exists.
- Never copy 0.5.1 binary checksums or artifacts and label them 0.5.2.
- Withhold stable/frozen-package/release claims until fresh binaries are locally built and verified.
- Keep PR draft until all required gates pass.

## Required local verification

Run what is available and record exact output:

```sh
cd rust
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test --workspace --all-targets --all-features
cd ..
python -m unittest discover -s tests -v
python tools/verify_upgrade_052.py --binary rust/target/debug/mission-center --report docs/evidence/0.5.2/candidate-probes.json
```

Also run the existing Rust/Python differential/oracle tests and focused regressions for every changed contract. Do not treat an unavailable tool, skipped platform, old 0.5.1 binary, or static inspection as a pass.

## Independent review loop

After implementation and pushes, request a separate reviewer with exactly:

> 不要相信前一輪結論，重新從正確性、回歸風險、效能、安全、資源使用與可維護性挑毛病，按照Mission Center標出待修優先度，只有真的沒有值得修的 P2 以上問題才准通過。

Fix all worthwhile P0/P1/P2 findings and re-review until the latest implemented head has no worthwhile P2+ findings. A clean review of a partial checkpoint is not a complete 0.5.2 release approval.
