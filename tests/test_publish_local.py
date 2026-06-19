import sys
import tempfile
import unittest
from pathlib import Path


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
        with tempfile.TemporaryDirectory(dir="C:/tmp") as temporary:
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
        with tempfile.TemporaryDirectory(dir="C:/tmp") as temporary:
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
            self.assertTrue((marketplace / ".codex-plugin" / "plugin.json").is_file())
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

    def test_verify_reports_drift(self):
        with tempfile.TemporaryDirectory(dir="C:/tmp") as temporary:
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

    def test_rejects_targets_outside_expected_tail(self):
        with tempfile.TemporaryDirectory(dir="C:/tmp") as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "skills/mission-center"):
                validate_target(root / "mission-center", ("skills", "mission-center"))
            with self.assertRaisesRegex(ValueError, "plugins/mission-center"):
                validate_target(root / "mission-center", ("plugins", "mission-center"))


if __name__ == "__main__":
    unittest.main()
