# Mission Center 0.5.2 implementation checkpoint

**Status: partial implementation / blocked, NOT a stable 0.5.2 release.**

All work is confined to `upgrade/0.5.2-executive-memory-20260912` and draft [PR #22](https://github.com/Gale0418/Codex-Mission-Center/pull/22). Do not merge. Main remains at `22a5186150e40f5a52ccfe2d08feba806f42108d`. Every commit carries `[skip ci]`; no CI is authorized. Local/offline tests are authorized.

## User-authorized scope

| Slice | Scope | Current state |
| --- | --- | --- |
| A | Complete native Rust resume content, validate reconcile evidence, fix Doctor severity aggregation | Baseline failures reproduced; implementation still pending |
| B | Bounded source-backed contextual recall and explicit preflight | Pending |
| C | Canonical-task commitment gaps and attention selection | Working-set policy source change and tests added; native build/differential verification pending; commitment checks pending |
| D | Safe external-operation result reconciliation and bounded research handoff | Pending |
| Release | Consistent 0.5.2 metadata, bilingual docs, release artifacts | Withheld until implementation and verification complete; existing 0.5.1 binaries must not be relabeled |

Keep `MissionCenter/tasks.md` the only task lifecycle truth. No Python runtime fallback, hosted service, background model, second memory/task database, or live production operations are authorized by this implementation plan. Do not treat this progress report as a competing task store.

## GitHub read/write probe

A repository blob was written and read back successfully before the work branch was created. Probe: `mc-052-20260912-branch-only-no-ci`. Incremental source, tests and evidence are committed remotely rather than left only in a sandbox.

## Actual baseline experiment

The existing 0.5.1 Linux executable was downloaded from the **already completed** PR #20 artifact (`34611734926`, artifact `10268552260`), not built by a new Actions run. Its SHA-256 was checked against its existing manifest:

`3d116fdbed8b15cfa6425d69e835b54eff99d5b109f60f94c7a09fe8e14ab4a9`

Command, with `<baseline-binary>` referring to that verified local executable:

```sh
python tools/verify_upgrade_052.py --binary <baseline-binary> --report baseline.json
```

**Observed: exit 1; 1 of 7 probes passed, 6 failed.** These are synthetic workspace fixtures executed against a real old binary, not ten-day production results and not tests of the new Rust source. The report is [baseline-probes.json](evidence/0.5.2/baseline-probes.json). Re-running through the bounded process runner produced the same report.

| Priority | Reproduced finding | Status |
| --- | --- | --- |
| P1 | Malformed ledger is classified `ready` by resume and `pass` by reconcile | Open |
| P1 | An empty evidence directory is marked `pass` | Open |
| P1 | A missing Passport after a corrupt Passport can downgrade Doctor from error to pass; reversing row order changes the result | Open |
| P1 | Rust resume does not return the documented recovery content packet | Open |
| P2 | Six unrelated Blocked rows can displace the active task from the bounded view | Source repair added; native verification pending |

Read-only resume/reconcile preserved canonical tasks in the baseline fixture (the single passing probe).

## Implemented source checkpoint

The native derived working-set policy reserves the first canonical In Progress task, then eligible P0 tasks and direct anchor dependencies, then other active/review/blocked/ready work. It deduplicates IDs, excludes Done/Backlog and stays within six slots. This API still has no explicit selected-task-ID parameter. It changes a derived view, not canonical task order.

Seven Rust integration tests cover starvation, P0 precedence, dependencies, Done/Backlog exclusion, deduplication, deterministic ties, and a large urgent set. **They have not been compiled or run in this environment.**

The compatibility oracle now imports the same specified policy from `common/working_set.py`, preserving its existing function API so compatibility sync and Doctor no longer intentionally use the old Blocked-first policy. Full cross-language parity still needs the actual Rust build and existing differential suite.

The black-box test harness consumes stdout/stderr concurrently with per-stream limits and a process-group deadline instead of writing unlimited temporary output files. It is a **POSIX-only development runner**, not a security sandbox; it does not constrain arbitrary child filesystem/network activity. Windows fails closed until equivalent process-tree management is implemented.

The resume probe checks the documented nested `data.content` fields plus top-level `readNext`, not a newly invented flat schema.

## Independent review, round 1

Requested a separate Codex GitHub review with the exact user prompt:

> 不要相信前一輪結論，重新從正確性、回歸風險、效能、安全、資源使用與可維護性挑毛病，按照Mission Center標出待修優先度，只有真的沒有值得修的 P2 以上問題才准通過。

The bot independently reviewed `3fba99f91f1b940e9b74be81a6f656fab4784fa5` and returned two P2 findings, so **round 1 did not pass**:

1. Align Python compatibility/oracle selection with the new Rust anchor policy.
2. Enforce test-child output bounds while it runs, not only after it exits.

Both have source/test repairs prepared. A new independent review must verify those repairs; self-review is not independent approval. A clean review of this partial diff would not certify the unfinished 0.5.2 scope.

## Local verification of the review fixes

On Linux / Python 3.13.5:

```sh
python -m unittest discover -s tests -p 'test_*_052.py' -v
```

**20 targeted tests passed, exit 0, 4.176 seconds.** Ten exercise the real Python working-set selector, nine exercise process output/deadline cleanup, and one rejects a malformed check-status field. This is not the complete project test suite.

```sh
python -m py_compile tools/bounded_process.py tools/verify_upgrade_052.py \
  skills/mission-center/scripts/common/working_set.py \
  skills/mission-center/scripts/mission_maintenance.py
```

**Exit 0.** Syntax compilation is not proof that the entire compatibility application imports/runs or that Rust builds. The updated bounded harness then re-ran the baseline and retained the expected exit-1 result above.

## Blocking environment facts and remaining work

- This execution environment has no Rust compiler/Cargo/rustup and cannot clone or download a compiler through its restricted network. No new Rust binary, fmt/clippy result, full test result or cross-platform certification is claimed.
- A Codex Cloud implementation request was sent to PR #22, but the bot explicitly rejected it because no Codex Cloud environment exists for this repository. No remote implementation job is running.
- Independent GitHub **review** is separately functional (round 1 above). Review availability is not evidence that cloud implementation/build availability exists.
- Continue on this branch in a provisioned development environment, compile the Rust changes, update stale expectations, run full local/differential tests, implement A/B/remaining C/D, then repeat independent P0/P1/P2 review.
- Keep the PR draft and the release blocked until the whole acceptance scope and evidence are satisfied. Do not change guardrails or run production deployments, migrations, payments or mail to manufacture evidence.
