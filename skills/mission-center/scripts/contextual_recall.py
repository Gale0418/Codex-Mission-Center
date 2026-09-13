#!/usr/bin/env python3
"""Validate and read bounded, source-backed Mission Center context cards.

This module is a compatibility oracle.  The formal Plugin runtime is Rust.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path, PureWindowsPath
from typing import Any

try:
    from security_scanner import scan_forbidden_content
except ImportError:  # pragma: no cover
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from security_scanner import scan_forbidden_content


CONTEXTS = {"resume", "enter-review", "before-deploy", "before-migration", "after-repeated-failure"}
VALIDITIES = {"active", "superseded", "incompatible", "recheck-required"}
SCOPE_FIELDS = ("taskId", "component", "phase", "operation", "version", "scopeDigest")
MAX_CARDS = 64
MAX_SOURCE_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 16 * 1024
_SAFE_ID = re.compile(r"^CTX-[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_MANIFEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any, limit: int) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= limit


def _safe_locator(value: Any) -> bool:
    if not _text(value, 1024) or not value.startswith("MissionCenter/") or "\\" in value or "://" in value or ":" in value:
        return False
    path = Path(value)
    windows = PureWindowsPath(value)
    return not path.is_absolute() and not windows.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _mission_root(workspace: Path) -> Path:
    root = Path(workspace).expanduser().resolve()
    return root if root.name.casefold() == "missioncenter" else root / "MissionCenter"


def _workspace_root(workspace: Path) -> Path:
    root = Path(workspace).expanduser().resolve()
    return root.parent if root.name.casefold() == "missioncenter" else root


def _safe_source_path(workspace: Path, locator: str) -> Path:
    root = _workspace_root(workspace)
    mission = root / "MissionCenter"
    candidate = root / locator
    current = root
    for part in Path(locator).parts:
        current = current / part
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("source path contains a symlink")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(mission.resolve(strict=True))
    except ValueError as exc:
        raise ValueError("source path escapes MissionCenter") from exc
    if not resolved.is_file():
        raise ValueError("source is not a regular file")
    return resolved


def validate_context_manifest(manifest: Any, workspace: Path | None = None) -> list[str]:
    if not isinstance(manifest, dict):
        return ["context manifest must be an object"]
    errors = list(scan_forbidden_content(manifest))
    allowed_root = {"schemaVersion", "artifactType", "manifestId", "cards"}
    errors.extend(f"unknown field: {key}" for key in sorted(set(manifest) - allowed_root))
    if manifest.get("schemaVersion") != "1.0":
        errors.append("schemaVersion must be 1.0")
    if manifest.get("artifactType") != "context-manifest":
        errors.append("artifactType must be context-manifest")
    manifest_id = manifest.get("manifestId")
    if manifest_id is not None and (
        not isinstance(manifest_id, str) or not _SAFE_MANIFEST_ID.fullmatch(manifest_id)
    ):
        errors.append("manifestId must be safe bounded text")
    cards = manifest.get("cards")
    if not isinstance(cards, list) or not cards:
        errors.append("cards must be a non-empty list")
        return errors
    if len(cards) > MAX_CARDS:
        errors.append(f"cards may contain at most {MAX_CARDS} entries")
    ids: set[str] = set()
    records: dict[str, dict[str, Any]] = {}
    active_scopes: set[tuple[str, tuple[str, ...]]] = set()
    source_anchors: set[tuple[str, str]] = set()
    edges: dict[str, str] = {}
    checked_workspace = _workspace_root(workspace) if workspace is not None else None
    for index, card in enumerate(cards):
        field = f"cards[{index}]"
        if not isinstance(card, dict):
            errors.append(f"{field} must be an object")
            continue
        allowed = {"id", "context", "reason", "scope", "source", "validity", "requiredVerification", "supersedes"}
        errors.extend(f"{field} unknown field: {key}" for key in sorted(set(card) - allowed))
        identifier = card.get("id")
        if not isinstance(identifier, str) or not _SAFE_ID.fullmatch(identifier):
            errors.append(f"{field}.id must use safe CTX- format")
        elif identifier in ids:
            errors.append(f"{field}.id must be unique")
        else:
            ids.add(identifier)
            records[identifier] = card
        context = card.get("context")
        if context not in CONTEXTS:
            errors.append(f"{field}.context is invalid")
        reason = card.get("reason")
        if reason is not None and not _text(reason, 2048):
            errors.append(f"{field}.reason must be bounded non-empty text")
        scope = card.get("scope")
        if not isinstance(scope, dict):
            errors.append(f"{field}.scope must be an object")
            scope = {}
        else:
            errors.extend(f"{field}.scope unknown field: {key}" for key in sorted(set(scope) - set(SCOPE_FIELDS)))
            for key, value in scope.items():
                if key == "scopeDigest":
                    if not isinstance(value, str) or not _SHA256.fullmatch(value):
                        errors.append(f"{field}.scope.scopeDigest must be a lowercase SHA-256 digest")
                elif not _text(value, 2048):
                    errors.append(f"{field}.scope.{key} must be bounded non-empty text")
        validity = card.get("validity")
        if validity not in VALIDITIES:
            errors.append(f"{field}.validity is invalid")
        scope_key = tuple(str(scope.get(key, "")) for key in SCOPE_FIELDS)
        if validity == "active" and context in CONTEXTS and (context, scope_key) in active_scopes:
            errors.append(f"{field} conflicts with another active card in the same scope")
        elif validity == "active" and context in CONTEXTS:
            active_scopes.add((context, scope_key))
        source = card.get("source")
        if not isinstance(source, dict):
            errors.append(f"{field}.source must be an object")
        else:
            errors.extend(f"{field}.source unknown field: {key}" for key in sorted(set(source) - {"locator", "anchor", "digest"}))
            locator, anchor, digest = source.get("locator"), source.get("anchor"), source.get("digest")
            if not _safe_locator(locator):
                errors.append(f"{field}.source.locator must be a safe relative locator")
            if not _text(anchor, 512) or any(ord(char) < 32 for char in anchor):
                errors.append(f"{field}.source.anchor must be bounded non-empty text")
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                errors.append(f"{field}.source.digest must be a lowercase SHA-256 digest")
            if isinstance(locator, str) and isinstance(anchor, str):
                if (locator, anchor) in source_anchors:
                    errors.append(f"{field} duplicates source locator and anchor")
                source_anchors.add((locator, anchor))
                if checked_workspace is not None and _safe_locator(locator):
                    try:
                        source_path = _safe_source_path(checked_workspace, locator)
                        payload = source_path.read_bytes()
                        if len(payload) > MAX_SOURCE_BYTES:
                            errors.append(f"{field}.source exceeds {MAX_SOURCE_BYTES} bytes")
                        elif isinstance(digest, str) and _SHA256.fullmatch(digest) and hashlib.sha256(payload).hexdigest() != digest:
                            errors.append(f"{field}.source.digest does not match source")
                    except (OSError, ValueError) as exc:
                        errors.append(f"{field}.source.locator {exc}")
        verification = card.get("requiredVerification")
        if not isinstance(verification, list):
            errors.append(f"{field}.requiredVerification must be a list")
        else:
            if len(verification) > 16:
                errors.append(f"{field}.requiredVerification may contain at most 16 entries")
            for verification_index, item in enumerate(verification):
                if not _text(item, 2048):
                    errors.append(f"{field}.requiredVerification[{verification_index}] must be bounded non-empty text")
        target = card.get("supersedes")
        if target is not None:
            if not isinstance(target, str) or not _SAFE_ID.fullmatch(target):
                errors.append(f"{field}.supersedes must reference a safe CTX- id")
            elif isinstance(identifier, str) and identifier in records:
                edges[identifier] = target
    for identifier, target in edges.items():
        if target not in records:
            errors.append(f"cards[{identifier}] supersedes missing card: {target}")
        elif records[identifier].get("scope") != records[target].get("scope"):
            errors.append(f"cards[{identifier}] supersedes a card from a different scope")
    for start in edges:
        seen: set[str] = set()
        node = start
        while node in edges:
            if node in seen:
                errors.append("cards supersedes graph contains a cycle")
                return errors
            seen.add(node)
            node = edges[node]
    return errors


def _scope_matches(card_scope: dict[str, Any], requested: dict[str, str] | None) -> bool:
    requested = requested or {}
    return all(not value or requested.get(key) == value for key, value in card_scope.items())


def _anchor_excerpt(text: str, anchor: str) -> str | None:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == anchor.strip()), None)
    if start is None:
        return None
    heading = re.match(r"^(#{1,6})\s", lines[start].lstrip())
    end = min(len(lines), start + 16)
    if heading:
        level = len(heading.group(1))
        for index in range(start + 1, len(lines)):
            other = re.match(r"^(#{1,6})\s", lines[index].lstrip())
            if other and len(other.group(1)) <= level:
                end = index
                break
    return "\n".join(lines[start:end]).strip()


def _bounded_result(result: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    cards = result.get("cards")
    if not isinstance(cards, list):
        raise ValueError("context result has no bounded card list")
    while True:
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
        result["bytes"] = len(encoded)
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
        if len(encoded) <= max_bytes:
            result["bytes"] = len(encoded)
            final = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
            if len(final) == result["bytes"]:
                return result
            continue
        if not cards:
            raise ValueError("context result metadata exceeds 16 KiB")
        cards.pop()
        result["truncated"] = True


def recall_context(
    manifest: dict[str, Any], workspace: Path, context: str,
    scope: dict[str, str] | None = None, max_bytes: int = MAX_OUTPUT_BYTES,
) -> dict[str, Any]:
    if context not in CONTEXTS:
        raise ValueError("unsupported context")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 0 < max_bytes <= MAX_OUTPUT_BYTES:
        raise ValueError("max_bytes must be between 1 and 16384")
    # Keep structural corruption distinct from source freshness. Runtime source
    # checks below classify digest drift as stale and access failures as corrupt.
    errors = validate_context_manifest(manifest, None)
    if errors:
        return _bounded_result(
            {"status": "corrupt", "context": context, "cards": [], "errors": errors, "bytes": 0, "maxBytes": max_bytes},
            max_bytes,
        )
    cards: list[dict[str, Any]] = []
    status = "pass"
    for card in manifest["cards"]:
        if card["context"] != context or not _scope_matches(card["scope"], scope):
            continue
        item = {"id": card["id"], "validity": card["validity"], "reason": card.get("reason"), "requiredVerification": card["requiredVerification"]}
        if card["validity"] != "active":
            item["status"] = "stale" if card["validity"] == "superseded" else card["validity"]
            if status != "corrupt":
                status = "stale"
            cards.append(item)
            continue
        try:
            path = _safe_source_path(workspace, card["source"]["locator"])
            payload = path.read_bytes()
        except (OSError, ValueError) as exc:
            item["status"] = "corrupt"
            item["error"] = str(exc)
            status = "corrupt"
            cards.append(item)
            continue
        if len(payload) > MAX_SOURCE_BYTES:
            item["status"] = "corrupt"
            item["error"] = "source exceeds 65536 bytes"
            status = "corrupt"
        elif hashlib.sha256(payload).hexdigest() != card["source"]["digest"]:
            item["status"] = "stale"
            item["error"] = "source digest mismatch"
            status = "stale" if status != "corrupt" else status
        else:
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                item["status"] = "corrupt"
                item["error"] = "source is not UTF-8"
                status = "corrupt"
            else:
                excerpt = _anchor_excerpt(text, card["source"]["anchor"])
                if excerpt is None:
                    item["status"] = "stale"
                    item["error"] = "source anchor is absent"
                    status = "stale" if status != "corrupt" else status
                else:
                    item["status"] = "covered"
                    item["source"] = {"locator": card["source"]["locator"], "anchor": card["source"]["anchor"], "digest": card["source"]["digest"]}
                    item["excerpt"] = excerpt
        cards.append(item)
    result = {"status": status if cards else "unknown", "context": context, "cards": cards, "errors": [], "bytes": 0, "maxBytes": max_bytes}
    return _bounded_result(result, max_bytes)


def preflight(manifest: dict[str, Any], workspace: Path, context: str, scope: dict[str, str] | None = None) -> dict[str, Any]:
    recalled = recall_context(manifest, workspace, context, scope)
    covered = [card for card in recalled["cards"] if card.get("status") == "covered"]
    required = sorted({item for card in covered for item in card.get("requiredVerification", [])})
    if recalled["status"] in {"corrupt", "stale"}:
        coverage, decision = "unknown", "blocked"
    elif not covered:
        coverage, decision = "not-covered", "unknown"
    else:
        coverage, decision = "covered", "advisory-only"
    return {"status": recalled["status"], "context": context, "coverage": coverage, "decision": decision, "requiredVerification": required, "cards": recalled["cards"], "readOnly": True}


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("validate", "recall", "preflight"))
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--context", choices=sorted(CONTEXTS), default="resume")
    args = parser.parse_args()
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.mode == "validate":
        errors = validate_context_manifest(payload, args.workspace)
        result = {"valid": not errors, "errors": errors}
    elif args.mode == "recall":
        result = recall_context(payload, args.workspace, args.context)
    else:
        result = preflight(payload, args.workspace, args.context)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("valid", result.get("status") not in {"corrupt", "stale"}) else 1


if __name__ == "__main__":
    raise SystemExit(_main())
