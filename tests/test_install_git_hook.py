import importlib.util
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "scripts" / "install_git_hook.py"
POWERSHELL_MODULE_PATH = ROOT / "scripts" / "install_git_hook.ps1"


def load_installer():
    spec = importlib.util.spec_from_file_location("mission_center_install_git_hook", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallGitHookTests(unittest.TestCase):
    def test_powershell_installer_generates_python_installer_contract(self):
        powershell = shutil.which("pwsh")
        if not powershell:
            self.skipTest("PowerShell 7 unavailable")
        installer = load_installer()
        with workspace_tempdir("hook-powershell-contract-") as temporary:
            repo = Path(temporary)
            (repo / ".git" / "hooks").mkdir(parents=True)
            result = subprocess.run(
                [
                    powershell,
                    "-NoLogo",
                    "-NoProfile",
                    "-File",
                    str(POWERSHELL_MODULE_PATH),
                    "-TargetRepoPath",
                    str(repo),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            hook = repo / ".git" / "hooks" / "pre-commit"
            self.assertEqual(hook.read_bytes(), installer.PRE_COMMIT_HOOK_SCRIPT.encode("utf-8"))
            self.assertTrue(installer.install_git_hook(repo))

    def test_existing_non_tool_hook_is_preserved_and_fails(self):
        installer = load_installer()
        with workspace_tempdir("hook-non-tool-") as temporary:
            repo = Path(temporary)
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

    def test_existing_post_commit_is_never_changed(self):
        with workspace_tempdir("hook-post-commit-preserved-") as temporary:
            repo = Path(temporary)
            post_commit = repo / ".git" / "hooks" / "post-commit"
            post_commit.parent.mkdir(parents=True)
            post_commit.write_text("#!/bin/sh\necho user-post-commit\n", encoding="utf-8")
            self.assertTrue(load_installer().install_git_hook(repo))
            self.assertEqual(post_commit.read_text(encoding="utf-8"), "#!/bin/sh\necho user-post-commit\n")
            self.assertTrue((repo / ".git" / "hooks" / "pre-commit").exists())

    def test_existing_tool_hook_is_idempotent(self):
        installer = load_installer()
        with workspace_tempdir("hook-tool-") as temporary:
            repo = Path(temporary)
            hook = repo / ".git" / "hooks" / "pre-commit"
            hook.parent.mkdir(parents=True)
            hook.write_text(installer.PRE_COMMIT_HOOK_SCRIPT, encoding="utf-8")
            self.assertTrue(installer.install_git_hook(repo))

    def test_generated_hook_selects_python_fallbacks_and_fails_without_python(self):
        installer = load_installer()
        sh = shutil.which("sh")
        if not sh and sys.platform == "win32":
            git = shutil.which("git")
            candidate = Path(git).parents[1] / "bin" / "sh.exe" if git else None
            sh = str(candidate) if candidate and candidate.is_file() else None
        if not sh:
            self.skipTest("POSIX shell unavailable")

        with workspace_tempdir("hook-python-fallbacks-") as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            hook = root / "pre-commit"
            with hook.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(
                    installer.PRE_COMMIT_HOOK_SCRIPT.replace(
                        "REPO_ROOT=$(git rev-parse --show-toplevel)",
                        f'REPO_ROOT="{root.as_posix()}"',
                    )
                )
            checker = root / "scripts" / "check_mission_center.py"
            checker.parent.mkdir()
            checker.write_text("# test placeholder\n", encoding="utf-8")

            def run_with(*names, failed=()):
                for child in fake_bin.iterdir():
                    child.unlink()
                log = root / "invocation.log"
                if log.exists():
                    log.unlink()
                for name in names:
                    executable = fake_bin / name
                    with executable.open("w", encoding="utf-8", newline="\n") as handle:
                        handle.write(
                            '#!/bin/sh\n'
                            + ("if [ \"$1\" = \"-c\" ]; then exit 127; fi\n" if name in failed else "")
                            + 'printf "%s\\n" "$0 $*" > '
                            + f'"{log.as_posix()}"\n'
                        )
                    executable.chmod(0o755)
                env = {"PATH": str(fake_bin)}
                return subprocess.run(
                    [sh, str(hook)],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                ), log

            for available, selected, expected_prefix in (
                (("python3", "python", "py"), "python3", ""),
                (("python", "py"), "python", ""),
                (("py",), "py", "-3 "),
            ):
                result, log = run_with(*available)
                self.assertEqual(result.returncode, 0, result.stderr)
                invocation = log.read_text(encoding="utf-8")
                self.assertIn(f"/{selected} ", invocation.replace("\\", "/"))
                self.assertIn(
                    expected_prefix + str(checker).replace("\\", "/"),
                    invocation.replace("\\", "/"),
                )

            result, log = run_with()
            self.assertEqual(result.returncode, 1)
            self.assertIn("commit blocked", result.stderr)
            self.assertFalse(log.exists())

            result, log = run_with("python3", "python", failed=("python3",))
            self.assertEqual(result.returncode, 0, result.stderr)
            invocation = log.read_text(encoding="utf-8")
            self.assertIn("/python ", invocation.replace("\\", "/"))
            self.assertNotIn("/python3 ", invocation.replace("\\", "/"))

    def test_git_file_is_rejected_without_creating_hooks(self):
        with workspace_tempdir("hook-git-file-") as temporary:
            repo = Path(temporary)
            (repo / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
            self.assertFalse(load_installer().install_git_hook(repo))
            self.assertFalse((repo / ".git" / "hooks").exists())

    def test_existing_generated_crlf_hook_is_upgraded_to_lf(self):
        installer = load_installer()
        with workspace_tempdir("hook-tool-crlf-") as temporary:
            repo = Path(temporary)
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


if __name__ == "__main__":
    unittest.main()
