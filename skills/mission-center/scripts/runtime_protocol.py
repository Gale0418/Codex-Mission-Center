#!/usr/bin/env python3
"""Normalize runtime events and maintain a privacy-safe RuntimeState."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from optimization_core import atomic_write_json, utc_now


RUNTIME_STATES = {"idle", "working", "waiting_approval", "blocked", "finished", "failed", "stale", "disconnected"}
ATTENTION_KINDS = {"approval", "question", "blocked", "error", "verification"}
SENSITIVE_KEYS = {"prompt", "reasoning", "command", "arguments", "args", "environment", "env", "token", "secret", "authorization", "input", "content"}
RUNTIME_ROOT_FIELDS = {"schemaVersion", "updatedAt", "sourceStatus", "capabilities", "attention", "agents"}
CAPABILITY_FIELDS = {"approve", "reject", "focus"}
ATTENTION_FIELDS = {"agentId", "kind", "activity", "taskIds"}
AGENT_FIELDS = {
    "provider", "sessionId", "threadId", "turnId", "agentId", "parentAgentId",
    "taskIds", "state", "activity", "attention", "requiresAttention", "startedAt",
    "lastSeenAt", "sequence", "recentEventIds",
}


def empty_runtime_state(source_status: str = "disconnected") -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "updatedAt": utc_now(),
        "sourceStatus": source_status,
        "capabilities": {"approve": False, "reject": False, "focus": False},
        "attention": [],
        "agents": [],
    }


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items() if key.casefold() not in SENSITIVE_KEYS}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def sanitize_runtime_state(state: dict[str, Any]) -> dict[str, Any]:
    """Project runtime persistence onto the protocol's explicit allowlist."""
    root = {key: value for key, value in state.items() if key in RUNTIME_ROOT_FIELDS}
    capabilities = root.get("capabilities")
    root["capabilities"] = (
        {key: bool(value) for key, value in capabilities.items() if key in CAPABILITY_FIELDS}
        if isinstance(capabilities, dict) else {}
    )
    attention = root.get("attention")
    root["attention"] = [
        {key: sanitize(value) for key, value in item.items() if key in ATTENTION_FIELDS}
        for item in attention if isinstance(item, dict)
    ] if isinstance(attention, list) else []
    agents = root.get("agents")
    normalized_agents = []
    for agent in agents if isinstance(agents, list) else []:
        if not isinstance(agent, dict):
            continue
        projected = {key: sanitize(value) for key, value in agent.items() if key in AGENT_FIELDS}
        projected.setdefault("agentId", "unknown")
        projected.setdefault("state", "disconnected")
        projected.setdefault("attention", "none")
        projected.setdefault("activity", "Unknown runtime activity")
        projected.setdefault("requiresAttention", False)
        projected.setdefault("taskIds", [])
        normalized_agents.append(projected)
    root["agents"] = normalized_agents
    return sanitize(root)


def validate_initialize_response(message: dict[str, Any], request_id: int = 1) -> dict[str, Any]:
    """Validate the app-server initialize handshake before consuming events."""
    if message.get("id") != request_id:
        raise ValueError("Unexpected initialize response ID")
    if message.get("error") is not None:
        raise ValueError("Codex app-server initialize failed")
    result = message.get("result")
    if not isinstance(result, dict):
        raise ValueError("Codex app-server initialize result must be an object")
    return sanitize(result)


def _identifier(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def normalize_codex_message(message: dict[str, Any], sequence: int, task_links: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """Convert one official app-server JSON-RPC notification/request to AgentEvent."""
    method = str(message.get("method") or "")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    thread_id = _first(params, "threadId", "thread_id") or _nested(params, "thread", "id")
    turn_id = _first(params, "turnId", "turn_id") or _nested(params, "turn", "id")
    item = params.get("item") if isinstance(params.get("item"), dict) else {}
    agent_id = str(_first(params, "agentId", "agent_id") or _nested(item, "agent", "id") or thread_id or "codex")
    parent_id = _first(params, "parentAgentId", "parent_agent_id")
    event_type, state, activity, attention = _map_codex_method(method, params, item)
    if not event_type:
        return []
    explicit_tasks = _extract_task_ids(params)
    linked = (task_links or {}).get(agent_id, [])
    task_ids = sorted(set(explicit_tasks or linked))
    timestamp = _bounded_timestamp(_first(params, "timestamp", "createdAt", "created_at"))
    event = {
        "schemaVersion": "1.0",
        "eventId": str(_first(params, "eventId", "event_id") or _identifier(method, thread_id, turn_id, item.get("id"), sequence)),
        "timestamp": timestamp,
        "provider": "codex",
        "sessionId": str(_first(params, "sessionId", "session_id") or thread_id or "connected-endpoint"),
        "threadId": str(thread_id) if thread_id else None,
        "turnId": str(turn_id) if turn_id else None,
        "agentId": agent_id,
        "parentAgentId": str(parent_id) if parent_id else None,
        "taskIds": task_ids,
        "eventType": event_type,
        "activity": activity,
        "attention": attention,
        "sequence": sequence,
        "state": state,
    }
    if method.casefold() == "item/started" and _is_collab_tool_call(item):
        sender = str(item.get("senderThreadId") or agent_id)
        receivers = item.get("receiverThreadIds") if isinstance(item.get("receiverThreadIds"), list) else []
        if receivers:
            return [sanitize({**event, "eventId": _identifier(event["eventId"], receiver), "agentId": str(receiver), "parentAgentId": sender, "threadId": str(receiver), "activity": "Subagent started"}) for receiver in receivers]
    return [sanitize(event)]


def _map_codex_method(method: str, params: dict[str, Any], item: dict[str, Any]) -> tuple[str, str, str, str]:
    lower = method.casefold()
    item_type = str(item.get("type") or params.get("itemType") or "").casefold()
    if lower in {"thread/started", "thread/resumed", "thread/loaded"}:
        return "session_started", "idle", "Session connected", "none"
    if lower == "turn/started":
        return "turn_started", "working", "Working", "none"
    if lower == "turn/completed":
        status = str(_nested(params, "turn", "status") or params.get("status") or "completed").casefold()
        if status in {"failed", "error"}:
            return "turn_failed", "failed", "Turn failed", "error"
        if status in {"interrupted", "cancelled", "canceled"}:
            return "turn_blocked", "blocked", "Turn interrupted", "blocked"
        return "turn_finished", "finished", "Awaiting task verification", "verification"
    if "requestapproval" in lower or lower in {"tool/requestuserinput", "mcpserver/elicitation/request"}:
        kind = "question" if "userinput" in lower or "elicitation" in lower else "approval"
        return "approval_requested", "waiting_approval", "Waiting for approval" if kind == "approval" else "Waiting for answer", kind
    if lower == "serverrequest/resolved":
        return "approval_resolved", "working", "Approval resolved", "none"
    if lower == "error":
        return "error", "failed", "Runtime error", "error"
    if lower == "thread/tokenusage/updated":
        return "usage_updated", "working", "Usage updated", "none"
    if lower == "item/started":
        if item_type in {"collabagenttoolcall", "collabtoolcall"}:
            return "subagent_started", "working", "Collaborating with subagent", "none"
        labels = {
            "commandexecution": "Running command",
            "filechange": "Applying file changes",
            "mcptoolcall": "Using MCP tool",
            "dynamictoolcall": "Using tool",
            "websearch": "Searching the web",
        }
        return "item_started", "working", labels.get(item_type, "Working on item"), "none"
    if lower == "item/completed":
        return "item_completed", "working", "Item completed", "none"
    if lower in {"heartbeat", "runtime/heartbeat"}:
        return "heartbeat", "idle", "Connected", "none"
    return "", "idle", "", "none"


def _is_collab_tool_call(item: dict[str, Any]) -> bool:
    return str(item.get("type") or "").casefold() in {
        "collabagenttoolcall",
        "collabtoolcall",
    }


def reduce_event(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Apply one event without changing any MissionCenter task file."""
    event = sanitize(event)
    if event.get("state") not in RUNTIME_STATES:
        raise ValueError(f"Unsupported runtime state: {event.get('state')}")
    if event.get("eventType") == "turn_finished" and not event.get("taskIds"):
        event = {**event, "activity": "Turn completed", "attention": "none"}
    agents = {agent["agentId"]: dict(agent) for agent in state.get("agents", []) if agent.get("agentId")}
    agent_id = str(event["agentId"])
    current = agents.get(agent_id)
    if current and event.get("eventId") in current.get("recentEventIds", []):
        return state
    if current and int(event.get("sequence", 0)) <= int(current.get("sequence", -1)):
        return state
    created = event["timestamp"] if current is None else current.get("startedAt", event["timestamp"])
    recent = ([] if current is None else current.get("recentEventIds", []))[-19:] + [event["eventId"]]
    agents[agent_id] = {
        "provider": event["provider"],
        "sessionId": event["sessionId"],
        "threadId": event.get("threadId"),
        "turnId": event.get("turnId"),
        "agentId": agent_id,
        "parentAgentId": event.get("parentAgentId"),
        "taskIds": event.get("taskIds", []),
        "state": event["state"],
        "activity": event["activity"],
        "attention": event["attention"],
        "requiresAttention": event["attention"] in ATTENTION_KINDS,
        "startedAt": created,
        "lastSeenAt": event["timestamp"],
        "sequence": event["sequence"],
        "recentEventIds": recent,
    }
    next_state = dict(state)
    next_state["schemaVersion"] = "1.0"
    next_state["updatedAt"] = utc_now()
    next_state["agents"] = sorted(agents.values(), key=lambda item: (item["sessionId"], item["agentId"]))
    next_state["attention"] = [
        {"agentId": item["agentId"], "kind": item["attention"], "activity": item["activity"], "taskIds": item["taskIds"]}
        for item in next_state["agents"] if item["requiresAttention"]
    ]
    return next_state


def age_runtime_state(state: dict[str, Any], now: datetime | None = None, socket_closed: bool = False) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    aged = dict(state)
    agents = []
    for original in state.get("agents", []):
        agent = dict(original)
        seen = _parse_time(agent.get("lastSeenAt"))
        age = (now - seen).total_seconds() if seen else float("inf")
        if socket_closed:
            agent.update(state="disconnected", activity="Disconnected", attention="blocked", requiresAttention=True)
        elif age >= 60:
            agent.update(
                state="stale",
                activity="No recent provider activity",
                attention="none",
                requiresAttention=False,
            )
        agents.append(agent)
    aged["agents"] = agents
    aged["sourceStatus"] = "disconnected" if socket_closed else state.get("sourceStatus", "connected")
    aged["updatedAt"] = utc_now()
    aged["attention"] = [{"agentId": a["agentId"], "kind": a["attention"], "activity": a["activity"], "taskIds": a.get("taskIds", [])} for a in agents if a.get("requiresAttention")]
    return aged


def write_runtime_state(path: Path, state: dict[str, Any]) -> None:
    atomic_write_json(path, sanitize_runtime_state(state))


def touch_runtime_state(state: dict[str, Any]) -> dict[str, Any]:
    """Record a live transport heartbeat without changing agent activity state."""
    touched = dict(state)
    timestamp = utc_now()
    touched["updatedAt"] = timestamp
    touched["sourceStatus"] = "connected"
    return touched


def load_last_valid(path: Path, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("agents"), list):
            raise ValueError("agents must be a list")
        return sanitize_runtime_state(payload)
    except (OSError, ValueError, json.JSONDecodeError):
        return fallback if fallback is not None else empty_runtime_state("file")


def _extract_task_ids(params: dict[str, Any]) -> list[str]:
    metadata = params.get("metadata") if isinstance(params.get("metadata"), dict) else {}
    raw = params.get("taskIds") or metadata.get("taskIds") or metadata.get("missionCenterTaskIds") or []
    return [str(value) for value in raw] if isinstance(raw, list) else []


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    return next((mapping[key] for key in keys if mapping.get(key) is not None), None)


def _nested(mapping: dict[str, Any], parent: str, child: str) -> Any:
    value = mapping.get(parent)
    return value.get(child) if isinstance(value, dict) else None


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _bounded_timestamp(value: Any) -> str:
    now = datetime.now(timezone.utc)
    parsed = _parse_time(value) if value is not None else None
    if parsed is None or parsed > now:
        return now.isoformat().replace("+00:00", "Z")
    return str(value)
