import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
TEST_TMP_ROOT = Path(tempfile.gettempdir()) / "codex-mission-center-hook-tests"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


def fresh_test_dir(name: str) -> Path:
    path = TEST_TMP_ROOT / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path
MODULE_PATH = ROOT / "scripts" / "install_git_hook.py"


def load_installer():
    spec = importlib.util.spec_from_file_location("mission_center_install_git_hook", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallGitHookTests(unittest.TestCase):
    def test_existing_non_tool_hook_is_preserved_and_fails(self):
        installer = load_installer()
        repo = fresh_test_dir("hook-non-tool")
        try:
            hook = repo / ".git" / "hooks" / "pre-commit"
            hook.parent.mkdir(parents=True)
            hook.write_text("#!/bin/sh\necho user-hook\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), str(repo)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(hook.read_text(encoding="utf-8"), "#!/bin/sh\necho user-hook\n")
        finally:
            shutil.rmtree(repo)

    def test_existing_post_commit_is_never_changed(self):
        repo = fresh_test_dir("hook-post-commit-preserved")
        try:
            post_commit = repo / ".git" / "hooks" / "post-commit"
            post_commit.parent.mkdir(parents=True)
            post_commit.write_text("#!/bin/sh\necho user-post-commit\n", encoding="utf-8")
            self.assertTrue(load_installer().install_git_hook(repo))
            self.assertEqual(post_commit.read_text(encoding="utf-8"), "#!/bin/sh\necho user-post-commit\n")
            self.assertTrue((repo / ".git" / "hooks" / "pre-commit").exists())
        finally:
            shutil.rmtree(repo)

    def test_existing_tool_hook_is_idempotent(self):
        installer = load_installer()
        repo = fresh_test_dir("hook-tool")
        try:
            hook = repo / ".git" / "hooks" / "pre-commit"
            hook.parent.mkdir(parents=True)
            hook.write_text(installer.PRE_COMMIT_HOOK_SCRIPT, encoding="utf-8")
            self.assertTrue(installer.install_git_hook(repo))
        finally:
            shutil.rmtree(repo)

    def test_existing_generated_crlf_hook_is_upgraded_to_lf(self):
        installer = load_installer()
        repo = fresh_test_dir("hook-tool-crlf")
        try:
            hook = repo / ".git" / "hooks" / "pre-commit"
            hook.parent.mkdir(parents=True)
            legacy = (
                "#!/bin/sh\n"
                f"{installer.TOOL_MARKER}\n"
                "python skills/mission-center/scripts/sync_mission_center.py 2>/dev/null || true\n"
            )
            hook.write_bytes(legacy.replace("\n", "\r\n").encode("utf-8"))

            self.assertTrue(installer.install_git_hook(repo))

            self.assertEqual(
                hook.read_bytes(),
                installer.PRE_COMMIT_HOOK_SCRIPT.encode("utf-8"),
            )
            self.assertNotIn(b"\r\n", hook.read_bytes())
            if sys.platform != "win32":
                self.assertTrue(hook.stat().st_mode & 0o100)
        finally:
            shutil.rmtree(repo)


if __name__ == "__main__":
    unittest.main()
