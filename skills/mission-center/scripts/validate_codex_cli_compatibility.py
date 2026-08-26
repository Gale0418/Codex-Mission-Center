#!/usr/bin/env python3
"""Validate the bounded, read-only MC-044 compatibility matrix."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any


ROOT_REQUIRED = {
    "schemaVersion",
    "spike",
    "title",
    "observedAt",
    "scope",
    "officialSources",
    "localProbe",
    "probeRecords",
    "matrix",
    "decision",
}
MATRIX_REQUIRED = {"surface", "localEvidence", "status", "probeRecordIds"}
MATRIX_COMMAND_FIELDS = {"officialCommand", "localCommand"}
MATRIX_STATUSES = {
    "observed-install",
    "blocked-local",
    "officially-documented-local-unverified",
    "officially-documented-not-executed",
    "repo-source-and-test-verified",
}
PROBE_REQUIRED = {"id", "command", "platform", "recordedAt", "exitCode", "resultCategory", "evidenceLocator"}
PROBE_PLATFORMS = {"Windows", "WSL"}
PROBE_RESULTS = {"pass", "blocked", "not-executed", "local-unverified"}
SOURCE_REQUIRED = {"topic", "url", "evidence"}
DECISION_REQUIRED = {"retainCompatibilityLayer", "reason", "nextVerification"}
MAX_COMMAND_LENGTH = 256
MAX_LOCATOR_LENGTH = 512


def _is_non_empty_string(value: Any, limit: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and "\n" not in value and "\r" not in value


def _is_safe_locator(value: Any) -> bool:
    if not _is_non_empty_string(value, MAX_LOCATOR_LENGTH):
        return False
    path = value.split("#", 1)[0].replace("\\", "/")
    return not (
        path.startswith(("/", "//"))
        or PureWindowsPath(path).is_absolute()
        or not path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    )


def _is_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_matrix(matrix: Any) -> list[str]:
    """Return strict shape errors without executing any command or writing files."""
    if not isinstance(matrix, dict):
        return ["matrix must be an object"]
    errors: list[str] = []
    missing = sorted(ROOT_REQUIRED - set(matrix))
    if missing:
        errors.append(f"matrix missing required fields: {', '.join(missing)}")
    if set(matrix) - ROOT_REQUIRED:
        errors.append("matrix contains unknown fields")
    if matrix.get("schemaVersion") != "1.0":
        errors.append("schemaVersion must be 1.0")
    if matrix.get("spike") != "MC-044":
        errors.append("spike must be MC-044")
    if not _is_non_empty_string(matrix.get("title"), 256):
        errors.append("title must be a bounded string")
    if not isinstance(matrix.get("observedAt"), str):
        errors.append("observedAt must be a date string")
    else:
        try:
            datetime.strptime(matrix["observedAt"], "%Y-%m-%d")
        except ValueError:
            errors.append("observedAt must be a date string")
    if not _is_non_empty_string(matrix.get("scope"), 512):
        errors.append("scope must be a bounded string")
    sources = matrix.get("officialSources")
    if not isinstance(sources, list) or not sources:
        errors.append("officialSources must be a non-empty list")
        sources = []
    for index, source in enumerate(sources):
        prefix = f"officialSources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if set(source) != SOURCE_REQUIRED:
            errors.append(f"{prefix} must contain exactly topic, url, and evidence")
        for field in SOURCE_REQUIRED:
            if not _is_non_empty_string(source.get(field), 1024):
                errors.append(f"{prefix}.{field} must be a bounded string")
    if not isinstance(matrix.get("localProbe"), dict):
        errors.append("localProbe must be an object")
    decision = matrix.get("decision")
    if not isinstance(decision, dict):
        errors.append("decision must be an object")
    else:
        if set(decision) != DECISION_REQUIRED:
            errors.append("decision must contain exactly retainCompatibilityLayer, reason, and nextVerification")
        if not isinstance(decision.get("retainCompatibilityLayer"), bool):
            errors.append("decision.retainCompatibilityLayer must be boolean")
        for field in DECISION_REQUIRED - {"retainCompatibilityLayer"}:
            if not _is_non_empty_string(decision.get(field), 1024):
                errors.append(f"decision.{field} must be a bounded string")
    records = matrix.get("probeRecords")
    if not isinstance(records, list) or not records:
        errors.append("probeRecords must be a non-empty list")
        records = []
    record_ids: set[str] = set()
    for index, record in enumerate(records):
        prefix = f"probeRecords[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = sorted(PROBE_REQUIRED - set(record))
        if missing:
            errors.append(f"{prefix} missing required fields: {', '.join(missing)}")
        if set(record) - PROBE_REQUIRED:
            errors.append(f"{prefix} contains unknown fields")
        record_id = record.get("id")
        if not _is_non_empty_string(record_id, 128):
            errors.append(f"{prefix}.id must be a bounded string")
        elif record_id in record_ids:
            errors.append(f"duplicate probe record id: {record_id}")
        else:
            record_ids.add(record_id)
        if not _is_non_empty_string(record.get("command"), MAX_COMMAND_LENGTH):
            errors.append(f"{prefix}.command must be a bounded single-line string")
        if record.get("platform") not in PROBE_PLATFORMS:
            errors.append(f"{prefix}.platform has an invalid value")
        if not _is_timestamp(record.get("recordedAt")):
            errors.append(f"{prefix}.recordedAt must be timezone-aware ISO-8601")
        exit_code = record.get("exitCode")
        if exit_code is not None and (isinstance(exit_code, bool) or not isinstance(exit_code, int)):
            errors.append(f"{prefix}.exitCode must be an integer or null")
        if record.get("resultCategory") not in PROBE_RESULTS:
            errors.append(f"{prefix}.resultCategory has an invalid value")
        if not _is_safe_locator(record.get("evidenceLocator")):
            errors.append(f"{prefix}.evidenceLocator must be a safe relative locator")

    entries = matrix.get("matrix")
    if not isinstance(entries, list) or not entries:
        errors.append("matrix must be a non-empty list")
        entries = []
    for index, entry in enumerate(entries):
        prefix = f"matrix[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = sorted(MATRIX_REQUIRED - set(entry))
        if missing:
            errors.append(f"{prefix} missing required fields: {', '.join(missing)}")
        if set(entry) - MATRIX_REQUIRED - MATRIX_COMMAND_FIELDS:
            errors.append(f"{prefix} contains unknown fields")
        if not _is_non_empty_string(entry.get("surface"), 128):
            errors.append(f"{prefix}.surface must be a bounded string")
        command_fields = MATRIX_COMMAND_FIELDS & set(entry)
        if len(command_fields) != 1:
            errors.append(f"{prefix} must contain exactly one command field")
        elif not _is_non_empty_string(entry[next(iter(command_fields))], MAX_COMMAND_LENGTH):
            errors.append(f"{prefix} command field must be a bounded string")
        if not _is_non_empty_string(entry.get("localEvidence"), MAX_COMMAND_LENGTH):
            errors.append(f"{prefix}.localEvidence must be a bounded string")
        if entry.get("status") not in MATRIX_STATUSES:
            errors.append(f"{prefix}.status has an invalid value")
        references = entry.get("probeRecordIds")
        if not isinstance(references, list) or not references or not all(
            _is_non_empty_string(item, 128) for item in references
        ):
            errors.append(f"{prefix}.probeRecordIds must be a non-empty string list")
        else:
            for record_id in references:
                if record_id not in record_ids:
                    errors.append(f"{prefix} references unknown probe record: {record_id}")
    return errors


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", nargs="?", default="skills/mission-center/references/codex-cli-plugin-compatibility-matrix.json")
    args = parser.parse_args(argv)
    errors = validate_matrix(json.loads(Path(args.matrix).read_text(encoding="utf-8")))
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("Codex CLI compatibility matrix: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
