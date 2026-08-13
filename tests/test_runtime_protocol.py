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

from mission_runtime import HudHandler, RecoverableTransportError, StdioTransport, codex_stdio_command, connect_live, is_loopback_host_header, link_task, loopback_server_type, packaged_runtime_requirements, replay, task_ids_from_workspace, validate_websockets_version
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

    def test_packaged_runtime_requirements_is_resolved_from_script_ancestors(self):
        with workspace_tempdir() as temp:
            root = Path(temp) / "plugin"
            script = root / "skills" / "mission-center" / "scripts" / "mission_runtime.py"
            script.parent.mkdir(parents=True)
            script.write_text("# placeholder\n", encoding="utf-8")
            requirements = root / "requirements-runtime.txt"
            requirements.write_text("websockets\n", encoding="utf-8")
            self.assertEqual(packaged_runtime_requirements(script), requirements.resolve())

    def test_packaged_runtime_requirements_has_safe_shallow_fallback(self):
        shallow = Path("C:/mission_runtime.py")
        self.assertEqual(packaged_runtime_requirements(shallow), shallow.resolve().parent / "requirements-runtime.txt")

    def test_task_link_parser_handles_escaped_pipe_and_crlf(self):
        with workspace_tempdir() as temp:
            workspace = Path(temp)
            mission = workspace / "MissionCenter"
            mission.mkdir()
            (mission / "tasks.md").write_bytes(
                b"| ID | Title | Status |\r\n| --- | --- | --- |\r\n| MC-009 | a\\|b | Ready |\r\n"
            )
            self.assertEqual(task_ids_from_workspace(workspace), {"MC-009"})

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
        for item_type in ("collabAgentToolCall", "collabToolCall"):
            with self.subTest(item_type=item_type):
                message = {"method": "item/started", "params": {"threadId": "parent", "item": {"id": "i", "type": item_type, "senderThreadId": "parent", "receiverThreadIds": ["child-a", "child-b"], "prompt": "must not persist"}}}
                events = normalize_codex_message(message, 1)
                self.assertEqual([event["agentId"] for event in events], ["child-a", "child-b"])
                self.assertTrue(all(event["parentAgentId"] == "parent" for event in events))
                self.assertNotIn("prompt", json.dumps(events))

    def test_collab_tool_call_does_not_infer_unverified_singular_receiver(self):
        message = {"method": "item/started", "params": {"threadId": "parent", "item": {"id": "i", "type": "collabAgentToolCall", "newThreadId": "child"}}}
        event = normalize_codex_message(message, 1)[0]
        self.assertEqual(event["agentId"], "parent")

    def test_stale_disconnect_and_reconnect(self):
        state = reduce_event(empty_runtime_state("connected"), self.event())
        now = datetime(2026, 8, 9, 0, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(age_runtime_state(state, now)["agents"][0]["state"], "stale")
        later = datetime(2026, 8, 9, 0, 3, 1, tzinfo=timezone.utc)
        aged = age_runtime_state(state, later)
        self.assertEqual(aged["agents"][0]["state"], "stale")
        self.assertEqual(aged["sourceStatus"], "connected")
        self.assertFalse(aged["agents"][0]["requiresAttention"])
        self.assertEqual(aged["attention"], [])
        disconnected = age_runtime_state(state, later, socket_closed=True)
        self.assertEqual(disconnected["agents"][0]["state"], "disconnected")
        reconnected = reduce_event(aged, self.event(2, state="working"))
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

    def test_unlinked_completion_is_silent_but_linked_completion_requires_verification(self):
        unlinked = normalize_codex_message(
            {"method": "turn/completed", "params": {"threadId": "t", "agentId": "a", "status": "completed"}},
            1,
        )[0]
        silent = reduce_event(empty_runtime_state("connected"), unlinked)
        self.assertFalse(silent["agents"][0]["requiresAttention"])
        self.assertEqual(silent["attention"], [])
        linked = normalize_codex_message(
            {"method": "turn/completed", "params": {"threadId": "t", "agentId": "a", "status": "completed", "taskIds": ["MC-009"]}},
            2,
        )[0]
        attention = reduce_event(silent, linked)
        self.assertTrue(attention["agents"][0]["requiresAttention"])
        self.assertEqual(attention["attention"][0]["kind"], "verification")

    def test_runtime_reference_limits_visibility_until_attach_contract_is_verified(self):
        reference = (ROOT / "skills/mission-center/references/runtime-agent-protocol.md").read_text(encoding="utf-8")
        for phrase in ("configured endpoint", "never global Codex Desktop monitoring", "thread/list", "thread/loaded/list", "thread/resume", "explicitly declared and tested"):
            self.assertIn(phrase, reference)

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

    def test_transport_is_closed_after_partial_connect_failure(self):
        class PartialTransport:
            def __init__(self):
                self.closed = False

            async def connect(self):
                raise ConnectionError("partial setup")

            async def close(self):
                self.closed = True

        with workspace_tempdir() as temp:
            transport = PartialTransport()
            with self.assertRaisesRegex(ConnectionError, "partial setup"):
                asyncio.run(connect_live(Path(temp), transport=transport))
            self.assertTrue(transport.closed)

    def test_initialize_ignores_notifications_and_malformed_frames_before_matching_response(self):
        class OrderedTransport:
            def __init__(self):
                self.messages = iter([
                    json.dumps({"method": "thread/started", "params": {"thread": {"id": "early"}}}),
                    "{broken",
                    json.dumps({"id": 1, "result": {"serverInfo": {"name": "codex"}}}),
                ])
                self.sent = []
                self.closed = False

            async def connect(self):
                return None

            async def send(self, message):
                self.sent.append(message)

            async def recv(self):
                try:
                    return next(self.messages)
                except StopIteration as exc:
                    raise ConnectionError("closed after initialize") from exc

            async def close(self):
                self.closed = True

        with workspace_tempdir() as temp:
            transport = OrderedTransport()
            with self.assertRaisesRegex(ConnectionError, "closed after initialize"):
                asyncio.run(connect_live(Path(temp), transport=transport))
            self.assertEqual([message.get("method") for message in transport.sent], ["initialize", "initialized"])
            self.assertTrue(transport.closed)

    def test_invalid_or_unsupported_live_payload_preserves_last_valid_runtime_state(self):
        class FakeSocket:
            def __init__(self, payload):
                self.payloads = iter([
                    json.dumps({"id": 1, "result": {}}),
                    payload,
                ])

            async def send(self, message):
                return None

            async def recv(self):
                try:
                    return next(self.payloads)
                except StopIteration as exc:
                    raise ConnectionError("closed") from exc

            async def close(self):
                return None

        async def fake_connect(*args, **kwargs):
            return FakeSocket(payload)

        websockets = types.ModuleType("websockets")
        websockets.__version__ = "16.1"
        asyncio_module = types.ModuleType("websockets.asyncio")
        client_module = types.ModuleType("websockets.asyncio.client")
        client_module.connect = fake_connect
        modules = {
            "websockets": websockets,
            "websockets.asyncio": asyncio_module,
            "websockets.asyncio.client": client_module,
        }
        for payload in ("{broken", json.dumps({"method": "unsupported/event", "params": {}})):
            with self.subTest(payload=payload), workspace_tempdir() as temp:
                workspace = Path(temp)
                path = workspace / "output/mission-center-runtime/runtime-state.json"
                original = empty_runtime_state("file")
                write_runtime_state(path, original)
                with mock.patch.dict(sys.modules, modules):
                    with self.assertRaisesRegex(ConnectionError, "closed"):
                        asyncio.run(connect_live(workspace, "ws://127.0.0.1:9999", None))
                self.assertEqual(load_last_valid(path), original)

    def test_loopback_host_validation_and_server_family(self):
        for value in ("127.0.0.1:8765", "localhost", "[::1]:8765"):
            self.assertTrue(is_loopback_host_header(value))
        self.assertFalse(is_loopback_host_header("evil.example:8765"))
        self.assertEqual(loopback_server_type("127.0.0.1").address_family, socket.AF_INET)
        self.assertEqual(loopback_server_type("::1").address_family, socket.AF_INET6)

    def test_hud_root_redirects_to_asset_directory_for_relative_images(self):
        handler = object.__new__(HudHandler)
        handler.path = "/"
        handler.headers = {"Host": "127.0.0.1:8765"}
        responses = []
        headers = []
        handler.send_response = lambda code: responses.append(code)
        handler.send_header = lambda name, value: headers.append((name, value))
        handler.end_headers = lambda: None
        with mock.patch.object(HudHandler.__mro__[1], "do_GET") as parent_get:
            handler.do_GET()
        self.assertEqual(responses, [302])
        self.assertIn(("Location", "/mission-center-assets/visual-summary.html"), headers)
        parent_get.assert_not_called()

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

    def test_thread_status_object_mappings_and_closed(self):
        cases = [
            ({"type": "active", "activeFlags": []}, "working", "none", "working"),
            ({"type": "idle"}, "idle", "none", "idle"),
            ({"type": "systemError"}, "failed", "error", "error"),
            ({"type": "notLoaded"}, "disconnected", "none", "idle"),
        ]
        for status_obj, expected_state, expected_attn, expected_kind in cases:
            with self.subTest(status=status_obj):
                msg = {"method": "thread/status/changed", "params": {"threadId": "t1", "agentId": "a1", "status": status_obj}}
                events = normalize_codex_message(msg, 1)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["state"], expected_state)
                self.assertEqual(events[0]["attention"], expected_attn)
                self.assertEqual(events[0].get("activityKind"), expected_kind)

        # thread/closed test
        closed_msg = {"method": "thread/closed", "params": {"threadId": "t1", "agentId": "a1"}}
        closed_events = normalize_codex_message(closed_msg, 2)
        self.assertEqual(len(closed_events), 1)
        self.assertEqual(closed_events[0]["state"], "disconnected")
        self.assertEqual(closed_events[0]["attention"], "none")

        # Unknown / malformed status must be ignored (return [])
        for bad_status in [{"type": "active"}, {"type": "unknown_type"}, "active_string", None, 123]:
            with self.subTest(bad_status=bad_status):
                bad_msg = {"method": "thread/status/changed", "params": {"threadId": "t1", "agentId": "a1", "status": bad_status}}
                self.assertEqual(normalize_codex_message(bad_msg, 3), [])

    def test_activity_kind_privacy_and_no_location(self):
        mappings = [
            ("commandExecution", "command_execution"),
            ("fileChange", "file_change"),
            ("mcpToolCall", "tool_use"),
            ("dynamicToolCall", "tool_use"),
            ("webSearch", "web_search"),
        ]
        for item_type, expected_kind in mappings:
            with self.subTest(item_type=item_type):
                msg = {
                    "method": "item/started",
                    "params": {
                        "threadId": "t1",
                        "agentId": "a1",
                        "item": {
                            "id": "i1",
                            "type": item_type,
                            "prompt": "secret prompt text",
                            "command": "secret command line",
                            "arguments": {"secret": "val"},
                        },
                    },
                }
                events = normalize_codex_message(msg, 1)
                self.assertEqual(len(events), 1)
                event = events[0]
                self.assertEqual(event.get("activityKind"), expected_kind)
                self.assertNotIn("location", event)
                dumped = json.dumps(event)
                self.assertNotIn("secret prompt text", dumped)
                self.assertNotIn("secret command line", dumped)
                self.assertNotIn("secret", dumped)

        # Test requestApproval -> waiting_input
        approval_msg = {
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "t1", "agentId": "a1", "command": "rm -rf /"},
        }
        app_events = normalize_codex_message(approval_msg, 2)
        self.assertEqual(app_events[0].get("activityKind"), "waiting_input")
        self.assertNotIn("location", app_events[0])

        unknown = normalize_codex_message(
            {"method": "item/started", "params": {"threadId": "t1", "item": {"id": "i2", "type": "futureItem"}}},
            3,
        )[0]
        self.assertEqual(unknown["activityKind"], "unknown")

        for method in ("thread/tokenUsage/updated", "heartbeat", "transport/activity"):
            self.assertEqual(normalize_codex_message({"method": method, "params": {"threadId": "t1"}}, 4), [])

    def test_stdio_transport_and_last_valid(self):
        async def run_test():
            reader = asyncio.StreamReader()
            reader.feed_data(json.dumps({"id": 1, "result": {"serverInfo": {"name": "codex"}}}).encode("utf-8") + b"\n")
            reader.feed_eof()

            written = []

            class MockWriter:
                def write(self, data):
                    written.append(data)

                async def drain(self):
                    pass

                def close(self):
                    pass

                async def wait_closed(self):
                    pass

            transport = StdioTransport(["codex"], reader, MockWriter())
            await transport.connect()
            await transport.send({"id": 1, "method": "initialize", "params": {}})
            msg1 = await transport.recv()
            self.assertIn("serverInfo", msg1)
            self.assertTrue(written[0].endswith(b"\n"))
            with self.assertRaises(ConnectionError):
                await transport.recv()
            await transport.close()

        asyncio.run(run_test())

    def test_stdio_transport_replaces_invalid_utf8_and_recovers_from_oversized_lines(self):
        async def run_test():
            reader = asyncio.StreamReader(limit=4)
            reader.feed_data(b"\xff\n")
            reader.feed_data(b"12345\n")
            reader.feed_eof()
            transport = StdioTransport(["codex"], reader, object())
            self.assertEqual(await transport.recv(), "\ufffd")
            with self.assertRaises(RecoverableTransportError):
                await transport.recv()

        asyncio.run(run_test())

    def test_stdio_transport_reports_packaged_executable_limit(self):
        async def run_test():
            transport = StdioTransport(["codex.exe"])
            with mock.patch(
                "mission_runtime.asyncio.create_subprocess_exec",
                side_effect=PermissionError("packaged app"),
            ):
                with self.assertRaisesRegex(RuntimeError, "standalone CLI executable"):
                    await transport.connect()

        asyncio.run(run_test())

    def test_stdio_command_is_explicit_and_never_uses_a_shell(self):
        command = codex_stdio_command("C:/Tools/codex.exe")
        self.assertEqual(command, ["C:/Tools/codex.exe", "app-server", "--listen", "stdio://"])
        with mock.patch("mission_runtime.os.name", "nt"), mock.patch(
            "mission_runtime.shutil.which", return_value="C:/Tools/codex"
        ), mock.patch("mission_runtime.os.path.isfile", return_value=True), mock.patch.dict(
            "os.environ", {}, clear=True
        ):
            self.assertEqual(
                codex_stdio_command(),
                ["C:/Tools/codex.exe", "app-server", "--listen", "stdio://"],
            )
        with mock.patch("mission_runtime.shutil.which", return_value=None), mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "--codex-executable"):
                codex_stdio_command()


if __name__ == "__main__":
    unittest.main()
