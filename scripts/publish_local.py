#!/usr/bin/env python3
"""Publish the canonical Mission Center Skill to local derived locations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path


PLUGIN_ITEMS = (
    ".codex-plugin",
    "assets",
    "skills",
    "scripts",
    "README.md",
    "LICENSE",
    "NOTICE.md",
    "PRIVACY.md",
)
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
MARKETPLACE_CATEGORY_FALLBACK = "Productivity"


def is_excluded(relative: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in relative.parts) or (
        relative.suffix.lower() in EXCLUDED_SUFFIXES
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_plugin_manifest(repo: Path) -> dict:
    manifest_path = repo / ".codex-plugin" / "plugin.json"
    return load_json(manifest_path)


def normalize_plugin_manifest_bytes(content: bytes) -> bytes:
    manifest = json.loads(content.decode("utf-8"))
    version = str(manifest.get("version", ""))
    manifest["version"] = version.split("+codex.", 1)[0]
    return json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")


def build_marketplace_manifest(plugin_manifest: dict) -> dict:
    plugin_name = plugin_manifest["name"]
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
    stamped["version"] = f"{plugin_manifest['version']}+codex.{uuid.uuid4().hex}"
    return (json.dumps(stamped, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def iter_files(root: Path):
    if not root.exists():
        return
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
    resolved = path.expanduser().resolve()
    actual_tail = tuple(part.casefold() for part in resolved.parts[-2:])
    normalized_tail = tuple(part.casefold() for part in expected_tail)
    if actual_tail != normalized_tail:
        expected = "/".join(expected_tail)
        raise ValueError(f"Target must end with {expected}: {resolved}")
    return resolved


def copy_tree_contents(source: Path, destination: Path) -> None:
    for relative, path in iter_files(source):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def stage_skill(source: Path, staging: Path) -> None:
    copy_tree_contents(source, staging)


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
                manifest_path = target_dir / "plugin.json"
                if stamp_version:
                    manifest_path.write_bytes(stamped_plugin_manifest_bytes(plugin_manifest))
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
    target.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    staging = target.parent / f".{target.name}.staging-{token}"
    backup = target.parent / f".{target.name}.backup-{token}"
    staging.mkdir()
    try:
        stage_writer(staging)
        if target.exists():
            target.rename(backup)
        try:
            staging.rename(target)
        except Exception:
            if backup.exists() and not target.exists():
                backup.rename(target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


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
        ("personal", file_map(canonical), file_map(personal)),
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
        if candidate.exists():
            return candidate.resolve()

    for name in ("codex", "codex.exe"):
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved).resolve()

    return None


def register_marketplace_and_plugin(
    codex_executable: Path,
    marketplace_root: Path,
    plugin_manifest: dict,
) -> None:
    marketplace_name = f"{plugin_manifest['name']}-local"
    plugin_ref = f"{plugin_manifest['name']}@{marketplace_name}"
    subprocess.run(
        [str(codex_executable), "plugin", "marketplace", "add", str(marketplace_root)],
        check=True,
    )
    subprocess.run(
        [str(codex_executable), "plugin", "add", plugin_ref],
        check=True,
    )


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
    repo = args.repo.expanduser().resolve()
    canonical = repo / "skills" / "mission-center"
    if not (canonical / "SKILL.md").is_file():
        raise ValueError(f"Canonical Skill not found: {canonical}")
    if not (repo / ".codex-plugin" / "plugin.json").is_file():
        raise ValueError(f"Plugin manifest not found: {repo}")

    personal = validate_target(args.personal_skill, ("skills", "mission-center"))
    marketplace = validate_target(args.marketplace_plugin, ("plugins", "mission-center"))
    marketplace_root = marketplace.parent.parent
    cache_skill = None
    if args.cache_skill is not None:
        cache_skill = validate_target(args.cache_skill, ("skills", "mission-center"))

    if args.write and cache_skill is not None:
        raise ValueError("--cache-skill is verify-only; cache is Codex-managed")

    if args.dry_run:
        print_changes("personal", map_diff(file_map(canonical), file_map(personal)))
        print_changes(
            "marketplace",
            map_diff(marketplace_file_map(repo), file_map(marketplace_root)),
        )
        if cache_skill is not None:
            print_changes("cache", map_diff(file_map(canonical), file_map(cache_skill)))
        return 0

    if args.write:
        replace_from_stage(personal, lambda staging: stage_skill(canonical, staging))
        replace_from_stage(
            marketplace_root,
            lambda staging: stage_marketplace(repo, staging, stamp_version=args.register),
        )
        if args.register:
            codex_executable = get_codex_executable(args.codex_cli)
            if codex_executable is None:
                raise RuntimeError(
                    "Codex executable not found. Set CODEX_CLI_PATH or pass --codex-cli before using --register."
                )
            register_marketplace_and_plugin(
                codex_executable,
                marketplace_root,
                load_plugin_manifest(repo),
            )

    return 0 if verify_targets(canonical, personal, repo, marketplace_root, cache_skill) else 1


if __name__ == "__main__":
    raise SystemExit(main())
