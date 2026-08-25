import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]


def run_wrapper(command: list[str], temporary: Path, *, mode: str, register: str = "0") -> subprocess.CompletedProcess[str]:
    codex_home = temporary / "codex-home"
    env = os.environ.copy()
    env.update(
        {
            "CODEX_HOME": str(codex_home),
            "MISSION_CENTER_PERSONAL_SKILL": str(codex_home / "skills" / "mission-center"),
            "MISSION_CENTER_MARKETPLACE_PLUGIN": str(
                codex_home / "local-marketplaces" / "mission-center" / "plugins" / "mission-center"
            ),
            "MISSION_CENTER_PUBLISH_MODE": mode,
            "MISSION_CENTER_PUBLISH_REGISTER": register,
            "PYTHONUTF8": "1",
        }
    )
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


class InstallWrapperTests(unittest.TestCase):
    def test_python_wrapper_executes_publisher(self):
        with workspace_tempdir("install-wrapper-") as temporary:
            root = Path(temporary)
            result = run_wrapper(
                [sys.executable, str(ROOT / "scripts" / "install.py")],
                root,
                mode="--write",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                (root / "codex-home" / "skills" / "mission-center" / "SKILL.md").is_file()
            )
            self.assertTrue(
                (
                    root
                    / "codex-home"
                    / "local-marketplaces"
                    / "mission-center"
                    / "plugins"
                    / "mission-center"
                    / ".codex-plugin"
                    / "plugin.json"
                ).is_file()
            )

    @unittest.skipUnless(
        os.name != "nt" and shutil.which("bash") and shutil.which("python3"),
        "Unix wrapper prerequisites are unavailable",
    )
    def test_unix_wrappers_execute_publisher(self):
        for name in ("install-unix.sh", "install-plugin-unix.sh"):
            with self.subTest(name=name), workspace_tempdir("install-wrapper-") as temporary:
                result = run_wrapper(
                    ["bash", str(ROOT / "scripts" / name)],
                    Path(temporary),
                    mode="--dry-run",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Dry-run completed", result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell wrapper prerequisites are unavailable")
    def test_powershell_wrappers_execute_publisher(self):
        for name in ("install.ps1", "install-windows.ps1", "install-plugin-windows.ps1"):
            with self.subTest(name=name), workspace_tempdir("install-wrapper-") as temporary:
                mode = "--write" if name == "install.ps1" else "--dry-run"
                result = run_wrapper(
                    ["pwsh", "-NoLogo", "-NoProfile", "-File", str(ROOT / "scripts" / name)],
                    Path(temporary),
                    mode=mode,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if mode == "--dry-run":
                    self.assertIn("Dry-run completed", result.stdout)
                else:
                    self.assertTrue(
                        (
                            Path(temporary)
                            / "codex-home"
                            / "skills"
                            / "mission-center"
                            / "SKILL.md"
                        ).is_file()
                    )


if __name__ == "__main__":
    unittest.main()
