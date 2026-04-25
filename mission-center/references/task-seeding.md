# Task Seeding

## Purpose

Generate an initial Linear-like task tree from a vague goal without requiring the user to handcraft it.

## Default Skeleton

Create one epic plus the standard supporting tasks:

- intake and clarification
- project setup
- task breakdown
- implementation slices
- verification / smoke tests
- closeout

## Rules

- Keep the first tree small.
- Add tasks only for the current goal.
- Make dependencies explicit.
- Include at least one verification task.
- Include at least one follow-up / closeout task.

## When to Expand

Add more tasks only when:

- the user confirms a larger scope
- the work has a real blocker
- a slice can be executed independently
