#!/usr/bin/env python3
"""Validate a bounded Research Portfolio and route explicit saturation signals."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

try:
    from mission_maintenance import parse_tasks
    from security_scanner import scan_forbidden_content
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mission_maintenance import parse_tasks
    from security_scanner import scan_forbidden_content


SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "research-portfolio"
HYPOTHESIS_KINDS = {"exploit", "adjacent_explore", "moonshot"}
SATURATION_ACTIONS = {"continue", "broaden_search", "human_decision", "stop"}
HYPOTHESIS_STATUSES = {"unverified", "research_needed", "active", "promoted", "rejected", "stopped"}
SOURCE_TRUST = {"trusted_local", "untrusted_external_evidence", "unverified"}
SOURCE_LICENSE = {"known", "compatible", "incompatible", "unknown", "not_applicable"}
SOURCE_STATUSES = {"discovered", "verified", "rejected", "advisory_only", "promoted"}
LOCAL_SOURCE_TYPES = {"local", "repo", "workspace", "fixture"}
SIGNAL_FIELDS = (
    "repeatedRootCause",
    "renamedHypothesis",
    "metricStalled",
    "budgetBurning",
    "sharedUnverifiedPremise",
    "lowMarginalGainCount",
)
HYPOTHESIS_FIELDS = (
    "id", "kind", "question", "mechanism", "currentEvidenceRefs",
    "smallestDiscriminatingTest", "expectedObservation", "falsificationConditions",
    "dependencies", "risks", "budget", "successNextAction", "failureKnowledge",
    "revalidateWhen", "status",
)
SOURCE_FIELDS = ("locator", "sourceType", "provenance", "trustStatus", "licenseStatus", "retrievedAt", "status")
BASE_FIELDS = ("schemaVersion", "artifactType", "taskId", "initialHypothesisAllocation", "allocationKind", "hypotheses", "sourceLedger", "saturationSignals", "selectedAction")
ALLOWED_FIELDS = set(BASE_FIELDS) | {"hardConstraintFailure", "budgetExhausted", "promotionStatus"}
ALLOCATION_FIELDS = ("exploit", "adjacent_explore", "moonshot")
CANONICAL_TASK_FIELDS = ("ID", "Title", "Priority", "Status", "Depends on", "Next action", "Verification")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _bounded_text(value: Any, field: str, errors: list[str], limit: int = 2048) -> None:
    if not _text(value):
        errors.append(f"{field} must be a non-empty string")
    elif len(value) > limit:
        errors.append(f"{field} exceeds {limit} characters")


def _list(value: Any, field: str, errors: list[str], *, non_empty: bool = True) -> None:
    if not isinstance(value, list) or (non_empty and not value):
        errors.append(f"{field} must be a {'non-empty ' if non_empty else ''}list")
        return
    if len(value) > 32:
        errors.append(f"{field} may contain at most 32 entries")
    for index, item in enumerate(value):
        if isinstance(item, str) and len(item) > 2048:
            errors.append(f"{field}[{index}] exceeds 2048 characters")


def _check_allowed_fields(value: dict[str, Any], allowed: tuple[str, ...], field: str, errors: list[str]) -> None:
    """Mirror nested schema objects with additionalProperties=false."""
    allowed_set = set(allowed)
    for key in value:
        if key not in allowed_set:
            errors.append(f"{field} unknown field: {key}")


def _nonnegative(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


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


def default_initial_allocation() -> dict[str, int]:
    """Return a starting hypothesis allocation, never an optimality claim."""
    return {"exploit": 60, "adjacent_explore": 30, "moonshot": 10}


def saturation_signal_count(signals: dict[str, Any]) -> int:
    count = sum(1 for field in SIGNAL_FIELDS[:-1] if signals.get(field) is True)
    marginal = signals.get("lowMarginalGainCount", 0)
    return count + (1 if isinstance(marginal, int) and not isinstance(marginal, bool) and marginal > 0 else 0)


def route_saturation(
    signals: dict[str, Any],
    *,
    hard_constraint_failure: bool = False,
    budget_exhausted: bool = False,
) -> dict[str, Any]:
    """Route only explicit local saturation input; never runs research or promotes a source."""
    if not isinstance(signals, dict):
        raise ValueError("saturation signals must be an object")
    if not isinstance(hard_constraint_failure, bool) or not isinstance(budget_exhausted, bool):
        raise ValueError("hard_constraint_failure and budget_exhausted must be boolean")
    unknown = [field for field in signals if field not in SIGNAL_FIELDS]
    if unknown:
        raise ValueError(f"saturation signals unknown field: {unknown[0]}")
    errors: list[str] = []
    for field in SIGNAL_FIELDS[:-1]:
        if not isinstance(signals.get(field), bool):
            errors.append(f"{field} must be boolean")
    marginal = signals.get("lowMarginalGainCount", 0)
    if not isinstance(marginal, int) or isinstance(marginal, bool) or marginal < 0:
        errors.append("lowMarginalGainCount must be a non-negative integer")
    if errors:
        raise ValueError("; ".join(errors))
    count = saturation_signal_count(signals)
    if hard_constraint_failure or budget_exhausted:
        action = "stop"
        reason = "hard constraint failure or budget exhausted"
    elif count >= 2:
        action = "broaden_search"
        reason = "at least two explicit saturation signals"
    else:
        action = "continue"
        reason = "fewer than two explicit saturation signals"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "route": "saturation",
        "selectedAction": action,
        "signalCount": count,
        "reason": reason,
        "hardConstraintFailure": bool(hard_constraint_failure),
        "budgetExhausted": bool(budget_exhausted),
    }


def _validate_budget(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return
    _check_allowed_fields(value, ("token", "tool", "time"), field, errors)
    for name in ("token", "tool", "time"):
        if not _nonnegative(value.get(name)):
            errors.append(f"{field}.{name} must be a non-negative number (zero is explicit)" )


def _local_locator_error(
    locator: str,
    workspace: Path | None,
    *,
    require_existing_file: bool = False,
) -> str | None:
    """Ensure local provenance uses a relative locator contained by workspace."""
    # Reject URL schemes (including local:// and https:// fixture spoofing) and
    # absolute paths before resolving the candidate.
    if urlsplit(locator).scheme or locator.startswith(("//", "\\\\")):
        return "must be a relative path inside workspace; URL locators are invalid"
    candidate = Path(locator)
    if candidate.is_absolute() or PureWindowsPath(locator).is_absolute():
        return "must be a relative path inside workspace; absolute locators are invalid"
    if workspace is None:
        if ".." in candidate.parts or ".." in PureWindowsPath(locator).parts:
            return "cannot verify parent traversal without workspace"
        return None
    root = Path(workspace).expanduser().resolve()
    if root.name.casefold() == "missioncenter":
        root = root.parent
    try:
        resolved = (root / candidate).resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return "must resolve inside workspace; parent traversal escapes are invalid"
    if require_existing_file and not resolved.is_file():
        return "must reference an existing file before it can be trusted or promoted"
    return None


def _validate_source_ledger(
    entries: Any, errors: list[str], workspace: Path | None
) -> tuple[set[str], set[str], set[str]]:
    if not isinstance(entries, list):
        errors.append("sourceLedger must be a list")
        return set(), set(), set()
    if len(entries) > 32:
        errors.append("sourceLedger may contain at most 32 entries")
    locators: set[str] = set()
    untrusted: set[str] = set()
    unverifiable_local: set[str] = set()
    for index, source in enumerate(entries):
        if not isinstance(source, dict):
            errors.append(f"sourceLedger[{index}] must be an object")
            continue
        _check_allowed_fields(source, SOURCE_FIELDS, f"sourceLedger[{index}]", errors)
        for field in SOURCE_FIELDS:
            if field not in source:
                errors.append(f"sourceLedger[{index}].{field} is required")
        for field in ("locator", "sourceType", "provenance", "trustStatus", "licenseStatus", "retrievedAt", "status"):
            _bounded_text(source.get(field), f"sourceLedger[{index}].{field}", errors, 1024)
        locator = source.get("locator")
        if _text(locator):
            if locator in locators:
                errors.append(f"sourceLedger has duplicate locator: {locator}")
            locators.add(locator)
        trust = source.get("trustStatus")
        if trust not in SOURCE_TRUST:
            errors.append(f"sourceLedger[{index}].trustStatus is invalid")
        if source.get("licenseStatus") not in SOURCE_LICENSE:
            errors.append(f"sourceLedger[{index}].licenseStatus is invalid")
        status = source.get("status")
        if status not in SOURCE_STATUSES:
            errors.append(f"sourceLedger[{index}].status is invalid")
        source_type = str(source.get("sourceType", "")).casefold()
        if source_type in LOCAL_SOURCE_TYPES and _text(locator):
            locator_error = _local_locator_error(
                locator,
                workspace,
                require_existing_file=trust == "trusted_local" or status == "promoted",
            )
            if locator_error:
                errors.append(f"sourceLedger[{index}].locator {locator_error}")
            if workspace is None:
                unverifiable_local.add(locator)
                if trust == "trusted_local":
                    errors.append(f"sourceLedger[{index}] trusted_local requires workspace verification")
                if status == "promoted":
                    errors.append(f"sourceLedger[{index}] local provenance cannot be promoted without workspace verification")
        if source_type not in LOCAL_SOURCE_TYPES and trust != "untrusted_external_evidence":
            errors.append(f"sourceLedger[{index}] external content must be untrusted_external_evidence")
        if trust == "untrusted_external_evidence":
            if _text(locator):
                untrusted.add(locator)
            if status == "promoted":
                errors.append(f"sourceLedger[{index}] untrusted external evidence cannot be promoted")
    return locators, untrusted, unverifiable_local


def validate_research_portfolio(record: Any, workspace: Path | None = None) -> list[str]:
    """Return bounded contract errors; validation never performs research or promotion."""
    if not isinstance(record, dict):
        return ["portfolio must be an object"]
    errors: list[str] = scan_forbidden_content(record)
    errors.extend(f"unknown field: {field}" for field in sorted(set(record) - ALLOWED_FIELDS))
    if record.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("schemaVersion must be 1.0")
    if record.get("artifactType") != ARTIFACT_TYPE:
        errors.append("artifactType must be research-portfolio")
    for field in BASE_FIELDS:
        if field not in record:
            errors.append(f"{field} is required")
    _bounded_text(record.get("taskId"), "taskId", errors, 128)
    if workspace is not None and _text(record.get("taskId")) and _canonical_task(workspace, record["taskId"]) is None:
        errors.append("taskId is not present in canonical tasks.md")

    allocation = record.get("initialHypothesisAllocation")
    if isinstance(allocation, dict):
        _check_allowed_fields(allocation, ALLOCATION_FIELDS, "initialHypothesisAllocation", errors)
    if not isinstance(allocation, dict) or set(allocation) != HYPOTHESIS_KINDS or any(not _nonnegative(value) for value in allocation.values()) or sum(allocation.values()) != 100:
        errors.append("initialHypothesisAllocation must contain exploit, adjacent_explore, moonshot totaling 100")
    if record.get("allocationKind") != "initial_hypothesis_allocation":
        errors.append("allocationKind must be initial_hypothesis_allocation, not an optimality claim")

    hypotheses = record.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        errors.append("hypotheses must be a non-empty list")
        hypotheses = []
    if len(hypotheses) > 12:
        errors.append("hypotheses may contain at most 12 entries")
    locators, untrusted, unverifiable_local = _validate_source_ledger(record.get("sourceLedger"), errors, workspace)
    seen_ids: set[str] = set()
    seen_kinds: set[str] = set()
    for index, hypothesis in enumerate(hypotheses):
        if not isinstance(hypothesis, dict):
            errors.append(f"hypotheses[{index}] must be an object")
            continue
        _check_allowed_fields(hypothesis, HYPOTHESIS_FIELDS, f"hypotheses[{index}]", errors)
        for field in HYPOTHESIS_FIELDS:
            if field not in hypothesis:
                errors.append(f"hypotheses[{index}].{field} is required")
        identifier = hypothesis.get("id")
        if not _text(identifier) or identifier in seen_ids:
            errors.append(f"hypotheses[{index}].id must be unique non-empty text")
        else:
            seen_ids.add(identifier)
        if hypothesis.get("kind") not in HYPOTHESIS_KINDS:
            errors.append(f"hypotheses[{index}].kind is invalid")
        else:
            seen_kinds.add(hypothesis["kind"])
        for field in ("question", "mechanism", "smallestDiscriminatingTest", "expectedObservation", "successNextAction", "failureKnowledge", "revalidateWhen"):
            _bounded_text(hypothesis.get(field), f"hypotheses[{index}].{field}", errors)
        _list(hypothesis.get("falsificationConditions"), f"hypotheses[{index}].falsificationConditions", errors)
        _list(hypothesis.get("dependencies"), f"hypotheses[{index}].dependencies", errors, non_empty=False)
        _list(hypothesis.get("risks"), f"hypotheses[{index}].risks", errors, non_empty=False)
        _validate_budget(hypothesis.get("budget"), f"hypotheses[{index}].budget", errors)
        refs = hypothesis.get("currentEvidenceRefs")
        if not isinstance(refs, list):
            errors.append(f"hypotheses[{index}].currentEvidenceRefs must be a list")
            refs = []
        for ref in refs:
            if not _text(ref):
                errors.append(f"hypotheses[{index}].currentEvidenceRefs contains empty locator")
            elif ref not in locators:
                errors.append(f"hypotheses[{index}] references unknown source locator: {ref}")
        status = hypothesis.get("status")
        if status not in HYPOTHESIS_STATUSES:
            errors.append(f"hypotheses[{index}].status is invalid")
        if not refs and status not in {"unverified", "research_needed"}:
            errors.append(f"hypotheses[{index}] empty evidenceRefs require unverified or research_needed status")
        if status == "promoted" and any(ref in untrusted for ref in refs):
            errors.append(f"hypotheses[{index}] cannot promote untrusted external evidence")
        if status == "promoted" and any(ref in unverifiable_local for ref in refs):
            errors.append(f"hypotheses[{index}] cannot promote unverifiable local evidence without workspace verification")
    for kind in sorted(HYPOTHESIS_KINDS - seen_kinds):
        errors.append(f"hypotheses must include at least one {kind} hypothesis")

    signals = record.get("saturationSignals")
    if isinstance(signals, dict):
        _check_allowed_fields(signals, SIGNAL_FIELDS, "saturationSignals", errors)
    try:
        routed = route_saturation(
            signals,
            hard_constraint_failure=record.get("hardConstraintFailure", False),
            budget_exhausted=record.get("budgetExhausted", False),
        )
        selected_action = record.get("selectedAction")
        if selected_action not in SATURATION_ACTIONS:
            errors.append("selectedAction is invalid")
        elif routed["selectedAction"] == "stop" and selected_action not in {"stop", "human_decision"}:
            errors.append("hard constraint failure or budget exhausted requires stop or human_decision")
        elif routed["selectedAction"] != "stop" and selected_action != routed["selectedAction"]:
            errors.append(f"selectedAction must match deterministic route: {routed['selectedAction']}")
    except ValueError as exc:
        errors.append(str(exc))

    promotion = record.get("promotionStatus", "advisory_only")
    if promotion not in {"advisory_only", "not_promoted", "promoted"}:
        errors.append("promotionStatus is invalid")
    if promotion == "promoted" and untrusted:
        errors.append("portfolio with untrusted external evidence cannot be promoted")
    if promotion == "promoted" and unverifiable_local:
        errors.append("portfolio with unverifiable local evidence cannot be promoted without workspace verification")
    return errors


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("portfolio", type=Path)
    validate.add_argument("--workspace", type=Path)
    saturate = commands.add_parser("saturate")
    saturate.add_argument("signals", type=Path)
    saturate.add_argument("--hard-constraint-failure", action="store_true")
    saturate.add_argument("--budget-exhausted", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "validate":
        errors = validate_research_portfolio(json.loads(args.portfolio.read_text(encoding="utf-8")), args.workspace)
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 1
    result = route_saturation(
        json.loads(args.signals.read_text(encoding="utf-8")),
        hard_constraint_failure=args.hard_constraint_failure,
        budget_exhausted=args.budget_exhausted,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
