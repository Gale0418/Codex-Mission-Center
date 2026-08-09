#!/usr/bin/env python3
"""Dependency-free adaptive routing and bounded shadow evaluation."""

from __future__ import annotations

import json
import math
import re
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
EXPERT_PROFILES = {
    "codebase_analyst": {"mission": "Bound local behavior and constraints", "artifact": "evidence_map"},
    "researcher": {"mission": "Compare prior art and primary sources", "artifact": "prior_art_matrix"},
    "architect": {"mission": "Select boundaries and contracts", "artifact": "decision_record"},
    "implementer": {"mission": "Deliver the smallest safe slice", "artifact": "working_change"},
    "verifier": {"mission": "Independently test promotion claims", "artifact": "verification_evidence"},
    "performance_cost_optimizer": {"mission": "Improve measurable trade-offs", "artifact": "pareto_candidates"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a structured classifier result without inventing evidence."""
    defaults = {
        "schemaVersion": SCHEMA_VERSION,
        "taskType": "research",
        "parameterShape": "none",
        "measurement": "none",
        "noise": "unknown",
        "reversibility": "unknown",
        "risk": "medium",
        "budget": {"trials": 0, "tokens": 0, "wallClockSeconds": 0},
        "objectives": [],
        "differentiable": False,
        "factorCount": 0,
        "localCases": [],
        "unknowns": [],
    }
    profile = {**defaults, **raw}
    profile["schemaVersion"] = SCHEMA_VERSION
    if not isinstance(profile.get("unknowns"), list):
        profile["unknowns"] = []
    if profile["measurement"] in {"none", "subjective"}:
        profile["unknowns"] = sorted({str(item) for item in profile["unknowns"]} | {"repeatable_metric"})
    return profile


def route_profile(profile: dict[str, Any]) -> dict[str, Any]:
    measurement = profile.get("measurement", "none")
    shape = profile.get("parameterShape", "none")
    factors = int(profile.get("factorCount", 0) or 0)
    objectives = profile.get("objectives") or []
    budget = profile.get("budget") or {}
    reasons: list[str] = []
    missing: list[str] = []

    if measurement in {"none", "subjective"} and profile.get("taskType") != "deterministic":
        missing.append("repeatable_metric")
        return _decision("research_spike", "evidence_collection", ["No repeatable measurement is available"], missing)
    if profile.get("taskType") == "deterministic" or shape == "none":
        return _decision("skip", "direct_verification", ["The task is deterministic or has no tunable parameters"], [])
    if int(budget.get("trials", 0) or 0) < 1:
        return _decision("research_spike", "budget_definition", ["Experiment budget is missing"], ["positive_trial_budget"])

    mode = "experimental" if measurement in {"repeatable", "expensive"} else "hybrid"
    if len(objectives) > 1 or shape == "multi_objective":
        strategy = "pareto_nsga2" if int(budget.get("trials", 0)) >= 20 else "pareto_trade_study"
        reasons.append("Multiple objectives must remain separate")
    elif profile.get("noise") == "high":
        strategy = "robust_doe_taguchi"
        reasons.append("High measurement noise")
    elif shape == "mixed" or shape == "categorical":
        strategy = "tpe"
        reasons.append("Categorical or mixed parameters")
    elif shape == "continuous" and profile.get("differentiable"):
        strategy = "gradient_method"
        reasons.append("Continuous differentiable objective")
    elif shape == "continuous" and measurement == "expensive" and factors <= 12:
        strategy = "bayesian_optimization"
        reasons.append("Few expensive black-box parameters")
    elif factors >= 4:
        strategy = "screening_doe"
        reasons.append("Many factors require screening")
    elif shape == "discrete":
        strategy = "trade_study_scenario_stress"
        mode = "decision" if profile.get("risk") == "low" else "hybrid"
        reasons.append("Few discrete alternatives")
    else:
        strategy = "bounded_trade_study"
        mode = "hybrid"
        reasons.append("Evidence supports only bounded comparison")
    return _decision(mode, strategy, reasons, missing)


def _decision(mode: str, strategy: str, reason: list[str], missing: list[str]) -> dict[str, Any]:
    return {"schemaVersion": SCHEMA_VERSION, "mode": mode, "strategy": strategy, "reason": reason, "missingEvidence": missing, "promotionPolicy": "manual_review_only"}


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("experimentId", "kind", "candidates", "cases", "metrics", "hardConstraints", "budget", "stoppingConditions", "validation", "promotionState"):
        if field not in manifest:
            errors.append(f"missing:{field}")
    budget = manifest.get("budget") or {}
    for field in ("trials", "tokens", "wallClockSeconds"):
        value = budget.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f"invalid_budget:{field}")
    for field, limit in (("maxConcurrency", 2), ("retriesPerTrial", 1)):
        value = budget.get(field, limit)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > limit:
            errors.append(f"invalid_budget:{field}")
    if manifest.get("promotionState") != "shadow":
        errors.append("promotionState_must_be_shadow")
    experiment_id = manifest.get("experimentId")
    if not isinstance(experiment_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", experiment_id):
        errors.append("invalid:experimentId")
    metrics = manifest.get("metrics")
    if not isinstance(metrics, list) or not metrics or any(
        not isinstance(metric, dict)
        or not isinstance(metric.get("name"), str)
        or not metric.get("name")
        or metric.get("direction") not in {"minimize", "maximize"}
        for metric in (metrics if isinstance(metrics, list) else [])
    ):
        errors.append("invalid:metrics")
    return errors


def evaluate_observations(manifest: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    errors = validate_manifest(manifest)
    if errors:
        return _empty_result(manifest.get("experimentId", "unknown"), "invalid", errors)
    budget = manifest["budget"]
    accepted: list[dict[str, Any]] = []
    used_tokens = 0
    used_seconds = 0.0
    attempts: dict[tuple[str, str], int] = {}
    budget_exhausted = False
    for observation in observations:
        key = (str(observation.get("candidate", "unknown")), str(observation.get("case", "default")))
        attempts[key] = attempts.get(key, 0) + 1
        if attempts[key] > budget.get("retriesPerTrial", 1) + 1:
            continue
        tokens = int(observation.get("tokens", 0) or 0)
        seconds = float(observation.get("wallClockSeconds", 0) or 0)
        if len(accepted) >= budget["trials"] or used_tokens + tokens > budget["tokens"] or used_seconds + seconds > budget["wallClockSeconds"]:
            budget_exhausted = True
            break
        accepted.append(observation)
        used_tokens += tokens
        used_seconds += seconds
    if not accepted:
        return _empty_result(manifest["experimentId"], "stopped", ["no_experiment_data"])

    metrics = manifest["metrics"]
    valid: list[dict[str, Any]] = []
    unknowns: list[str] = []
    for item in accepted:
        values = item.get("metrics") or {}
        missing = [metric["name"] for metric in metrics if not isinstance(values.get(metric["name"]), (int, float)) or not math.isfinite(values[metric["name"]])]
        if missing:
            unknowns.append(f"{item.get('candidate', 'unknown')}:{','.join(missing)}")
            continue
        if _passes_constraints(item, manifest["hardConstraints"]):
            valid.append(item)

    pareto = _pareto(valid, metrics)
    baseline_id = manifest.get("baselineCandidate")
    baseline = next((item for item in valid if item.get("candidate") == baseline_id), None)
    deltas: dict[str, Any] = {}
    if baseline:
        for item in valid:
            if item is baseline:
                continue
            deltas[str(item.get("candidate"))] = {m["name"]: item["metrics"][m["name"]] - baseline["metrics"][m["name"]] for m in metrics}

    composite = None
    if manifest.get("normalization") and manifest.get("weights"):
        composite = _composite(valid, metrics, manifest["normalization"], manifest["weights"])
    sample_count = len(accepted)
    confidence = "high" if sample_count >= 20 else "medium" if sample_count >= 8 else "low"
    recommendation = "review" if pareto and not unknowns else "insufficient_evidence"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "experimentId": manifest["experimentId"],
        "status": "budget_exhausted" if budget_exhausted else "completed",
        "baselineDelta": deltas,
        "paretoCandidates": pareto,
        "confidence": confidence,
        "sampleCount": sample_count,
        "unknowns": sorted(set(unknowns)),
        "compositeLoss": composite,
        "promotionRecommendation": recommendation,
        "promotionState": "review" if recommendation == "review" else "shadow",
        "budgetUsed": {"trials": sample_count, "tokens": used_tokens, "wallClockSeconds": used_seconds},
        "evaluatedAt": utc_now(),
    }


def _passes_constraints(item: dict[str, Any], constraints: list[dict[str, Any]]) -> bool:
    values = item.get("metrics") or {}
    for rule in constraints:
        value = values.get(rule.get("metric"))
        if not isinstance(value, (int, float)):
            return False
        if "max" in rule and value > rule["max"]:
            return False
        if "min" in rule and value < rule["min"]:
            return False
    return True


def _pareto(items: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> list[str]:
    winners: list[str] = []
    for candidate in items:
        dominated = False
        for other in items:
            if other is candidate:
                continue
            no_worse = True
            better = False
            for metric in metrics:
                name = metric["name"]
                a, b = other["metrics"][name], candidate["metrics"][name]
                if metric["direction"] == "maximize":
                    no_worse &= a >= b
                    better |= a > b
                else:
                    no_worse &= a <= b
                    better |= a < b
            if no_worse and better:
                dominated = True
                break
        if not dominated:
            winners.append(str(candidate.get("candidate", "unknown")))
    return sorted(set(winners))


def _composite(items: list[dict[str, Any]], metrics: list[dict[str, Any]], normalization: dict[str, Any], weights: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for item in items:
        total = 0.0
        for metric in metrics:
            name = metric["name"]
            bounds = normalization.get(name, {})
            low, high = bounds.get("min"), bounds.get("max")
            if not isinstance(low, (int, float)) or not isinstance(high, (int, float)) or high <= low:
                raise ValueError(f"Invalid normalization for {name}")
            normalized = (item["metrics"][name] - low) / (high - low)
            loss = 1 - normalized if metric["direction"] == "maximize" else normalized
            total += loss * float(weights.get(name, 0))
        scores[str(item.get("candidate", "unknown"))] = round(total, 6)
    return scores


def _empty_result(experiment_id: str, status: str, unknowns: list[str]) -> dict[str, Any]:
    return {"schemaVersion": SCHEMA_VERSION, "experimentId": experiment_id, "status": status, "baselineDelta": {}, "paretoCandidates": [], "confidence": "none", "sampleCount": 0, "unknowns": unknowns, "compositeLoss": None, "promotionRecommendation": "insufficient_evidence", "promotionState": "shadow", "budgetUsed": {"trials": 0, "tokens": 0, "wallClockSeconds": 0.0}, "evaluatedAt": utc_now()}
