# Python oracle／compatibility boundary

This directory is the explicit compatibility boundary for the pre-Rust
Mission Center implementation. The source checkout keeps legacy Python
modules at their historical paths so differential and historical test oracles
remain reproducible; they are not formal plugin runtime inputs.

The Rust CLI is the only supported implementation for the packaged plugin.
The stable-package assembler must exclude both `scripts/` and Python files,
and must fail if a hook or plugin manifest invokes Python. Do not add new
production behavior to the Python oracle. Changes here are limited to parity
fixtures, historical replay, and migration diagnostics.

The source-checkout `scripts/install*` wrappers are compatibility publishers,
not formal installers. They require the explicit environment opt-in
`MISSION_CENTER_PYTHON_COMPAT=1`; without it they fail before locating Python
or writing anything. If the Rust binary/package is unavailable, use the
remediation in the release instructions or build/provide the verified package
out-of-band. These wrappers never compile, download, or silently substitute a
Python runtime for the formal package.

See `manifest.json` for the bounded list of retained oracle roots and the
formal-package exclusion rules.
