"""Fail-closed validation for Completion Adversarial Critic Council records."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any


ROUTES = {"skip", "critic_lite", "critic_full"}
SEVERITIES = {"Critical", "High", "Medium", "Low"}
DISPOSITIONS = {"fixed", "rejected-with-counterevidence", "deferred", "accepted"}
OUTCOMES = {"passed", "limited", "blocked"}
COVERAGE = {"covered", "unknown", "not_applicable"}
GAME_CHECKPOINTS = {
    "first_launch",
    "onboarding",
    "core_loop",
    "failure_retry",
    "settings",
    "persistence",
    "progression",
    "ending_exit",
}
FINDING_ID = re.compile(
    r"^CACC-[A-Za-z0-9._-]+-[a-z0-9-]+-[0-9a-f]{8}-[1-9][0-9]*$"
)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _mapping(value: Any) -> bool:
    return isinstance(value, dict)


def _manifest_entries(manifest: Any) -> list[Any] | None:
    if isinstance(manifest, list):
        return manifest
    if isinstance(manifest, dict):
        entries = manifest.get("entries", manifest.get("artifacts"))
        return entries if isinstance(entries, list) else None
    return None


def _requires_human_acceptance(finding: dict[str, Any]) -> bool:
    return finding.get("chairFinalDisposition") == "accepted"


def _valid_acceptance(value: Any) -> bool:
    return _mapping(value) and all(
        _text(value.get(field))
        for field in ("approverIdentity", "approvalTime", "scope", "reason", "expiry", "reopenTrigger")
    )



def _validate_state_record(record: dict[str, Any]) -> list[str]:
    """Validate schema 1.1 lifecycle states without inventing dispatch evidence."""
    errors: list[str] = []
    route = record.get("selectedRoute")
    status = record.get("executionStatus")
    if route not in ROUTES: errors.append("selectedRoute must be skip, critic_lite, or critic_full")
    if status not in {"skipped", "not_dispatched", "completed"}: errors.append("executionStatus must be skipped, not_dispatched, or completed")
    if not isinstance(record.get("requiredByPolicy"), bool): errors.append("requiredByPolicy must be boolean")
    if not _text(record.get("taskId")): errors.append("taskId is required")
    if not _text(record.get("chairRecordLocator")): errors.append("chairRecordLocator is required")
    elif not record["chairRecordLocator"].replace("\\", "/").startswith(
        "output/mission-center-critique/"
    ):
        errors.append("chairRecordLocator must use output/mission-center-critique/")
    if record.get("requiredByPolicy") is True and status in {"skipped", "not_dispatched"}:
        errors.append("requiredByPolicy records must be completed")
    if status in {"skipped", "not_dispatched"}:
        if not _text(record.get("reason")): errors.append(f"{status} requires reason")
        return errors
    # Completed records use the established full contract after an explicit v1.1-to-v1.0 projection.
    projected = dict(record); projected["schemaVersion"]="1.0"; projected["route"]=route
    errors.extend(validate_critic_record(projected))
    return errors

def validate_critic_record(record: Any) -> list[str]:
    """Return contract errors; never raise for malformed, untrusted input."""
    try:
        errors: list[str] = []
        if not _mapping(record):
            return ["record must be an object"]

        schema_version = record.get("schemaVersion")
        if schema_version == "1.1":
            return _validate_state_record(record)
        if schema_version != "1.0":
            errors.append("schemaVersion must be 1.0 or 1.1")
        route = record.get("route")
        if route not in ROUTES:
            errors.append("route must be skip, critic_lite, or critic_full")
        if not _text(record.get("taskId")):
            errors.append("taskId is required")
        if not _text(record.get("chairRecordLocator")):
            errors.append("chairRecordLocator is required")
        elif not record["chairRecordLocator"].replace("\\", "/").startswith(
            "output/mission-center-critique/"
        ):
            errors.append("chairRecordLocator must use output/mission-center-critique/")

        entries = _manifest_entries(record.get("artifactManifest"))
        manifest_lane_ids: list[str] = []
        if not entries:
            errors.append("artifactManifest must contain entries")
        else:
            for index, entry in enumerate(entries):
                if not _mapping(entry) or not _text(entry.get("locator")):
                    errors.append(f"artifactManifest entry {index} needs locator")
                    continue
                if not _text(entry.get("laneId")):
                    errors.append(f"artifactManifest entry {index} needs laneId")
                else:
                    manifest_lane_ids.append(entry["laneId"])
                sha256 = entry.get("sha256")
                has_hash = _text(sha256) and bool(
                    re.fullmatch(r"[0-9a-fA-F]{64}", sha256)
                )
                if _text(sha256) and not has_hash:
                    errors.append(f"artifactManifest entry {index} has invalid sha256")
                if not (
                    has_hash
                    or _text(entry.get("version"))
                    or _text(entry.get("archiveLocator"))
                ):
                    errors.append(f"artifactManifest entry {index} needs sha256, version, or archiveLocator")

        snapshots = record.get("snapshots")
        if not isinstance(snapshots, list) or not 1 <= len(snapshots) <= 2:
            errors.append("snapshots must contain one or two snapshots")
        elif all(_mapping(snapshot) for snapshot in snapshots):
            first = snapshots[0]
            if first.get("parent") not in (None, ""):
                errors.append("first snapshot must not have a parent")
            first_id = first.get("id", first.get("snapshotId"))
            snapshot_ids: set[str] = set()
            for index, snapshot in enumerate(snapshots):
                snapshot_id = snapshot.get("id", snapshot.get("snapshotId"))
                if not _text(snapshot_id) or snapshot_id in snapshot_ids:
                    errors.append(f"snapshot {index} needs a unique id")
                else:
                    snapshot_ids.add(snapshot_id)
                for field in ("revision", "hash", "evidenceLinks"):
                    if field == "evidenceLinks":
                        valid = isinstance(snapshot.get(field), list) and bool(snapshot[field])
                    else:
                        valid = _text(snapshot.get(field))
                    if not valid:
                        errors.append(f"snapshot {index} needs {field}")
            if len(snapshots) == 2 and snapshots[1].get("parent") != first_id:
                errors.append("delta snapshot parent must reference first snapshot")
        else:
            errors.append("each snapshot must be an object")

        if route in {"critic_lite", "critic_full"}:
            authorization = record.get("authorization")
            if not _mapping(authorization) or authorization.get("explicitApproval") is not True:
                errors.append("critic routes require explicit authorization")
            budgets = record.get("budgets")
            if not _mapping(budgets) or any(
                not _positive_number(budgets.get(field))
                for field in ("total", "perSeat", "tool", "wallClock")
            ):
                errors.append("critic routes require positive total, perSeat, tool, and wallClock budgets")
            critics = record.get("critics")
            if not isinstance(critics, list) or len(critics) < (3 if route == "critic_full" else 2):
                errors.append("route has insufficient critic seats")
                critic_ids: set[str] = set()
            else:
                critic_ids = {
                    critic.get("id")
                    for critic in critics
                    if _mapping(critic) and _text(critic.get("id"))
                }
                if len(critic_ids) != len(critics):
                    errors.append("critic seats need unique ids")

            outcome = record.get("outcome")
            if outcome not in OUTCOMES:
                errors.append("critic routes require passed, limited, or blocked outcome")

            lanes = record.get("lanes")
            lane_ids: set[str] = set()
            has_uncovered_required = False
            if not isinstance(lanes, list) or not lanes:
                errors.append("critic routes require non-empty lanes")
            else:
                for index, lane in enumerate(lanes):
                    if not _mapping(lane):
                        errors.append(f"lane {index} must be an object")
                        continue
                    lane_id = lane.get("id")
                    if not _text(lane_id) or lane_id in lane_ids:
                        errors.append(f"lane {index} needs a unique id")
                    else:
                        lane_ids.add(lane_id)
                    if not _text(lane.get("kind")):
                        errors.append(f"lane {index} needs kind")
                    if not isinstance(lane.get("required"), bool):
                        errors.append(f"lane {index} needs boolean required")
                    status = lane.get("coverageStatus")
                    if status not in COVERAGE:
                        errors.append(f"lane {index} has invalid coverageStatus")
                    if status == "covered":
                        if lane.get("seatId") not in critic_ids:
                            errors.append(f"lane {index} needs an assigned critic seat")
                        if not _text(lane.get("evidenceLocator")):
                            errors.append(f"lane {index} needs evidenceLocator")
                    elif status in {"unknown", "not_applicable"} and not _text(
                        lane.get("capabilityReason")
                    ):
                        errors.append(f"lane {index} needs capabilityReason")
                    if lane.get("required") is True and status != "covered":
                        has_uncovered_required = True

                    if lane.get("kind") == "game/interactive":
                        journey = lane.get("journeyCoverage")
                        if not isinstance(journey, list):
                            errors.append(f"lane {index} needs journeyCoverage")
                        else:
                            by_checkpoint = {
                                item.get("checkpoint"): item
                                for item in journey
                                if _mapping(item) and _text(item.get("checkpoint"))
                            }
                            if set(by_checkpoint) != GAME_CHECKPOINTS:
                                errors.append(f"lane {index} needs every game checkpoint")
                            for checkpoint, item in by_checkpoint.items():
                                checkpoint_status = item.get("coverageStatus")
                                if checkpoint_status not in COVERAGE:
                                    errors.append(
                                        f"lane {index} checkpoint {checkpoint} has invalid coverageStatus"
                                    )
                                elif checkpoint_status == "covered" and not _text(
                                    item.get("evidenceLocator")
                                ):
                                    errors.append(
                                        f"lane {index} checkpoint {checkpoint} needs evidenceLocator"
                                    )
                                elif checkpoint_status != "covered" and not _text(
                                    item.get("reason")
                                ):
                                    errors.append(
                                        f"lane {index} checkpoint {checkpoint} needs reason"
                                    )
                                if checkpoint_status == "unknown":
                                    has_uncovered_required = True

            for lane_id in manifest_lane_ids:
                if lane_id not in lane_ids:
                    errors.append(f"artifactManifest references unknown lane {lane_id}")
            if has_uncovered_required and outcome == "passed":
                errors.append("required unknown coverage prevents passed outcome")
            if route == "critic_full":
                arbiter = record.get("arbiter")
                if not _mapping(arbiter) or not _text(arbiter.get("id")) or arbiter["id"] in critic_ids:
                    errors.append("critic_full requires an independent arbiter")
            if record.get("notDispatched") is True or record.get("dispatchStatus") == "notDispatched":
                errors.append("critic routes cannot be notDispatched")

        if record.get("smokePassedByCouncil") is True:
            errors.append("council evidence cannot be smoke evidence")

        findings = record.get("findings", [])
        if not isinstance(findings, list):
            errors.append("findings must be a list")
        else:
            seen_ids: set[str] = set()
            for index, finding in enumerate(findings):
                if not _mapping(finding):
                    errors.append(f"finding {index} must be an object")
                    continue
                finding_id = finding.get("id")
                if (
                    not _text(finding_id)
                    or not FINDING_ID.fullmatch(finding_id)
                    or finding_id in seen_ids
                ):
                    errors.append(f"finding {index} needs a unique stable id")
                else:
                    seen_ids.add(finding_id)
                severity = finding.get("severity")
                if severity not in SEVERITIES:
                    errors.append(f"finding {index} has invalid severity")
                for field in (
                    "category",
                    "observation",
                    "evidenceLocator",
                    "reproOrReadPath",
                    "impact",
                    "confidence",
                    "recommendation",
                ):
                    if not _text(finding.get(field)):
                        errors.append(f"finding {index} needs {field}")
                if "unknown" not in finding:
                    errors.append(f"finding {index} needs unknown")
                if not _text(finding.get("criticProposedDisposition")):
                    errors.append(f"finding {index} needs criticProposedDisposition")
                disposition = finding.get("chairFinalDisposition")
                if disposition not in DISPOSITIONS:
                    errors.append(f"finding {index} has invalid chairFinalDisposition")
                if severity == "Critical" and disposition == "accepted":
                    errors.append(f"finding {index}: Critical cannot be human accepted")
                if severity == "Critical" and disposition not in {"fixed", "rejected-with-counterevidence"}:
                    errors.append(f"finding {index}: unresolved Critical finding")
                if severity == "High" and disposition == "deferred" and not _valid_acceptance(finding.get("humanAcceptance")):
                    errors.append(f"finding {index}: deferred High finding needs complete humanAcceptance")
                if _requires_human_acceptance(finding) and not _valid_acceptance(finding.get("humanAcceptance")):
                    errors.append(f"finding {index}: accepted finding needs complete humanAcceptance")
        return errors
    except Exception:
        return ["record could not be validated"]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: critic_contract.py RECORD.json", file=sys.stderr)
        return 1
    try:
        record = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"invalid critic record input: {error}", file=sys.stderr)
        return 1
    errors = validate_critic_record(record)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
