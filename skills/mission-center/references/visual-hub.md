# Visual Hub

## Purpose

Use the HUD as a task-lifecycle board. `MissionCenter/tasks.md` is the only source for helper count, order, names, and zones.

## Task Mapping

- Create exactly one helper for each selected task row.
- Use the task ID as the helper ID and the task short title as its name.
- Keep task order aligned with `tasks.md`.
- Never derive helper count from owners, active agents, processes, or parallel work.
- Do not create a placeholder helper when no valid task exists.

Map task statuses to HUD zones:

| Task status | HUD zone |
| --- | --- |
| `Backlog`, `Ready` | `Intake` |
| `In Progress` | `In Progress` |
| `Blocked` | `Blocked` |
| `Review` | `Review` |
| `Done` | Rest area |

Show the first 10 unfinished tasks. Completed tasks do not consume those slots. Keep at most 15 helpers total and retire the oldest completed tasks first.

## Bootstrap Output

Copy the bundled HUD into `output/mission-center-assets/` and create `MissionCenter/visual-hub.md` with a direct link to `visual-summary.html`. Run `scripts/sync_mission_center.py` after task changes so the JSON state and Markdown summaries stay aligned.

If task parsing fails, report the exact error and keep the previous state file. Do not invent tasks to make the HUD look populated.
