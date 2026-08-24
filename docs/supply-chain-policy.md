# Supply-chain policy

Mission Center core remains standard-library-only. The optional Runtime WebSocket dependency has two deliberately separate declarations:

- `requirements-runtime.txt` is the user-facing compatibility range (`websockets>=16.1,<17`).
- `requirements-runtime.lock` is the CI/release input. It selects the official platform-independent 16.1 wheel by URL and verifies its SHA-256 with pip `--require-hashes`.

The CI workflow pins every GitHub Action to a full 40-character commit SHA and leaves the reviewed major tag in a comment for maintainability. The current pins were resolved from the official `actions/checkout` and `actions/setup-python` v6 refs. Never guess or shorten a SHA; upgrades must resolve the official ref again and review the resulting commit before changing the workflow.

Release rules:

- keep the WebSocket path optional and unsupported for production while the upstream Codex app-server WebSocket surface remains experimental;
- install the CI/release dependency only from `requirements-runtime.lock` with `--require-hashes`;
- do not add runtime dependencies without focused compatibility, privacy, and license review;
- preserve the offline stdlib path as the release fallback.
