# Smoke Test Catalog

## Goal

Provide default verification ideas when the task does not already name a clear smoke test.

## Suggested Patterns

- `Intake / planning`
  - checklist review
  - scope confirmation
  - blocker confirmation

- `Workspace / file generation`
  - verify files exist
  - inspect generated headers and tables
  - rerun script on a clean temp workspace

- `Task tracking / sync`
  - confirm progress recalculates
  - confirm blocked tasks appear in the blocked list
  - confirm active tasks list is current

- `Normalization`
  - confirm labels become lowercase
  - confirm priorities map to canonical values
  - confirm statuses map to canonical values

- `Closeout / snapshot`
  - confirm closeout file exists
  - confirm snapshot exists
  - confirm reopenable fields are present
