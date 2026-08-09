# Runtime Agent Protocol

Runtime data is optional telemetry. It never changes task lifecycle or ordering; `tasks.md` remains authoritative.

Passive observation performs no model call and adds no model-token usage. Connected agents' own work retains its normal quota behavior. Any future LLM classification or agent-driven trial must be explicitly enabled and charged against its declared token budget.

## Contracts

`AgentEvent` normalizes provider events with schema version, event ID, timestamp, provider, session/thread/turn/agent IDs, parent agent, explicit Task IDs, event type, activity, attention, and sequence. Persist no prompt, reasoning, complete command, tool arguments, environment variables, bearer token, or secret.

`RuntimeState` uses only `idle`, `working`, `waiting_approval`, `blocked`, `finished`, `failed`, `stale`, and `disconnected`. `ProviderCapabilities` declares whether approve, reject, or focus is supported; controls stay hidden otherwise and all approval actions retain the provider's native permission contract.

Write `output/mission-center-runtime/runtime-state.json` by temporary file and atomic replacement. Ignore duplicate events and stale out-of-order sequences. A 10-second heartbeat is expected; after 60 seconds an agent is `stale`, and after 180 seconds or a closed connection it is `disconnected`.

## Codex Adapter

Use the official Codex app-server JSON-RPC contract as the primary source. Support JSONL replay, file fallback, and an optional WebSocket companion. Live WebSocket support may use `websockets>=16.1,<17`, imported lazily so the offline core has no required third-party dependency.

Validate initialize, thread, turn, item, approval, `collabToolCall`, error, and token-usage messages. Claim visibility only for sessions connected to the configured endpoint, never global Codex Desktop monitoring.

Task linking accepts dispatch metadata, provider metadata, or an explicit CLI/HUD selection. Do not persist fuzzy text matches.

## Attention

Raise attention only for approval, question, blocked, error, or finished-awaiting-verification. Ordinary work activity is silent.
