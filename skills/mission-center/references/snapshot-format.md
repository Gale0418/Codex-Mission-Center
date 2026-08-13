# Execution Checkpoint Format

## Purpose

Capture a reopenable, bounded execution checkpoint. It is a view of canonical workspace state, never a second source of lifecycle truth.

## Canonical fields

`Active task`, `Status`, `Revision`, `Fingerprint`, `Dependencies`, and `Verification` are derived only from `MissionCenter/tasks.md`, canonical workspace files, and Git. CLI input cannot override them. A resume of an inactive workspace may omit the usual body and state that task selection must resume from `tasks.md`.

## Operator annotations

The CLI may append only short `Notes`, `Hypotheses`, `Changes`, and structured `Recent attempts`. Attempts retain at most five records with `phase`, `errorSignature`, and optional falsifiable `hypothesis` / evidence locator. Do not record chain-of-thought, raw logs, complete commands, credentials, tokens, or secrets.

## Retry Gate

Two matching error signatures or three failures in one phase enter `diagnosis` mode: stop modifying and deploying. Leave this mode only with a new falsifiable hypothesis plus new evidence; create a fresh checkpoint after the evidence changes.

## Migration

The old Snapshot headings are accepted as historical files. Regenerate them with `snapshot_mission_center.py`; deprecated fact-like CLI flags are ignored so they cannot overwrite canonical facts.
