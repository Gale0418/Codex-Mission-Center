import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import workspace_tempdir

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'skills' / 'mission-center' / 'scripts' / 'snapshot_mission_center.py'
spec = importlib.util.spec_from_file_location('snapshot_continuity', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExecutionContinuityTests(unittest.TestCase):
    def test_retry_gate_enters_diagnosis_for_repeated_signature(self):
        attempts = [{'phase': 'build', 'errorSignature': 'E42'}, {'phase': 'test', 'errorSignature': 'E42'}]
        result = module.retry_gate(attempts)
        self.assertEqual(result['mode'], 'diagnosis')
        self.assertTrue(result['stopModifyingAndDeploying'])

    def test_retry_gate_enters_diagnosis_for_three_phase_failures_and_bounds_history(self):
        attempts = [{'phase': 'test', 'errorSignature': str(index)} for index in range(6)]
        result = module.retry_gate(attempts)
        self.assertEqual(result['mode'], 'diagnosis')
        self.assertEqual(len(result['recentAttempts']), module.MAX_RECENT_ATTEMPTS)

    def test_attempt_rejects_secret_like_data(self):
        with self.assertRaises(ValueError):
            module.sanitize_attempt({'phase': 'deploy', 'errorSignature': 'token=bad'})

    def test_recent_attempt_reader_keeps_valid_entries_around_invalid_one(self):
        payload = [
            {"phase": "test", "errorSignature": "E1"},
            {"phase": "deploy", "errorSignature": "token=bad"},
            {"phase": "build", "errorSignature": "E2"},
        ]
        text = module.ATTEMPTS_METADATA_PREFIX + json.dumps(payload)
        with self.assertWarns(RuntimeWarning):
            attempts = module.read_recent_attempts(text)
        self.assertEqual([item["errorSignature"] for item in attempts], ["E1", "E2"])

    def test_canonical_fingerprint_normalizes_line_endings(self):
        row = {"ID": "T-1", "Title": "Test", "Status": "In Progress"}
        fingerprints = []
        for contents in ((b"a\r\nb", b"c\rd"), (b"a\nb", b"c\nd")):
            with patch.object(module, '_task_rows', return_value=[row]), \
                 patch.object(module.Path, 'exists', return_value=True), \
                 patch.object(module.Path, 'read_bytes', side_effect=contents), \
                 patch.object(module.subprocess, 'run') as run:
                run.return_value.stdout = 'revision\n'
                fingerprints.append(module.canonical_facts(ROOT)["fingerprint"])
        self.assertEqual(fingerprints[0], fingerprints[1])

    def test_canonical_facts_uses_null_separator_and_canonical_dependencies(self):
        row = {'ID': 'T-1', 'Title': 'Test', 'Status': 'In Progress', 'Depends on': 'T-0', '依賴': 'legacy', 'Verification': 'pytest'}
        with patch.object(module, '_task_rows', return_value=[row]), \
             patch.object(module.Path, 'exists', return_value=True), \
             patch.object(module.Path, 'read_bytes', side_effect=[b'tasks', b'project']), \
             patch.object(module.subprocess, 'run') as run:
            run.return_value.stdout = 'revision\n'
            facts = module.canonical_facts(ROOT)
        self.assertEqual(facts['fingerprint'], module.hashlib.sha256(b'tasks\0projectrevision').hexdigest())
        self.assertEqual(facts['dependencies'], 'T-0')
        self.assertEqual(run.call_args.kwargs['timeout'], 10)

    def test_canonical_facts_keeps_traditional_chinese_dependency_fallback(self):
        row = {'ID': 'T-1', 'Title': 'Test', 'Status': 'In Progress', '依賴': 'legacy'}
        with patch.object(module, '_task_rows', return_value=[row]), \
             patch.object(module.Path, 'exists', return_value=False), \
             patch.object(module.subprocess, 'run') as run:
            run.return_value.stdout = 'revision\n'
            facts = module.canonical_facts(ROOT)
        self.assertEqual(facts['dependencies'], 'legacy')

    def test_canonical_facts_falls_back_when_git_times_out(self):
        with patch.object(module, '_task_rows', return_value=[]), \
             patch.object(module.Path, 'exists', return_value=False), \
             patch.object(module.subprocess, 'run', side_effect=subprocess.TimeoutExpired('git', 10)):
            facts = module.canonical_facts(ROOT)
        self.assertEqual(facts['revision'], 'unavailable')

    def test_snapshot_merges_prior_attempts_across_invocations(self):
        with workspace_tempdir("snapshot-continuity-") as temporary:
            workspace = Path(temporary)
            mission = workspace / 'MissionCenter'
            mission.mkdir()
            (mission / 'tasks.md').write_text(
                '| ID | Title | Status | Depends on | Verification |\n| --- | --- | --- | --- | --- |\n| T-1 | Fix | In Progress | | unittest |\n',
                encoding='utf-8',
            )
            first = {'phase': 'test', 'errorSignature': 'E42'}
            second = {'phase': 'build', 'errorSignature': 'E42'}
            for attempt in (first, second):
                previous_argv = sys.argv
                try:
                    sys.argv = ['snapshot_mission_center.py', str(workspace), '--attempt', json.dumps(attempt)]
                    self.assertEqual(module.main(), 0)
                finally:
                    sys.argv = previous_argv
            snapshot = (mission / 'snapshot.md').read_text(encoding='utf-8')
            self.assertIn('- State: active', snapshot)
            self.assertIn('- Retry gate: diagnosis', snapshot)
            self.assertEqual(module.read_recent_attempts(snapshot), [first, second])

    def test_diagnosis_requires_new_hypothesis_and_evidence_to_unlock(self):
        with workspace_tempdir("snapshot-unlock-") as temporary:
            workspace = Path(temporary)
            mission = workspace / "MissionCenter"
            mission.mkdir()
            (mission / "tasks.md").write_text(
                "| ID | Title | Status | Depends on | Verification |\n| --- | --- | --- | --- | --- |\n| T-1 | Fix | In Progress | | unittest |\n",
                encoding="utf-8",
            )
            repeated = '{"phase":"test","errorSignature":"E42"}'
            with patch.object(sys, "argv", ["snapshot", str(workspace), "--attempt", repeated, "--attempt", repeated]):
                self.assertEqual(module.main(), 0)
            with patch.object(sys, "argv", ["snapshot", str(workspace), "--hypothesis", "cache is stale", "--evidence", "fresh trace differs"]):
                self.assertEqual(module.main(), 0)
            snapshot = (workspace / "MissionCenter" / "snapshot.md").read_text(encoding="utf-8")
            self.assertIn("- Retry gate: verification_required", snapshot)
            self.assertIn("Diagnosis evidence JSON", snapshot)
            with patch.object(sys, "argv", ["snapshot", str(workspace), "--verification-result", "pass", "--verification-action", "unit_test", "--verification-evidence", "focused suite passed"]):
                self.assertEqual(module.main(), 0)
            verified = (workspace / "MissionCenter" / "snapshot.md").read_text(encoding="utf-8")
            self.assertIn("- Retry gate: retry", verified)
            self.assertIn("Verification evidence JSON", verified)
            with patch.object(sys, "argv", ["snapshot", str(workspace), "--attempt", repeated, "--attempt", repeated, "--hypothesis", "cache is stale", "--evidence", "fresh trace differs"]):
                self.assertEqual(module.main(), 0)
            self.assertIn("- Retry gate: diagnosis", (workspace / "MissionCenter" / "snapshot.md").read_text(encoding="utf-8"))

    def test_verification_result_requires_verification_gate(self):
        with workspace_tempdir("snapshot-verification-gate-") as temporary:
            workspace = Path(temporary)
            mission = workspace / "MissionCenter"
            mission.mkdir()
            (mission / "tasks.md").write_text(
                "| ID | Title | Status | Depends on | Verification |\n| --- | --- | --- | --- | --- |\n| T-1 | Fix | In Progress | | unittest |\n",
                encoding="utf-8",
            )
            with patch.object(sys, "argv", ["snapshot", str(workspace), "--verification-result", "fail"]):
                with self.assertRaises(SystemExit):
                    module.main()

    def test_snapshot_writes_canonical_state_for_english_and_traditional_chinese(self):
        for language, title in (('en', 'Task'), ('zh-TW', '任務')):
            with self.subTest(language=language), workspace_tempdir("snapshot-state-") as temporary:
                workspace = Path(temporary)
                mission = workspace / 'MissionCenter'
                mission.mkdir()
                (mission / 'tasks.md').write_text(
                    f'| ID | Title | Status | Depends on | Verification |\n| --- | --- | --- | --- | --- |\n| T-1 | {title} | In Progress | | unittest |\n',
                    encoding='utf-8',
                )
                if language == 'zh-TW':
                    (mission / 'project.md').write_text('# 專案\n', encoding='utf-8')
                previous_argv = sys.argv
                try:
                    sys.argv = ['snapshot_mission_center.py', str(workspace)]
                    self.assertEqual(module.main(), 0)
                finally:
                    sys.argv = previous_argv
                self.assertIn('- State: active', (mission / 'snapshot.md').read_text(encoding='utf-8'))
    def test_main_writes_real_newlines(self):
        previous_argv = sys.argv
        try:
            sys.argv = ['snapshot_mission_center.py', str(ROOT)]
            with patch.object(module, 'detect_language', return_value='en'), \
                 patch.object(module, 'canonical_facts', return_value={'active': 'None', 'status': 'Inactive', 'revision': 'test', 'fingerprint': 'hash', 'dependencies': 'None', 'verification': 'None'}), \
                 patch.object(module.Path, 'mkdir'), \
                 patch.object(module.Path, 'write_text') as write_text:
                self.assertEqual(module.main(), 0)
        finally:
            sys.argv = previous_argv
        content = write_text.call_args.args[0]
        self.assertIn('\n', content)
        self.assertNotIn('\\n', content)
        self.assertEqual(write_text.call_args.kwargs["newline"], "\n")


if __name__ == '__main__':
    unittest.main()
