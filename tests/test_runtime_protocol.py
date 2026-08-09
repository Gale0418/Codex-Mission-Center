import json
import asyncio
import sys
import types
import unittest
import socket
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mission_runtime import connect_live, is_loopback_host_header, link_task, loopback_server_type, replay, validate_websockets_version
from runtime_protocol import age_runtime_state, empty_runtime_state, load_last_valid, normalize_codex_message, reduce_event, sanitize, touch_runtime_state, validate_initialize_response, write_runtime_state


class RuntimeProtocolTests(unittest.TestCase):
    def event(self, sequence=1, agent="a", state="working", attention="none", event_id=None, task_ids=None):
        return {"schemaVersion": "1.0", "eventId": event_id or f"e-{sequence}-{agent}", "timestamp": "2026-08-09T00:00:00Z", "provider": "codex", "sessionId": "s", "threadId": "t", "turnId": "turn", "agentId": agent, "parentAgentId": None, "taskIds": task_ids or [], "eventType": "test", "activity": "Working", "attention": attention, "sequence": sequence, "state": state}

    def test_zero_one_many_and_fifteen_agents(self):
        state = empty_runtime_state()
        self.assertEqual(state["agents"], [])
        for index in range(15):
            state = reduce_event(state, self.event(index + 1, f"a-{index}"))
        self.assertEqual(len(state["agents"]), 15)

    def test_initialize_handshake_is_validated_and_sanitized(self):
        result = validate_initialize_response({"id": 1, "result": {"serverInfo": {"name": "codex"}, "token": "secret"}})
        self.assertEqual(result["serverInfo"]["name"], "codex")
        self.assertNotIn("token", result)
        with self.assertRaises(ValueError):
            validate_initialize_response({"id": 2, "result": {}})
        with self.assertRaises(ValueError):
            validate_initialize_response({"id": 1, "error": {"message": "no"}})

    def test_optional_websocket_version_range(self):
        validate_websockets_version("16.1")
        validate_websockets_version("16.9.2")
        with self.assertRaises(RuntimeError):
            validate_websockets_version("16.0")
        with self.assertRaises(RuntimeError):
            validate_websockets_version("17.0")

    def test_duplicate_and_out_of_order_events_are_ignored(self):
        state = reduce_event(empty_runtime_state(), self.event(2, event_id="same"))
        duplicate = reduce_event(state, self.event(3, event_id="same", state="failed"))
        old = reduce_event(state, self.event(1, state="failed"))
        self.assertEqual(duplicate["agents"][0]["state"], "working")
        self.assertEqual(old["agents"][0]["state"], "working")

    def test_approval_resolved_and_task_state_independence(self):
        requested = normalize_codex_message({"method": "item/commandExecution/requestApproval", "params": {"threadId": "t", "agentId": "a"}}, 1)[0]
        state = reduce_event(empty_runtime_state(), requested)
        self.assertEqual(state["agents"][0]["state"], "waiting_approval")
        resolved = normalize_codex_message({"method": "serverRequest/resolved", "params": {"threadId": "t", "agentId": "a"}}, 2)[0]
        state = reduce_event(state, resolved)
        self.assertEqual(state["agents"][0]["state"], "working")

    def test_parent_link_attention_and_sanitization(self):
        event = self.event(attention="error", state="failed", task_ids=["MC-009"])
        event["parentAgentId"] = "parent"
        event["prompt"] = "secret prompt"
        state = reduce_event(empty_runtime_state(), event)
        self.assertEqual(state["agents"][0]["parentAgentId"], "parent")
        self.assertEqual(state["attention"][0]["kind"], "error")
        self.assertNotIn("prompt", json.dumps(sanitize(event)))

    def test_future_provider_timestamp_is_clamped(self):
        event = normalize_codex_message(
            {"method": "turn/started", "params": {"threadId": "t", "timestamp": "2999-01-01T00:00:00Z"}},
            1,
        )[0]
        self.assertLess(datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")), datetime(2999, 1, 1, tzinfo=timezone.utc))

    def test_collab_tool_call_creates_parent_linked_subagent(self):
        message = {"method": "item/started", "params": {"threadId": "parent", "item": {"id": "i", "type": "collabToolCall", "senderThreadId": "parent", "receiverThreadIds": ["child"], "prompt": "must not persist"}}}
        event = normalize_codex_message(message, 1)[0]
        self.assertEqual(event["agentId"], "child")
        self.assertEqual(event["parentAgentId"], "parent")
        self.assertNotIn("prompt", json.dumps(event))

    def test_stale_disconnect_and_reconnect(self):
        state = reduce_event(empty_runtime_state("connected"), self.event())
        now = datetime(2026, 8, 9, 0, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(age_runtime_state(state, now)["agents"][0]["state"], "stale")
        later = datetime(2026, 8, 9, 0, 3, 1, tzinfo=timezone.utc)
        self.assertEqual(age_runtime_state(state, later)["agents"][0]["state"], "disconnected")
        reconnected = reduce_event(age_runtime_state(state, later), self.event(2, state="working"))
        self.assertEqual(reconnected["agents"][0]["state"], "working")

    def test_naive_timestamp_is_treated_as_utc(self):
        state = reduce_event(empty_runtime_state("connected"), self.event())
        state["agents"][0]["lastSeenAt"] = "2026-08-09T00:00:00"
        now = datetime(2026, 8, 9, 0, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(age_runtime_state(state, now)["agents"][0]["state"], "stale")

    def test_heartbeat_preserves_agent_state(self):
        state = reduce_event(empty_runtime_state("connected"), self.event(state="waiting_approval", attention="approval"))
        touched = touch_runtime_state(state)
        self.assertEqual(touched["agents"][0]["state"], "waiting_approval")
        self.assertEqual(touched["sourceStatus"], "connected")
        self.assertEqual(touched["agents"][0]["lastSeenAt"], state["agents"][0]["lastSeenAt"])

    def test_runtime_state_size_and_reducer_latency_budget(self):
        import time
        state = empty_runtime_state()
        started = time.perf_counter()
        for index in range(15):
            state = reduce_event(state, self.event(index + 1, f"agent-{index}", task_ids=[f"MC-{index:03d}"]))
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 0.25)
        self.assertLess(len(json.dumps(state).encode("utf-8")), 64 * 1024)

    def test_atomic_write_invalid_json_and_last_valid(self):
        with workspace_tempdir() as temp:
            path = Path(temp) / "runtime.json"
            valid = empty_runtime_state("file")
            write_runtime_state(path, valid)
            last = load_last_valid(path)
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(load_last_valid(path, last), valid)
            path.write_text("[]", encoding="utf-8")
            self.assertEqual(load_last_valid(path, last), valid)

    def test_runtime_persistence_uses_allowlisted_fields(self):
        with workspace_tempdir() as temp:
            path = Path(temp) / "runtime.json"
            state = reduce_event(empty_runtime_state(), self.event())
            state["userPrompt"] = "secret"
            state["agents"][0]["commandLine"] = "danger"
            state["agents"][0]["futureProviderPayload"] = {"text": "secret"}
            write_runtime_state(path, state)
            persisted = path.read_text(encoding="utf-8")
            self.assertNotIn("userPrompt", persisted)
            self.assertNotIn("commandLine", persisted)
            self.assertNotIn("futureProviderPayload", persisted)

    def test_connect_failure_preserves_last_valid_runtime_state(self):
        async def failing_connect(*args, **kwargs):
            raise ConnectionError("offline")

        websockets = types.ModuleType("websockets")
        websockets.__version__ = "16.1"
        asyncio_module = types.ModuleType("websockets.asyncio")
        client_module = types.ModuleType("websockets.asyncio.client")
        client_module.connect = failing_connect
        modules = {
            "websockets": websockets,
            "websockets.asyncio": asyncio_module,
            "websockets.asyncio.client": client_module,
        }
        with workspace_tempdir() as temp:
            workspace = Path(temp)
            path = workspace / "output/mission-center-runtime/runtime-state.json"
            original = empty_runtime_state("file")
            write_runtime_state(path, original)
            with mock.patch.dict(sys.modules, modules):
                with self.assertRaisesRegex(ConnectionError, "offline"):
                    asyncio.run(connect_live(workspace, "ws://127.0.0.1:9999", None))
            self.assertEqual(load_last_valid(path), original)

    def test_loopback_host_validation_and_server_family(self):
        for value in ("127.0.0.1:8765", "localhost", "[::1]:8765"):
            self.assertTrue(is_loopback_host_header(value))
        self.assertFalse(is_loopback_host_header("evil.example:8765"))
        self.assertEqual(loopback_server_type("127.0.0.1").address_family, socket.AF_INET)
        self.assertEqual(loopback_server_type("::1").address_family, socket.AF_INET6)

    def test_malformed_agent_is_normalized_before_aging(self):
        with workspace_tempdir() as temp:
            path = Path(temp) / "runtime.json"
            path.write_text('{"agents":[{}]}', encoding="utf-8")
            loaded = load_last_valid(path)
            aged = age_runtime_state(loaded, datetime.now(timezone.utc))
            self.assertEqual(aged["agents"][0]["agentId"], "unknown")

    def test_replay_unknown_event_and_explicit_link(self):
        with workspace_tempdir() as temp:
            workspace = Path(temp)
            (workspace / "MissionCenter").mkdir()
            (workspace / "MissionCenter/tasks.md").write_text("| ID | Title | Status |\n| --- | --- | --- |\n| MC-009 | Runtime | Ready |\n", encoding="utf-8")
            linked = link_task(workspace, "agent-a", ["MC-009"])
            self.assertEqual(linked["links"]["agent-a"], ["MC-009"])
            stream = workspace / "events.jsonl"
            messages = [{"method": "unknown/event", "params": {}}, {"method": "turn/started", "params": {"threadId": "t", "agentId": "agent-a"}}, {"method": "turn/completed", "params": {"threadId": "t", "agentId": "agent-a", "status": "completed"}}]
            stream.write_text("\n".join(json.dumps(item) for item in messages), encoding="utf-8")
            state = replay(workspace, stream)
            self.assertEqual(state["agents"][0]["state"], "finished")
            self.assertEqual(state["agents"][0]["taskIds"], ["MC-009"])
            task_text = (workspace / "MissionCenter/tasks.md").read_text(encoding="utf-8")
            self.assertIn("| MC-009 | Runtime | Ready |", task_text)


if __name__ == "__main__":
    unittest.main()
