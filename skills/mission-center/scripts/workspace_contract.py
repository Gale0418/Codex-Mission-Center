#!/usr/bin/env python3
"""Canonical files and lifecycle values for one Mission Center workspace."""

REQUIRED_FILES = (
    "brief.md",
    "focus.md",
    "guardrails.md",
    "daily-log.md",
    "project.md",
    "progress.md",
    "tasks.md",
    "decisions.md",
    "smoke-tests.md",
    "notes.md",
    "snapshot.md",
    "closeout.md",
    "visual-hub.md",
)

DERIVED_FILES = ("brief.md", "focus.md")

CANONICAL_STATUSES = (
    "Backlog",
    "Ready",
    "In Progress",
    "Blocked",
    "Review",
    "Done",
)
