import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from publish_local import main, validate_target


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_fake_repo(root: Path) -> Path:
    repo = root / "repo"
    write(repo / ".codex-plugin" / "plugin.json", '{"name":"mission-center"}\n')
    write(repo / "assets" / "icon.svg", "<svg/>\n")
    write(repo / "scripts" / "install.txt", "installer\n")
    write(repo / "README.md", "readme\n")
    write(repo / "LICENSE", "license\n")
    write(repo / "NOTICE.md", "notice\n")
    write(repo / "PRIVACY.md", "privacy\n")
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
                '{"name":"mission-center","version":"0.1.0","interface":{"displayName":"Mission Center","category":"Productivity"}}\n',
            )
            personal = root / "personal" / "skills" / "mission-center"
            marketplace = root / "marketplace" / "plugins" / "mission-center"
            fake_codex = root / "fake-codex"
            fake_codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

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
            self.assertIn('"version": "0.1.0+codex.', manifest)
            marketplace_manifest = (
                marketplace.parent.parent / ".agents" / "plugins" / "marketplace.json"
            ).read_text(encoding="utf-8")
            self.assertIn('"name": "mission-center-local"', marketplace_manifest)
            self.assertIn('"path": "./plugins/mission-center"', marketplace_manifest)
            expected_calls = [
                ([str(fake_codex), "plugin", "remove", "mission-center@mission-center-local"], False),
                ([str(fake_codex), "plugin", "marketplace", "remove", "mission-center-local"], False),
                ([str(fake_codex), "plugin", "marketplace", "add", str(marketplace.parent.parent)], True),
                ([str(fake_codex), "plugin", "add", "mission-center@mission-center-local"], True),
            ]
            self.assertEqual(len(run_mock.call_args_list), len(expected_calls))
            for actual_call, (expected_command, expected_check) in zip(run_mock.call_args_list, expected_calls):
                actual_command = actual_call.args[0]
                if sys.platform == "win32":
                    self.assertTrue(Path(actual_command[0]).samefile(fake_codex))
                else:
                    self.assertEqual(actual_command[0], expected_command[0])
                self.assertEqual(actual_command[1:], expected_command[1:])
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


if __name__ == "__main__":
    unittest.main()
