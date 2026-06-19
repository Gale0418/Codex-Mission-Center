# Visual Hub

## Purpose

Use this pattern when the workspace should include a clickable visual MissionCenter HUD alongside the markdown task workspace.
The HUD should expose separate `SmokeTest` and `Review` lanes when the workspace tracks those check columns, and the task rows should use `YES / NO` so the helpers visibly travel through the workflow.

## Bootstrap Output

Create a file such as `visual-hub.md` during workspace bootstrap.
Keep it short and obvious:

```md
# Visual Hub

- Open HUD: `output/mission-center-assets/visual-summary.html`
- Current view: active helpers, task states, progress, and blockers
- Current view: active helpers, task states, progress, SmokeTest, and Review lanes
- Sync mode: keep task state updated in real time as the workspace changes
- Helper roster: one visible helper per active agent
```

`scripts/bootstrap_mission_center.py` should also copy the bundled HUD files into:

```text
output/mission-center-assets/
  visual-summary.html
  visual-state.json
  update-visual-state.ps1
  mission-base-main.png
  mission-helper-roster-8-fixed.png
  mission-helper-roster-8-girls-2.png
```

## P0 Sequence

When the user wants the workspace to start in a visible, animated state, seed these P0 items first:

1. Create the `MissionCenter/` folder.
1. Create the task flow scaffold.
1. Add the repair / bug-fix loop.
1. Add smoke tests and verification steps.
1. Link the visual HUD so helpers can be watched while tasks move.

## Helper Asset

Keep the full helper roster under `assets/visual-hub/` so a freshly installed skill can create the animated HUD without downloading extra assets.
The current roster is split across two 8-character sheets:

- `mission-helper-roster-8-fixed.png`
- `mission-helper-roster-8-girls-2.png`

The helper count shown in the HUD should match the number of active agents whenever possible.
