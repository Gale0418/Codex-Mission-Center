# Privacy Policy

Mission Center runs locally in the user's Codex workspace.

## Data handling

- The bundled scripts read and write files inside the selected workspace to keep `MissionCenter/` summaries aligned.
- The project does not include built-in telemetry, analytics, or automatic upload of workspace contents.
- Any network access depends on the host Codex session, installed plugins, or tools the user explicitly invokes.

## Local publishing

The local publish scripts copy the skill and plugin package into local Codex directories on the same machine. They do not send workspace contents to a remote service.

## User control

Users can inspect, edit, or delete the generated `MissionCenter/` files at any time.
## Optional Runtime Telemetry

Mission Center's core workflow is offline and file-based. The optional local companion binds to loopback and writes runtime snapshots only inside the current repository under `output/mission-center-runtime/`.

Persisted runtime telemetry contains identifiers, explicit MissionCenter Task links, lifecycle events, coarse activity labels, attention state, sequence, and timestamps. It intentionally excludes prompts, reasoning, full commands, tool arguments, environment values, authorization headers, tokens, and secrets.

The adapter observes only sessions connected to the configured endpoint. It does not claim global Codex Desktop visibility, scan other repositories, auto-approve provider requests, or change `MissionCenter/tasks.md`.
