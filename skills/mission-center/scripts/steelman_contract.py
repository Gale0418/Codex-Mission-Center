#!/usr/bin/env python3
"""Validate and route bounded Steelman Evolution artifacts without model calls."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

try:
    from mission_maintenance import parse_tasks
    from security_scanner import scan_forbidden_content
except ImportError:  # pragma: no cover - supports direct execution from another cwd
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mission_maintenance import parse_tasks
    from security_scanner import scan_forbidden_content


SCHEMA_VERSION = "1.0"
ARTIFACT_TYPE = "steelman-evolution"
ROUTES = {"skip", "steelman_lite", "steelman_full"}
RISKS = {"low", "medium", "high"}
PERSPECTIVE_KINDS = {"simulated", "real_subagent"}
REAL_STATUSES = {"planned", "not_dispatched", "completed"}
BASE_REQUIRED_FIELDS = (
    "taskId",
    "selectedRoute",
    "maxRounds",
    "perspectives",
    "realSubagentsCompleted",
)
STEELMAN_REQUIRED_FIELDS = (
    "trueGoal",
    "currentBest",
    "strongestOpposition",
    "thirdRoute",
    "flipVariables",
    "smallestDiscriminatingTest",
    "materialDissent",
    "reopenConditions",
    "qualityContract",
    "architectureContract",
    "evidenceRefs",
    "unknowns",
)
ALLOWED_FIELDS = set(BASE_REQUIRED_FIELDS) | set(STEELMAN_REQUIRED_FIELDS) | {
    "schemaVersion",
    "artifactType",
    "skipReason",
    "perspectives",
    "authorization",
    "budgets",
    "realSubagentsCompleted",
}
CANONICAL_TASK_FIELDS = ("ID", "Title", "Priority", "Status", "Depends on", "Next action", "Verification")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _bounded_text(value: Any, field: str, errors: list[str], limit: int = 4096) -> None:
    if not _text(value):
        errors.append(f"{field} must be a non-empty string")
    elif len(value) > limit:
        errors.append(f"{field} exceeds {limit} characters")


def _non_empty_collection(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{field} must be a non-empty list")


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _canonical_task(workspace: Path, task_id: str) -> dict[str, str] | None:
    root = Path(workspace).expanduser().resolve()
    root = root if root.name.casefold() == "missioncenter" else root / "MissionCenter"
    tasks_path = root / "tasks.md"
    if not tasks_path.is_file():
        return None
    for task in parse_tasks(tasks_path):
        if task.get("ID", "").strip().casefold() == task_id.strip().casefold():
            return {field: task.get(field, "") for field in CANONICAL_TASK_FIELDS}
    return None


def _validate_perspectives(record: dict[str, Any], route: str, errors: list[str]) -> None:
    perspectives = record.get("perspectives", [])
    if not isinstance(perspectives, list):
        errors.append("perspectives must be a list")
        return
    if route == "steelman_lite" and len(perspectives) < 2:
        errors.append("steelman_lite requires at least two perspectives")
    if route == "steelman_full" and len(perspectives) < 3:
        errors.append("steelman_full requires at least three perspectives")
    ids: set[str] = set()
    completed_real = False
    for index, perspective in enumerate(perspectives):
        if not isinstance(perspective, dict):
            errors.append(f"perspectives[{index}] must be an object")
            continue
        identifier = perspective.get("id")
        if not _text(identifier) or identifier in ids:
            errors.append(f"perspectives[{index}] needs a unique id")
        else:
            ids.add(identifier)
        kind = perspective.get("kind")
        if kind not in PERSPECTIVE_KINDS:
            errors.append(f"perspectives[{index}] kind must be simulated or real_subagent")
        for field in ("observation", "blindSpot", "recommendation"):
            _bounded_text(perspective.get(field), f"perspectives[{index}].{field}", errors)
        if kind == "real_subagent":
            status = perspective.get("status")
            if status not in REAL_STATUSES:
                errors.append(f"perspectives[{index}] real_subagent status is invalid")
            if status == "completed":
                completed_real = True
                _non_empty_collection(perspective.get("evidenceRefs"), f"perspectives[{index}].evidenceRefs", errors)
    declared = record.get("realSubagentsCompleted")
    if not isinstance(declared, bool):
        errors.append("realSubagentsCompleted must be boolean")
    elif declared != completed_real:
        errors.append("realSubagentsCompleted must match completed real_subagent perspectives")


def _validate_authorization(record: dict[str, Any], errors: list[str]) -> None:
    completed_real = record.get("realSubagentsCompleted") is True
    authorization = record.get("authorization")
    budgets = record.get("budgets")
    if not completed_real:
        return
    if not isinstance(authorization, dict) or authorization.get("explicitAuthorization") is not True:
        errors.append("real subagent completion requires explicitAuthorization")
    if not isinstance(budgets, dict) or any(
        not _positive_number(budgets.get(field)) for field in ("total", "perSeat", "tool", "wallClock")
    ):
        errors.append("real subagent completion requires positive total, perSeat, tool, and wallClock budgets")


def validate_steelman_artifact(record: Any, workspace: Path | None = None) -> list[str]:
    """Return contract errors for untrusted input; never claim execution occurred."""
    if not isinstance(record, dict):
        return ["artifact must be an object"]
    errors: list[str] = scan_forbidden_content(record)
    unknown = sorted(set(record) - ALLOWED_FIELDS)
    errors.extend(f"unknown field: {field}" for field in unknown)
    if record.get("schemaVersion") != SCHEMA_VERSION:
        errors.append("schemaVersion must be 1.0")
    if record.get("artifactType") != ARTIFACT_TYPE:
        errors.append("artifactType must be steelman-evolution")
    for field in BASE_REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"{field} is required")
    _bounded_text(record.get("taskId"), "taskId", errors, 128)
    unknowns = record.get("unknowns")
    if "unknowns" in record and not isinstance(unknowns, list):
        errors.append("unknowns must be a list")
    route = record.get("selectedRoute")
    if route not in ROUTES:
        errors.append("selectedRoute must be skip, steelman_lite, or steelman_full")
    max_rounds = record.get("maxRounds")
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or not 0 <= max_rounds <= 2:
        errors.append("maxRounds must be an integer from 0 through 2")
    elif route == "skip" and max_rounds != 0:
        errors.append("skip requires maxRounds 0")
    elif route in {"steelman_lite", "steelman_full"} and max_rounds < 1:
        errors.append("steelman routes require at least one round")
    if route == "skip" and not _text(record.get("skipReason")):
        errors.append("skip requires skipReason")
    if route in {"steelman_lite", "steelman_full"}:
        for field in STEELMAN_REQUIRED_FIELDS:
            if field not in record:
                errors.append(f"{field} is required for {route}")
        for field in ("trueGoal", "currentBest", "strongestOpposition", "thirdRoute", "smallestDiscriminatingTest"):
            _bounded_text(record.get(field), field, errors)
        for field in ("qualityContract", "architectureContract"):
            value = record.get(field)
            if not (_text(value) or (isinstance(value, dict) and bool(value))):
                errors.append(f"{field} must be a non-empty string or object")
        for field in ("flipVariables", "materialDissent", "reopenConditions", "evidenceRefs"):
            _non_empty_collection(record.get(field), field, errors)
        dissent = record.get("materialDissent")
        if isinstance(dissent, list):
            for index, item in enumerate(dissent):
                if isinstance(item, str):
                    if not item.strip():
                        errors.append(f"materialDissent[{index}] must not be empty")
                elif isinstance(item, dict):
                    for field in ("position", "impact", "resolution"):
                        _bounded_text(item.get(field), f"materialDissent[{index}].{field}", errors)
                else:
                    errors.append(f"materialDissent[{index}] must be text or object")
    if workspace is not None and _text(record.get("taskId")) and _canonical_task(workspace, record["taskId"]) is None:
        errors.append("taskId is not present in canonical tasks.md")
    _validate_perspectives(record, route, errors) if route in ROUTES else None
    _validate_authorization(record, errors)
    if record.get("realSubagentsCompleted") is True and route == "skip":
        errors.append("skip cannot claim real subagent completion")
    return errors


def route_steelman(
    workspace: Path,
    task_id: str | dict[str, Any],
    *,
    risk: str = "medium",
    risk_level: str | None = None,
    deterministic: bool = False,
) -> dict[str, Any]:
    """Select a route from explicit local risk inputs; no artifact or subagent is dispatched."""
    context = task_id if isinstance(task_id, dict) else {}
    if isinstance(task_id, dict):
        task_id = str(context.get("taskId", ""))
        if risk_level is None and context.get("riskLevel") is not None:
            risk_level = str(context["riskLevel"])
        if context.get("risk") is not None and risk == "medium":
            risk = str(context["risk"])
        if deterministic is False and context.get("deterministic") is not None:
            deterministic = bool(context["deterministic"])
    canonical = _canonical_task(workspace, task_id)
    if canonical is None:
        raise ValueError(f"taskId is not present in canonical tasks.md: {task_id}")
    selected_risk = (risk_level if risk_level is not None else risk).strip().casefold()
    if selected_risk not in RISKS:
        raise ValueError("risk must be low, medium, or high")
    if deterministic and selected_risk == "low":
        route, max_rounds, reason = "skip", 0, "deterministic low-risk change"
    elif selected_risk == "high":
        route, max_rounds, reason = "steelman_full", 2, "high-risk decision requires complete steelman"
    else:
        route, max_rounds, reason = "steelman_lite", 1, "material trade-off requires bounded steelman"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "artifactType": ARTIFACT_TYPE,
        "taskId": task_id,
        "lifecycleSource": "tasks.md",
        "canonicalTask": canonical,
        "selectedRoute": route,
        "maxRounds": max_rounds,
        "reason": reason,
        "artifactRequired": route != "skip",
        "perspectivesAreSimulatedByDefault": True,
        "realSubagentsCompleted": False,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    route = subparsers.add_parser("route")
    route.add_argument("workspace")
    route.add_argument("task_id")
    route.add_argument("--risk", default="medium")
    route.add_argument("--deterministic", action="store_true")
    validate = subparsers.add_parser("validate")
    validate.add_argument("artifact", type=Path)
    validate.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    if args.command == "route":
        result = route_steelman(args.workspace, args.task_id, risk=args.risk, deterministic=args.deterministic)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    record = json.loads(args.artifact.read_text(encoding="utf-8"))
    errors = validate_steelman_artifact(record, args.workspace)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(_main())
