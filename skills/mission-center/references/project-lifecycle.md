# Project Lifecycle

## Open

Use this state while the goal is active and the task tree is still changing.

## Wrap Up

Before closing a project or cycle:

- run the last smoke test
- mark completed work `Done`
- identify unfinished items explicitly
- summarize key decisions
- record the next open question if any
- write a closeout note with outcomes, risks, and carryover work
- add a short retro note on what worked and what should change next time

## Archive

Archive only after the workspace reflects reality:

- `project.md` has a final activity note
- `progress.md` shows the final state
- `tasks.md` clearly separates done, blocked, and leftover work
- `smoke-tests.md` preserves verification history
- `closeout.md` exists when the project or cycle ended cleanly
- `snapshot.md` exists for the last reopenable checkpoint

## Reopen

When a project returns later:

- read `project.md`, `progress.md`, and `tasks.md`
- update the cycle or goal if needed
- keep the old history intact
- if there is a `closeout.md`, treat it as historical context rather than source of truth
- if there is a `snapshot.md`, use it to rebuild the starting context quickly
