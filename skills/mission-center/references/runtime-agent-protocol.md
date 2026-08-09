# Runtime Agent Protocol

Runtime data is optional telemetry. It never changes task lifecycle or ordering; `tasks.md` remains authoritative.

Passive observation performs no model call and adds no model-token usage. Connected agents' own work retains its normal quota behavior. Any future LLM classification or agent-driven trial must be explicitly enabled and charged against its declared token budget.

## Contracts

`AgentEvent` normalizes provider events with schema version, event ID, timestamp, provider, session/thread/turn/agent IDs, parent agent, explicit Task IDs, event type, activity, attention, and sequence. Persist no prompt, reasoning, complete command, tool arguments, environment variables, bearer token, or secret.

`RuntimeState` uses only `idle`, `working`, `waiting_approval`, `blocked`, `finished`, `failed`, `stale`, and `disconnected`. `ProviderCapabilities` declares whether approve, reject, or focus is supported; controls stay hidden otherwise and all approval actions retain the provider's native permission contract.

Write `output/mission-center-runtime/runtime-state.json` by temporary file and atomic replacement. Ignore duplicate events and stale out-of-order sequences. Transport health and provider activity freshness are separate: an open socket or any received message touches transport health, while an agent becomes `stale` after 60 seconds without provider activity. Only a closed socket or connection failure makes transport or an agent `disconnected`; silence alone never does.

## Codex Adapter

Use the official Codex app-server JSON-RPC contract as the primary source. Support JSONL replay, file fallback, and an optional WebSocket companion. Live WebSocket support may use `websockets>=16.1,<17`, imported lazily so the offline core has no required third-party dependency.

Validate initialize, thread, turn, item, approval, current `collabAgentToolCall`, legacy `collabToolCall`, error, and token-usage messages. Collaboration receivers are accepted only from the documented `receiverThreadIds` array; do not infer a child from unverified singular fields. Claim visibility only for sessions connected to the configured endpoint, never global Codex Desktop monitoring.

### Visibility and Attach Capability

The v1 adapter observes only the configured endpoint after its initialize handshake. It does not enumerate, attach to, resume, or claim visibility over arbitrary Desktop threads. `thread/list`, `thread/loaded/list`, and `thread/resume` are deliberately not called until their endpoint contract, permissions, pagination, and resume semantics are verified against the connected provider. A future attach capability must be explicitly declared and tested before the HUD exposes it.

Task linking accepts dispatch metadata, provider metadata, or an explicit CLI/HUD selection. Do not persist fuzzy text matches.

## Attention

Raise attention only for approval, question, blocked, error, or finished-awaiting-verification. A completed turn raises verification attention only when it is explicitly linked to a MissionCenter task; ordinary work activity and unlinked completion are silent.
