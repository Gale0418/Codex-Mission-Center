# Rust-only 0.5.1 preview

`.codex-plugin/release-preview.json` is the checked-in release contract for
the Rust-only migration preview. Its version is `0.5.1-rust.1`, while the
four-platform Rust binaries remain versioned against the `0.5.1` base release
inside `platform-manifest.json`.

This metadata is intentionally not a stable-release declaration and is not an
installation instruction. `installable: false` means the package is not yet a
supported marketplace install: the root plugin version, four-platform package,
and clean-checkout gate still have to converge. Deliberately
explicit `install --package` and `publish apply` commands can now materialize
a fully verified local package with an operation receipt; matching rollback
commands are available, and neither path downloads, compiles, or silently
falls back to Python. The selector is explicit for Windows x86_64, Linux
x86_64, macOS x86_64, and macOS arm64; an unavailable target must remain
unknown rather than being replaced by a download or a silent fallback.

Marketplace discovery is also a native, local transaction. After the verified
plugin tree has been materialized at `<marketplace>/plugins/mission-center`,
run `mission-center install register apply --plugin-root <absolute-plugin>
--marketplace-root <absolute-marketplace> --operation-id <id> --version 0.5.1-rust.1`.
The command atomically writes `.agents/plugins/marketplace.json`, emits a
bounded receipt, and supports exact replay, `register rollback --receipt`,
and `register reconcile --marketplace-root`; it never invokes the Codex CLI or
opens a browser.

After an interrupted apply/publish, run `install reconcile --root <absolute-package-parent>` (or the equivalent `publish reconcile`) to scan the bounded
transaction directory. Receipts are validated against their operation ID,
paths, digest and target phases; only `started` receipts are rolled back, while
committed/aborted receipts are reported as facts. Malformed, oversized or
unsafe receipts fail closed without additional writes.

The same native transaction scan is available as
`mission-center reconcile --transaction-root <absolute-package-parent>`;
without that flag, `mission-center reconcile --root <workspace>` retains its
read-only workspace reconciliation contract.

Canonical lifecycle transitions are now native as well. Use one operation per
step, for example
`mission-center transition MC-061 Review --operation-id <id> --timestamp
<RFC3339> --root <workspace>`. The Rust core rejects illegal jumps (including
`In Progress` directly to `Done`), rewrites only the selected Status cell, and
records an idempotent operation receipt.

The frozen package contract is `frozen-package-v1`: every selected binary is
verified with SHA-256 and the Rust verifier runs offline. Changes to the
preview version, platform list, checksum algorithm, or fallback policy must be
accompanied by release metadata tests and a focused Rust publish verification.
On Windows, `hooks/hooks.json` invokes `bin/mission-center.ps1`; this native
selector validates the local plugin and four-platform manifests plus the
Windows binary checksum before invoking the Rust executable. Missing,
mismatched, or unsupported inputs fail closed without an alternate runtime.

The stable-package assembler deliberately omits source-checkout `scripts/`
helpers and Python files from `skills/`; those remain compatibility/oracle
material under the explicit [`compat/python-oracle/`](../compat/python-oracle/)
boundary and are not formal plugin runtime inputs. It also omits the Python
`requirements-runtime.txt` dependency and this preview-only
`release-preview.json` marker. The staged package is asserted to contain
neither Python files, Python dependency manifest, preview-only release metadata,
compatibility boundary, nor a root `scripts/` tree before the Rust verifier runs.

The source-checkout `scripts/install*` wrappers are likewise compatibility
publishers only. They fail closed unless `MISSION_CENTER_PYTHON_COMPAT=1` is
set explicitly, and they never compile, download, or select a Python fallback
when a Rust package/binary is missing. Formal installation must use an already
built and locally verified Rust package; missing artifacts require explicit
remediation rather than an implicit migration.

The preview HUD hook is Rust-native: `hooks/hooks.json` invokes
`mission-center hook hud`, which manages one bounded loopback child per
workspace using a nonce-bearing control file, a 16 KiB startup receipt, health
checks, and a six-hour TTL. It never opens an external browser and reports a
sidebar intent as advisory host context; an intent is not evidence that the
Codex sidebar was presented.
