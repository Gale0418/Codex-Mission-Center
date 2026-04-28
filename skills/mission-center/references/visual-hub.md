# Visual Hub

## Purpose

Use this pattern when the workspace should include a clickable visual MissionCenter HUD alongside the markdown task workspace.

## Bootstrap Output

Create a file such as `visual-hub.md` during workspace bootstrap.
Keep it short and obvious:

```md
# Visual Hub

- Open HUD: `output/mission-center-assets/visual-summary.html`
- Current view: active helpers, task states, progress, and blockers
- Helper roster: auto-assigned by the visual panel
```

## P0 Sequence

When the user wants the workspace to start in a visible, animated state, seed these P0 items first:

1. Create the `MissionCenter/` folder.
1. Create the task flow scaffold.
1. Add the repair / bug-fix loop.
1. Add smoke tests and verification steps.
1. Link the visual HUD so helpers can be watched while tasks move.

## Helper Asset

If the skill needs a visual placeholder for documentation or examples, keep a small helper avatar asset under `assets/` so the skill folder is not empty of imagery.
