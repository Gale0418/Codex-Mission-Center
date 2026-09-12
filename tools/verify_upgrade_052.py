#!/usr/bin/env python3
"""Offline, black-box acceptance probes for Mission Center 0.5.2.

This is a development test harness, NOT a Python runtime fallback. It executes
only the explicitly supplied local binary against disposable workspaces. It
never runs CI, connects to a model/provider, or writes the caller's workspace.
Process execution requires Linux PID/user namespaces plus util-linux
``unshare``; unsupported platforms fail closed with exit 2. The runner bounds
captured output and lifetime, not arbitrary child filesystem/network/resource
operations.

Exit 0 means all probes passed; exit 1 means an assertion failed; exit 2 means
setup, execution, timeout, JSON decoding, or report writing failed. A baseline
failure is deliberately NOT converted into a successful upgrade verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from typing import Any

from bounded_process import run_bounded

TIMEOUT_SECONDS = 30
MAX_OUTPUT_BYTES = 1024 * 1024
RESUME_MAX_BYTES = 16 * 1024
RESUME_MAX_VALUE_NODES = 10_000
FIXTURE_DATE = "2026-09-12"
TASK_HEADER = (
    "# Tasks\n\n"
    "| ID | Title | Type | Parent | Priority | Status | Owner | Depends on | "
    "Next action | Verification | Estimate | Labels | Comments |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)
RESUME_CONTENT_FIELDS = {
    "handoff",
    "brief",
    "workingSet",
    "activeCriticalLessons",
    "snapshot",
}


def task_row(task_id: str, status: str, priority: str = "P1") -> str:
    return (
        f"| {task_id} | Fixture {task_id} | task | | {priority} | {status} | "
        "worker | | Run local check | local test | S | | fixture |\n"
    )


def invoke(binary: Path, root: Path, *args: str) -> dict[str, Any]:
    """Run one candidate command and retain its raw envelope for validation.

    Path redaction is deliberately deferred until the final report is built.
    Otherwise replacing a long fixture path with ``<fixture>`` could shrink a
    resume packet before its shared 16 KiB contract is measured.
    """
    exit_code, output, errors = run_bounded(
        [str(binary), *args, "--root", str(root)],
        timeout=TIMEOUT_SECONDS,
        max_output_bytes=MAX_OUTPUT_BYTES,
    )
    payload = json.loads(output.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("CLI envelope must be a JSON object")
    return {
        "command": list(args),
        "exitCode": exit_code,
        "envelope": payload,
        "stderr": errors.decode("utf-8", errors="replace"),
    }


def data_of(result: dict[str, Any]) -> dict[str, Any]:
    envelope = result.get("envelope")
    if not isinstance(envelope, dict):
        return {}
    data = envelope.get("data")
    return data if isinstance(data, dict) else {}


def check_status(result: dict[str, Any], name: str) -> str | None:
    checks = data_of(result).get("checks", [])
    if not isinstance(checks, list):
        return None
    value = next(
        (
            check.get("status")
            for check in checks
            if isinstance(check, dict) and check.get("name") == name
        ),
        None,
    )
    return value if isinstance(value, str) else None


def _resume_envelope_valid(result: dict[str, Any]) -> bool:
    """Enforce the stable closed-world successful CLI envelope before data use."""
    if result.get("exitCode") != 0:
        return False
    envelope = result.get("envelope")
    if not isinstance(envelope, dict):
        return False
    required = {"schemaVersion", "command", "status", "data"}
    allowed = required | {"route"}
    if not required.issubset(envelope) or not set(envelope).issubset(allowed):
        return False
    if envelope.get("schemaVersion") != "1.0":
        return False
    if envelope.get("command") != "resume" or envelope.get("status") != "ok":
        return False
    if "route" in envelope and envelope.get("route") != "resume":
        return False
    return isinstance(envelope.get("data"), dict)


def _bounded_resume_string_bytes(payload: dict[str, Any]) -> int | None:
    """Count every bounded public JSON key/string/scalar representation.

    The metric intentionally excludes JSON structural punctuation/quotes but
    includes every object key, string value, null, boolean, and integer value.
    Floats are not part of the documented resume contract and fail closed.
    Counting the numeric ``bytes`` declaration itself is safe: a valid packet
    must use the small fixed point implied by its decimal digit count.
    """
    stack: list[Any] = [payload]
    total = 0
    nodes = 0
    while stack:
        value = stack.pop()
        nodes += 1
        if nodes > RESUME_MAX_VALUE_NODES:
            return None
        if isinstance(value, str):
            total += len(value.encode("utf-8"))
        elif isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    return None
                stack.append(key)
                stack.append(item)
        elif isinstance(value, list):
            stack.extend(value)
        elif value is None:
            total += 4
        elif isinstance(value, bool):
            total += 4 if value else 5
        elif isinstance(value, int):
            total += len(str(value).encode("ascii"))
        elif isinstance(value, float):
            return None
        else:
            return None
        if total > RESUME_MAX_BYTES:
            return total
    return total


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _nullable_string(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _section_matches_source(
    name: str,
    value: str | None,
    source: str | None,
    read_next: list[str],
) -> bool:
    if source is None:
        return value is None
    if value == source:
        return True
    if name not in read_next or not isinstance(value, str):
        return False
    marker = "[TRUNCATED]"
    if value.endswith(marker):
        return source.startswith(value[: -len(marker)])
    return False


def resume_contract_valid(
    result: dict[str, Any],
    expected_sections: dict[str, str | None] | None = None,
) -> bool:
    """Validate the complete successful shared-budget Resume 1.1 packet."""
    if not _resume_envelope_valid(result):
        return False
    payload = data_of(result)
    required_fields = {
        "schemaVersion",
        "route",
        "sourceFresh",
        "dateFresh",
        "staleReasons",
        "filesRead",
        "content",
        "handoff",
        "ledgerStatus",
        "ledgerError",
        "context",
        "bytes",
        "maxBytes",
        "canonicalFallback",
        "fallbackReason",
        "truncated",
        "truncatedMarker",
        "readNext",
    }
    if not required_fields.issubset(payload):
        return False
    if payload.get("schemaVersion") != "1.1" or payload.get("route") != "resume":
        return False
    for name in ("sourceFresh", "dateFresh", "canonicalFallback", "truncated"):
        if not isinstance(payload.get(name), bool):
            return False
    for name in ("staleReasons", "filesRead", "readNext"):
        if not _string_list(payload.get(name)):
            return False
    if payload.get("ledgerStatus") not in {"missing", "ready", "corrupt"}:
        return False
    for name in ("ledgerError", "fallbackReason", "truncatedMarker"):
        if not _nullable_string(payload.get(name)):
            return False
    if payload.get("handoff") is not None and not isinstance(payload.get("handoff"), dict):
        return False

    content = payload.get("content")
    if not isinstance(content, dict) or not RESUME_CONTENT_FIELDS.issubset(content):
        return False
    if not all(value is None or isinstance(value, str) for value in content.values()):
        return False
    if not isinstance(content.get("brief"), str) or not content["brief"]:
        return False
    if not isinstance(content.get("workingSet"), str) or not content["workingSet"]:
        return False

    context = payload.get("context")
    if not isinstance(context, dict):
        return False
    included = context.get("includedBytes")
    if not isinstance(included, dict) or set(included) != set(content):
        return False
    for name, value in content.items():
        declared = included.get(name)
        if (
            isinstance(declared, bool)
            or not isinstance(declared, int)
            or declared < 0
            or declared != len((value or "").encode("utf-8"))
        ):
            return False

    read_next = payload["readNext"]
    if expected_sections is not None:
        for name, source in expected_sections.items():
            if name not in content or not _section_matches_source(
                name, content[name], source, read_next
            ):
                return False

    actual_bytes = _bounded_resume_string_bytes(payload)
    if actual_bytes is None:
        return False
    used_bytes = payload.get("bytes")
    max_bytes = payload.get("maxBytes")
    if (
        isinstance(used_bytes, bool)
        or not isinstance(used_bytes, int)
        or isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
    ):
        return False
    return used_bytes == actual_bytes and 0 <= used_bytes <= max_bytes <= RESUME_MAX_BYTES


def corrupt_resume_contract_valid(
    result: dict[str, Any],
    expected_sections: dict[str, str | None] | None = None,
) -> bool:
    if not resume_contract_valid(result, expected_sections):
        return False
    data = data_of(result)
    content = data["content"]
    return (
        data.get("ledgerStatus") == "corrupt"
        and isinstance(data.get("ledgerError"), str)
        and bool(data["ledgerError"].strip())
        and data.get("handoff") is None
        and content.get("handoff") is None
        and data.get("canonicalFallback") is True
        and isinstance(data.get("fallbackReason"), str)
        and bool(data["fallbackReason"].strip())
        and bool(data.get("readNext"))
    )


def sync(binary: Path, root: Path, operation: str) -> None:
    result = invoke(
        binary,
        root,
        "sync",
        "--operation-id",
        operation,
        "--timestamp",
        FIXTURE_DATE + "T08:00:01Z",
    )
    if result["exitCode"] != 0:
        raise RuntimeError("fixture sync failed: " + json.dumps(result, ensure_ascii=False))


def _redact_report_paths(report: dict[str, Any], root: Path) -> dict[str, Any]:
    """Redact disposable paths only after every acceptance assertion is done."""
    serialized = json.dumps(report, ensure_ascii=False)
    return json.loads(serialized.replace(str(root), "<fixture>"))


def collect(binary: Path) -> dict[str, Any]:
    probes: list[dict[str, Any]] = []

    def record(name: str, passed: bool, observed: Any, expected: str) -> None:
        probes.append(
            {
                "name": name,
                "passed": passed,
                "expected": expected,
                "observed": observed,
            }
        )

    with tempfile.TemporaryDirectory(prefix="mc-052-probe-") as temporary:
        root = Path(temporary)
        initialized = invoke(
            binary,
            root,
            "init",
            "--operation-id",
            "probe-init",
            "--timestamp",
            FIXTURE_DATE + "T08:00:00Z",
            "--language",
            "en",
        )
        if initialized["exitCode"] != 0:
            raise RuntimeError("fixture init failed: " + json.dumps(initialized))
        mission = root / "MissionCenter"
        tasks_path = mission / "tasks.md"
        tasks_path.write_text(
            TASK_HEADER
            + "".join(task_row(f"MC-{index:03d}", "Blocked") for index in range(1, 7))
            + task_row("MC-007", "In Progress"),
            encoding="utf-8",
        )
        sync(binary, root, "probe-sync-active")
        working_set_path = mission / "working-set.md"
        brief_path = mission / "brief.md"
        working_set = working_set_path.read_text(encoding="utf-8")
        expected_sections = {
            "brief": brief_path.read_text(encoding="utf-8"),
            "workingSet": working_set,
        }
        record(
            "active_task_survives_six_unrelated_blockers",
            "MC-007" in working_set,
            working_set,
            "The active MC-007 remains represented in the bounded working set.",
        )
        task_before = tasks_path.read_bytes()
        resumed = invoke(binary, root, "resume", "--date", FIXTURE_DATE)
        record(
            "resume_delivers_documented_context",
            resume_contract_valid(resumed, expected_sections),
            resumed,
            "resume returns the stable CLI envelope and actual generated workspace context within the shared 16 KiB budget.",
        )
        (mission / "execution-ledger.jsonl").write_text("{not-json}\n", encoding="utf-8")
        (root / "output" / "mission-center-evidence").mkdir(parents=True)
        reconciled = invoke(binary, root, "reconcile", "--date", FIXTURE_DATE)
        record(
            "reconcile_rejects_corrupt_ledger",
            check_status(reconciled, "ledger")
            in {"error", "corrupt", "invalid", "fail", "failed"},
            reconciled,
            "A present but malformed ledger is explicitly rejected, not passed by existence.",
        )
        record(
            "empty_evidence_directory_is_not_verified",
            check_status(reconciled, "evidence_envelope")
            in {
                "unknown",
                "missing",
                "empty",
                "not_applicable",
                "not-applicable",
                "error",
                "invalid",
            },
            reconciled,
            "An empty evidence directory does not count as verified evidence.",
        )
        corrupted_resume = invoke(binary, root, "resume", "--date", FIXTURE_DATE)
        record(
            "resume_does_not_call_corrupt_ledger_ready",
            corrupt_resume_contract_valid(corrupted_resume, expected_sections),
            corrupted_resume,
            "A corrupt ledger yields a complete Resume 1.1 packet with no trusted handoff, a nonempty corruption error, canonical fallback, and explicit read-next guidance.",
        )
        record(
            "read_only_commands_preserve_canonical_tasks",
            task_before == tasks_path.read_bytes(),
            {"tasksUnchanged": task_before == tasks_path.read_bytes()},
            "resume and reconcile do not mutate tasks.md.",
        )
        (mission / "execution-ledger.jsonl").unlink()
        passports = root / "output" / "mission-center-passports"
        passports.mkdir(parents=True)
        (passports / "MC-001.json").write_text(
            '{"schemaVersion":"incorrect"}', encoding="utf-8"
        )
        rows = [task_row("MC-001", "Done"), task_row("MC-002", "Done")]
        doctors = []
        for index, order in enumerate((rows, list(reversed(rows)))):
            tasks_path.write_text(TASK_HEADER + "".join(order), encoding="utf-8")
            sync(binary, root, f"probe-sync-passports-{index}")
            doctors.append(invoke(binary, root, "doctor"))
        record(
            "doctor_error_severity_is_order_independent",
            all(
                result["exitCode"] != 0
                and check_status(result, "completion_passport") == "error"
                for result in doctors
            ),
            doctors,
            "A corrupt passport remains an error regardless of a later missing passport.",
        )
        report = {
            "schemaVersion": "1.0",
            "artifactType": "upgrade-052-black-box-probes",
            "fixtureDate": FIXTURE_DATE,
            "fixtureIsSynthetic": True,
            "binarySha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "pythonVersion": platform.python_version(),
            "platform": platform.system(),
            "ciExecuted": False,
            "independentReview": "not-performed",
            "passed": sum(probe["passed"] for probe in probes),
            "total": len(probes),
            "probes": probes,
        }
        return _redact_report_paths(report, root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        binary = args.binary.expanduser().resolve(strict=True)
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise RuntimeError("--binary must be an executable local file")
        report = collect(binary)
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.report:
            args.report.write_text(text, encoding="utf-8")
        print(text, end="")
        return 0 if report["passed"] == report["total"] else 1
    except (
        OSError,
        RuntimeError,
        ValueError,
        RecursionError,
        subprocess.TimeoutExpired,
    ) as error:
        print(
            json.dumps(
                {"status": "probe_setup_error", "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())