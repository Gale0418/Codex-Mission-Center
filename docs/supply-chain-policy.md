# Supply-chain policy

Mission Center core remains standard-library-only. The optional Runtime WebSocket dependency has two deliberately separate declarations:

- `requirements-runtime.txt` is the user-facing compatibility range (`websockets>=16.1,<17`).
- `requirements-runtime.lock` is the CI/release input. It selects the official platform-independent 16.1 wheel by URL and verifies its SHA-256 with pip `--require-hashes`.

The CI workflow pins every GitHub Action to a full 40-character commit SHA and leaves the reviewed major tag in a comment for maintainability. The current pins were resolved from the official `actions/checkout` and `actions/setup-python` v6 refs. Never guess or shorten a SHA; upgrades must resolve the official ref again and review the resulting commit before changing the workflow.

Release rules:

- keep the WebSocket path optional and unsupported for production while the upstream Codex app-server WebSocket surface remains experimental;
- install the CI/release dependency only from `requirements-runtime.lock` with `--require-hashes`;
- do not add runtime dependencies without focused compatibility, privacy, and license review;
- preserve the offline stdlib path as the release fallback.

Rust workspace rules:

- Rust CI installs the exact `1.98.1` toolchain with the minimal profile and
  `rustfmt`/`clippy`, then runs metadata, formatting, Clippy, and workspace
  tests with `--locked --offline` where dependency resolution is involved.
- When `rust/vendor/` and `rust/.cargo/config.toml` are present, CI requires
  `crates-io` to replace with `vendored-sources` and the source directory to
  be `vendor`. It accepts only the exact crates.io registry/sparse URLs or a
  workspace-local path, rejects Git, evil registries, and path escapes, and
  requires every registry package to have a 64-hex checksum matching its
  `.crate-checksum.json` or Cargo vendor checksum metadata.
  The accepted crates.io source IDs are
  `registry+https://github.com/rust-lang/crates.io-index`,
  `registry+https://index.crates.io/`, and
  `sparse+https://index.crates.io/`.
- Build output under `rust/target/` is ignored. The separate `rust-release`
  matrix builds one CLI binary for each of
  `windows-x86_64`, `linux-x86_64`, `macos-x86_64`, and `macos-aarch64` with
  the matching Rust target, checks the executable magic/architecture, and
  retains the binary beside a SHA-256 manifest for 14 days when the pinned
  target is available. It never downloads another job's artifact, invokes
  Python, or falls back to an unlocked or online build; rustup's pinned
  toolchain bootstrap is the only toolchain acquisition step.
- Release smoke is read-only: the compiled binary executes `runtime
  capability` and stdin-only `publish verify --version 0.5.1` against the
  checked-in fixture; `jq` parses the complete versioned envelopes and checks
  exit status, command/route, version, and selected platform. The macOS arm64
  lane records `smoke=unknown` when `uname -m` is not `arm64`; a cross-target
  build is not presented as a native smoke pass. If the arm target is absent,
  the lane records cross-build unavailable and smoke unknown before skipping
  release steps. The existing Rust matrix jobs
  still build the debug CLI and run `tests.test_rust_differential` with an
  absolute `MISSION_CENTER_RUST_BIN`; the differential suite is not skipped in
  CI.
- The single `test` aggregator requires both the Python matrix and every Rust
  matrix job to report success, so branch protection cannot pass while Rust
  checks are failing.
- `NOTICE.md` and the workspace MIT license remain part of the attribution
  surface. Any copied or adapted third-party content must retain its license
  and attribution there or beside the adapted file.

Point-in-time checks:

- The `serde_json` vendored status is a property of the checked-in tree at the
  time of review, not a permanent guarantee; re-check the vendor directory,
  Cargo.lock, and Cargo config after every dependency change.
- A known advisory scan status is also only a point-in-time result and cannot
  be treated as a permanent guarantee. Re-run the approved advisory scan when
  dependencies or the lockfile change.
