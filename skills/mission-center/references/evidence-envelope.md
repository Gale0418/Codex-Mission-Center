# Revision-bound Evidence Envelope

Evidence envelopes are optional, versioned records under `output/mission-center-evidence/*.json`. They bind one `taskId` and `checkId` to a bounded, explicit file `scope`, a SHA-256 `scopeDigest`, a result, and artifact locators. They are evidence only; `tasks.md` remains the sole lifecycle source.

## Fields

- `schemaVersion`: currently `1.0`.
- `envelopeId`: stable ID used by `supersedes`.
- `taskId`, `checkId`: canonical task and verification identity.
- `scope`: non-empty workspace-relative files included in the digest.
- `scopeDigest`: SHA-256 of the sorted, explicitly listed scope paths and bytes. Files outside `scope` do not affect freshness.
- `sourceRevision`: optional source revision label; it is descriptive and never replaces the scope digest.
- `result`: `pass`, `fail`, or `unknown`.
- `status`: `current` or `superseded`.
- `artifactLocators`: non-empty workspace-relative files containing the bounded evidence.
- `recordedAt`: timezone-aware ISO-8601 timestamp.
- `supersedes`: optional prior envelope ID on a new `current` envelope. The prior envelope must be marked `superseded` and have the same task/check.

Malformed envelopes are `corrupt`; a digest mismatch is `stale`; duplicate current task/check records or invalid supersession relationships are `conflict`. Existing tasks without an envelope remain a migration `unknown` warning and do not invalidate the v0.4 workspace. Once an envelope is present and linked to a task, these failures block Doctor.
