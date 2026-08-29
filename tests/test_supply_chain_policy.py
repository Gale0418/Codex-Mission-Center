import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
import tomllib
import textwrap
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).parents[1]


_ALLOWED_REGISTRIES = {
    "registry+https://github.com/rust-lang/crates.io-index",
    "registry+https://index.crates.io/",
    "sparse+https://index.crates.io/",
}


def _scan_vendored_cargo_sources(workspace: Path) -> None:
    """Apply the CI Cargo source/checksum policy to a fixture workspace."""
    config = tomllib.loads((workspace / ".cargo" / "config.toml").read_text(encoding="utf-8"))
    sources = config.get("source", {})
    if sources.get("crates-io", {}).get("replace-with") != "vendored-sources":
        raise ValueError("Cargo config must replace crates-io with vendored-sources")
    if sources.get("vendored-sources", {}).get("directory") != "vendor":
        raise ValueError("Cargo config must use the vendor directory")

    lock = tomllib.loads((workspace / "Cargo.lock").read_text(encoding="utf-8"))
    vendor = workspace / "vendor"

    def check_workspace_path(value: str) -> None:
        uri = urlsplit(value[5:])
        path = unquote(uri.path) if uri.scheme == "file" else value[5:]
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        try:
            candidate = Path(path).resolve()
            candidate.relative_to(workspace.resolve())
        except ValueError as exc:
            raise ValueError(f"Cargo.lock path source escapes workspace: {value}") from exc
        if not candidate.exists():
            raise ValueError(f"Cargo.lock path source does not exist: {value}")

    for package in lock.get("package", []):
        source = package.get("source")
        if source is None:
            continue
        if source.startswith("git+"):
            raise ValueError(f"Cargo.lock contains a git dependency: {source}")
        if source.startswith("path+"):
            check_workspace_path(source)
            continue
        if source not in _ALLOWED_REGISTRIES:
            raise ValueError(f"Cargo.lock contains an unknown registry: {source}")
        checksum = package.get("checksum", "")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError(f"Missing or invalid checksum for {package['name']}")
        package_dir = vendor / f"{package['name']}-{package['version']}"
        metadata_path = next(
            (package_dir / name for name in (".crate-checksum.json", ".cargo-checksum.json") if (package_dir / name).is_file()),
            None,
        )
        if metadata_path is None:
            raise ValueError(f"Missing vendor checksum metadata for {package['name']}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        vendor_checksum = metadata.get("package", metadata.get("checksum", ""))
        if vendor_checksum != checksum:
            raise ValueError(f"Vendor checksum mismatch for {package['name']}")


def _write_scan_fixture(root: Path, *, source: str, checksum: str | None = "a" * 64, config: str | None = None) -> None:
    (root / ".cargo").mkdir(parents=True)
    (root / "vendor" / "serde_json-1.0.151").mkdir(parents=True)
    config = config or (
        '[source.crates-io]\nreplace-with = "vendored-sources"\n\n'
        '[source.vendored-sources]\ndirectory = "vendor"\n'
    )
    (root / ".cargo" / "config.toml").write_text(config, encoding="utf-8")
    checksum_line = f'checksum = "{checksum}"\n' if checksum is not None else ""
    (root / "Cargo.lock").write_text(
        'version = 4\n\n[[package]]\nname = "serde_json"\nversion = "1.0.151"\n'
        f'source = "{source}"\n{checksum_line}',
        encoding="utf-8",
    )
    (root / "vendor" / "serde_json-1.0.151" / ".crate-checksum.json").write_text(
        json.dumps({"package": checksum or ""}), encoding="utf-8"
    )


def _embedded_cargo_scanner_source(workflow: str) -> str:
    marker = "          python - <<'PY'\n"
    end_marker = "          PY\n"
    start = workflow.index(marker) + len(marker)
    end = workflow.index(end_marker, start)
    return textwrap.dedent(workflow[start:end])


class SupplyChainPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = (ROOT / "docs" / "supply-chain-policy.md").read_text(encoding="utf-8")
        self.workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    def test_actions_and_release_dependency_are_content_pinned(self):
        requirements = (ROOT / "requirements-runtime.txt").read_text(encoding="utf-8")
        lock = (ROOT / "requirements-runtime.lock").read_text(encoding="utf-8")
        self.assertIn("websockets>=16.1,<17", self.policy)
        self.assertIn("websockets>=16.1,<17", requirements)
        self.assertIn("websockets-16.1-py3-none-any.whl", lock)
        self.assertRegex(lock, r"--hash=sha256:[0-9a-f]{64}")
        self.assertIn("--require-hashes -r requirements-runtime.lock", self.workflow)
        refs = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", self.workflow)
        self.assertTrue(refs)
        for ref in refs:
            self.assertRegex(ref, r"^[0-9a-f]{40}$")
        self.assertIn("Never guess", self.policy)

    def test_rust_ci_locks_toolchain_and_offline_commands(self):
        self.assertIn("os: [ubuntu-latest, windows-latest, macos-latest]", self.workflow)
        self.assertIn("toolchain install 1.98.0 --profile minimal --component rustfmt,clippy", self.workflow)
        self.assertIn("cargo metadata --locked --offline", self.workflow)
        self.assertIn("cargo fmt --all -- --check", self.workflow)
        self.assertIn("cargo clippy --workspace --all-targets --all-features --locked --offline -- -D warnings", self.workflow)
        self.assertIn("cargo test --workspace --locked --offline", self.workflow)
        self.assertIn('rustup_bin="$HOME/.cargo/bin/rustup"', self.workflow)

    def test_vendoring_license_and_artifact_policy_are_documented(self):
        self.assertIn("rust/vendor/", self.workflow)
        self.assertIn("Cargo.lock contains a git dependency", self.workflow)
        self.assertIn("unknown source", self.workflow)
        self.assertIn("rust/vendor/", self.policy)
        self.assertIn("rust/target/", self.policy)
        self.assertIn("NOTICE.md", self.policy)
        self.assertIn("MIT license", self.policy)
        self.assertIn("upload-artifact", self.workflow)
        self.assertIn("retention-days: 14", self.workflow)
        self.assertIn("serde_json", self.policy)
        self.assertIn("vendored status", self.policy)
        self.assertIn("known advisory scan status", self.policy)
        self.assertIn("permanent guarantee", self.policy)

    def test_target_output_is_ignored(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertRegex(gitignore, r"(?m)^/?rust/target/\s*$")

    def test_aggregator_gates_python_and_rust(self):
        self.assertIn("needs: [python, rust, rust-release, rust-stable-package]", self.workflow)
        self.assertIn('needs.python.result', self.workflow)
        self.assertIn('needs.rust.result', self.workflow)
        self.assertIn('needs.rust-release.result', self.workflow)
        self.assertIn('needs.rust-stable-package.result', self.workflow)
        self.assertNotIn('needs.matrix.result', self.workflow)

    def test_rust_differential_is_built_configured_and_run(self):
        self.assertIn("cargo build --package mission-center-cli --locked --offline", self.workflow)
        self.assertIn("MISSION_CENTER_RUST_BIN", self.workflow)
        self.assertIn("rust/target/debug/mission-center", self.workflow)
        self.assertIn("python -m unittest tests.test_rust_differential -v", self.workflow)
        self.assertNotIn("skip", self.workflow[self.workflow.index("Run Rust/Python differential tests"):])

    def test_cargo_source_scanner_rejects_evil_registry_path_and_missing_checksum(self):
        cases = {
            "evil-registry": "registry+https://evil.example/",
            "git-dependency": "git+https://github.com/evil/dependency?rev=deadbeef",
        }
        for name, source in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                workspace = Path(temporary)
                _write_scan_fixture(workspace, source=source)
                with self.assertRaises(ValueError):
                    _scan_vendored_cargo_sources(workspace)

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            outside = (workspace.parent / "outside-vendor").as_uri()
            _write_scan_fixture(workspace, source=f"path+{outside}")
            with self.assertRaises(ValueError):
                _scan_vendored_cargo_sources(workspace)

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            _write_scan_fixture(workspace, source=next(iter(_ALLOWED_REGISTRIES)), checksum=None)
            with self.assertRaises(ValueError):
                _scan_vendored_cargo_sources(workspace)

    def test_cargo_source_scanner_rejects_misconfigured_vendor_and_accepts_matching_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            _write_scan_fixture(
                workspace,
                source=next(iter(_ALLOWED_REGISTRIES)),
                config='[source.crates-io]\nreplace-with = "wrong-source"\n',
            )
            with self.assertRaises(ValueError):
                _scan_vendored_cargo_sources(workspace)

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            _write_scan_fixture(workspace, source=next(iter(_ALLOWED_REGISTRIES)))
            _scan_vendored_cargo_sources(workspace)

    def test_embedded_cargo_scanner_compiles_and_runs_valid_and_invalid_fixtures(self):
        scanner = _embedded_cargo_scanner_source(self.workflow)
        with tempfile.TemporaryDirectory() as temporary:
            scanner_path = Path(temporary) / "embedded_scanner.py"
            scanner_path.write_text(scanner, encoding="utf-8")
            py_compile.compile(str(scanner_path), doraise=True)

            valid_root = Path(temporary) / "valid"
            valid_root.mkdir()
            _write_scan_fixture(valid_root / "rust", source=next(iter(_ALLOWED_REGISTRIES)))
            valid = subprocess.run(
                [sys.executable, "-c", scanner],
                cwd=valid_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(valid.returncode, 0, valid.stderr)

            invalid_root = Path(temporary) / "invalid"
            invalid_root.mkdir()
            _write_scan_fixture(invalid_root / "rust", source="registry+https://evil.example/")
            invalid = subprocess.run(
                [sys.executable, "-c", scanner],
                cwd=invalid_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("unknown source", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
