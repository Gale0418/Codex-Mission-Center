# Smoke Test Patterns

## Choose the Smallest Useful Check

Pick the cheapest test that still proves the user-facing goal.

## Common Patterns

- CLI flow: run the command with a known input and verify the output
- File flow: create the files, then verify their contents and structure
- UI flow: open the screen, interact once, and verify the visible state
- Data flow: write one record, then verify it is read back correctly

## Recording Standard

For every smoke test, capture:

- what was run
- what should have happened
- what actually happened
- whether it passed
- what task it validates

## Escalation Rule

If no fast smoke test exists, write the closest reproducible manual check and label it manual.
