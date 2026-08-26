import json
import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from publish_local import (
    FileTransaction,
    get_codex_executable,
    is_usable_codex_executable,
    main,
    normalized_version,
    register_marketplace_and_plugin,
    reject_symlink_components,
    validate_target,
)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_fake_repo(root: Path) -> Path:
    repo = root / "repo"
    write(repo / ".codex-plugin" / "plugin.json", '{"name":"mission-center","version":"0.1.0"}\n')
    write(repo / "assets" / "icon.svg", "<svg/>\n")
    write(repo / "scripts" / "install.txt", "installer\n")
    write(repo / "README.md", "readme\n")
    write(repo / "LICENSE", "license\n")
    write(repo / "NOTICE.md", "notice\n")
    write(repo / "PRIVACY.md", "privacy\n")
    write(repo / "requirements-runtime.txt", "websockets>=16.1,<17\n")
    write(repo / "skills" / "mission-center" / "SKILL.md", "canonical\n")
    write(
        repo / "skills" / "mission-center" / "references" / "rules.md",
        "rules\n",
    )
    write(
        repo / "skills" / "mission-center" / "scripts" / "__pycache__" / "bad.pyc",
        "generated\n",
    )
    return repo


class PublishLocalTests(unittest.TestCase):
    def test_rejects_user_controlled_symlink_component(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            link = root / "link"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                    self.skipTest("symlink creation requires SeCreateSymbolicLinkPrivilege")
                raise
            with self.assertRaisesRegex(ValueError, "must not contain symlinks"):
                reject_symlink_components(link / "child", "target")

    def test_codex_discovery_prefers_sandbox_and_rejects_windowsapps_path_alias(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            sandbox = root / ".sandbox-bin" / "codex.exe"
            sandbox.parent.mkdir(parents=True)
            sandbox.write_text("sandbox\n", encoding="utf-8")
            sandbox.chmod(sandbox.stat().st_mode | stat.S_IXUSR)
            alias = root / "WindowsApps" / "codex.exe"
            alias.parent.mkdir(parents=True)
            alias.write_text("alias\n", encoding="utf-8")
            alias.chmod(alias.stat().st_mode | stat.S_IXUSR)

            with patch.dict(
                os.environ,
                {
                    "CODEX_HOME": str(root),
                    "HOME": str(root),
                    "USERPROFILE": str(root),
                },
                clear=True,
            ):
                with patch("publish_local.shutil.which", return_value=str(alias)):
                    self.assertEqual(get_codex_executable(), sandbox.resolve())

                sandbox.unlink()
                with patch("publish_local.shutil.which", return_value=str(alias)):
                    with patch("publish_local._is_windows_platform", return_value=True):
                        self.assertIsNone(get_codex_executable())

    def test_codex_candidate_must_be_a_file(self):
        with workspace_tempdir("publish-local-") as temporary:
            directory = Path(temporary) / "codex.exe"
            directory.mkdir()
            self.assertFalse(is_usable_codex_executable(directory))

    def test_semver_normalization_discards_arbitrary_build_metadata(self):
        self.assertEqual(normalized_version("1.2.3-beta.2+vendor.build"), "1.2.3-beta.2")
        with self.assertRaises(ValueError):
            normalized_version("1.2")

    def test_dry_run_does_not_create_targets(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            repo = make_fake_repo(root)
            personal = root / "personal" / "skills" / "mission-center"
            marketplace = root / "marketplace" / "plugins" / "mission-center"
            result = main(
                [
                    "--repo",
                    str(repo),
                    "--personal-skill",
                    str(personal),
                    "--marketplace-plugin",
                    str(marketplace),
                    "--dry-run",
                ]
            )
            self.assertEqual(result, 0)
            self.assertFalse(personal.exists())
            self.assertFalse(marketplace.exists())

    def test_write_syncs_skill_and_plugin_without_generated_files(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            repo = make_fake_repo(root)
            personal = root / "personal" / "skills" / "mission-center"
            marketplace = root / "marketplace" / "plugins" / "mission-center"
            write(personal / "obsolete.txt", "remove\n")
            result = main(
                [
                    "--repo",
                    str(repo),
                    "--personal-skill",
                    str(personal),
                    "--marketplace-plugin",
                    str(marketplace),
                    "--write",
                ]
            )
            self.assertEqual(result, 0)
            self.assertEqual(
                (personal / "SKILL.md").read_text(encoding="utf-8"),
                "canonical\n",
            )
            self.assertEqual(
                (personal / "requirements-runtime.txt").read_text(encoding="utf-8"),
                "websockets>=16.1,<17\n",
            )
            self.assertFalse((personal / "obsolete.txt").exists())
            self.assertFalse((personal / "scripts" / "__pycache__").exists())
            self.assertTrue(
                (marketplace.parent.parent / ".agents" / "plugins" / "marketplace.json").is_file()
            )
            self.assertTrue((marketplace / ".codex-plugin" / "plugin.json").is_file())
            self.assertEqual(
                (marketplace / "PRIVACY.md").read_text(encoding="utf-8"),
                "privacy\n",
            )
            self.assertEqual(
                (marketplace / "requirements-runtime.txt").read_text(encoding="utf-8"),
                "websockets>=16.1,<17\n",
            )
            self.assertEqual(
                main(
                    [
                        "--repo",
                        str(repo),
                        "--personal-skill",
                        str(personal),
                        "--marketplace-plugin",
                        str(marketplace),
                        "--verify",
                    ]
                ),
                0,
            )

    def test_write_with_register_refreshes_plugin_version_and_calls_codex_cli(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            repo = make_fake_repo(root)
            write(
                repo / ".codex-plugin" / "plugin.json",
                '{"name":"mission-center","version":"0.1.0+codex.previous","interface":{"displayName":"Mission Center","category":"Productivity"}}\n',
            )
            personal = root / "personal" / "skills" / "mission-center"
            marketplace = root / "marketplace" / "plugins" / "mission-center"
            fake_codex = root / "fake-codex"
            fake_codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)

            with patch("publish_local.subprocess.run") as run_mock:
                run_mock.return_value.returncode = 0
                result = main(
                    [
                        "--repo",
                        str(repo),
                        "--personal-skill",
                        str(personal),
                        "--marketplace-plugin",
                        str(marketplace),
                        "--write",
                        "--register",
                        "--codex-cli",
                        str(fake_codex),
                    ]
                )

            self.assertEqual(result, 0)
            manifest = (marketplace / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
            stamped_version = json.loads(manifest)["version"]
            self.assertEqual(stamped_version.count("+"), 1)
            self.assertTrue(stamped_version.startswith("0.1.0+codex."))
            self.assertNotIn("codex.previous", stamped_version)
            marketplace_manifest = (
                marketplace.parent.parent / ".agents" / "plugins" / "marketplace.json"
            ).read_text(encoding="utf-8")
            self.assertIn('"name": "mission-center-local"', marketplace_manifest)
            self.assertIn('"path": "./plugins/mission-center"', marketplace_manifest)
            expected_calls = [
                ([str(fake_codex), "plugin", "remove", "mission-center@mission-center-local"], False, {0}),
                ([str(fake_codex), "plugin", "marketplace", "remove", "mission-center-local"], False, {0}),
                ([str(fake_codex), "plugin", "marketplace", "add", str(marketplace.parent.parent)], True, {0, 4}),
                ([str(fake_codex), "plugin", "add", "mission-center@mission-center-local"], True, {0}),
            ]
            self.assertEqual(len(run_mock.call_args_list), len(expected_calls))
            for actual_call, (expected_command, expected_check, path_indexes) in zip(run_mock.call_args_list, expected_calls):
                actual_command = actual_call.args[0]
                self.assertEqual(len(actual_command), len(expected_command))
                for index, (actual, expected) in enumerate(zip(actual_command, expected_command)):
                    if index in path_indexes:
                        self.assertTrue(Path(actual).samefile(Path(expected)))
                    else:
                        self.assertEqual(actual, expected)
                self.assertEqual(actual_call.kwargs, {"check": expected_check})

    def test_verify_reports_drift(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            repo = make_fake_repo(root)
            personal = root / "personal" / "skills" / "mission-center"
            marketplace = root / "marketplace" / "plugins" / "mission-center"
            main(
                [
                    "--repo",
                    str(repo),
                    "--personal-skill",
                    str(personal),
                    "--marketplace-plugin",
                    str(marketplace),
                    "--write",
                ]
            )
            write(personal / "SKILL.md", "drifted\n")
            self.assertEqual(
                main(
                    [
                        "--repo",
                        str(repo),
                        "--personal-skill",
                        str(personal),
                        "--marketplace-plugin",
                        str(marketplace),
                        "--verify",
                    ]
                ),
                1,
            )

    def test_write_rejects_codex_managed_cache_target(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            repo = make_fake_repo(root)
            personal = root / "personal" / "skills" / "mission-center"
            marketplace = root / "marketplace" / "plugins" / "mission-center"
            cache = root / "cache" / "skills" / "mission-center"
            with self.assertRaisesRegex(ValueError, "Codex-managed"):
                main(
                    [
                        "--repo",
                        str(repo),
                        "--personal-skill",
                        str(personal),
                        "--marketplace-plugin",
                        str(marketplace),
                        "--cache-skill",
                        str(cache),
                        "--write",
                    ]
                )

    def test_rejects_targets_outside_expected_tail(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "skills/mission-center"):
                validate_target(root / "mission-center", ("skills", "mission-center"))
            with self.assertRaisesRegex(ValueError, "plugins/mission-center"):
                validate_target(root / "mission-center", ("plugins", "mission-center"))

    def test_verify_reports_plugin_drift_outside_skill_directory(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            repo = make_fake_repo(root)
            personal = root / "personal" / "skills" / "mission-center"
            marketplace = root / "marketplace" / "plugins" / "mission-center"
            main(
                [
                    "--repo",
                    str(repo),
                    "--personal-skill",
                    str(personal),
                    "--marketplace-plugin",
                    str(marketplace),
                    "--write",
                ]
            )
            write(marketplace / "assets" / "icon.svg", "drifted\n")
            self.assertEqual(
                main(
                    [
                        "--repo",
                        str(repo),
                        "--personal-skill",
                        str(personal),
                        "--marketplace-plugin",
                        str(marketplace),
                        "--verify",
                    ]
                ),
                1,
            )

    def test_register_requires_resolvable_codex_cli(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            repo = make_fake_repo(root)
            write(
                repo / ".codex-plugin" / "plugin.json",
                '{"name":"mission-center","version":"0.1.0","interface":{"displayName":"Mission Center"}}\n',
            )
            personal = root / "personal" / "skills" / "mission-center"
            marketplace = root / "marketplace" / "plugins" / "mission-center"
            with patch("publish_local.get_codex_executable", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "Codex executable not found"):
                    main(
                        [
                            "--repo",
                            str(repo),
                            "--personal-skill",
                            str(personal),
                            "--marketplace-plugin",
                            str(marketplace),
                            "--write",
                            "--register",
                        ]
                    )

    def test_register_preflight_happens_before_existing_targets_change(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            repo = make_fake_repo(root)
            personal = root / "personal" / "skills" / "mission-center"
            marketplace = root / "marketplace" / "plugins" / "mission-center"
            write(personal / "old.txt", "keep\n")
            write(marketplace / "old.txt", "keep\n")
            with patch("publish_local.get_codex_executable", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "Codex executable not found"):
                    main([
                        "--repo", str(repo), "--personal-skill", str(personal),
                        "--marketplace-plugin", str(marketplace), "--write", "--register",
                    ])
            self.assertEqual((personal / "old.txt").read_text(encoding="utf-8"), "keep\n")
            self.assertEqual((marketplace / "old.txt").read_text(encoding="utf-8"), "keep\n")

    def test_registration_failure_rolls_back_both_published_targets(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            repo = make_fake_repo(root)
            personal = root / "personal" / "skills" / "mission-center"
            marketplace = root / "marketplace" / "plugins" / "mission-center"
            write(personal / "old.txt", "personal-old\n")
            write(marketplace / "old.txt", "marketplace-old\n")
            fake_codex = root / "fake-codex"
            fake_codex.write_text("fake\n", encoding="utf-8")
            fake_codex.chmod(fake_codex.stat().st_mode | stat.S_IXUSR)
            failure = subprocess.CalledProcessError(7, [str(fake_codex), "plugin", "marketplace", "add"])
            outcomes = [
                subprocess.CompletedProcess([], 0),
                subprocess.CompletedProcess([], 0),
                failure,
                *([subprocess.CompletedProcess([], 0)] * 4),
            ]
            with patch("publish_local.subprocess.run", side_effect=outcomes) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    main([
                        "--repo", str(repo), "--personal-skill", str(personal),
                        "--marketplace-plugin", str(marketplace), "--write", "--register",
                        "--codex-cli", str(fake_codex),
                    ])
            self.assertEqual((personal / "old.txt").read_text(encoding="utf-8"), "personal-old\n")
            self.assertEqual((marketplace / "old.txt").read_text(encoding="utf-8"), "marketplace-old\n")
            self.assertEqual(len(run.call_args_list), 7)
            self.assertFalse(any("staging-" in item.name or "backup-" in item.name for item in personal.parent.iterdir()))

    def test_file_transaction_rollback_is_idempotent_after_commit_failure(self):
        with workspace_tempdir("publish-local-") as temporary:
            root = Path(temporary)
            first_target = root / "first"
            first_target.mkdir()
            write(first_target / "state.txt", "original\n")
            first_staging = root / ".first.staging"
            first_staging.mkdir()
            write(first_staging / "state.txt", "replacement\n")
            second_target = root / "second"
            second_staging = root / ".second.staging"
            first_backup = root / ".first.backup"
            second_backup = root / ".second.backup"
            transaction = FileTransaction(
                [
                    (first_target, first_staging, first_backup),
                    (second_target, second_staging, second_backup),
                ]
            )

            with self.assertRaises(FileNotFoundError):
                transaction.commit()
            # commit() already rolls back its partial commit; the caller's
            # defensive rollback must not remove the restored target.
            transaction.rollback()
            self.assertEqual(
                (first_target / "state.txt").read_text(encoding="utf-8"),
                "original\n",
            )

    def test_registration_oserror_does_not_recreate_unknown_registrations(self):
        fake_codex = Path("codex")
        with patch("publish_local.subprocess.run", side_effect=OSError("unavailable")) as run:
            with self.assertRaisesRegex(OSError, "unavailable"):
                register_marketplace_and_plugin(
                    fake_codex,
                    Path("marketplace-root"),
                    {"name": "mission-center"},
                )
        commands = [call.args[0][1:] for call in run.call_args_list]
        self.assertEqual(
            commands,
            [
                ["plugin", "remove", "mission-center@mission-center-local"],
                ["plugin", "remove", "mission-center@mission-center-local"],
                ["plugin", "marketplace", "remove", "mission-center-local"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
