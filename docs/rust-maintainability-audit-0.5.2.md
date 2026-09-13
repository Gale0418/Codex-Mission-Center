# Rust 0.5.2 maintainability audit

Date: 2026-09-13

This audit records structural and behavioral observations. It does not treat source
line counts as performance measurements or claim cross-platform behavior without
execution evidence.

## Boundary decisions

- `mission-center-core` remains the only parser and state model for canonical tasks.
- `mission-center-policy` owns versioned, bounded context and research contracts.
- `mission-center-workspace` owns safe workspace paths, operation records, locks, and
  external-operation state transitions.
- `mission-center-cli` composes read-only context, preflight, commitment, and evidence
  views into the stable JSON envelope; it does not become a second truth store.
- Python remains an oracle/test boundary and is not callable as a formal runtime
  fallback.

The 0.5.2 additions deliberately reuse these boundaries. No vector database, network
client, background daemon, workflow engine, or new third-party dependency was added.

## Observed structure

| Rust source | Lines | `clone()` calls | `serde_json::Value`/`Value::` refs | Functions |
| --- | ---: | ---: | ---: | ---: |
| `mission-center-workspace/src/lib.rs` | 6,319 | 60 | 8 | 203 |
| `mission-center-workspace/src/derived_views.rs` | 805 | 1 | 0 | 22 |
| `mission-center-cli/src/main.rs` | 6,134 | 34 | 97 | 153 |
| `mission-center-cli/src/contextual.rs` | 272 | 0 | 20 | 7 |
| `mission-center-publish/src/lib.rs` | 3,534 | 13 | 22 | 138 |
| `mission-center-policy/src/lib.rs` | 4,127 | 13 | 85 | 78 |
| `mission-center-runtime/src/lib.rs` | 3,033 | 36 | 21 | 129 |
| `mission-center-core/src/lib.rs` | 844 | 1 | 4 | 37 |

These regex counts are navigation proxies, not allocation or performance benchmarks.
The new contextual read/composition code has its own bounded CLI module; the external
operation writer remains inside the existing workspace transaction boundary. Further
module extraction should move one tested behavior at a time instead of producing a
release-only file shuffle.

## Safety and maintenance observations

- Context recall reads only manifest-named files beneath `MissionCenter/`, applies file,
  item, and output byte budgets, validates provenance digests and lifecycle metadata,
  and rejects traversal, URL-like, symlink, reparse, duplicate, and secret-like input.
- Preflight is read-only. Missing coverage is `unknown` or advisory; it is never treated
  as approval. Stale, incompatible, corrupt, or explicitly required missing context
  blocks the operation boundary.
- Commitment closure treats free-form `Verification` as one opaque requirement. This
  avoids a brittle natural-language grammar and keeps evidence reconciliation as the
  source of derived state.
- External reconciliation distinguishes local replay safety from external exactly-once
  delivery. Ambiguous interruption remains `unknown`; same ID with a changed payload is
  a conflict.
- Research findings extend the existing portfolio contract instead of introducing an
  agent-memory database. Old portfolios without findings remain valid.

## Residual limits

- Filesystem path checks reduce accidental and adversarial path substitution but cannot
  prove the absence of every operating-system-level TOCTOU race.
- External services remain outside the local transaction boundary. Reconciliation can
  validate receipts and evidence, not prove an unobservable side effect.
- Local macOS execution is not Windows, Linux, or macOS x86_64 evidence. The stable
  release therefore requires fresh four-platform GitHub artifacts from the exact merged
  revision.

## Verification record

- Rust 1.98.1 offline workspace/all-target/all-feature suite: 194 tests passed.
- Python 3.11 discovery: 508 tests passed; 20 capability-dependent tests skipped on
  macOS (Linux PID namespaces, PowerShell/Windows launchers, or optional `jsonschema`).
- `cargo fmt --all -- --check`, full-workspace Clippy with `-D warnings`, and
  `git diff --check`: passed locally.
- Independent review and GitHub four-platform run IDs are added only after those gates
  complete. An unavailable or unexecuted gate is never recorded as passing.
