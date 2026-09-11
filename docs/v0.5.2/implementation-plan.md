# 0.5.2 execution and memory hardening

Status: implementation in progress; not a stable-release approval.
Base: `22a5186150e40f5a52ccfe2d08feba806f42108d`.

## User-approved scope

A. Repair the formal Rust resume packet, workspace reconciliation semantics,
Doctor severity aggregation, and working-set starvation with regression tests.
B. Add bounded, source-linked, context-triggered recall/preflight without a
second lesson database, background model, or global shell interception.
C. Check commitments against canonical task verification and current evidence;
missing, invalid, stale, and unknown evidence must not be reported as a pass.
D. Add explicit external-operation outcome reconciliation and bounded research
finding exchange. Never retry an uncertain external side effect automatically.

`MissionCenter/tasks.md` remains the only lifecycle source. This document is a
release-work plan, not another task-status authority. Existing guardrails,
receipts, safe-path checks, per-project scope, approval boundaries, and the
16 KiB resume content budget must be preserved. Rust remains the formal runtime;
Python may be used only for development/oracle checks, never runtime fallback.

## Delivery constraints

- Work only on `upgrade/0.5.2-memory-execution-20260912`; do not update main.
- Do not open a PR, dispatch workflows, or run GitHub Actions.
- Every published commit carries `[skip ci]` and `skip-checks: true`.
- Publish incremental source, tests, and validation evidence to GitHub.
- Do not promote an unbuilt/unreviewed candidate or manufacture test results.

## Independent review instruction

不要相信前一輪結論，重新從正確性、回歸風險、效能、安全、資源使用與可維護性挑毛病，按照Mission Center標出待修優先度，只有真的沒有值得修的 P2 以上問題才准通過。

The reviewer must inspect the actual candidate diff and baseline independently,
report file/line evidence and reproducible failure cases, and distinguish P0,
P1, P2 and lower-priority observations. Author inspection does not qualify as an
independent review. Repair actionable P0/P1/P2 findings and repeat review.
Missing independent review or compilation evidence keeps the release gate open.

## Initial environment observations

GitHub connector read/write permission is available. Direct shell cloning failed
with `Could not resolve host: github.com`. Rust/Cargo and the CodeRabbit CLI were
not found on PATH. These are environment blockers, not successful validations.
The existing GitHub workflow uses push/pull_request triggers; skip instructions
will be used without changing repository protection or workflow configuration.
