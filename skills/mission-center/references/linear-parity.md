# Linear Parity Map

## Local Task Model

Use one `Project` for the mission. Use `Cycle` for the current milestone or time box, `Epic` for a broad outcome, `Task` for a verifiable delivery slice, and `Subtask` for a small executable step.

Track stable IDs, parent links, priority, status, owner when useful, dependencies, next action, verification, estimate, labels, and concise comments. Keep blockers and decision history visible.

## Rolling Planning

- Build the full Epic map so the overall direction is visible.
- Detail only the first verifiable milestone into Tasks and Subtasks.
- Keep later work as a coarse Backlog until the current milestone produces evidence.
- Revisit research, risks, dependencies, and scope before expanding the next milestone.
- Split a task when it contains more than one independently verifiable outcome or crosses a risky boundary.

## Status and Priority

Use `Backlog -> Ready -> In Progress -> Blocked -> Review -> Done`.

- `P0`: urgent or blocking
- `P1`: high value or high risk
- `P2`: normal
- `P3`: low priority or optional

Use a small stable label set such as `intake`, `research`, `plan`, `execution`, `verification`, `blocked`, and `closeout`.

## Superpowers Alignment

Linear owns task structure and state. Superpowers owns decision and execution discipline:

```text
Brainstorm -> Spec -> Plan -> TDD -> Verify -> Closeout
```

Scale document depth with risk. Never skip mission understanding, task-draft approval, or final verification.

## Boundaries

Do not require a Linear app, OAuth, external workspace, or hidden task state. `MissionCenter/tasks.md` remains the local source of truth.
