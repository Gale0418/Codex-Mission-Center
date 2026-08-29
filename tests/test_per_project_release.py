import hashlib
import json
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "skills" / "mission-center" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workspace_contract import REQUIRED_FILES


class PerProjectReleaseTests(unittest.TestCase):
    def test_repo_dogfood_workspace_is_trackable_and_complete(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertNotIn("MissionCenter/", ignored)
        actual = {
            path.name
            for path in (ROOT / "MissionCenter").iterdir()
            if path.is_file()
        }
        self.assertTrue(set(REQUIRED_FILES).issubset(actual))

    def test_repo_snapshot_uses_current_checkpoint_format(self):
        snapshot = (ROOT / "MissionCenter" / "snapshot.md").read_text(encoding="utf-8")
        state = next(
            (value for value in ("active", "inactive") if f"- State: {value}" in snapshot),
            None,
        )
        self.assertIsNotNone(state)
        for field in ("進行中任務", "狀態", "版本", "指紋", "恢復"):
            self.assertIn(field, snapshot)
        if state == "active":
            for field in ("依賴", "驗證", "Retry gate"):
                self.assertIn(field, snapshot)

    def test_readme_declares_per_project_only_contract(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for sentence in (
            "Mission Center is per-project only.",
            "Use it inside the current repo/workspace.",
            "It creates or reads `./MissionCenter/`.",
            "It does not monitor all repositories.",
            "It does not merge tasks across projects.",
        ):
            self.assertIn(sentence, readme)

    def test_documented_layout_matches_canonical_contract(self):
        expected = set(REQUIRED_FILES)
        for relative in (
            "README.md",
            "skills/mission-center/references/task-workspace.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for name in expected:
                self.assertIn(name, text, f"{relative} omits {name}")

    def test_ci_runs_unit_and_single_workspace_cli_checks(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for phrase in (
            "push:",
            "pull_request:",
            "python -m unittest discover -s tests -p \"test_*.py\" -v",
            'workspace="${RUNNER_TEMP}/mc-demo"',
            'bootstrap_mission_center.py "$workspace" --language zh-TW',
            'normalize_mission_center.py "$workspace"',
            'sync_mission_center.py "$workspace"',
            'doctor_mission_center.py "$workspace"',
        ):
            self.assertIn(phrase, workflow)
        self.assertIn("os: [ubuntu-latest, windows-latest]", workflow)
        self.assertIn("runtime: [core, websocket]", workflow)
        for phrase in (
            "  python:\n    name: python (${{ matrix.os }}, ${{ matrix.runtime }})",
            "  rust:\n    name: rust (${{ matrix.os }})",
            "  test:\n    name: test\n    needs: [python, rust, rust-release, rust-stable-package]\n    if: always()",
            'test "${{ needs.python.result }}" = "success"',
            'test "${{ needs.rust.result }}" = "success"',
            'test "${{ needs.rust-release.result }}" = "success"',
        ):
            self.assertIn(phrase, workflow)

    def test_historical_validation_record_has_exact_task_set_and_bounded_counts(self):
        record = json.loads(
            (ROOT / "MissionCenter" / "evidence" / "historical-validation-2026-08-29.json").read_text(
                encoding="utf-8"
            )
        )
        expected = {f"MC-{index:03d}" for index in range(1, 61)}
        task_ids = [task["taskId"] for task in record["tasks"]]
        self.assertEqual(len(task_ids), 60)
        self.assertEqual(set(task_ids), expected)
        self.assertEqual(len(task_ids), len(set(task_ids)))
        for layer in ("currentReplay", "historicalReplay"):
            self.assertEqual(sum(record["summary"][layer].values()), 60)
            observed = Counter(task[layer]["status"] for task in record["tasks"])
            self.assertEqual(
                record["summary"][layer],
                {status: observed[status] for status in record["summary"][layer]},
            )
        schema = json.loads(
            (ROOT / "MissionCenter" / "evidence" / "historical-validation.schema.json").read_text(
                encoding="utf-8"
            )
        )
        try:
            import jsonschema
        except ImportError as exc:  # pragma: no cover - repository test dependency
            self.skipTest(f"jsonschema unavailable: {exc}")
        jsonschema.validate(record, schema)

    def test_historical_schema_rejects_pass_without_revision(self):
        record_path = ROOT / "MissionCenter" / "evidence" / "historical-validation-2026-08-29.json"
        schema_path = ROOT / "MissionCenter" / "evidence" / "historical-validation.schema.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        try:
            import jsonschema
        except ImportError as exc:  # pragma: no cover - repository test dependency
            self.skipTest(f"jsonschema unavailable: {exc}")
        mutated = json.loads(json.dumps(record))
        mutated["tasks"][0]["historicalReplay"].update(
            {
                "status": "pass",
                "classification": "Observed Fact",
                "sourceClassification": "Observed Fact",
                "revision": None,
            }
        )
        errors = list(jsonschema.Draft202012Validator(schema).iter_errors(mutated))
        self.assertTrue(errors, "historical pass without a unique git revision must fail closed")

    def test_historical_validation_digest_is_bounded_and_content_free(self):
        record_path = ROOT / "MissionCenter" / "evidence" / "historical-validation-2026-08-29.json"
        schema_path = ROOT / "MissionCenter" / "evidence" / "historical-validation.schema.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        digest = record["workingTreeDiffDigest"]
        self.assertTrue(record["workingTreeDirty"])
        self.assertEqual(digest["algorithm"], "sha256")
        self.assertFalse(digest["includesFileContents"])
        self.assertFalse(digest["includesSecrets"])
        self.assertLessEqual(digest["entryCount"], digest["maxEntries"])

        head_revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        if head_revision != record["currentRevision"]:
            return

        diff = subprocess.run(
            ["git", "diff", "HEAD", "--name-status", "--no-renames", "--", "."],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.splitlines()
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.splitlines()
        excluded = {
            record_path.relative_to(ROOT).as_posix(),
            schema_path.relative_to(ROOT).as_posix(),
        }
        manifest = [line for line in untracked if line.replace("\\", "/") not in excluded]
        normalized_manifest = [path.replace("\\", "/") for path in manifest]
        entries = sorted(
            f"tracked\t{line}"
            for line in diff
            if line.split("\t")[-1].replace("\\", "/") not in excluded
        )
        entries.extend(
            sorted(
                f"untracked\t{path}"
                for path in normalized_manifest
            )
        )
        self.assertGreaterEqual(len(entries), digest["entryCount"])
        entries = entries[: digest["maxEntries"]]
        canonical = "\n".join(["mission-center-working-tree-digest-v1", *entries]) + "\n"
        self.assertEqual(len(entries), digest["entryCount"])
        self.assertEqual(hashlib.sha256(canonical.encode("utf-8")).hexdigest(), digest["value"])

    def test_historical_validation_offline_replay(self):
        """Validate only local record structure; never replay external human evidence."""
        record_path = ROOT / "MissionCenter" / "evidence" / "historical-validation-2026-08-29.json"
        schema_path = ROOT / "MissionCenter" / "evidence" / "historical-validation.schema.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        try:
            import jsonschema
        except ImportError as exc:  # pragma: no cover - repository test dependency
            self.skipTest(f"jsonschema unavailable: {exc}")
        jsonschema.validate(record, schema)

        expected_ids = [f"MC-{index:03d}" for index in range(1, 61)]
        task_ids = [task["taskId"] for task in record["tasks"]]
        self.assertEqual(task_ids, expected_ids)
        self.assertEqual(len(task_ids), len(set(task_ids)))
        self.assertEqual(len(record["tasks"]), 60)

        current_counts = record["summary"]["currentReplay"]
        historical_counts = record["summary"]["historicalReplay"]
        self.assertEqual(sum(current_counts.values()), 60)
        self.assertEqual(sum(historical_counts.values()), 60)
        observed_current = Counter(task["currentReplay"]["status"] for task in record["tasks"])
        observed_historical = Counter(task["historicalReplay"]["status"] for task in record["tasks"])
        self.assertEqual(
            current_counts,
            {status: observed_current[status] for status in current_counts},
        )
        self.assertEqual(
            historical_counts,
            {status: observed_historical[status] for status in historical_counts},
        )

        expected_historical_passes = {
            "MC-001",
            "MC-002",
            "MC-005",
            "MC-008",
            "MC-026",
            "MC-034",
            "MC-038",
            "MC-053",
        }
        for task in record["tasks"]:
            historical = task["historicalReplay"]
            if task["taskId"] in expected_historical_passes:
                self.assertEqual(historical["status"], "pass")
                self.assertRegex(historical["revision"], r"^[0-9a-f]{40}$")
            else:
                self.assertEqual(historical["status"], "unknown")
                self.assertEqual(historical["classification"], "Unknown")

        digest = record["workingTreeDiffDigest"]
        self.assertRegex(digest["value"], r"^[0-9a-f]{64}$")
        self.assertEqual(digest["algorithm"], "sha256")
        self.assertIsInstance(digest["entryCount"], int)
        self.assertGreaterEqual(digest["entryCount"], 0)
        self.assertLessEqual(digest["entryCount"], digest["maxEntries"])
        self.assertFalse(digest["includesFileContents"])
        self.assertFalse(digest["includesSecrets"])
        self.assertIn("Chrome", record["sourcePolicy"])
        self.assertIn("CodeRabbit", record["sourcePolicy"])
        self.assertIn("Critic", record["sourcePolicy"])

    def test_release_checklist_repeats_product_boundaries(self):
        checklist = (ROOT / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8").lower()
        for phrase in (
            "publish dry-run",
            "publish verify",
            "global monitoring",
            "merge tasks across repositories",
        ):
            self.assertIn(phrase, checklist)

    def test_skill_has_no_global_overview_route(self):
        skill = (ROOT / "skills" / "mission-center" / "SKILL.md").read_text(encoding="utf-8").lower()
        self.assertNotIn("global-overview", skill)
        self.assertFalse((ROOT / "skills" / "mission-center" / "references" / "global-overview.md").exists())


if __name__ == "__main__":
    unittest.main()
