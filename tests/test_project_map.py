import json
import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import workspace_tempdir

ROOT = Path(__file__).parents[1]
SCRIPT_DIR = ROOT / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from project_map import (  # noqa: E402
    HTML_NAME,
    JSON_NAME,
    MANIFEST_NAME,
    LOCK_NAME,
    ProjectMapLock,
    build_project_map,
    canonical_fingerprint,
    publish_project_map,
    validate_project_map,
    validate_published_manifest,
)
import project_map  # noqa: E402


def make_workspace(root: Path, *, traditional: bool = False) -> Path:
    workspace = root / ("zh" if traditional else "en")
    mission = workspace / "MissionCenter"
    mission.mkdir(parents=True)
    (mission / "project.md").write_text(
        "# 任務地圖\n\n目標：跨語言 project map\n" if traditional else "# Project Map\n\nGoal: cross-language project map\n",
        encoding="utf-8",
    )
    header = "| ID | 標題 | 類型 | 父層 | 優先級 | 狀態 | 負責人 | 依賴 | |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n" if traditional else "| ID | Title | Type | Parent | Priority | Status | Owner | Depends on | Next action |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
    rows = (
        "| T-001 | 根任務 | Epic |  | P0 | Ready | Codex |  | 開始 |\n| T-002 | 子任務 | Task | T-001 | P1 | Done | Codex | T-001 | 完成 |\n"
        if traditional
        else "| T-001 | Root task | Epic |  | P0 | Ready | Codex |  | Start |\n| T-002 | Child task | Task | T-001 | P1 | Done | Codex | T-001 | Done |\n"
    )
    (mission / "tasks.md").write_text(header + rows, encoding="utf-8")
    return workspace


class ProjectMapTests(unittest.TestCase):
    def test_builds_cross_language_maps_with_canonical_fingerprint_and_edges(self):
        with workspace_tempdir("project-map-") as temporary:
            for traditional in (False, True):
                workspace = make_workspace(Path(temporary), traditional=traditional)
                value = build_project_map(workspace, generated_at="2026-08-26T00:00:00Z")
                self.assertEqual(value["language"], "zh-TW" if traditional else "en")
                self.assertEqual([node["id"] for node in value["nodes"]], ["T-001", "T-002"])
                self.assertEqual(value["edges"], [{"from": "T-001", "to": "T-002", "kind": "parent"}, {"from": "T-001", "to": "T-002", "kind": "dependsOn"}])
                self.assertEqual(value["sourceFingerprint"], canonical_fingerprint(workspace / "MissionCenter"))

    def test_publish_is_atomic_and_keeps_runtime_state_separate(self):
        with workspace_tempdir("project-map-") as temporary:
            workspace = make_workspace(Path(temporary))
            result = publish_project_map(workspace, generated_at="2026-08-26T00:00:00Z")
            output = workspace / "output" / "mission-center-project-map"
            self.assertTrue((output / JSON_NAME).is_file())
            self.assertTrue((output / HTML_NAME).is_file())
            self.assertTrue((output / MANIFEST_NAME).is_file())
            self.assertFalse((output / LOCK_NAME).exists())
            self.assertFalse((workspace / "output" / "mission-center-runtime").exists())
            value = json.loads((output / JSON_NAME).read_text(encoding="utf-8"))
            manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(validate_published_manifest(output), manifest)
            self.assertEqual(value["sourceFingerprint"], result["sourceFingerprint"])
            self.assertEqual(value["generation"], result["generation"])
            self.assertEqual(manifest["generation"], value["generation"])
            self.assertEqual(manifest["sourceFingerprint"], value["sourceFingerprint"])
            for name in (JSON_NAME, HTML_NAME):
                self.assertEqual(
                    manifest["files"][name],
                    hashlib.sha256((output / name).read_bytes()).hexdigest(),
                )
            self.assertIn("T-002", (output / HTML_NAME).read_text(encoding="utf-8"))
            self.assertEqual(list(output.glob("*.tmp")), [])

    def test_build_reads_each_bounded_source_once_and_publish_aborts_on_change(self):
        with workspace_tempdir("project-map-snapshot-") as temporary:
            workspace = make_workspace(Path(temporary))
            with patch.object(project_map, "_read_source", wraps=project_map._read_source) as reader:
                build_project_map(workspace, generated_at="2026-08-26T00:00:00Z")
            self.assertEqual(reader.call_count, 2)
            with patch.object(project_map, "canonical_fingerprint", return_value="0" * 64):
                with self.assertRaisesRegex(RuntimeError, "sources changed"):
                    publish_project_map(workspace, generated_at="2026-08-26T00:00:00Z")
            self.assertFalse((workspace / "output" / "mission-center-project-map" / JSON_NAME).exists())

    def test_manifest_commit_marker_rejects_interrupted_mixed_pair(self):
        with workspace_tempdir("project-map-manifest-") as temporary:
            workspace = make_workspace(Path(temporary))
            publish_project_map(workspace, generated_at="2026-08-26T00:00:00Z")
            mission = workspace / "MissionCenter"
            tasks = mission / "tasks.md"
            tasks.write_text(tasks.read_text(encoding="utf-8").replace("Child task", "Changed task"), encoding="utf-8")
            output = workspace / "output" / "mission-center-project-map"
            original = project_map._atomic_write
            calls = 0

            def fail_on_html(path, content):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected HTML publish failure")
                return original(path, content)

            with patch.object(project_map, "_atomic_write", side_effect=fail_on_html):
                with self.assertRaises(OSError):
                    publish_project_map(workspace, generated_at="2026-08-26T00:00:00Z")
            with self.assertRaisesRegex(ValueError, "manifest"):
                validate_published_manifest(output)

    def test_publish_does_not_commit_manifest_after_post_build_source_change(self):
        with workspace_tempdir("project-map-post-change-") as temporary:
            workspace = make_workspace(Path(temporary))
            fingerprint = canonical_fingerprint(workspace / "MissionCenter")
            output = workspace / "output" / "mission-center-project-map"
            with patch.object(project_map, "canonical_fingerprint", side_effect=[fingerprint, "0" * 64]):
                with self.assertRaisesRegex(RuntimeError, "during project map publish"):
                    publish_project_map(workspace, generated_at="2026-08-26T00:00:00Z")
            self.assertFalse((output / MANIFEST_NAME).exists())

    def test_line_endings_do_not_change_fingerprint_but_source_change_does(self):
        with workspace_tempdir("project-map-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            before = canonical_fingerprint(mission)
            for path in (mission / "project.md", mission / "tasks.md"):
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            self.assertEqual(canonical_fingerprint(mission), before)
            (mission / "tasks.md").write_text((mission / "tasks.md").read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertNotEqual(canonical_fingerprint(mission), before)

    def test_active_lock_fails_closed_and_does_not_remove_owner_lock(self):
        with workspace_tempdir("project-map-lock-") as temporary:
            path = Path(temporary) / "map.lock"
            with ProjectMapLock(path):
                with self.assertRaises(TimeoutError):
                    with ProjectMapLock(path):
                        pass
                self.assertTrue(path.exists())
            self.assertFalse(path.exists())

    def test_stale_lock_fails_closed_and_requires_explicit_recovery(self):
        with workspace_tempdir("project-map-stale-lock-") as temporary:
            path = Path(temporary) / "map.lock"
            stale = {"pid": 999999, "token": "dead-owner"}
            path.write_text(json.dumps(stale), encoding="utf-8")
            with self.assertRaisesRegex(TimeoutError, "explicit owner recovery"):
                with ProjectMapLock(path):
                    pass
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), stale)

    def test_concurrent_stale_lock_attempts_all_fail_closed(self):
        with workspace_tempdir("project-map-stale-concurrency-") as temporary:
            path = Path(temporary) / "map.lock"
            stale = {"pid": 999999, "token": "dead-owner"}
            path.write_text(json.dumps(stale), encoding="utf-8")

            def attempt() -> str:
                try:
                    with ProjectMapLock(path):
                        return "acquired"
                except TimeoutError:
                    return "busy"

            for _ in range(10):
                with ThreadPoolExecutor(max_workers=8) as executor:
                    results = list(executor.map(lambda _item: attempt(), range(8)))
                self.assertEqual(results, ["busy"] * 8)
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")), stale)

    def test_owner_token_prevents_replaced_lock_cleanup(self):
        with workspace_tempdir("project-map-lock-") as temporary:
            path = Path(temporary) / "map.lock"
            lock = ProjectMapLock(path)
            lock.__enter__()
            try:
                replacement = {"pid": 999999, "token": "replacement-owner"}
                path.write_text(json.dumps(replacement), encoding="utf-8")
            finally:
                lock.__exit__(None, None, None)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), replacement)

    def test_duplicate_task_ids_fail_closed(self):
        with workspace_tempdir("project-map-duplicate-") as temporary:
            workspace = make_workspace(Path(temporary))
            tasks = workspace / "MissionCenter" / "tasks.md"
            text = tasks.read_text(encoding="utf-8")
            tasks.write_text(text + text.splitlines()[-2] + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate task ID"):
                build_project_map(workspace)

    def test_html_escapes_untrusted_project_and_task_text(self):
        with workspace_tempdir("project-map-html-") as temporary:
            workspace = make_workspace(Path(temporary))
            mission = workspace / "MissionCenter"
            (mission / "project.md").write_text(
                '# <img src="x">\n\nGoal: & <script>alert(1)</script>\n', encoding="utf-8"
            )
            tasks = (mission / "tasks.md").read_text(encoding="utf-8")
            (mission / "tasks.md").write_text(tasks.replace("Child task", '<script>alert("x")</script>'), encoding="utf-8")
            value = build_project_map(workspace, generated_at="2026-08-26T00:00:00Z")
            rendered = project_map.render_html(value)
            self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", rendered)
            self.assertIn("&lt;img src=&quot;x&quot;&gt;", rendered)
            self.assertNotIn("<script>", rendered)

    def test_project_map_validator_rejects_invalid_public_shapes(self):
        with workspace_tempdir("project-map-schema-") as temporary:
            value = build_project_map(make_workspace(Path(temporary)), generated_at="2026-08-26T00:00:00Z")
            validate_project_map(value)
            for mutate in (
                lambda item: item["nodes"][0].pop("status"),
                lambda item: item["nodes"][0].__setitem__("status", "Unknown"),
                lambda item: item["edges"][0].__setitem__("kind", "unknown"),
                lambda item: item["edges"][0].__setitem__("from", "missing"),
            ):
                broken = json.loads(json.dumps(value))
                mutate(broken)
                with self.assertRaises(ValueError):
                    validate_project_map(broken)

    def test_project_map_schema_declares_public_required_fields(self):
        schema = json.loads(
            (ROOT / "skills" / "mission-center" / "schemas" / "project-map.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], "1.0")
        self.assertEqual(
            set(schema["required"]),
            {"schemaVersion", "sourceFingerprint", "sources", "generatedAt", "generation", "language", "project", "counts", "nodes", "edges"},
        )

    def test_source_and_output_parent_symlinks_fail_closed(self):
        with workspace_tempdir("project-map-symlink-") as temporary:
            root = Path(temporary)
            real = make_workspace(root)
            linked = root / "linked"
            linked.mkdir()
            try:
                (linked / "MissionCenter").symlink_to(real / "MissionCenter", target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks are unavailable")
            with self.assertRaisesRegex(OSError, "source root"):
                build_project_map(linked)

            output_workspace = make_workspace(root / "output")
            outside = root / "outside-output"
            outside.mkdir()
            (output_workspace / "output").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(OSError, "output must not contain symlinks"):
                publish_project_map(output_workspace)


if __name__ == "__main__":
    unittest.main()
