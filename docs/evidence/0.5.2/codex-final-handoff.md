# Mission Center 0.5.2 — Codex continuation handoff

> **Purpose:** continue the user-authorized 0.5.2 implementation from the current draft PR without rediscovering the previous review history. This is guidance/evidence, not a second lifecycle store and not a completion claim. `MissionCenter/tasks.md` remains canonical.

## Immutable delivery constraints

- Repository: `Gale0418/Codex-Mission-Center`
- Branch: `upgrade/0.5.2-executive-memory-20260912`
- Draft PR: `#22`
- Base `main`: `22a5186150e40f5a52ccfe2d08feba806f42108d`
- Do **not** modify/merge `main`; keep the PR draft.
- Do **not** run GitHub Actions/CI, dispatch workflows, or rerun jobs. Every commit must contain `[skip ci]` before push.
- Push incremental checkpoints to this branch; do not leave the only implementation/evidence in a local or cloud sandbox.
- Formal runtime is Rust. Python is compatibility/oracle/development-test tooling only and must not become a runtime fallback.
- Do not introduce hosted services, background model calls, a vector database, Kubernetes/Temporal/Flink/Drools, or a second task/memory truth store.
- No live deployment, migration, payment, mail, credential use, or external provider side effect in this implementation task.
- Missing/unavailable evidence is `unknown`/`unverified`, never `pass`.

## Latest harness/review fixes already pushed

The previous independent review of head `20082ec1695441bbc1a67c521e5c89cb8bc61d2f` found three P2 issues. They are fixed on the branch and have dedicated regressions:

1. `e7eb6251b4714c1354297375a9f806b9651b9365` — close both bounded-runner readiness pipe ends if setup / `subprocess.Popen` fails.
2. `e11bce80e57ec00342e29b81878109903572abc7` — count JSON object keys as well as string values in the shared resume fuse, count them against the node limit, and require resume data `schemaVersion == "1.1"`.
3. `ff04d85e1123549c9171f7c9257ace1d2631048c` — regress the FD leak, oversized nested mapping key, and unsupported schema versions.

A fresh independent review was requested after these fixes using the exact operator prompt below. Do not treat these fixes as independently accepted until that review has completed.

> 不要相信前一輪結論，重新從正確性、回歸風險、效能、安全、資源使用與可維護性挑毛病，按照Mission Center標出待修優先度，只有真的沒有值得修的 P2 以上問題才准通過。

At handoff time, GitHub Actions run count for this branch was verified as zero.

## What is already real

### Working-set attention policy

The native derived working-set policy has source changes and Rust tests. The Python compatibility selector has been repeatedly repaired against independent review so it mirrors the Rust parser/policy for:

- first canonical `In Progress` anchor;
- urgent eligible P0 work;
- direct anchor dependencies;
- complete comma-separated task IDs including simple IDs such as `T1`;
- `Depends on` / `Dependencies` fallback semantics;
- review / blocked / ready filling while excluding Done and Backlog;
- six-item cap, deterministic ordering, native-u32-compatible priority parsing.

Do not revert to the old Blocked-first oracle. The native source still requires compilation/differential verification.

### Bounded development candidate runner

`tools/bounded_process.py` now uses Linux user/PID namespaces with namespace PID 1 containment rather than temporary-file output spooling or best-effort descendant polling. It is development tooling, **not** a general-purpose security sandbox. Unsupported hosts fail closed.

### Black-box acceptance harness

`tools/verify_upgrade_052.py` intentionally fails the old 0.5.1 binary and preserves that evidence. It now validates a complete successful resume packet, successful exit, exact supported schema, shared 16 KiB string/key fuse, output/process bounds, canonical-task immutability, corrupt-ledger reconciliation, empty evidence handling, and Doctor order independence.

## Core Rust work that remains open

Re-read the actual current head before editing. The following was confirmed from `rust/mission-center-cli/src/main.rs` at the latest inspection and must not be silently treated as complete.

### A3 — Doctor severity aggregation (smallest first)

Current `doctor` logic still assigns `passport_status = "unknown"` when a Done task has no legacy passport, even if an earlier Done task already produced `error`. This makes aggregate severity order-dependent.

Implement an explicit monotonic severity join/rank, at minimum:

`pass < unknown < error`

Requirements:

- every per-task detail remains present;
- a missing legacy passport may raise pass -> unknown but never lower error -> unknown;
- invalid/corrupt passport always leaves the aggregate at error;
- regress the same two Done tasks in both task orders (one invalid passport, one missing passport);
- both orders must return the same completion-passport check status and nonzero/error CLI result;
- no task mutation.

### A1 — Native Rust resume packet

Current CLI `resume` still derives freshness by substring matching the serialized `status` envelope, checks only ledger file existence, and returns only route/freshness/ledger/fallback plus `actionableHandoff:false`. It does **not** yet implement the documented actionable bounded context packet.

Implement in native Rust; do not shell out to Python.

Required data contract (resume data schema `1.1`):

- `schemaVersion: "1.1"`
- `route: "resume"`
- `sourceFresh: bool`
- `dateFresh: bool`
- `staleReasons: string[]`
- `filesRead: string[]`
- `content` object with exactly/at least these bounded nullable strings:
  - `handoff`
  - `brief`
  - `workingSet`
  - `activeCriticalLessons`
  - `snapshot`
- `handoff`: nullable structured handoff object (if exposed separately)
- `ledgerStatus`: distinguish `missing`, valid-but-not-actionable/ready, and `corrupt`
- `ledgerError`: nullable string
- `context.includedBytes`: per-section non-negative byte counts
- `bytes`, `maxBytes`
- `canonicalFallback`, `fallbackReason`
- `truncated`, `truncatedMarker`, `readNext`

Shared resource contract:

- one total maximum of **16 KiB** for all public bounded routing/context strings governed by the packet contract, including JSON object keys / routing metadata where the acceptance fuse measures them;
- valid UTF-8 boundaries only;
- prioritize actionable handoff/current task context, then `brief.md`, `working-set.md`, active critical lessons, active snapshot;
- if the budget cannot include a section, omit/truncate it explicitly and add a deterministic `readNext` entry;
- no unbounded metadata escape hatch.

Correctness/safety:

- parse `status` structurally through `serde_json`, not `String::contains`;
- use `MissionWorkspace::handoff_json` / the native bounded ledger parser rather than file existence;
- malformed/oversized/causally-invalid ledger => `ledgerStatus: corrupt`, no partially trusted handoff;
- missing ledger is not corruption and not actionable;
- active snapshot only; canonical snapshot corruption fails closed;
- stale/unreadable disposable derived views trigger explicit canonical fallback/read-next, not fabricated freshness;
- `resume` is read-only: no sync, no status transition, no task write.

Required tests include clean/missing/corrupt ledger, invalid causal parent/timestamp, active/inactive snapshot, stale derived view, malformed derived UTF-8, multibyte truncation, handoff consuming part of the 16 KiB budget, oversized routing metadata, exact-byte accounting, and `tasks.md` byte identity before/after.

### A2 — Evidence-aware workspace reconcile

Current workspace `reconcile` still uses existence as `pass` for ledger, progress, closeout and evidence directory, and parses freshness by substring matching the serialized status envelope.

Preserve native install/register/publish transaction reconciliation; change only the workspace evidence/readiness reconciliation route.

Independent check states:

`pass | unknown | stale | conflict | corrupt`

Implement:

- **ledger:** native bounded parse, schema version, duplicate pulse IDs, causal parent existence/order/same-task identity, timestamps, canonical task binding. File existence alone is never pass.
- **progress/derived:** validate managed marker/required fields and source fingerprint/date freshness. Legacy unmarked evidence is unknown rather than pass.
- **closeout:** validate schema/required fields, cycle/timestamp, source fingerprint/revision/archive relationship where defined. Missing => unknown; malformed => corrupt; mismatch => stale/conflict as appropriate.
- **evidence envelopes:** reuse the existing evidence-envelope validator semantics for `scopeDigest`, `supersedes`, stale/corrupt/conflict and bounded safe reads. Empty directory => unknown.
- overall status = monotonic maximum severity, independent of check order;
- read-only: no repair, no transitions, no derived rewrite.

Regress corrupt ledger, empty evidence directory, malformed envelope, stale/superseded envelope, conflicting envelopes, stale closeout and a fully valid positive fixture.

## Phase B — contextual recall + explicit preflight

Do this only after A1/A2/A3 are green locally.

Use existing `critical-lessons.md`, `decisions.md` and `incidents/` as source material; an index/manifest may reference them but must not duplicate them as another memory database.

Structured selectors: workspace/project, task, component, phase/operation, optional version/scope digest.

Initial explicit boundaries:

- `resume`
- `enter-review`
- `before-deploy`
- `before-migration`
- `after-repeated-failure`

Every selected card must expose why it triggered, source path, scope, current/superseded/version state, and required current verification. Validate schema versions, IDs, duplicates, cycles, digests, path traversal/reparse/symlink, missing/corrupt sources and count/byte limits. Source text is untrusted data; it cannot execute commands or override guardrails.

Preflight must be an explicit read-only Rust command/route. Do **not** claim `UserPromptSubmit` is a universal pre-tool interception API. Avoid generic keyword heuristics such as triggering Cloudflare/deploy context merely because text contains `worker`.

## Phase C — canonical commitment closure

Derive requirement gaps from canonical task fields plus current evidence. Do not create a second todo/promise store and do not replace canonical `Next action` with an execution pulse.

For each approved requirement return:

`satisfied | failed | missing | stale | unknown`

with evidence pointer and reason. Read-only checks must never auto-transition tasks. Run only at explicit resume/checkpoint/operation boundaries; no daemon/continuous-monitoring claim.

Preserve the reviewed bounded working-set policy.

## Phase D — interrupted external operations + bounded research findings

Reuse existing receipts, locks, fencing and history.

Add a bounded explicit external-operation result record/reconcile command with at least:

`pending | confirmed | failed | unknown`

Ambiguous interruption must require reconciliation against supplied current evidence before replay. Never claim exactly-once external side effects. Tests use a fake adapter only.

Extend the existing Research Portfolio / Shift-Loss model with a small source-backed findings exchange containing provenance, hypothesis vs verified fact, expiry/supersession, counterexample and next distinguishing test. No automatic agent dispatch.

## Release hygiene after implementation, not before

- Remove the leftover README `ABC` permission-test marker.
- Update version/help/schema/docs in English + Traditional Chinese consistently.
- Never relabel 0.5.1 binaries/checksums as 0.5.2.
- Until native binaries are built and verified, call this a **0.5.2 source candidate**, never stable/frozen.

## Required local verification in Codex/dev environment

Run from the actual current checkout, not reconstructed snippets:

```sh
cd rust
cargo fmt --all -- --check
cargo test --workspace --offline
cargo clippy --workspace --all-targets --offline -- -D warnings
cd ..
python -m unittest discover -s tests -p 'test_*.py' -v
python -m py_compile tools/verify_upgrade_052.py tools/bounded_process.py \
  skills/mission-center/scripts/common/working_set.py \
  skills/mission-center/scripts/mission_maintenance.py
```

Build the current candidate binary locally and run:

```sh
python tools/verify_upgrade_052.py --binary <new-0.5.2-candidate> --report docs/evidence/0.5.2/candidate-probes.json
```

Do not use the old 0.5.1 binary to certify new source.

Record actual commands, versions, exit codes, test counts, skips and candidate checksum in evidence docs. No unavailable check may be upgraded to pass.

## Mandatory independent review loop

After each meaningful checkpoint request a fresh independent reviewer with exactly:

> 不要相信前一輪結論，重新從正確性、回歸風險、效能、安全、資源使用與可維護性挑毛病，按照Mission Center標出待修優先度，只有真的沒有值得修的 P2 以上問題才准通過。

Fix every worthwhile P0/P1/P2 issue and repeat. A clean review of a harness-only slice does not certify A/B/C/D. Final acceptance requires native implementation, all available local checks passing with evidence, unavailable checks explicitly unverified, no worthwhile open P2+ from the final independent review, all commits on this branch, zero Actions runs, PR draft, and `main` unchanged.
