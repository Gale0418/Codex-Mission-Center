# Normalization Rules

## Priority

Normalize priority values to one of:

- `P0`
- `P1`
- `P2`
- `P3`

Map common variants:

- `urgent`, `high`, `critical` -> `P0` or `P1` based on blocker severity
- `medium`, `normal` -> `P2`
- `low`, `nice to have` -> `P3`

## Status

Normalize status values to one of:

- `Backlog`
- `Ready`
- `In Progress`
- `Blocked`
- `Review`
- `Done`

## Labels

Use lowercase, comma-separated labels only.

Allowed core labels:

- `intake`
- `plan`
- `execution`
- `verification`
- `blocked`
- `closeout`

## Parent / Dependency Hygiene

- keep one direct parent per row
- use task IDs only
- avoid circular dependencies
