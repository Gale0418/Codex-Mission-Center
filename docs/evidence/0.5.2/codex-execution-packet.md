# Codex execution packet — Mission Center 0.5.2

> **This file is implementation guidance, not a second task/lifecycle store and not a completion claim.** `MissionCenter/tasks.md` remains the only task lifecycle truth.

## Remote state and immutable constraints

- Repository: `Gale0418/Codex-Mission-Center`
- Work branch: `upgrade/0.5.2-executive-memory-20260912`
- Draft PR: `#22`
- Baseline `main`: `22a5186150e40f5a52ccfe2d08feba806f42108d`
- Source checkpoint inspected for this packet: `44a5bbcfef76a4069081a0911a20bfbc6451be14`
- Never modify or merge `main`; keep PR #22 draft until the operator separately approves release.
- Never dispatch, rerun, or enable GitHub Actions/CI. Every commit must already contain `[skip ci]` before push.
- Push incremental source/test/documentation checkpoints to this branch. Do not leave the only implementation or evidence in a Codex sandbox.
- Formal runtime remains Rust. Python is compatibility/oracle/test tooling only, never a production fallback.
- Preserve unrelated user changes; no force-push.
- No live deployment, migration, payment, mail, credential use, hosted service, vector database, or background model call.
- Missing/unavailable verification is `unknown` or `unverified`, never `pass`.

## Confirmed native defects at the source checkpoint

These were re-read from the actual Rust entry point, not inferred from old binaries.

1. **A1 / Resume is not actionable.** `rust/mission-center-cli/src/main.rs`, `run(...): "resume"` only returns route/freshness/ledger-existence plus `actionableHandoff:false`. It does not return the documented bounded `brief`, `workingSet`, `activeCriticalLessons`, active `snapshot`, `handoff`, or `readNext` packet.
2. **A2 / Reconcile treats existence as success.** The current `reconcile` branch marks ledger, progress, closeout and the evidence directory as `pass` based on existence. It does not distinguish schema validity, causal consistency, revision freshness, supersession/conflict, or operational readiness.
3. **A3 / Doctor severity can regress.** A missing legacy passport assigns `unknown` even after an earlier passport error assigned `error`; task order can therefore weaken the aggregate result.
4. Existing 0.5.1 black-box evidence still reports one of seven acceptance probes passing and six failing. It is baseline evidence only, not a test of current source.

## Implementation order

### Phase A3 — monotonic Doctor aggregation

Do this first because it is small and independently testable.

- Introduce one explicit severity join/rank: `pass < unknown < error`.
- Aggregate every Done task through that join; no later task may lower the aggregate.
- Preserve all per-task details, including both missing legacy passport warnings and validation errors.
- Add observable CLI regressions with the same two Done tasks in both orders:
  - invalid passport then missing passport;
  - missing passport then invalid passport.
- Both must return the same envelope/status and preserve the error.

### Phase A1 — complete native Rust resume

Use the native workspace APIs, especially `MissionWorkspace::handoff_json`; do not shell out to Python.

Required contract:

- Read-only and deterministic for injected `--date`.
- One shared **16 KiB UTF-8 content budget** across selected hot content and its required bounded routing metadata.
- Prioritize in this order:
  1. valid actionable handoff/current task context;
  2. `brief.md`;
  3. `working-set.md`;
  4. active portion of `critical-lessons.md` only, excluding resolved history;
  5. active `snapshot.md` only.
- Return explicit `content` fields: `handoff`, `brief`, `workingSet`, `activeCriticalLessons`, `snapshot`.
- Return `includedBytes`, aggregate `bytes`, `maxBytes`, `truncated`, and `readNext`.
- Truncate only at valid UTF-8 boundaries; never split a code point.
- Parse the status envelope structurally with `serde_json`; do not infer freshness through substring matching.
- File existence is not readiness:
  - corrupt/oversized ledger => `ledgerStatus: corrupt`, no partially trusted handoff, canonical fallback/read-next guidance;
  - no ledger => `missing`, not an error and not actionable;
  - valid ledger with no current actionable pulse => valid but `actionableHandoff:false`;
  - stale derived views => explicit fallback/read-next, not fabricated current context.
- Canonical snapshot corruption remains fail-closed. Disposable derived-view corruption may be routed to canonical fallback with an explicit reason.
- No task mutation, no status transition, no sync, and no implicit writes.

Required tests include clean/missing/corrupt ledger, active/inactive snapshot, multibyte truncation, aggregate 16 KiB bound including metadata, smaller remaining budget after handoff, stale derived views, and proof that `tasks.md` bytes do not change.

### Phase A2 — evidence-aware reconcile

Keep install/register/publish transaction reconciliation semantics intact. For the workspace reconcile command, emit independent checks with status from:

`pass | unknown | stale | conflict | corrupt`

- **Ledger:** bounded parse, schema, duplicate IDs, causal parent existence/order/task identity, timestamps, canonical-task binding. Existence alone is never pass.
- **Progress/derived views:** parse expected managed markers/fields, verify source fingerprints and date/revision freshness. A legacy unmarked file may be unknown, not pass.
- **Closeout:** validate schema/required fields, cycle/timestamp, source fingerprint and any immutable archive relationship. Missing evidence is unknown; malformed is corrupt; mismatched source is stale/conflict as appropriate.
- **Evidence envelopes:** reuse the existing evidence-envelope validation semantics for `scopeDigest`, `supersedes`, stale/corrupt/conflict and bounded reads. An empty directory is unknown, not pass.
- Overall severity is the maximum independent check severity; order-independent.
- Read-only: reconcile must never repair or transition anything.

Regress corrupt ledger, empty evidence directory, malformed envelope, stale/superseded envelope, conflicting envelopes, stale closeout, and a fully valid positive fixture.

### Phase B — minimal contextual recall and explicit preflight

Do not create a second memory database. Add only a bounded inspectable manifest/index referencing existing `critical-lessons.md`, `decisions.md`, and incident files.

- Structured context keys: workspace/project, task, component, phase/operation, optional version/scope digest.
- Initial explicit boundaries: `resume`, `enter-review`, `before-deploy`, `before-migration`, `after-repeated-failure`.
- Every returned card states why it triggered, source path, applicable scope, validity/supersession state, and the current verification still required.
- Validate schema/version, IDs, duplicates, reference cycles, source digests, path traversal/reparse/symlink, missing/corrupt sources, count and byte limits.
- Source text is untrusted data; it cannot override guardrails or execute commands.
- Superseded/version-incompatible cards cannot become active prescriptions. Unknown coverage remains explicit.
- Preflight is an explicit Rust read-only command/hook route. Do not claim global shell/tool interception; `UserPromptSubmit` is not a universal pre-tool API.
- Avoid keyword accidents: generic text containing `worker` must not trigger Cloudflare deployment history.
- During critical preflight suppress unrelated advisory noise, never safety-critical information.

### Phase C — canonical commitment closure

- Derive requirement gaps from canonical task fields and current evidence. No new promise/todo truth store.
- Report each approved requirement as `satisfied | failed | missing | stale | unknown` with evidence pointer and reason.
- Read-only observers never auto-transition tasks or overwrite canonical `Next action` with pulse `executionNextAction`.
- Run overdue/gap checks only at explicit resume/checkpoint/operation boundaries; no daemon claims.
- Preserve the already-reviewed bounded working-set anchor policy and Rust/Python oracle parity.

### Phase D — interrupted external operations and research handoff

- Reuse receipts, locks, fencing and history.
- Add an explicit bounded operation-result record/reconcile command with at least `pending | confirmed | failed | unknown`.
- After ambiguous interruption, replay is forbidden until supplied current evidence is reconciled.
- Never claim exactly-once external side effects.
- Use a fake adapter only in tests; no real provider call.
- Extend Research Portfolio/Shift-Loss with a small source-backed findings exchange: provenance, hypothesis versus verified fact, expiry/supersession, counterexample and next distinguishing test. No automatic agent dispatch.

### Release hygiene

- Remove the trailing `ABC` permission-test marker from `README.md`.
- Update version metadata, help, English and Traditional Chinese docs and schemas consistently only after implementation is real.
- Do not copy 0.5.1 checksums and label them 0.5.2.
- Until new binaries are built and verified, label the branch a **0.5.2 source candidate**, not stable/frozen release.

## Required local verification

Run offline/local commands where the environment supports them and record exact exit codes, counts, skips and tool versions in `docs/upgrade-0.5.2.md` or a linked evidence report.

```sh
cd rust
cargo fmt --all -- --check
cargo test --workspace --offline
cargo clippy --workspace --all-targets --offline -- -D warnings
cd ..
python -m unittest discover -s tests -p 'test_*.py' -v
python -m py_compile tools/verify_upgrade_052.py tools/bounded_process.py \
  skills/mission-center/scripts/common/working_set.py
```

Also run the 0.5.2 black-box harness against the newly built candidate binary, not the old 0.5.1 baseline, and preserve its JSON report.

## Review loop / acceptance gate

After each implementation checkpoint, request a fresh independent reviewer using exactly:

> 不要相信前一輪結論，重新從正確性、回歸風險、效能、安全、資源使用與可維護性挑毛病，按照Mission Center標出待修優先度，只有真的沒有值得修的 P2 以上問題才准通過。

Fix every worthwhile P0/P1/P2 finding and repeat. A clean review of one slice does not certify unfinished slices. Final acceptance requires:

- all A/B/C/D work implemented or explicitly removed from the approved scope by the operator;
- available local checks passing with preserved evidence;
- unavailable platform/toolchain checks explicitly unverified;
- no worthwhile open P2+ finding in the final independent review;
- all commits remotely present on the work branch, no Actions run, PR still draft, `main` unchanged.
