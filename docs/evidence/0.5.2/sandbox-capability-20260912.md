# 0.5.2 current sandbox capability boundary — 2026-09-12

This is execution evidence only, not release evidence.

## GitHub

- Connected GitHub repository read/write: **available**.
- Branch commits and read-back: **available**.
- Draft PR review requests: **available**.
- GitHub Actions/CI: **intentionally not invoked** per operator instruction.
- Branch workflow-run query after the latest harness fixes returned `total_count: 0`.

## Direct container/network

A direct clone was re-tested from the ChatGPT container:

```text
git clone --branch upgrade/0.5.2-executive-memory-20260912 --single-branch \
  https://github.com/Gale0418/Codex-Mission-Center.git /tmp/mc052
fatal: unable to access 'https://github.com/Gale0418/Codex-Mission-Center.git/':
Could not resolve host: github.com
```

Result: direct GitHub DNS/network access from the container is unavailable at this checkpoint. This prevents a safe full-checkout patch/build workflow here; it does **not** imply GitHub itself or the connector is unavailable.

## Local tools

Observed in the current container:

```text
Python 3.13.5
/usr/bin/unshare
```

`rustc` and `cargo` were not present on `PATH`.

Consequences:

- the Python bounded-runner design can be independently executed in a Linux environment that permits user/PID namespaces;
- this ChatGPT container cannot truthfully claim Rust formatting, compilation, clippy, workspace tests, a new candidate binary, or black-box verification against new Rust source;
- core Rust changes that require rewriting a large entry point without a compiler should be completed in an actual Codex/dev checkout using `docs/evidence/0.5.2/codex-final-handoff.md` rather than by pretending source inspection is a build result.

## Honesty gate

Unavailable verification remains `unverified`. Old 0.5.1 binary observations are baseline evidence only. A future Codex/dev run must execute the native commands documented in `codex-final-handoff.md` and preserve the resulting output/checksums before 0.5.2 can be called stable.
