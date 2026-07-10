# Per-Project Mission Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a tested, per-project-only Mission Center with a single-workspace doctor, CI, fixture, dogfood workspace, and aligned documentation.

**Architecture:** A small `workspace_contract.py` module provides canonical filenames and lifecycle statuses. Existing bootstrap, normalize, sync, visual-state, and publish code remain the behavioral core; the new doctor composes their parsers and calculations without scanning beyond the requested workspace.

**Tech Stack:** Python 3 standard library, Markdown, `unittest`, GitHub Actions YAML.

## Global Constraints

- Operate only on the explicitly selected current workspace and its `./MissionCenter/`.
- `MissionCenter/tasks.md` is the only task lifecycle and ordering source.
- Do not add a global dashboard, registry, repository scan, background monitor, or cross-repository task merge.
- Preserve English and Traditional Chinese templates.
- Use test-first changes for executable behavior.

---

### Task 1: Canonical Workspace Contract

**Files:** Create `skills/mission-center/scripts/workspace_contract.py`; modify bootstrap and contract tests.

**Interfaces:** Export `REQUIRED_FILES` and `CANONICAL_STATUSES` tuples. Bootstrap consumes `REQUIRED_FILES` to guard template completeness.

- [ ] Add a failing test that compares English and Traditional Chinese bootstrap output with `REQUIRED_FILES`.
- [ ] Run the focused test and confirm the missing contract import fails.
- [ ] Add the contract module and bootstrap completeness check.
- [ ] Run the focused tests and confirm both languages pass.

### Task 2: Behavior Coverage For Existing Scripts

**Files:** Create focused bootstrap, normalize, sync, and visual-state tests; extend publish tests only where coverage is absent.

**Interfaces:** Tests call existing CLI entry points or public functions with temporary workspaces.

- [ ] Add failing assertions for exact file layout, status/priority aliases, estimate progress, count fallback, localized fields, invalid statuses, dry-run, verify drift, and target-path rejection.
- [ ] Run each focused module and classify already-supported behavior versus real gaps.
- [ ] Make only the minimal production changes needed for failing requirements.
- [ ] Re-run all focused modules.

### Task 3: Single-Workspace Doctor

**Files:** Create `doctor_mission_center.py`, `test_doctor_mission_center.py`, and the demo fixture.

**Interfaces:** `inspect_workspace(workspace: Path) -> list[str]` returns errors; `main(argv) -> int` prints a report and returns 0 only when no errors exist.

- [ ] Add failing tests for a valid fixture, missing files, invalid status, Done without smoke-test evidence, stale progress, and malformed task rows.
- [ ] Run the doctor tests and confirm the missing module fails.
- [ ] Implement strict local checks by reusing the canonical contract, sync calculations, and visual-state validation.
- [ ] Re-run doctor tests and the fixture CLI smoke test.

### Task 4: Dogfood Workspace And Documentation

**Files:** Create root `MissionCenter/`; modify README files, SKILL.md, task-workspace and platform-support references; remove global-overview reference.

**Interfaces:** The root workspace tracks MC-001 through MC-008 and records smoke-test evidence before Done.

- [ ] Add contract tests that reject global overview/registry language and require the canonical layout.
- [ ] Run contract tests and confirm current global wording/layout drift fails.
- [ ] Update documentation and create the local task workspace.
- [ ] Sync the workspace and run contract tests.

### Task 5: CI And Release Gate

**Files:** Create `.github/workflows/ci.yml` and `RELEASE_CHECKLIST.md`.

**Interfaces:** CI runs unittest discovery followed by bootstrap, normalize, sync, and doctor on `/tmp/mc-demo` for push and pull request events.

- [ ] Add release-metadata tests for workflow commands and forbidden global features.
- [ ] Run them and confirm missing artifacts fail.
- [ ] Add the workflow and checklist with exact commands and boundaries.
- [ ] Run release-metadata and full unit tests.

### Task 6: Final Verification And Local Publish

**Files:** Update root MissionCenter progress, smoke tests, snapshot, and closeout; publish the canonical skill to local derived locations.

**Interfaces:** `publish_local.py --dry-run`, `--write`, and `--verify` keep personal and marketplace copies identical to the repository source.

- [ ] Run full unittest discovery and the complete CLI smoke path.
- [ ] Run the skill validator, `git diff --check`, and a forbidden-feature search.
- [ ] Record observed results in the root MissionCenter and resync it.
- [ ] Publish to the personal skill and local marketplace paths, then verify zero drift.

