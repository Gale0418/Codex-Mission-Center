# Runtime Agent Protocol

版本與支援邊界見 [Runtime 相容性矩陣](runtime-compatibility-matrix.md)。WebSocket companion 是 experimental、unsupported for production；本文件的 endpoint-only 與 fail-closed 規則優先於任何 UI 顯示需求。

Runtime data is optional telemetry. It never changes task lifecycle or ordering; `tasks.md` remains authoritative.

Passive observation performs no model call and adds no model-token usage. Connected agents' own work retains its normal quota behavior. Any future LLM classification or agent-driven trial must be explicitly enabled and charged against its declared token budget.

## Contracts

`AgentEvent` normalizes provider events with schema version, event ID, timestamp, provider, session/thread/turn/agent IDs, parent agent, explicit Task IDs, event type, activity, attention, sequence, and optional `activityKind`. Persist no prompt, reasoning, complete command, tool arguments, environment variables, bearer token, or secret. `location` is omitted from telemetry and derived on the presentation layer if needed.

`RuntimeState` uses only `idle`, `working`, `waiting_approval`, `blocked`, `finished`, `failed`, `stale`, and `disconnected`. `ProviderCapabilities` declares whether approve, reject, or focus is supported; controls stay hidden otherwise and all approval actions retain the provider's native permission contract.

Write `output/mission-center-runtime/runtime-state.json` by temporary file and atomic replacement. Ignore duplicate events and stale out-of-order sequences. Transport health and provider activity freshness are separate: an open transport or any received message touches transport health, while an agent becomes `stale` after 60 seconds without provider activity. Only a closed socket/stdio connection or explicit disconnect makes transport or an agent `disconnected`; silence alone never does.

## Codex Adapter

Use the official Codex app-server JSON-RPC contract as the primary source. Support stdio transport (stdlib-only live source), JSONL replay, file fallback, and an optional WebSocket companion (`websockets>=16.1,<17`, imported lazily so the offline core has no required third-party dependency).

Launch stdio with an argument array and no shell. A WindowsApps-packaged Desktop executable may deny direct subprocess creation; fail with a precise `--codex-executable` instruction instead of introducing a shell fallback or claiming the connection succeeded.

Validate initialize, `thread/started`, `thread/status/changed`, `thread/closed`, turn, item, approval, current `collabAgentToolCall`, legacy `collabToolCall`, and error messages. Recognize token-usage messages as transport activity, but do not convert them into agent activity or attention. Do not rely on `thread/resumed` or `thread/loaded` as notifications.

### ThreadStatus Mapping

In app-server 0.147.0-alpha.6.5, `ThreadStatus` is an object (`{ "type": "notLoaded" | "idle" | "systemError" | "active", "activeFlags": [...] }`):

- `type == "active"` -> `state="working"`, `attention="none"`
- `type == "idle"` -> `state="idle"`, `attention="none"`
- `type == "systemError"` -> `state="failed"`, `attention="error"`
- `type == "notLoaded"` -> `state="disconnected"`, `attention="none"` (explicit provider disconnect signal, not transport silence)
- Method `thread/closed` -> `state="disconnected"`, `attention="none"`
- If `status.type` is unrecognized or malformed, ignore the entire provider message without altering state.

### ActivityKind Privacy

Optional `activityKind` enum (`unknown`, `idle`, `working`, `command_execution`, `file_change`, `tool_use`, `web_search`, `waiting_input`, `verification`, `blocked`, `error`) is derived strictly from verified method and `item.type` enums. Prompt text, command lines, shell inputs, and tool arguments are never parsed or read for activity classification.

### Visibility and Attach Capability

The v1 adapter observes only the configured endpoint after its initialize handshake and is never global Codex Desktop monitoring. It does not enumerate, attach to, resume, or claim visibility over arbitrary Desktop threads. `thread/list`, `thread/loaded/list`, and `thread/resume` are deliberately not called after handshake. A future attach capability must verify permissions, pagination, ownership, and resume semantics, then be explicitly declared and tested before the HUD exposes it.

Task linking accepts dispatch metadata, provider metadata, or an explicit CLI/HUD selection. Do not persist fuzzy text matches.

## Attention

Raise attention only for approval, question, blocked, error, or finished-awaiting-verification. A completed turn raises verification attention only when it is explicitly linked to a MissionCenter task; ordinary work activity and unlinked completion are silent.
