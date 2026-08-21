#!/usr/bin/env python3
"""Evaluate privacy-safe, structured Shift-Loss cases without model calls."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

try:
    from mission_maintenance import parse_tasks
    from security_scanner import scan_forbidden_content
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mission_maintenance import parse_tasks
    from security_scanner import scan_forbidden_content


SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "shift-loss-eval"
VARIANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CASE_FIELDS = (
    "caseId", "taskId", "variant", "shouldRecall", "shouldIgnore", "shouldSupersede",
    "actualRecall", "actualIgnore", "actualSupersede", "firstCorrectActionMs", "staleMemoryInjected",
    "wrongBranch", "tokensUsed", "verifiedProgress", "evidenceClaims", "evidenceBackedClaims",
    "falseDone", "recoveryDistance", "unverifiedDestructiveAction", "activeGuardrailWithoutSource",
    "multipleWritersSameBranch",
)
BASE_FIELDS = ("schemaVersion", "artifactType", "taskId", "variant", "cases")
ALLOWED_FIELDS = set(BASE_FIELDS)
METRIC_NAMES = ("HRA", "TFCA", "SMIR", "WBR", "TVP", "EvidenceCoverage", "FalseDone", "RecoveryDistance")
CANONICAL_TASK_FIELDS = ("ID", "Title", "Priority", "Status", "Depends on", "Next action", "Verification")


def _canonical_task(workspace: Path, task_id: str) -> dict[str, str] | None:
    root = Path(workspace).expanduser().resolve()
    root = root if root.name.casefold() == "missioncenter" else root / "MissionCenter"
    path = root / "tasks.md"
    if not path.is_file():
        return None
    for task in parse_tasks(path):
        if task.get("ID", "").strip().casefold() == task_id.strip().casefold():
            return {field: task.get(field, "") for field in CANONICAL_TASK_FIELDS}
    return None


def _text(value: Any, limit: int = 128) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def _nonnegative(value: Any, *, integer: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return False
    return not integer or isinstance(value, int)


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return None if denominator == 0 else numerator / denominator


_scan_forbidden = scan_forbidden_content


def validate_case(case: Any, workspace: Path | None = None) -> list[str]:
    if not isinstance(case, dict):
        return ["case must be an object"]
    errors = _scan_forbidden(case)
    errors.extend(f"unknown case field: {key}" for key in sorted(set(case) - set(CASE_FIELDS)))
    for field in CASE_FIELDS:
        if field not in case:
            errors.append(f"case.{field} is required")
    for field in ("caseId", "taskId", "variant"):
        if not _text(case.get(field)):
            errors.append(f"case.{field} must be bounded non-empty text")
    if _text(case.get("variant")) and not VARIANT_PATTERN.fullmatch(case["variant"]):
        errors.append("case.variant must be a versionable identifier")
    if _text(case.get("caseId")) and not CASE_ID_PATTERN.fullmatch(case["caseId"]):
        errors.append("case.caseId must be a bounded identifier")
    for field in (
        "shouldRecall", "shouldIgnore", "shouldSupersede", "actualRecall", "actualIgnore", "actualSupersede",
        "staleMemoryInjected", "wrongBranch", "verifiedProgress", "falseDone", "unverifiedDestructiveAction",
        "activeGuardrailWithoutSource", "multipleWritersSameBranch",
    ):
        if not isinstance(case.get(field), bool):
            errors.append(f"case.{field} must be boolean")
    if not any(case.get(field) is True for field in ("shouldRecall", "shouldIgnore", "shouldSupersede")):
        errors.append("case must have at least one true shouldRecall/shouldIgnore/shouldSupersede target")
    if case.get("firstCorrectActionMs") is not None and not _nonnegative(case.get("firstCorrectActionMs")):
        errors.append("case.firstCorrectActionMs must be non-negative or null")
    valid_counts: dict[str, bool] = {}
    for field in ("tokensUsed", "evidenceClaims", "evidenceBackedClaims"):
        valid_counts[field] = _nonnegative(case.get(field), integer=True)
        if not valid_counts[field]:
            errors.append(f"case.{field} must be a non-negative integer")
    if valid_counts["evidenceClaims"] and valid_counts["evidenceBackedClaims"] and case["evidenceBackedClaims"] > case["evidenceClaims"]:
        errors.append("case.evidenceBackedClaims cannot exceed evidenceClaims")
    if case.get("recoveryDistance") is not None and not _nonnegative(case.get("recoveryDistance")):
        errors.append("case.recoveryDistance must be a non-negative number")
    if workspace is not None and _text(case.get("taskId")) and _canonical_task(workspace, case["taskId"]) is None:
        errors.append("case.taskId is not present in canonical tasks.md")
    return errors


def validate_shift_loss(record: Any, workspace: Path | None = None) -> list[str]:
    if not isinstance(record, dict):
        return ["result must be an object"]
    errors = _scan_forbidden(record)
    errors.extend(f"unknown result field: {key}" for key in sorted(set(record) - ALLOWED_FIELDS))
    if record.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("schemaVersion must be 1.0")
    if record.get("artifactType") != ARTIFACT_TYPE:
        errors.append("artifactType must be shift-loss-eval")
    for field in BASE_FIELDS:
        if field not in record:
            errors.append(f"result.{field} is required")
    for field in ("taskId", "variant"):
        if not _text(record.get(field)):
            errors.append(f"result.{field} must be bounded non-empty text")
    if _text(record.get("variant")) and not VARIANT_PATTERN.fullmatch(record["variant"]):
        errors.append("result.variant must be a versionable identifier")
    cases = record.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("result.cases must be a non-empty list")
        cases = []
    if len(cases) > 128:
        errors.append("result.cases may contain at most 128 entries")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        errors.extend(f"cases[{index}]: {error}" for error in validate_case(case, None))
        if isinstance(case, dict):
            if case.get("taskId") != record.get("taskId"):
                errors.append(f"cases[{index}].taskId must match result.taskId")
            if case.get("variant") != record.get("variant"):
                errors.append(f"cases[{index}].variant must match result.variant")
            identifier = case.get("caseId")
            if isinstance(identifier, str):
                if identifier in seen:
                    errors.append(f"duplicate caseId: {identifier}")
                seen.add(identifier)
    if workspace is not None and _text(record.get("taskId")) and _canonical_task(workspace, record["taskId"]) is None:
        errors.append("result.taskId is not present in canonical tasks.md")
    return errors


def aggregate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate explicit cases; null means the metric denominator was zero."""
    total = len(cases)
    target_total = sum(
        int(case["shouldRecall"]) + int(case["shouldIgnore"]) + int(case["shouldSupersede"])
        for case in cases
    )
    correct_target_actions = sum(
        int(case["shouldRecall"] and case["actualRecall"])
        + int(case["shouldIgnore"] and case["actualIgnore"])
        + int(case["shouldSupersede"] and case["actualSupersede"])
        for case in cases
    )
    first_action_values = [case["firstCorrectActionMs"] for case in cases if case["firstCorrectActionMs"] is not None]
    verified_progress_count = sum(case["verifiedProgress"] for case in cases)
    hra = _ratio(correct_target_actions, target_total)
    tfca = _ratio(sum(first_action_values), len(first_action_values))
    smir = _ratio(sum(case["staleMemoryInjected"] for case in cases), total)
    recovery_values = [case["recoveryDistance"] for case in cases if case["recoveryDistance"] is not None]
    metrics = {
        "HRA": hra,
        "TFCA": tfca,
        "SMIR": smir,
        "WBR": _ratio(sum(case["wrongBranch"] for case in cases), total),
        "TVP": _ratio(sum(case["tokensUsed"] for case in cases), verified_progress_count),
        "EvidenceCoverage": _ratio(sum(case["evidenceBackedClaims"] for case in cases), sum(case["evidenceClaims"] for case in cases)),
        "FalseDone": sum(case["falseDone"] for case in cases),
        "RecoveryDistance": _ratio(sum(recovery_values), len(recovery_values)),
    }
    hard_counts = {
        "FalseDone": sum(case["falseDone"] for case in cases),
        "UnverifiedDestructiveAction": sum(case["unverifiedDestructiveAction"] for case in cases),
        "ActiveGuardrailWithoutSource": sum(case["activeGuardrailWithoutSource"] for case in cases),
        "MultipleWritersSameBranch": sum(case["multipleWritersSameBranch"] for case in cases),
    }
    hard_ok = all(value == 0 for value in hard_counts.values())
    return {
        "caseCount": total,
        "metrics": metrics,
        "denominators": {"HRA": target_total, "TFCA": len(first_action_values), "SMIR": total, "WBR": total, "TVP": verified_progress_count, "total": total, "EvidenceCoverage": sum(case["evidenceClaims"] for case in cases), "RecoveryDistance": len(recovery_values)},
        "hardConstraints": hard_counts,
        "hardConstraintsPassed": hard_ok,
        "overallStatus": "failed_hard_constraint" if not hard_ok else ("incomplete" if total == 0 else "passed"),
    }


def evaluate_shift_loss(record: dict[str, Any], workspace: Path | None = None) -> dict[str, Any]:
    errors = validate_shift_loss(record, workspace)
    if errors:
        return {"schemaVersion": SCHEMA_VERSION, "artifactType": ARTIFACT_TYPE, "valid": False, "errors": errors}
    result = aggregate_cases(record["cases"])
    result.update({"schemaVersion": SCHEMA_VERSION, "artifactType": ARTIFACT_TYPE, "taskId": record["taskId"], "variant": record["variant"], "valid": True})
    return result


def compare_paired(baseline: dict[str, Any], new: dict[str, Any], workspace: Path | None = None) -> dict[str, Any]:
    baseline_errors = validate_shift_loss(baseline, workspace)
    new_errors = validate_shift_loss(new, workspace)
    if baseline_errors or new_errors:
        return {"complete": False, "improvementClaim": False, "errors": {"baseline": baseline_errors, "new": new_errors}}
    if baseline["taskId"] != new["taskId"]:
        return {"complete": False, "improvementClaim": False, "errors": {"pair": ["baseline and new taskId must match"]}}
    baseline_by_id = {case["caseId"]: case for case in baseline["cases"]}
    new_by_id = {case["caseId"]: case for case in new["cases"]}
    shared = sorted(set(baseline_by_id) & set(new_by_id))
    missing_baseline = sorted(set(new_by_id) - set(baseline_by_id))
    missing_new = sorted(set(baseline_by_id) - set(new_by_id))
    result: dict[str, Any] = {"taskId": baseline["taskId"], "baselineVariant": baseline["variant"], "newVariant": new["variant"], "sharedCaseIds": shared, "missingBaseline": missing_baseline, "missingNew": missing_new, "complete": not missing_baseline and not missing_new, "improvementClaim": False}
    if result["complete"]:
        old = aggregate_cases([baseline_by_id[case_id] for case_id in shared])["metrics"]
        current = aggregate_cases([new_by_id[case_id] for case_id in shared])["metrics"]
        result["metricDeltas"] = {name: (None if old[name] is None or current[name] is None else current[name] - old[name]) for name in METRIC_NAMES}
        result["improvementClaim"] = False
    else:
        result["status"] = "incomplete_paired_cases"
    return result


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("result", type=Path)
    evaluate.add_argument("--workspace", type=Path)
    compare = commands.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("new", type=Path)
    compare.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    if args.command == "evaluate":
        result = evaluate_shift_loss(json.loads(args.result.read_text(encoding="utf-8")), args.workspace)
    else:
        result = compare_paired(json.loads(args.baseline.read_text(encoding="utf-8")), json.loads(args.new.read_text(encoding="utf-8")), args.workspace)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("valid", result.get("complete", False)) else 1


if __name__ == "__main__":
    raise SystemExit(_main())
