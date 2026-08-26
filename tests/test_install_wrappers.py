import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import workspace_tempdir


ROOT = Path(__file__).parents[1]


def run_wrapper(
    command: list[str],
    temporary: Path,
    *,
    mode: str,
    register: str | None = None,
    python_override: str | None = sys.executable,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
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
            "PYTHONUTF8": "1",
        }
    )
    if python_override is None:
        env.pop("MISSION_CENTER_PYTHON", None)
    else:
        env["MISSION_CENTER_PYTHON"] = python_override
    if register is None:
        env.pop("MISSION_CENTER_PUBLISH_REGISTER", None)
    else:
        env["MISSION_CENTER_PUBLISH_REGISTER"] = register
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


class InstallWrapperTests(unittest.TestCase):
    def test_python_wrapper_registration_is_explicit_opt_in(self):
        scripts = str(ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import install as install_wrapper

        base_env = {"HOME": str(ROOT), "USERPROFILE": str(ROOT)}
        with patch.dict(os.environ, base_env, clear=True):
            self.assertNotIn("--register", install_wrapper.build_publish_command(ROOT))
        with patch.dict(os.environ, {**base_env, "MISSION_CENTER_PUBLISH_REGISTER": "1"}, clear=True):
            self.assertIn("--register", install_wrapper.build_publish_command(ROOT))

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

    def test_formal_wrappers_request_registration_only_for_write(self):
        wrappers = (
            "install-windows.ps1",
            "install-plugin-windows.ps1",
            "install-unix.sh",
            "install-plugin-unix.sh",
        )
        for name in wrappers:
            normalized = (ROOT / "scripts" / name).read_text(encoding="utf-8").casefold()
            with self.subTest(name=name):
                self.assertIn("--register", normalized)
                if name.endswith(".ps1"):
                    self.assertIn('$mode -eq "--write"', normalized)
                    self.assertIn("py -3", normalized)
                else:
                    self.assertIn('[ "$mode" = "--write" ]', normalized)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell wrapper prerequisites are unavailable")
    def test_formal_powershell_write_fails_before_publish_without_cli(self):
        for name in ("install-windows.ps1", "install-plugin-windows.ps1"):
            with self.subTest(name=name), workspace_tempdir("install-wrapper-") as temporary:
                root = Path(temporary)
                result = run_wrapper(
                    [
                        str(shutil.which("pwsh")),
                        "-NoLogo",
                        "-NoProfile",
                        "-File",
                        str(ROOT / "scripts" / name),
                    ],
                    root,
                    mode="--write",
                    extra_env={"PATH": str(root / "empty-path")},
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Codex executable not found", result.stderr)
                self.assertFalse((root / "codex-home" / "skills" / "mission-center").exists())
                self.assertFalse(
                    (
                        root
                        / "codex-home"
                        / "local-marketplaces"
                        / "mission-center"
                        / "plugins"
                        / "mission-center"
                    ).exists()
                )

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell wrapper prerequisites are unavailable")
    def test_powershell_launcher_override_accepts_arguments(self):
        for name in ("install.ps1", "install-windows.ps1", "install-plugin-windows.ps1"):
            with self.subTest(name=name), workspace_tempdir("install-wrapper-") as temporary:
                mode = "--write" if name == "install.ps1" else "--dry-run"
                result = run_wrapper(
                    [
                        str(shutil.which("pwsh")),
                        "-NoLogo",
                        "-NoProfile",
                        "-File",
                        str(ROOT / "scripts" / name),
                    ],
                    Path(temporary),
                    mode=mode,
                    extra_env={"MISSION_CENTER_PYTHON": f'"{sys.executable}" -B'},
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

    @unittest.skipUnless(
        shutil.which("pwsh") and shutil.which("py"),
        "PowerShell and the Windows Python launcher are unavailable",
    )
    def test_powershell_wrappers_use_default_py3_candidate(self):
        for name in ("install.ps1", "install-windows.ps1", "install-plugin-windows.ps1"):
            with self.subTest(name=name), workspace_tempdir("install-wrapper-default-") as temporary:
                mode = "--write" if name == "install.ps1" else "--dry-run"
                result = run_wrapper(
                    ["pwsh", "-NoLogo", "-NoProfile", "-File", str(ROOT / "scripts" / name)],
                    Path(temporary),
                    mode=mode,
                    python_override=None,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if mode == "--dry-run":
                    self.assertIn("Dry-run completed", result.stdout)
                else:
                    self.assertTrue(
                        (Path(temporary) / "codex-home" / "skills" / "mission-center" / "SKILL.md").is_file()
                    )


if __name__ == "__main__":
    unittest.main()
