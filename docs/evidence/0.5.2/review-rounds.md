# Independent review rounds and verification: 0.5.2 partial checkpoint

This is an implementation/audit checkpoint, **not a complete or approved 0.5.2 release**. The A/B/C/D scope and known P1 baseline defects remain tracked in [the upgrade report](../../upgrade-0.5.2.md). No GitHub Actions/CI is authorized; every pushed commit carries `[skip ci]`.

## Round 1

Independent reviewer: `chatgpt-codex-connector[bot]`, review `5185858803`, source `3fba99f91f1b940e9b74be81a6f656fab4784fa5`.

Two P2 findings: native/oracle working-set policy mismatch and an unbounded test-child output spool. Source fixes were committed at `73d3ddbd0b6895edc08d3beff08c85531801d87b`. Twenty targeted Python tests passed; the log is [targeted-python-tests.txt](targeted-python-tests.txt). This did not validate a new Rust binary.

## Round 2

Independent reviewer: `chatgpt-codex-connector[bot]`, review `5185941873`, source `73d3ddbd0b6895edc08d3beff08c85531801d87b`.

- [P2: native task-ID dependency parsing](https://github.com/Gale0418/Codex-Mission-Center/pull/22#discussion_r3995718099): the compatibility selector's historical regex skipped valid IDs such as T1/T2 that the Rust comma-separated parser accepts. The selector now uses comma-separated complete IDs. The historical helper remains available to existing non-selector callers, whose semantics were not silently changed.
- [P2: migrate the existing ordering regression](https://github.com/Gale0418/Codex-Mission-Center/pull/22#discussion_r3995718102): the reviewer reported running `python -m unittest tests.test_mission_maintenance -v`: 39 tests, one failure in the old Blocked-first expectation. The existing regression now asserts the approved In Progress anchor policy; no test was deleted or weakened into a skip.

Additional local review hardened priority parsing against Python's huge-integer conversion limit while matching native u32 bounds/ASCII parsing, and deferred sorting Ready rows until that category is actually needed.

## Actual local verification of the round-2 fixes

Environment: Linux, Python 3.13.5.

```sh
python -m unittest discover -s tests -p 'test_*_052.py' -v
```

**23 tests passed, exit 0.** Initial run: 4.228 seconds; subsequent verified-source rerun: 3.944 seconds. Thirteen test the real Python selection implementation, nine test bounded child execution/output cleanup, and one rejects a malformed check-status envelope. Added cases cover T1/T2 dependencies, comma-separated non-MC identifiers, native u32 overflow and very long zero/nine prefixes.

The changed existing `test_mission_maintenance.py` was reconstructed byte-for-byte from its original GitHub blob (original SHA `194bba12e82ede15970b99e720a51b726fdc7512`), then only the relevant test name and expected ordering were changed. The updated test file compiles syntactically. Its affected test method was also executed in isolation with the real selector and passed. **This isolated test is not the full 39-test module or its dependency integration; the reviewer must re-run that module after this fix.**

## Round 3

Independent reviewer: `chatgpt-codex-connector[bot]`, review `5185992534`, source `1b82f4f684f76df376100d922f9af9f5fea726de`.

- [P2: canonical `Dependencies` header fallback](https://github.com/Gale0418/Codex-Mission-Center/pull/22#discussion_r3995768497): Python now follows the Rust parser's precedence—use `Depends on` when present, otherwise fall back to `Dependencies`—then parses complete comma-separated task IDs.
- [P2: require successful resume exit](https://github.com/Gale0418/Codex-Mission-Center/pull/22#discussion_r3995768501): the black-box probe now rejects a nonzero `resume` exit even if a malformed candidate emits plausible content.
- [P2: enforce the shared 16 KiB resume budget](https://github.com/Gale0418/Codex-Mission-Center/pull/22#discussion_r3995768502): the probe now verifies UTF-8 aggregate content bytes, exact declared `bytes`, and `0 <= bytes <= maxBytes <= 16384`.

Fix commits:

- `43650dfc295bddcda6120cdccca63624011558e2` — canonical dependency header fallback.
- `8b97f34750ba95f81d6ba8004f544270870b1917` — successful-exit and byte-budget resume contract.
- `7e2f18ad409847f812ba1bcd47d3a7140bdc4191` — selector regressions.
- `85518edc5d4e7440ed903ab5d3f25cce98764872` — resume-probe regressions.

## Actual local verification of the round-3 fixes

Environment: Linux, Python 3.13.5.

```sh
python -m py_compile skills/mission-center/scripts/common/working_set.py \
  tools/bounded_process.py tools/verify_upgrade_052.py \
  tests/test_working_set_052.py tests/test_bounded_process_052.py
python -m unittest discover -s tests -p 'test_*_052.py' -v
```

**28 tests passed, exit 0, in 3.549 seconds.** New cases cover the `Dependencies` alias, `Depends on` precedence, nonzero resume exit, UTF-8 accounting, false byte declarations, oversized content, and an overlarge `maxBytes`. Full output and executed-source SHA-256 values are in [round3-python-tests.txt](round3-python-tests.txt).

These tests validate the Python compatibility policy and development harness only. They do **not** validate the Rust source, full repository suite, Windows, release artifacts, or a production operation.

## Required next review and release gate

Request a fresh independent review of the latest commit using:

> 不要相信前一輪結論，重新從正確性、回歸風險、效能、安全、資源使用與可維護性挑毛病，按照Mission Center標出待修優先度，只有真的沒有值得修的 P2 以上問題才准通過。

A clean review of this partial diff does **not** close the known P1 baseline issues or certify the unfinished A/B/C/D upgrade. Native compilation, formatting, clippy, Rust integration/differential tests and complete implementation remain required. Keep the PR draft and main unchanged.
