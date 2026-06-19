#!/usr/bin/env python3
"""Publish the canonical Mission Center Skill to local derived locations."""

from __future__ import annotations

import argparse
import hashlib
import shutil
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
)
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def is_excluded(relative: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in relative.parts) or (
        relative.suffix.lower() in EXCLUDED_SUFFIXES
    )


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


def file_map(root: Path) -> dict[str, str]:
    return {relative.as_posix(): file_hash(path) for relative, path in iter_files(root)}


def plugin_file_map(repo: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in PLUGIN_ITEMS:
        item = repo / name
        if item.is_file():
            result[Path(name).as_posix()] = file_hash(item)
        elif item.is_dir():
            for relative, path in iter_files(item):
                result[(Path(name) / relative).as_posix()] = file_hash(path)
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


def stage_plugin(repo: Path, staging: Path) -> None:
    for name in PLUGIN_ITEMS:
        source = repo / name
        if source.is_file():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif source.is_dir():
            copy_tree_contents(source, staging / name)


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


def verify_skill_targets(
    canonical: Path,
    personal: Path,
    marketplace_skill: Path,
    cache_skill: Path | None,
) -> bool:
    expected = file_map(canonical)
    targets = [("personal", personal), ("marketplace", marketplace_skill)]
    if cache_skill is not None:
        targets.append(("cache", cache_skill))

    valid = True
    for label, target in targets:
        changes = map_diff(expected, file_map(target))
        print_changes(label, changes)
        valid = valid and not changes
    return valid


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish Mission Center from its canonical repository source."
    )
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--personal-skill", required=True, type=Path)
    parser.add_argument("--marketplace-plugin", required=True, type=Path)
    parser.add_argument("--cache-skill", type=Path)
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

    personal = validate_target(
        args.personal_skill, ("skills", "mission-center")
    )
    marketplace = validate_target(
        args.marketplace_plugin, ("plugins", "mission-center")
    )
    cache_skill = None
    if args.cache_skill is not None:
        cache_skill = validate_target(
            args.cache_skill, ("skills", "mission-center")
        )

    if args.dry_run:
        print_changes("personal", map_diff(file_map(canonical), file_map(personal)))
        print_changes(
            "marketplace", map_diff(plugin_file_map(repo), file_map(marketplace))
        )
        if cache_skill is not None:
            print_changes(
                "cache", map_diff(file_map(canonical), file_map(cache_skill))
            )
        return 0

    if args.write:
        replace_from_stage(personal, lambda staging: stage_skill(canonical, staging))
        replace_from_stage(marketplace, lambda staging: stage_plugin(repo, staging))

    return 0 if verify_skill_targets(
        canonical,
        personal,
        marketplace / "skills" / "mission-center",
        cache_skill,
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
