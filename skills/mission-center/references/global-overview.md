# Global Overview

## Purpose

Use a global overview only to summarize several Codex workspaces at once.
It is a dashboard layer, not the canonical task store.

## Hard Rules

- Each workspace keeps its own `MissionCenter/` as the source of truth.
- The hub may read workspace summaries, snapshots, or exported status files.
- The hub must not merge task tables from multiple folders into one queue.
- The hub must not write into another workspace unless that workspace is explicitly selected.
- Every global item needs a stable `workspaceId` and visible `workspacePath` or label.

## Recommended Hub Shape

```text
MissionCenterHub/
  registry.json
  global-state.json
  visual-summary-global.html
```

`registry.json` should store only workspace metadata:

```json
{
  "workspaces": [
    {
      "workspaceId": "mygame",
      "workspacePath": "D:\\MyGame",
      "goal": "MissionCenter visual panel",
      "status": "In Progress",
      "progress": 55,
      "updatedAt": "2026-04-25T00:00:00+08:00"
    }
  ]
}
```

## Display Model

- One visible helper may represent one workspace.
- Child helpers may represent subagents, but they must stay visually attached to their parent workspace.
- If a user asks to edit tasks, switch into the selected workspace first, then read that workspace's `MissionCenter/`.

## Anti-Pattern

Do not create one giant `Active` list that mixes unrelated tasks from different folders.
That makes progress, ownership, blockers, and smoke tests ambiguous.
