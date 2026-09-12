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

Verified source blob identities:

| File | Git blob SHA |
| --- | --- |
| `skills/mission-center/scripts/common/working_set.py` | `fcc61ba85e958be2cc45e07f556cfedbcd97ccf6` |
| `tests/test_working_set_052.py` | `613d20db8524b94380adc9568c0fdab1f36ff0a8` |
| `tests/test_mission_maintenance.py` | `3e3a693b50aa75955113bce733b9112f036877c2` |

All three identities were computed from the local bytes and matched the blobs uploaded to GitHub. No unexecuted Rust build, full-suite pass, cross-platform pass or independent approval is inferred from these Python tests.

## Required next review and release gate

Request a fresh independent review of the new commit using:

> 不要相信前一輪結論，重新從正確性、回歸風險、效能、安全、資源使用與可維護性挑毛病，按照Mission Center標出待修優先度，只有真的沒有值得修的 P2 以上問題才准通過。

A clean review of this partial diff does **not** close the known P1 baseline issues or certify the unfinished A/B/C/D upgrade. Native compilation, formatting, clippy, Rust integration/differential tests and complete implementation remain required. Keep the PR draft and main unchanged.
