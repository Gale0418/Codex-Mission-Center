#!/usr/bin/env python3
"""Publish the canonical Mission Center Skill to local derived locations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


PLUGIN_ITEMS = (
    ".codex-plugin",
    "assets",
    "hooks",
    "skills",
    "scripts",
    "README.md",
    "LICENSE",
    "NOTICE.md",
    "PRIVACY.md",
    "requirements-runtime.txt",
)
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
MARKETPLACE_CATEGORY_FALLBACK = "Productivity"
PLUGIN_NAME = "mission-center"
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def is_excluded(relative: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in relative.parts) or (
        relative.suffix.lower() in EXCLUDED_SUFFIXES
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_semver(version: object) -> str:
    value = str(version)
    if not SEMVER_PATTERN.fullmatch(value):
        raise ValueError(f"Plugin version must be SemVer: {value!r}")
    return value


def normalized_version(version: object) -> str:
    return validate_semver(version).split("+", 1)[0]


def load_plugin_manifest(repo: Path) -> dict:
    manifest_path = repo / ".codex-plugin" / "plugin.json"
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("Plugin manifest must be a JSON object")
    if manifest.get("name") != PLUGIN_NAME:
        raise ValueError(f"Plugin name must be {PLUGIN_NAME!r}")
    validate_semver(manifest.get("version"))
    return manifest


def normalize_plugin_manifest_bytes(content: bytes) -> bytes:
    manifest = json.loads(content.decode("utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Plugin manifest must be a JSON object")
    if manifest.get("name") != PLUGIN_NAME:
        raise ValueError(f"Plugin name must be {PLUGIN_NAME!r}")
    manifest["version"] = normalized_version(manifest.get("version"))
    return json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")


def build_marketplace_manifest(plugin_manifest: dict) -> dict:
    if plugin_manifest.get("name") != PLUGIN_NAME:
        raise ValueError(f"Plugin name must be {PLUGIN_NAME!r}")
    validate_semver(plugin_manifest.get("version"))
    plugin_name = PLUGIN_NAME
    display_name = plugin_manifest.get("interface", {}).get("displayName", plugin_name)
    category = (
        plugin_manifest.get("interface", {}).get("category")
        or MARKETPLACE_CATEGORY_FALLBACK
    )
    return {
        "name": f"{plugin_name}-local",
        "interface": {"displayName": f"Local {display_name}"},
        "plugins": [
            {
                "name": plugin_name,
                "source": {
                    "source": "local",
                    "path": f"./plugins/{plugin_name}",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": category,
            }
        ],
    }


def serialize_marketplace_manifest(manifest: dict) -> bytes:
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def stamped_plugin_manifest_bytes(plugin_manifest: dict) -> bytes:
    stamped = dict(plugin_manifest)
    version_prefix = normalized_version(plugin_manifest["version"])
    stamped["version"] = f"{version_prefix}+codex.{uuid.uuid4().hex}"
    return (json.dumps(stamped, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def iter_files(root: Path):
    if not root.exists():
        return
    ensure_source_tree(root)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if not is_excluded(relative):
            yield relative, path


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_hash(relative: Path, path: Path) -> str:
    if relative.as_posix().endswith(".codex-plugin/plugin.json"):
        content = normalize_plugin_manifest_bytes(path.read_bytes())
        return hashlib.sha256(content).hexdigest()
    return file_hash(path)


def file_map(root: Path) -> dict[str, str]:
    return {
        relative.as_posix(): normalized_hash(relative, path)
        for relative, path in iter_files(root)
    }


def marketplace_file_map(repo: Path) -> dict[str, str]:
    plugin_manifest = load_plugin_manifest(repo)
    result: dict[str, str] = {}
    for name in PLUGIN_ITEMS:
        item = repo / name
        if item.is_file():
            relative = Path("plugins") / plugin_manifest["name"] / name
            if relative.as_posix().endswith(".codex-plugin/plugin.json"):
                content = normalize_plugin_manifest_bytes(item.read_bytes())
                result[relative.as_posix()] = hashlib.sha256(content).hexdigest()
            else:
                result[relative.as_posix()] = file_hash(item)
        elif item.is_dir():
            for relative, path in iter_files(item):
                target = Path("plugins") / plugin_manifest["name"] / name / relative
                if target.as_posix().endswith(".codex-plugin/plugin.json"):
                    content = normalize_plugin_manifest_bytes(path.read_bytes())
                    result[target.as_posix()] = hashlib.sha256(content).hexdigest()
                else:
                    result[target.as_posix()] = file_hash(path)
    manifest_bytes = serialize_marketplace_manifest(build_marketplace_manifest(plugin_manifest))
    result[".agents/plugins/marketplace.json"] = hashlib.sha256(manifest_bytes).hexdigest()
    return result


def map_diff(expected: dict[str, str], actual: dict[str, str]) -> list[str]:
    changes = []
    for name in sorted(expected.keys() | actual.keys()):
        if name not in actual:
            changes.append(f"+ {name}")
        elif name not in expected:
            changes.append(f"- {name}")
        elif expected[name] != actual[name]:
            changes.append(f"M {name}")
    return changes


def validate_target(path: Path, expected_tail: tuple[str, str]) -> Path:
    candidate = path.expanduser()
    reject_symlink_components(candidate, "target")
    resolved = candidate.resolve()
    actual_tail = tuple(part.casefold() for part in resolved.parts[-2:])
    normalized_tail = tuple(part.casefold() for part in expected_tail)
    if actual_tail != normalized_tail:
        expected = "/".join(expected_tail)
        raise ValueError(f"Target must end with {expected}: {resolved}")
    return resolved


def reject_symlink_components(path: Path, label: str) -> None:
    """Reject symlink/junction components before resolving a source or target."""
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            # macOS exposes a few fixed root aliases (for example /var ->
            # /private/var). These are part of the platform layout, not
            # user-controlled source or target redirects. All other symlink
            # components remain forbidden.
            trusted_macos_aliases = {
                Path("/etc"): Path("/private/etc"),
                Path("/tmp"): Path("/private/tmp"),
                Path("/var"): Path("/private/var"),
            }
            trusted_target = trusted_macos_aliases.get(current)
            if (
                sys.platform == "darwin"
                and trusted_target is not None
                and current.resolve() == trusted_target
            ):
                continue
            raise ValueError(f"{label} must not contain symlinks: {path}")


def ensure_source_tree(root: Path) -> None:
    if not root.exists():
        return
    reject_symlink_components(root, "source")
    root_resolved = root.resolve()
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            item = current_path / name
            if item.is_symlink():
                raise ValueError(f"Source tree must not contain symlinks: {item}")
            try:
                item.resolve().relative_to(root_resolved)
            except ValueError as exc:
                raise ValueError(f"Source path escapes repository: {item}") from exc


def assert_within(root: Path, child: Path, label: str) -> None:
    try:
        child.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes its containing root: {child}") from exc


def copy_tree_contents(source: Path, destination: Path) -> None:
    for relative, path in iter_files(source):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def skill_file_map(repo: Path) -> dict[str, str]:
    result = file_map(repo / "skills" / "mission-center")
    requirements = repo / "requirements-runtime.txt"
    if requirements.is_file():
        result["requirements-runtime.txt"] = file_hash(requirements)
    return result


def stage_skill(repo: Path, source: Path, staging: Path) -> None:
    copy_tree_contents(source, staging)
    requirements = repo / "requirements-runtime.txt"
    if requirements.is_file():
        shutil.copy2(requirements, staging / "requirements-runtime.txt")


def stage_marketplace(repo: Path, staging: Path, stamp_version: bool) -> None:
    plugin_manifest = load_plugin_manifest(repo)
    plugin_root = staging / "plugins" / plugin_manifest["name"]
    for name in PLUGIN_ITEMS:
        source = repo / name
        if source.is_file():
            target = plugin_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if name == ".codex-plugin":
                raise ValueError("Unexpected file entry for .codex-plugin")
            shutil.copy2(source, target)
        elif source.is_dir():
            if name == ".codex-plugin":
                target_dir = plugin_root / name
                copy_tree_contents(source, target_dir)
            else:
                copy_tree_contents(source, plugin_root / name)

    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    if manifest_path.is_file() and stamp_version:
        manifest_path.write_bytes(stamped_plugin_manifest_bytes(plugin_manifest))

    marketplace_manifest_path = staging / ".agents" / "plugins" / "marketplace.json"
    marketplace_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    marketplace_manifest_path.write_bytes(
        serialize_marketplace_manifest(build_marketplace_manifest(plugin_manifest))
    )


def replace_from_stage(target: Path, stage_writer) -> None:
    transaction = prepare_file_transaction([(target, stage_writer)])
    try:
        transaction.commit()
    except Exception:
        transaction.rollback()
        raise
    transaction.finalize()


class FileTransaction:
    def __init__(self, entries: list[tuple[Path, Path, Path]]) -> None:
        self.entries = entries
        self.committed: list[tuple[Path, Path]] = []

    def commit(self) -> None:
        try:
            for target, staging, backup in self.entries:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    target.rename(backup)
                staging.rename(target)
                self.committed.append((target, backup))
        except Exception:
            self.rollback()
            raise

    def rollback(self) -> None:
        for target, backup in reversed(self.committed):
            if target.exists() or target.is_symlink():
                shutil.rmtree(target)
            if backup.exists() or backup.is_symlink():
                backup.rename(target)
        self.committed.clear()
        for target, staging, backup in self.entries:
            if staging.exists() or staging.is_symlink():
                shutil.rmtree(staging)
            if backup.exists() or backup.is_symlink():
                # A backup not yet committed belongs to the original target.
                if not target.exists():
                    backup.rename(target)

    def finalize(self) -> None:
        for _, staging, backup in self.entries:
            if staging.exists() or staging.is_symlink():
                shutil.rmtree(staging)
            if backup.exists() or backup.is_symlink():
                shutil.rmtree(backup)


def prepare_file_transaction(
    writers: list[tuple[Path, object]],
) -> FileTransaction:
    entries: list[tuple[Path, Path, Path]] = []
    try:
        for target, writer in writers:
            reject_symlink_components(target, "target")
            target.parent.mkdir(parents=True, exist_ok=True)
            token = uuid.uuid4().hex
            staging = target.parent / f".{target.name}.staging-{token}"
            backup = target.parent / f".{target.name}.backup-{token}"
            assert_within(target.parent, staging, "staging path")
            assert_within(target.parent, backup, "backup path")
            staging.mkdir()
            entries.append((target, staging, backup))
            writer(staging)
        return FileTransaction(entries)
    except Exception:
        for _, staging, backup in entries:
            if staging.exists() or staging.is_symlink():
                shutil.rmtree(staging)
            if backup.exists() or backup.is_symlink():
                shutil.rmtree(backup)
        raise


def print_changes(label: str, changes: list[str]) -> None:
    print(f"[{label}]")
    if changes:
        for change in changes:
            print(change)
    else:
        print("no changes")


def verify_targets(
    canonical: Path,
    personal: Path,
    repo: Path,
    marketplace_root: Path,
    cache_skill: Path | None,
) -> bool:
    targets = [
        ("personal", skill_file_map(repo), file_map(personal)),
        ("marketplace", marketplace_file_map(repo), file_map(marketplace_root)),
    ]
    if cache_skill is not None:
        targets.append(("cache", file_map(canonical), file_map(cache_skill)))

    valid = True
    for label, expected, actual in targets:
        changes = map_diff(expected, actual)
        print_changes(label, changes)
        valid = valid and not changes
    return valid


def is_usable_codex_executable(candidate: Path, *, from_path: bool = False) -> bool:
    """Return whether a candidate is a usable CLI file.

    WindowsApps command aliases can be discoverable through PATH while still
    rejecting direct subprocess launches.  They are intentionally ignored
    when discovered through PATH; an explicit path or CODEX_CLI_PATH remains
    an intentional override and is validated only as a file.
    """
    try:
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            return False
        if from_path and os.name == "nt":
            return not any(part.casefold() == "windowsapps" for part in candidate.parts)
    except OSError:
        return False
    return True


def get_codex_executable(explicit: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())

    env_override = os.environ.get("CODEX_CLI_PATH")
    if env_override:
        candidates.append(Path(env_override).expanduser())

    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    candidates.extend(
        [
            codex_home / ".sandbox-bin" / "codex",
            codex_home / ".sandbox-bin" / "codex.exe",
        ]
    )

    for candidate in candidates:
        if is_usable_codex_executable(candidate):
            return candidate.resolve()

    for name in ("codex", "codex.exe"):
        resolved = shutil.which(name)
        if resolved and is_usable_codex_executable(Path(resolved), from_path=True):
            return Path(resolved).resolve()

    return None


def register_marketplace_and_plugin(
    codex_executable: Path,
    marketplace_root: Path,
    plugin_manifest: dict,
) -> None:
    marketplace_name = f"{plugin_manifest['name']}-local"
    plugin_ref = f"{plugin_manifest['name']}@{marketplace_name}"
    previous_plugin = False
    previous_marketplace = False
    try:
        result = subprocess.run(
            [str(codex_executable), "plugin", "remove", plugin_ref],
            check=False,
        )
        # A successful remove proves that this registration existed before the
        # transaction and therefore must be recreated if a later add fails.
        previous_plugin = getattr(result, "returncode", 1) == 0
        result = subprocess.run(
            [str(codex_executable), "plugin", "marketplace", "remove", marketplace_name],
            check=False,
        )
        previous_marketplace = getattr(result, "returncode", 1) == 0
        subprocess.run(
            [str(codex_executable), "plugin", "marketplace", "add", str(marketplace_root)],
            check=True,
        )
        subprocess.run(
            [str(codex_executable), "plugin", "add", plugin_ref],
            check=True,
        )
    except Exception:
        # The CLI exposes remove/add but no portable transaction primitive. Rebuild
        # the prior local registration when a mutation fails; all rollback errors
        # are suppressed so the original failure remains visible to the caller.
        rollback_registration(
            codex_executable,
            marketplace_root,
            plugin_ref,
            marketplace_name,
            previous_marketplace,
            previous_plugin,
        )
        raise


def rollback_registration(
    codex_executable: Path,
    marketplace_root: Path,
    plugin_ref: str,
    marketplace_name: str,
    had_marketplace: bool,
    had_plugin: bool,
) -> None:
    def run(command: list[str]) -> None:
        try:
            subprocess.run([str(codex_executable), *command], check=False)
        except Exception:
            pass

    run(["plugin", "remove", plugin_ref])
    run(["plugin", "marketplace", "remove", marketplace_name])
    if had_marketplace:
        run(["plugin", "marketplace", "add", str(marketplace_root)])
    if had_plugin:
        run(["plugin", "add", plugin_ref])


def preflight(
    repo: Path,
    personal: Path,
    marketplace: Path,
    cache_skill: Path | None,
    write: bool,
    register: bool,
    codex_cli: Path | None,
) -> tuple[Path, Path | None, dict, Path | None]:
    reject_symlink_components(repo, "source repository")
    ensure_source_tree(repo)
    canonical = repo / "skills" / PLUGIN_NAME
    manifest_path = repo / ".codex-plugin" / "plugin.json"
    if not (canonical / "SKILL.md").is_file():
        raise ValueError(f"Canonical Skill not found: {canonical}")
    if not manifest_path.is_file():
        raise ValueError(f"Plugin manifest not found: {repo}")
    plugin_manifest = load_plugin_manifest(repo)
    personal_target = validate_target(personal, ("skills", PLUGIN_NAME))
    marketplace_target = validate_target(marketplace, ("plugins", PLUGIN_NAME))
    marketplace_root = marketplace_target.parent.parent
    assert_within(marketplace_root, marketplace_target, "marketplace plugin target")
    marketplace_manifest = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    assert_within(marketplace_root, marketplace_manifest, "marketplace manifest")
    cache_target = None
    if cache_skill is not None:
        cache_target = validate_target(cache_skill, ("skills", PLUGIN_NAME))
    if cache_target is not None and write:
        raise ValueError("--cache-skill is verify-only; cache is Codex-managed")
    codex_executable = None
    if register:
        codex_executable = get_codex_executable(codex_cli)
        if codex_executable is None:
            raise RuntimeError(
                "Codex executable not found. Set CODEX_CLI_PATH or pass --codex-cli before using --register."
            )
    # Build all source maps before any write; this also validates every derived
    # source path and catches symlink/escape attempts during --register preflight.
    skill_file_map(repo)
    marketplace_file_map(repo)
    return personal_target, cache_target, plugin_manifest, codex_executable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish Mission Center from its canonical repository source."
    )
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--personal-skill", required=True, type=Path)
    parser.add_argument("--marketplace-plugin", required=True, type=Path)
    parser.add_argument("--cache-skill", type=Path)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--codex-cli", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--verify", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_input = args.repo.expanduser()
    reject_symlink_components(repo_input, "source repository")
    repo = repo_input.resolve()
    canonical = repo / "skills" / PLUGIN_NAME
    personal, cache_skill, plugin_manifest, codex_executable = preflight(
        repo,
        args.personal_skill,
        args.marketplace_plugin,
        args.cache_skill,
        args.write,
        args.register,
        args.codex_cli,
    )
    marketplace = validate_target(args.marketplace_plugin, ("plugins", PLUGIN_NAME))
    marketplace_root = marketplace.parent.parent

    if args.dry_run:
        print_changes("personal", map_diff(skill_file_map(repo), file_map(personal)))
        print_changes(
            "marketplace",
            map_diff(marketplace_file_map(repo), file_map(marketplace_root)),
        )
        if cache_skill is not None:
            print_changes("cache", map_diff(file_map(canonical), file_map(cache_skill)))
        return 0

    if args.write:
        transaction = prepare_file_transaction(
            [
                (personal, lambda staging: stage_skill(repo, canonical, staging)),
                (
                    marketplace_root,
                    lambda staging: stage_marketplace(
                        repo, staging, stamp_version=args.register
                    ),
                ),
            ]
        )
        try:
            transaction.commit()
            if args.register and codex_executable is not None:
                register_marketplace_and_plugin(
                    codex_executable,
                    marketplace_root,
                    plugin_manifest,
                )
        except Exception:
            transaction.rollback()
            raise
        transaction.finalize()

    return 0 if verify_targets(canonical, personal, repo, marketplace_root, cache_skill) else 1


if __name__ == "__main__":
    raise SystemExit(main())
