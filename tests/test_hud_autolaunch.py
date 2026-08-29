import json
import io
import ctypes
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import workspace_tempdir

ROOT = Path(__file__).parents[1]
SCRIPT_DIR = ROOT / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import hud_autolaunch as hud  # noqa: E402
import mission_runtime  # noqa: E402


class FakeProcess:
    pid = 12345

    def terminate(self):
        pass


class FakeWin32Function:
    def __init__(self, callback):
        self.callback = callback
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.callback(*args)


class FakeKernel32:
    def __init__(self, handle=0, exit_code=0, exit_success=True):
        self.OpenProcess = FakeWin32Function(lambda *_args: handle)
        self.GetExitCodeProcess = FakeWin32Function(
            lambda _handle, output: (setattr(output._obj, "value", exit_code) or exit_success)
        )
        self.CloseHandle = FakeWin32Function(lambda *_args: True)


def workspace(root: Path) -> Path:
    path = root / "workspace"
    (path / "MissionCenter").mkdir(parents=True)
    (path / "output" / "mission-center-assets").mkdir(parents=True)
    (path / "MissionCenter" / "tasks.md").write_text("tasks\n", encoding="utf-8")
    (path / "output" / "mission-center-assets" / "visual-summary.html").write_text(
        "<html>hud</html>\n", encoding="utf-8"
    )
    return path


def hook_payload(prompt: str, turn_id: str, cwd: Path, *, permission_mode: str = "default", session_id: str = "session-1") -> dict:
    return {
        "hook_event_name": "UserPromptSubmit",
        "session_id": session_id,
        "turn_id": turn_id,
        "cwd": str(cwd),
        "permission_mode": permission_mode,
        "prompt": prompt,
    }


class HudAutolaunchTests(unittest.TestCase):
    def test_launch_refreshes_stale_hud_and_restores_packaged_backgrounds(self):
        with workspace_tempdir("hud-refresh-") as temporary:
            root = workspace(Path(temporary))
            assets = root / "output" / "mission-center-assets"
            for name in hud.MANAGED_VISUAL_ASSETS - {"visual-summary.html"}:
                (assets / name).unlink(missing_ok=True)
            with patch.object(hud, "launch_server", return_value=FakeProcess()), patch.object(
                hud, "check_health", return_value=True
            ), patch.object(hud, "choose_port", return_value=43100), patch.object(
                hud, "open_browser", return_value=False
            ):
                result = hud.launch_or_reuse(root, open_ui=False)

            packaged = ROOT / "skills" / "mission-center" / "assets" / "visual-hub"
            for name in hud.MANAGED_VISUAL_ASSETS:
                self.assertEqual((assets / name).read_bytes(), (packaged / name).read_bytes())
            self.assertEqual(
                result["hudAssetFingerprint"],
                hud.read_metadata(root)["hudAssetFingerprint"],
            )

    def test_health_asset_fingerprint_tracks_currently_served_files(self):
        with workspace_tempdir("hud-assets-health-") as temporary:
            root = workspace(Path(temporary))
            expected = hud.sync_packaged_hud_assets(root)
            output = root / "output"
            self.assertEqual(mission_runtime.fingerprint_hud_assets(output), expected)
            asset = output / "mission-center-assets" / "visual-summary.html"
            asset.write_text(asset.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
            self.assertNotEqual(mission_runtime.fingerprint_hud_assets(output), expected)

    def test_explicit_matcher_and_false_positives(self):
        self.assertTrue(hud.invocation_matches("$mission-center"))
        self.assertTrue(hud.invocation_matches("plugin://mission-center/skills"))
        self.assertTrue(hud.invocation_matches("@Mission Center, please"))
        for prompt in (
            r"\\$mission-center",
            "mission-center",
            "xplugin://mission-center",
            "@Mission Centered",
            "Please explain `$mission-center`",
            "```text\nplugin://mission-center/skills\n```",
            "引用 `@Mission Center` 而非啟動",
            '引用 "$mission-center"',
            "不要啟動 $mission-center",
            "請不要啟動 $mission-center",
            "Do not invoke @Mission Center",
            "Please explain '$mission-center'",
        ):
            self.assertFalse(hud.invocation_matches(prompt), prompt)
        self.assertTrue(hud.invocation_matches("不要引用 `$mission-center`，請啟動 $mission-center"))
        for prompt in (
            "Don't hide the explicit $mission-center; it's required.",
            "It's ready: $mission-center should remain visible; don't remove it.",
        ):
            self.assertTrue(hud.invocation_matches(prompt), prompt)

    def test_malformed_oversize_and_missing_turn_are_noops(self):
        self.assertIsNone(hud.bounded_hook_input(type("S", (), {"read": lambda *args: b"{"})()))
        self.assertIsNone(
            hud.bounded_hook_input(
                type("S", (), {"read": lambda *args: b"x" * (hud.MAX_STDIN_BYTES + 1)})()
            )
        )
        self.assertEqual(
            hud.handle_hook({"hook_event_name": "UserPromptSubmit", "prompt": "$mission-center"}),
            {"status": "ignored", "reason": "missing-turn-id"},
        )

    def test_hook_rejects_wrong_event_and_invalid_required_fields(self):
        base = hook_payload("$mission-center", "turn-1", Path("."))
        for key, value, reason in (
            ("hook_event_name", "Stop", "invalid-hook-event"),
            ("prompt", None, "invalid-prompt"),
            ("session_id", "", "missing-session-id"),
            ("permission_mode", "unknown", "invalid-permission-mode"),
            ("cwd", 42, "invalid-cwd"),
        ):
            payload = dict(base)
            payload[key] = value
            with self.subTest(key=key):
                self.assertEqual(hud.handle_hook(payload), {"status": "ignored", "reason": reason})

    def test_plan_mode_does_not_touch_workspace_or_open_browser(self):
        payload = hook_payload("$mission-center", "turn-plan", Path("does-not-exist"), permission_mode="plan")
        with patch.object(hud, "launch_server") as spawn, patch.object(hud, "open_browser") as browser:
            self.assertEqual(hud.handle_hook(payload), {"status": "ignored", "reason": "plan-mode"})
        spawn.assert_not_called()
        browser.assert_not_called()

    def test_hook_defaults_to_portable_mode_without_external_browser(self):
        with workspace_tempdir("hud-portable-hook-") as temporary:
            root = workspace(Path(temporary))
            with patch.object(hud, "launch_server", return_value=FakeProcess()), patch.object(
                hud, "check_health", return_value=True
            ), patch.object(hud, "choose_port", return_value=43111), patch.object(
                hud, "open_browser", return_value=False
            ) as browser:
                result = hud.handle_hook(hook_payload("$mission-center", "turn-portable", root))
            self.assertEqual(result["status"], "launched")
            browser.assert_not_called()

    def test_same_turn_and_cooldown_without_prompt_state(self):
        with workspace_tempdir("hud-") as temporary:
            root = workspace(Path(temporary))
            with patch.object(hud, "launch_server", return_value=FakeProcess()), patch.object(
                hud, "check_health", return_value=True
            ), patch.object(hud, "choose_port", return_value=43101), patch.object(
                hud, "open_browser", return_value=False
            ), patch.object(hud.time, "time", side_effect=[100.0, 101.0]):
                first = hud.handle_hook(hook_payload("$mission-center", "turn-1", root))
                same = hud.handle_hook(hook_payload("$mission-center", "turn-1", root))
                cooldown = hud.handle_hook(hook_payload("$mission-center", "turn-2", root))
            self.assertEqual(first["status"], "launched")
            self.assertEqual(same["reason"], "same-turn")
            self.assertEqual(cooldown["status"], "cooldown")
            raw = (root / hud.RUNTIME_DIR / hud.METADATA_NAME).read_text(encoding="utf-8")
            self.assertNotIn("prompt", raw.casefold())
            self.assertNotIn("token", raw.casefold())
            with patch.object(hud, "check_health", return_value=True), patch.object(
                hud, "open_browser", return_value=False
            ):
                cross_conversation = hud.handle_hook(
                    hook_payload("$mission-center", "turn-1", root, session_id="session-2"),
                    open_ui=False,
                )
            self.assertNotEqual(cross_conversation.get("reason"), "same-turn")
            self.assertEqual(hud.read_metadata(root)["lastSessionId"], "session-2")

    def test_stale_metadata_launches_and_healthy_metadata_reuses(self):
        with workspace_tempdir("hud-") as temporary:
            root = workspace(Path(temporary))
            fingerprint = hud.workspace_fingerprint(root)
            hud.atomic_metadata(root, {"workspaceFingerprint": fingerprint, "port": 43102, "url": "http://127.0.0.1:43102/"})
            with patch.object(hud, "check_health", side_effect=[False, True, True]), patch.object(
                hud, "launch_server", return_value=FakeProcess()
            ), patch.object(hud, "choose_port", return_value=43103), patch.object(
                hud, "open_browser", return_value=False
            ):
                result = hud.launch_or_reuse(root, open_ui=False)
            self.assertEqual(result["status"], "launched")

            with patch.object(hud, "check_health", return_value=True), patch.object(
                hud, "open_browser", return_value=False
            ):
                last_launch = float(hud.read_metadata(root)["lastLaunchAt"])
                reused = hud.launch_or_reuse(root, now=last_launch + hud.COOLDOWN_SECONDS + 0.1, open_ui=False)
            self.assertEqual(reused["status"], "reused")

    def test_concurrent_hooks_same_workspace_launch_once_and_commit_latest_turn(self):
        with workspace_tempdir("hud-concurrent-") as temporary:
            root = workspace(Path(temporary))
            launch_started = threading.Event()
            release_launch = threading.Event()
            launches = []

            def launch(*args):
                launches.append(args)
                launch_started.set()
                self.assertTrue(release_launch.wait(2))
                return FakeProcess()

            results = {}

            def submit(turn_id):
                results[turn_id] = hud.handle_hook(
                    hook_payload("$mission-center", turn_id, root),
                    open_ui=False,
                )

            with patch.object(hud, "launch_server", side_effect=launch), patch.object(
                hud, "check_health", return_value=True
            ), patch.object(hud, "choose_port", return_value=43104), patch.object(
                hud, "open_browser", return_value=False
            ), patch.object(hud, "_process_creation_identity", return_value="test-process"):
                first = threading.Thread(target=submit, args=("turn-1",))
                second = threading.Thread(target=submit, args=("turn-2",))
                first.start()
                self.assertTrue(launch_started.wait(2))
                second.start()
                release_launch.set()
                # The production lock intentionally permits a five-second health
                # transaction; give loaded CI hosts enough time to observe reuse.
                first.join(8)
                second.join(8)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(len(launches), 1)
            self.assertEqual(results["turn-1"]["status"], "launched")
            self.assertIn(results["turn-2"]["status"], {"cooldown", "reused"})
            metadata = hud.read_metadata(root)
            self.assertEqual(metadata["lastTurnId"], "turn-2")
            self.assertEqual(metadata["port"], 43104)

    def test_concurrent_hooks_different_workspaces_are_isolated(self):
        with workspace_tempdir("hud-isolated-") as temporary:
            first_root = workspace(Path(temporary) / "first")
            second_root = workspace(Path(temporary) / "second")
            launches = []

            def launch(workspace_path, port, nonce):
                launches.append((Path(workspace_path), port, nonce))
                return FakeProcess()

            with patch.object(hud, "launch_server", side_effect=launch), patch.object(
                hud, "check_health", return_value=True
            ), patch.object(hud, "choose_port", side_effect=[43105, 43106]), patch.object(
                hud, "open_browser", return_value=False
            ), patch.object(hud, "_process_creation_identity", return_value="test-process"):
                results = [
                    hud.handle_hook(hook_payload("$mission-center", "first", first_root), open_ui=False),
                    hud.handle_hook(hook_payload("$mission-center", "second", second_root), open_ui=False),
                ]

            self.assertEqual([result["status"] for result in results], ["launched", "launched"])
            self.assertEqual({item[0] for item in launches}, {first_root.resolve(), second_root.resolve()})
            first_metadata = hud.read_metadata(first_root)
            second_metadata = hud.read_metadata(second_root)
            self.assertNotEqual(first_metadata["workspaceFingerprint"], second_metadata["workspaceFingerprint"])
            self.assertEqual(first_metadata["lastTurnId"], "first")
            self.assertEqual(second_metadata["lastTurnId"], "second")
            self.assertNotEqual(first_metadata["port"], second_metadata["port"])

    def test_metadata_url_is_rebuilt_from_validated_loopback_port(self):
        with workspace_tempdir("hud-url-") as temporary:
            root = workspace(Path(temporary))
            fingerprint = hud.workspace_fingerprint(root)
            asset_fingerprint = hud.sync_packaged_hud_assets(root)
            hud.atomic_metadata(
                root,
                {
                    "workspaceFingerprint": fingerprint,
                    "hudAssetFingerprint": asset_fingerprint,
                    "port": 43107,
                    "sessionNonce": "nonce",
                    "url": "https://attacker.invalid/steal",
                    "lastLaunchAt": 0,
                },
            )
            with patch.object(hud, "check_health", return_value=True), patch.object(
                hud, "open_browser", return_value=False
            ) as browser:
                result = hud.launch_or_reuse(root, now=hud.COOLDOWN_SECONDS + 1, open_ui=True)
            self.assertEqual(result["status"], "reused")
            self.assertEqual(result["url"], "http://127.0.0.1:43107/")
            self.assertEqual(result["hudAssetFingerprint"], hud.read_metadata(root)["hudAssetFingerprint"])
            self.assertEqual(result["presentation"]["status"], "not_supported")
            browser.assert_called_once_with("http://127.0.0.1:43107/")

    def test_metadata_reuse_drops_unknown_legacy_fields(self):
        with workspace_tempdir("hud-metadata-") as temporary:
            root = workspace(Path(temporary))
            fingerprint = hud.workspace_fingerprint(root)
            asset_fingerprint = hud.sync_packaged_hud_assets(root)
            metadata = {
                "workspaceFingerprint": fingerprint,
                "hudAssetFingerprint": asset_fingerprint,
                "port": 43109,
                "sessionNonce": "nonce",
                "lastLaunchAt": 0,
                "token": "secret",
                "legacy": {"password": "secret"},
            }
            (root / hud.RUNTIME_DIR).mkdir(parents=True, exist_ok=True)
            (root / hud.RUNTIME_DIR / hud.METADATA_NAME).write_text(
                json.dumps(metadata), encoding="utf-8"
            )
            with patch.object(hud, "check_health", return_value=True), patch.object(
                hud, "open_browser", return_value=False
            ):
                result = hud.launch_or_reuse(root, now=hud.COOLDOWN_SECONDS + 1, open_ui=False)
            self.assertEqual(result["status"], "reused")
            raw = (root / hud.RUNTIME_DIR / hud.METADATA_NAME).read_text(encoding="utf-8")
            self.assertNotIn("token", raw)
            self.assertNotIn("legacy", raw)

    def test_health_rejects_redirects_and_nonce_mismatch(self):
        redirect = hud.urllib.error.HTTPError(
            "http://127.0.0.1:43108/_mission-center/health",
            302,
            "redirect",
            {"Location": "http://attacker.invalid/"},
            None,
        )
        with patch.object(hud._NO_REDIRECT_OPENER, "open", side_effect=redirect):
            self.assertFalse(hud.check_health(43108, "fingerprint", "nonce", "assets"))

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b'{"service":"mission-center-hud","workspaceFingerprint":"fingerprint","sessionNonce":"wrong"}'

        with patch.object(hud._NO_REDIRECT_OPENER, "open", return_value=Response()):
            self.assertFalse(hud.check_health(43108, "fingerprint", "nonce", "assets"))

        class LegacyResponse(Response):
            def read(self, _limit):
                return b'{"service":"mission-center-hud","workspaceFingerprint":"fingerprint","sessionNonce":"nonce"}'

        with patch.object(hud._NO_REDIRECT_OPENER, "open", return_value=LegacyResponse()):
            self.assertFalse(hud.check_health(43108, "fingerprint", "nonce", "assets"))

    def test_health_requires_matching_asset_fingerprint(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b'{"service":"mission-center-hud","workspaceFingerprint":"fingerprint","sessionNonce":"nonce","hudAssetFingerprint":"other"}'

        with patch.object(hud._NO_REDIRECT_OPENER, "open", return_value=Response()):
            self.assertFalse(hud.check_health(43108, "fingerprint", "nonce", "assets"))

    def test_atomic_metadata_uses_randomized_mkstemp_and_cleans_tempfile(self):
        with workspace_tempdir("hud-atomic-") as temporary:
            root = workspace(Path(temporary))
            temporary_names = []
            real_mkstemp = hud.tempfile.mkstemp

            def mkstemp(*args, **kwargs):
                result = real_mkstemp(*args, **kwargs)
                temporary_names.append(Path(result[1]))
                return result

            with patch.object(hud.tempfile, "mkstemp", side_effect=mkstemp):
                hud.atomic_metadata(root, {"value": "safe"})
            self.assertEqual(len(temporary_names), 1)
            self.assertNotEqual(
                temporary_names[0].name,
                f".{hud.METADATA_NAME}.{hud.os.getpid()}.tmp",
            )
            self.assertFalse(temporary_names[0].exists())

    def test_atomic_metadata_bytes_are_deterministic_across_field_order(self):
        with workspace_tempdir("hud-atomic-order-") as temporary:
            root = workspace(Path(temporary))
            first = {
                "url": "http://127.0.0.1:43108/",
                "port": 43108,
                "workspaceFingerprint": "fingerprint",
            }
            second = {
                "workspaceFingerprint": "fingerprint",
                "port": 43108,
                "url": "http://127.0.0.1:43108/",
            }
            with patch.object(hud, "_sanitize_metadata", side_effect=lambda value: value):
                hud.atomic_metadata(root, first)
                first_bytes = hud.metadata_path(root).read_bytes()
                hud.atomic_metadata(root, second)
                second_bytes = hud.metadata_path(root).read_bytes()
            self.assertEqual(first_bytes, second_bytes)

    def test_lock_creation_identity_detects_pid_reuse(self):
        with workspace_tempdir("hud-lock-identity-") as temporary:
            root = workspace(Path(temporary))
            lock = hud.lock_path(root)
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text(
                json.dumps({"pid": 123, "processIdentity": "old-process", "token": "old"}),
                encoding="ascii",
            )
            with patch.object(hud, "_process_creation_identity", return_value="new-process"), patch.object(
                hud, "_pid_alive", return_value=True
            ):
                self.assertFalse(hud._existing_lock_state(lock))

    def test_lock_retries_when_lock_vanishes_during_observation(self):
        with workspace_tempdir("hud-lock-race-") as temporary:
            root = workspace(Path(temporary))
            lock = hud.MetadataLock(root)
            lock.path.parent.mkdir(parents=True, exist_ok=True)
            lock.path.write_text("999999\n", encoding="ascii")
            observations = 0

            def vanish_during_observation(path):
                nonlocal observations
                observations += 1
                path.unlink(missing_ok=True)
                return None

            with patch.object(hud, "_existing_lock_state", side_effect=vanish_during_observation):
                with lock:
                    pass
            self.assertEqual(observations, 1)

    def test_metadata_lock_reclaims_dead_plain_and_json_pid_locks(self):
        with workspace_tempdir("hud-lock-") as temporary:
            root = workspace(Path(temporary))
            for raw in ("999999\n", json.dumps({"pid": 999999, "token": "old"})):
                lock = hud.lock_path(root)
                lock.parent.mkdir(parents=True, exist_ok=True)
                lock.write_text(raw, encoding="ascii")
                with patch.object(hud, "_pid_alive", return_value=False):
                    with hud.MetadataLock(root):
                        self.assertEqual(json.loads(lock.read_text(encoding="ascii"))["pid"], hud.os.getpid())
                self.assertFalse(lock.exists())

    def test_metadata_lock_fails_closed_for_active_and_malformed_locks(self):
        with workspace_tempdir("hud-lock-") as temporary:
            root = workspace(Path(temporary))
            lock = hud.lock_path(root)
            lock.parent.mkdir(parents=True, exist_ok=True)
            active = json.dumps({"pid": hud.os.getpid(), "token": "active"})
            for raw, alive in ((active, True), ("not-a-pid", None)):
                lock.write_text(raw, encoding="ascii")
                with patch.object(hud, "_pid_alive", return_value=alive):
                    with self.assertRaises(TimeoutError):
                        with hud.MetadataLock(root):
                            pass
                self.assertEqual(lock.read_text(encoding="ascii"), raw)

    def test_metadata_lock_retries_a_stale_cleanup_race(self):
        with workspace_tempdir("hud-lock-") as temporary:
            root = workspace(Path(temporary))
            lock = hud.lock_path(root)
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("999999\n", encoding="ascii")
            remove_calls = 0

            def remove_after_race(path: Path) -> bool:
                nonlocal remove_calls
                remove_calls += 1
                if remove_calls == 1:
                    return False
                path.unlink()
                return True

            with patch.object(hud, "_pid_alive", return_value=False), patch.object(
                hud, "_remove_stale_lock", side_effect=remove_after_race
            ), patch.object(hud.time, "sleep") as sleep:
                with hud.MetadataLock(root):
                    self.assertTrue(lock.exists())
                sleep.assert_called_once_with(hud.LOCK_RETRY_DELAY_SECONDS)

    def test_metadata_lock_does_not_remove_replaced_lock_on_exit(self):
        with workspace_tempdir("hud-lock-") as temporary:
            root = workspace(Path(temporary))
            lock = hud.MetadataLock(root)
            lock.__enter__()
            try:
                lock.handle.close()
                replacement = json.dumps({"pid": hud.os.getpid(), "token": "replacement"})
                lock.path.write_text(replacement, encoding="ascii")
                lock.__exit__(None, None, None)
                self.assertEqual(lock.path.read_text(encoding="ascii"), replacement)
            finally:
                lock.path.unlink(missing_ok=True)

    def test_metadata_lock_retries_release_after_transient_unlink_denial(self):
        with workspace_tempdir("hud-lock-release-race-") as temporary:
            root = workspace(Path(temporary))
            lock = hud.MetadataLock(root)
            original_unlink = Path.unlink
            calls = 0

            def unlink_with_transient_denial(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise PermissionError("transient sharing violation")
                return original_unlink(lock.path, *args, **kwargs)

            with patch.object(Path, "unlink", side_effect=unlink_with_transient_denial), patch.object(
                hud.time, "sleep"
            ) as sleep:
                with lock:
                    pass
            self.assertEqual(calls, 2)
            sleep.assert_called_once_with(hud.LOCK_RETRY_DELAY_SECONDS)
            self.assertFalse(lock.path.exists())

    def test_windows_pid_probe_configures_64_bit_handle_signatures(self):
        handle = 0x123456789ABCDEF0
        kernel32 = FakeKernel32(handle=handle, exit_code=259)
        with patch.object(hud.os, "name", "nt"), patch.object(
            hud.ctypes, "WinDLL", create=True, return_value=kernel32
        ), patch.object(hud.ctypes, "get_last_error", create=True, return_value=0):
            self.assertTrue(hud._pid_alive(42))
        self.assertEqual(kernel32.OpenProcess.argtypes, [hud.wintypes.DWORD, hud.wintypes.BOOL, hud.wintypes.DWORD])
        self.assertIs(kernel32.OpenProcess.restype, hud.wintypes.HANDLE)
        self.assertEqual(
            kernel32.GetExitCodeProcess.argtypes,
            [hud.wintypes.HANDLE, ctypes.POINTER(hud.wintypes.DWORD)],
        )
        self.assertIs(kernel32.GetExitCodeProcess.restype, hud.wintypes.BOOL)
        self.assertEqual(kernel32.CloseHandle.argtypes, [hud.wintypes.HANDLE])
        self.assertIs(kernel32.CloseHandle.restype, hud.wintypes.BOOL)
        self.assertEqual(kernel32.CloseHandle.calls, [(handle,)])

    def test_windows_pid_probe_distinguishes_dead_and_unknown_open_errors(self):
        for error, expected in ((87, False), (5, None)):
            with self.subTest(error=error):
                kernel32 = FakeKernel32(handle=0)
                with patch.object(hud.os, "name", "nt"), patch.object(
                    hud.ctypes, "WinDLL", create=True, return_value=kernel32
                ), patch.object(hud.ctypes, "get_last_error", create=True, return_value=error):
                    self.assertIs(hud._pid_alive(42), expected)
                self.assertEqual(kernel32.GetExitCodeProcess.calls, [])
                self.assertEqual(kernel32.CloseHandle.calls, [])

    def test_windows_pid_probe_handles_finished_process(self):
        kernel32 = FakeKernel32(handle=0x123456789ABCDEF0, exit_code=0)
        with patch.object(hud.os, "name", "nt"), patch.object(
            hud.ctypes, "WinDLL", create=True, return_value=kernel32
        ), patch.object(hud.ctypes, "get_last_error", create=True, return_value=0):
            self.assertFalse(hud._pid_alive(42))
        self.assertEqual(len(kernel32.CloseHandle.calls), 1)

    def test_missing_workspace_is_noop_and_tasks_bytes_are_unchanged(self):
        with workspace_tempdir("hud-") as temporary:
            root = Path(temporary) / "missing"
            self.assertEqual(hud.launch_or_reuse(root), {"status": "unavailable", "reason": "workspace-assets-missing"})
            root = workspace(Path(temporary))
            before = (root / "MissionCenter" / "tasks.md").read_bytes()
            with patch.object(hud, "launch_server") as spawn, patch.object(
                hud, "check_health", return_value=True
            ):
                hud.launch_or_reuse(root, open_ui=False)
            self.assertEqual(before, (root / "MissionCenter" / "tasks.md").read_bytes())
            spawn.assert_called_once()

    def test_workspace_identity_survives_normal_task_updates(self):
        with workspace_tempdir("hud-") as temporary:
            root = workspace(Path(temporary))
            before = hud.workspace_fingerprint(root)
            (root / "MissionCenter" / "tasks.md").write_text("updated tasks\n", encoding="utf-8")
            self.assertEqual(before, hud.workspace_fingerprint(root))
            self.assertEqual(before, mission_runtime.fingerprint_workspace(root))

    def test_browser_failure_and_headless_are_nonfatal(self):
        with patch.object(hud, "is_headless", return_value=True), patch.object(hud.webbrowser, "open") as browser:
            self.assertFalse(hud.open_browser("http://127.0.0.1:1/"))
            browser.assert_not_called()
        with patch.object(hud, "is_headless", return_value=False), patch.object(
            hud.webbrowser, "open", side_effect=RuntimeError("no browser")
        ):
            self.assertFalse(hud.open_browser("http://127.0.0.1:1/"))

    def test_health_payload_contract(self):
        fingerprint = "abc123"
        self.assertEqual(
            mission_runtime.health_payload(fingerprint),
            {"service": "mission-center-hud", "workspaceFingerprint": fingerprint},
        )
        self.assertEqual(
            mission_runtime.health_payload(fingerprint, session_nonce="nonce", hud_asset_fingerprint="assets"),
            {
                "service": "mission-center-hud",
                "workspaceFingerprint": fingerprint,
                "sessionNonce": "nonce",
                "hudAssetFingerprint": "assets",
            },
        )

    def test_hook_specific_output_is_formal_and_truthful(self):
        output = hud.hook_specific_output(
            {"status": "reused", "url": "http://127.0.0.1:43111/"}
        )
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("http://127.0.0.1:43111/", context)
        self.assertIn("built-in sidebar or preview surface", context)
        self.assertIn("cannot guarantee", context)
        self.assertIn("Do not rely on Chrome", context)
        self.assertIsNone(hud.hook_specific_output({"status": "unavailable"}))
        self.assertIsNone(hud.hook_specific_output({"status": "launched", "url": "https://attacker.invalid/"}))

    def test_side_panel_intent_is_bounded_and_workspace_singleton_keyed(self):
        fingerprint = "a" * 64
        assets = "b" * 64
        intent = hud.build_side_panel_intent("http://127.0.0.1:43111/", fingerprint, assets)
        self.assertEqual(intent["type"], "mission-center/hud-side-panel")
        self.assertEqual(intent["surface"], "codex-sidebar-or-preview")
        self.assertEqual(intent["mode"], "reuse")
        self.assertEqual(intent["reuseKey"], f"mission-center-hud:{fingerprint}")
        self.assertFalse(intent["externalBrowser"])
        self.assertIsNone(hud.build_side_panel_intent("https://attacker.invalid/", fingerprint, assets))

    def test_successful_launch_writes_side_panel_manifest_without_browser(self):
        with workspace_tempdir("hud-side-panel-") as temporary:
            root = workspace(Path(temporary))
            with patch.object(hud, "launch_server", return_value=FakeProcess()), patch.object(
                hud, "check_health", return_value=True
            ), patch.object(hud, "choose_port", return_value=43114), patch.object(
                hud, "open_browser"
            ) as browser:
                result = hud.launch_or_reuse(root)
            browser.assert_not_called()
            self.assertEqual(result["presentation"]["status"], "not_requested")
            self.assertEqual(result["sidePanelIntent"], hud.read_side_panel_manifest(root))
            self.assertEqual(
                hud.read_metadata(root)["instanceKey"],
                result["sidePanelIntent"]["reuseKey"],
            )

    def test_side_panel_manifest_rejects_external_or_tampered_intent(self):
        with workspace_tempdir("hud-side-panel-invalid-") as temporary:
            root = workspace(Path(temporary))
            path = hud.side_panel_manifest_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "type": "mission-center/hud-side-panel",
                        "version": "1.0",
                        "surface": "codex-sidebar-or-preview",
                        "mode": "reuse",
                        "reuseKey": "mission-center-hud:" + "a" * 64,
                        "url": "https://attacker.invalid/",
                        "workspaceFingerprint": "a" * 64,
                        "hudAssetFingerprint": "b" * 64,
                        "externalBrowser": True,
                    }
                ),
                encoding="utf-8",
            )
            self.assertIsNone(hud.read_side_panel_manifest(root))

    def test_healthy_reuse_is_singleton_and_does_not_reopen_or_rewrite_manifest(self):
        with workspace_tempdir("hud-side-panel-reuse-") as temporary:
            root = workspace(Path(temporary))
            with patch.object(hud, "launch_server", return_value=FakeProcess()) as launch, patch.object(
                hud, "check_health", return_value=True
            ), patch.object(hud, "choose_port", return_value=43115), patch.object(
                hud, "open_browser"
            ) as browser, patch.object(hud, "atomic_side_panel_manifest", wraps=hud.atomic_side_panel_manifest) as write_manifest:
                first = hud.launch_or_reuse(root, now=100.0)
                reused = hud.launch_or_reuse(root, now=104.0)
            self.assertEqual(first["status"], "launched")
            self.assertEqual(reused["status"], "reused")
            launch.assert_called_once()
            browser.assert_not_called()
            write_manifest.assert_called_once()
            self.assertEqual(first["sidePanelIntent"], reused["sidePanelIntent"])
            self.assertEqual(reused["presentation"]["status"], "not_requested")

    def test_contracts(self):
        hook_config = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        groups = hook_config["hooks"]["UserPromptSubmit"]
        self.assertEqual(len(groups), 1)
        handlers = groups[0]["hooks"]
        self.assertEqual(len(handlers), 2)
        self.assertEqual(handlers[0]["type"], "command")
        self.assertFalse(handlers[0]["async"])
        self.assertIn("bin/mission-center\" hook route", handlers[0]["command"])
        self.assertNotIn("python", handlers[0]["command"].lower())
        self.assertEqual(handlers[1]["type"], "command")
        self.assertTrue(handlers[1]["async"])
        self.assertIn("bin/mission-center\" hook hud", handlers[1]["command"])
        self.assertNotIn("python", handlers[1]["command"].lower())
        self.assertIn("commandWindows", handlers[0])
        self.assertIn("commandWindows", handlers[1])
        self.assertLessEqual((ROOT / "skills" / "mission-center" / "SKILL.md").stat().st_size, 6144)
        source = (SCRIPT_DIR / "hud_autolaunch.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertIn("--open-browser", source)
        self.assertIn("open_ui: bool = False", source)

    def test_hook_cli_is_silent(self):
        payload = json.dumps(
            hook_payload("ordinary text", "turn-quiet", Path("."))
        ).encode("utf-8")
        stdin = type("Input", (), {"buffer": io.BytesIO(payload)})()
        stdout = io.StringIO()
        with patch.object(sys, "stdin", stdin), patch.object(sys, "stdout", stdout):
            self.assertEqual(hud.main(["hook", "--no-browser"]), 0)
        self.assertEqual(stdout.getvalue(), "")

    def test_hook_cli_emits_formal_context_and_defaults_to_no_browser(self):
        payload = hook_payload("$mission-center", "turn-cli", Path("."))
        stdout = io.StringIO()
        with patch.object(hud, "bounded_hook_input", return_value=payload), patch.object(
            hud,
            "handle_hook",
            return_value={"status": "launched", "url": "http://127.0.0.1:43112/"},
        ) as handle, patch.object(sys, "stdout", stdout):
            self.assertEqual(hud.main(["hook"]), 0)
        handle.assert_called_once_with(payload, open_ui=False)
        output = json.loads(stdout.getvalue())
        self.assertIn("additionalContext", output["hookSpecificOutput"])
        self.assertIn("http://127.0.0.1:43112/", output["hookSpecificOutput"]["additionalContext"])

    def test_show_defaults_to_no_browser_and_requires_opt_in(self):
        result = {"status": "launched", "url": "http://127.0.0.1:43113/"}
        with patch.object(hud, "launch_or_reuse", return_value=result) as launch, patch.object(
            hud, "open_browser"
        ) as browser:
            self.assertEqual(hud.main(["show", "--workspace", "."]), 0)
        launch.assert_called_once_with(Path("."), open_ui=False)
        browser.assert_not_called()
        with patch.object(hud, "launch_or_reuse", return_value=result) as launch:
            self.assertEqual(hud.main(["show", "--workspace", ".", "--open-browser"]), 0)
        launch.assert_called_once_with(Path("."), open_ui=True)


if __name__ == "__main__":
    unittest.main()
