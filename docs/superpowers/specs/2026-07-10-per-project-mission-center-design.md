# Per-Project Mission Center Design

## Goal

Make Mission Center a deterministic, per-project-only Codex skill and plugin. Every repository owns one local `MissionCenter/`; no registry, cross-repository task merge, background scan, or global dashboard is part of the product.

## Workspace Contract

The canonical Markdown workspace contains exactly these files:

```text
MissionCenter/
  project.md
  progress.md
  tasks.md
  decisions.md
  smoke-tests.md
  notes.md
  snapshot.md
  closeout.md
  visual-hub.md
```

`tasks.md` is the only task lifecycle and ordering source. `progress.md` and `output/mission-center-assets/visual-state.json` are derived from the current workspace's tasks and smoke-test evidence.

## Components

- `workspace_contract.py` owns required filenames and canonical statuses.
- `bootstrap_mission_center.py` creates the canonical files in English or Traditional Chinese and copies local HUD assets.
- `normalize_mission_center.py` normalizes loose task metadata without accepting unknown lifecycle states as valid.
- `sync_mission_center.py` derives progress and HUD state from the local workspace.
- `doctor_mission_center.py` performs a read-only health check of one explicitly selected workspace and exits non-zero on errors.
- `tests/fixtures/demo-workspace/` supplies one minimal, valid per-project example used by doctor, sync, and visual-state tests.

## Doctor Contract

The doctor checks only `<workspace>/MissionCenter`. It verifies required files, strict task-table parsing, canonical statuses, smoke-test evidence for every Done task, reproducible progress percentage, and in-memory visual-state generation. It reports all discovered errors and never scans parent or sibling repositories.

## Documentation And Release

English and Traditional Chinese READMEs, the skill, and relevant references state that Mission Center is per-project only. CI runs unit tests plus the bootstrap-normalize-sync-doctor CLI path. The release checklist repeats the no-global-feature boundary.

## Testing

Tests assert the exact bootstrap file set, English and Traditional Chinese templates, normalization aliases, estimate and task-count progress modes, localized visual state, invalid-status failures, publish target safety and drift detection, doctor failures, and the valid demo fixture. Tests use temporary workspaces and do not read unrelated repositories.

