#!/usr/bin/env python3
"""Validate revision-bound, scope-aware MissionCenter evidence envelopes."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "evidence-envelope"
ENVELOPE_DIR = "output/mission-center-evidence"
MAX_ENVELOPE_BYTES = 64 * 1024
MAX_SCOPE_ITEMS = 64
MAX_ARTIFACT_LOCATORS = 64
MAX_TEXT_LENGTH = 1024
HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
ENVELOPE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TASK_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")
CHECK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
RESULTS = {"pass", "fail", "unknown"}
STATUSES = {"current", "superseded"}
REQUIRED_FIELDS = {
    "schemaVersion",
    "artifactType",
    "envelopeId",
    "taskId",
    "checkId",
    "scope",
    "scopeDigest",
    "result",
    "status",
    "artifactLocators",
    "recordedAt",
}
OPTIONAL_FIELDS = {"sourceRevision", "supersedes"}
ALLOWED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS


def workspace_root(workspace: Path) -> Path:
    root = Path(workspace).expanduser().resolve()
    return root.parent if root.name.casefold() == "missioncenter" else root


def normalize_locator(locator: Any) -> str | None:
    if not isinstance(locator, str) or not locator.strip():
        return None
    value = locator.strip().replace("\\", "/")
    try:
        scheme = urlsplit(value).scheme
    except ValueError:
        return None
    if scheme or value.startswith(("/", "//")) or PureWindowsPath(value).is_absolute():
        return None
    path = Path(value)
    if not value or "." == value or ".." in path.parts or ".." in PureWindowsPath(value).parts:
        return None
    return value


def _text(value: Any, field: str, errors: list[str], *, pattern: re.Pattern[str] | None = None) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a non-empty string")
        return
    if len(value) > MAX_TEXT_LENGTH:
        errors.append(f"{field} exceeds {MAX_TEXT_LENGTH} characters")
    if pattern is not None and not pattern.fullmatch(value):
        errors.append(f"{field} has an invalid format")


def scope_digest(workspace: Path, scope: list[str]) -> str:
    """Hash only explicitly listed, workspace-relative files in sorted order."""
    root = workspace_root(workspace)
    digest = hashlib.sha256()
    digest.update(b"mission-center-evidence-scope-v1\0")
    for locator in sorted(scope):
        normalized = normalize_locator(locator)
        if normalized is None:
            raise ValueError(f"invalid scope locator: {locator}")
        path = (root / normalized).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"scope locator escapes workspace: {locator}") from exc
        data = path.read_bytes()
        encoded = normalized.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def validate_envelope(
    envelope: Any,
    workspace: Path | None = None,
    *,
    verify_digest: bool = True,
) -> list[str]:
    """Return validation errors; never mutate or infer missing evidence."""
    if not isinstance(envelope, dict):
        return ["envelope must be an object"]
    errors: list[str] = []
    unknown = sorted(set(envelope) - ALLOWED_FIELDS)
    if unknown:
        errors.append(f"envelope contains unknown fields: {', '.join(unknown)}")
    if envelope.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion must be {SCHEMA_VERSION}")
    if envelope.get("artifactType") != ARTIFACT_TYPE:
        errors.append(f"artifactType must be {ARTIFACT_TYPE}")
    missing = sorted(REQUIRED_FIELDS - set(envelope))
    if missing:
        errors.append(f"envelope is missing required fields: {', '.join(missing)}")
    _text(envelope.get("envelopeId"), "envelopeId", errors, pattern=ENVELOPE_ID)
    _text(envelope.get("taskId"), "taskId", errors, pattern=TASK_ID)
    _text(envelope.get("checkId"), "checkId", errors, pattern=CHECK_ID)

    scope = envelope.get("scope")
    normalized_scope: list[str] = []
    if not isinstance(scope, list) or not scope:
        errors.append("scope must be a non-empty list")
    elif len(scope) > MAX_SCOPE_ITEMS:
        errors.append(f"scope may contain at most {MAX_SCOPE_ITEMS} files")
    else:
        for index, locator in enumerate(scope):
            normalized = normalize_locator(locator)
            if normalized is None:
                errors.append(f"scope[{index}] must be a safe relative file locator")
            elif normalized in normalized_scope:
                errors.append(f"scope contains duplicate locator: {normalized}")
            else:
                normalized_scope.append(normalized)

    scope_digest_value = envelope.get("scopeDigest")
    _text(scope_digest_value, "scopeDigest", errors)
    if isinstance(scope_digest_value, str) and not HEX_DIGEST.fullmatch(scope_digest_value):
        errors.append("scopeDigest must be a lowercase SHA-256 hex digest")

    result = envelope.get("result")
    if result not in RESULTS:
        errors.append("result must be pass, fail, or unknown")
    status = envelope.get("status")
    if status not in STATUSES:
        errors.append("status must be current or superseded")

    locators = envelope.get("artifactLocators")
    normalized_artifacts: list[str] = []
    if not isinstance(locators, list) or not locators:
        errors.append("artifactLocators must be a non-empty list")
    elif len(locators) > MAX_ARTIFACT_LOCATORS:
        errors.append(f"artifactLocators may contain at most {MAX_ARTIFACT_LOCATORS} files")
    else:
        for index, locator in enumerate(locators):
            normalized = normalize_locator(locator)
            if normalized is None:
                errors.append(f"artifactLocators[{index}] must be a safe relative file locator")
            elif normalized in normalized_artifacts:
                errors.append(f"artifactLocators contains duplicate locator: {normalized}")
            else:
                normalized_artifacts.append(normalized)

    recorded_at = envelope.get("recordedAt")
    _text(recorded_at, "recordedAt", errors)
    if isinstance(recorded_at, str):
        try:
            parsed = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                errors.append("recordedAt must include a timezone")
        except ValueError:
            errors.append("recordedAt must be an ISO-8601 date-time")

    if "sourceRevision" in envelope:
        _text(envelope.get("sourceRevision"), "sourceRevision", errors)
    if "supersedes" in envelope:
        _text(envelope.get("supersedes"), "supersedes", errors, pattern=ENVELOPE_ID)
    if status == "superseded" and "supersedes" in envelope:
        errors.append("superseded envelopes must not supersede another envelope")

    if workspace is not None and not errors:
        root = workspace_root(workspace)
        for field, locators_to_check in (("scope", normalized_scope), ("artifactLocators", normalized_artifacts)):
            for locator in locators_to_check:
                path = (root / locator).resolve()
                try:
                    path.relative_to(root)
                except ValueError:
                    errors.append(f"{field} locator escapes workspace: {locator}")
                    continue
                if not path.is_file():
                    errors.append(f"{field} locator does not reference an existing file: {locator}")
        if verify_digest and not errors:
            try:
                actual = scope_digest(root, normalized_scope)
            except (OSError, ValueError) as exc:
                errors.append(f"scope digest cannot be computed: {exc}")
            else:
                if actual != scope_digest_value:
                    errors.append("scopeDigest does not match the explicitly listed scope")
    return errors


def envelope_status(envelope: Any, workspace: Path | None = None) -> str:
    """Classify an envelope for reconciliation without changing its contents."""
    errors = validate_envelope(envelope, workspace)
    if not errors:
        return "pass"
    if any("scopeDigest does not match" in error for error in errors):
        return "stale"
    return "corrupt"
