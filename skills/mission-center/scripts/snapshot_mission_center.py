#!/usr/bin/env python3
"""Create a bounded, canonical Execution Checkpoint for MissionCenter."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from common.markdown_table import parse_table
MAX_RECENT_ATTEMPTS = 5
CANONICAL_ATTEMPT_FIELDS = {"phase", "errorSignature", "hypothesis", "evidence"}
ATTEMPTS_METADATA_PREFIX = "- Recent attempts JSON: "
DIAGNOSIS_METADATA_PREFIX = "- Diagnosis evidence JSON: "
VERIFICATION_METADATA_PREFIX = "- Verification evidence JSON: "
LOW_COST_VERIFICATIONS = {"unit_test", "integration_test", "config_validation", "dry_run", "local_reproduction", "staging_smoke", "read_only_query"}
SECRET_PATTERN = re.compile(r"(?i)(password|secret|api[_-]?key|token|authorization|bearer)\s*[:=]")

TEXT = {
    "en": {"title": "Execution Checkpoint", "captured_at": "Captured at", "active": "Active task", "status": "Status", "revision": "Revision", "fingerprint": "Fingerprint", "dependencies": "Dependencies", "verification": "Verification", "resume": "Resume", "attempts": "Recent attempts", "none": "None", "inactive": "No active task; resume from canonical task selection."},
    "zh-TW": {"title": "執行檢查點", "captured_at": "建立時間", "active": "進行中任務", "status": "狀態", "revision": "版本", "fingerprint": "指紋", "dependencies": "依賴", "verification": "驗證", "resume": "恢復", "attempts": "近期嘗試", "none": "無", "inactive": "目前沒有進行中任務；請從 canonical 任務清單重新選取。"},
}


def write_text_lf(path: Path, content: str) -> None:
    """Write UTF-8 text with stable LF newlines on every supported Python."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def detect_language(root: Path) -> str:
    for name in ("project.md", "progress.md", "tasks.md"):
        path = root / name
        if path.exists() and any(x in path.read_text(encoding="utf-8") for x in ("# 專案", "# 進度", "# 任務", "- 目標:", "- 目標：")):
            return "zh-TW"
    return "en"


def _task_rows(tasks: Path) -> list[dict[str, str]]:
    if not tasks.exists(): return []
    try: return parse_table(tasks)
    except ValueError: return []


def _field(row: dict[str,str], *names: str) -> str:
    lowered={key.lower():value for key,value in row.items()}
    for name in names:
        if name in row: return row[name]
        if name.lower() in lowered: return lowered[name.lower()]
    return ""


def canonical_facts(workspace: Path) -> dict[str, str]:
    root=workspace.resolve()/"MissionCenter"; rows=_task_rows(root/"tasks.md")
    active=[r for r in rows if _field(r,"Status","狀態") in {"In Progress","Blocked","進行中","阻塞"}]
    task=active[0] if active else None
    try:
        revision=subprocess.run(["git","-C",str(workspace.resolve()),"rev-parse","HEAD"],capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired): revision="unavailable"
    sources=[]
    for path in (root/"tasks.md", root/"project.md"):
        if path.exists():
            sources.append(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    fingerprint=hashlib.sha256(b"\0".join(sources)+revision.encode()).hexdigest()
    if not task:
        return {"active":"None","status":"Inactive","state":"inactive","revision":revision,"fingerprint":fingerprint,"dependencies":"None","verification":"None"}
    task_id=_field(task,"ID","Id")
    title=_field(task,"Title","標題")
    return {"active":" ".join(x for x in (task_id,title) if x),"status":_field(task,"Status","狀態") or "Unknown","state":"active","revision":revision,"fingerprint":fingerprint,"dependencies":_field(task,"Depends on","依賴") or "None","verification":_field(task,"Verification","驗證方式") or "None"}


def sanitize_attempt(value: Any) -> dict[str,str]:
    if not isinstance(value,dict) or set(value) - CANONICAL_ATTEMPT_FIELDS or not {"phase","errorSignature"} <= set(value): raise ValueError("attempt needs only phase, errorSignature, optional hypothesis/evidence")
    result={key:str(item).strip() for key,item in value.items()}
    if any(not item or len(item)>280 or SECRET_PATTERN.search(item) for item in result.values()): raise ValueError("attempt contains empty, oversized, or secret-like data")
    return result


def read_recent_attempts(snapshot_text: str) -> list[dict[str, str]]:
    """Load only writer-produced, bounded attempt metadata; historical prose is ignored."""
    match = re.search(r"^" + re.escape(ATTEMPTS_METADATA_PREFIX) + r"(.+)$", snapshot_text, re.MULTILINE)
    if not match:
        return []
    try:
        attempts = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(attempts, list):
        return []
    valid: list[dict[str, str]] = []
    for index, item in enumerate(attempts):
        try:
            valid.append(sanitize_attempt(item))
        except ValueError as error:
            warnings.warn(f"discarded invalid recent attempt at index {index}: {error}", RuntimeWarning)
    return valid[-MAX_RECENT_ATTEMPTS:]


def read_diagnosis_evidence(snapshot_text: str) -> list[dict[str, str]]:
    match = re.search(r"^" + re.escape(DIAGNOSIS_METADATA_PREFIX) + r"(.+)$", snapshot_text, re.MULTILINE)
    if not match:
        return []
    try:
        values = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(values, list):
        return []
    return [
        {"hypothesis": str(item.get("hypothesis", "")).strip(), "evidence": str(item.get("evidence", "")).strip()}
        for item in values
        if isinstance(item, dict) and item.get("hypothesis") and item.get("evidence")
    ][-MAX_RECENT_ATTEMPTS:]


def retry_gate(attempts: list[dict[str,str]]) -> dict[str, Any]:
    clean=[sanitize_attempt(item) for item in attempts][-MAX_RECENT_ATTEMPTS:]
    signatures={}; phases={}
    for item in clean:
        signatures[item["errorSignature"]]=signatures.get(item["errorSignature"],0)+1
        phases[item["phase"]]=phases.get(item["phase"],0)+1
    diagnosis=any(count>=2 for count in signatures.values()) or any(count>=3 for count in phases.values())
    return {"mode":"diagnosis" if diagnosis else "retry","stopModifyingAndDeploying":diagnosis,"recentAttempts":clean}


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("workspace",nargs="?",default=".")
    # Deprecated compatibility flags are deliberately ignored: facts are canonical.
    for name in ("project","cycle","goal","progress","active","blocked","decisions","questions"): parser.add_argument(f"--{name}")
    parser.add_argument("--note", action="append", default=[]); parser.add_argument("--hypothesis",action="append",default=[]); parser.add_argument("--evidence",action="append",default=[]); parser.add_argument("--change",action="append",default=[])
    parser.add_argument("--attempt",action="append",default=[]); parser.add_argument("--resume",action="store_true")
    parser.add_argument("--verification-result", choices=("pass", "fail"))
    parser.add_argument("--verification-action", choices=sorted(LOW_COST_VERIFICATIONS))
    parser.add_argument("--verification-evidence")
    args=parser.parse_args(); workspace=Path(args.workspace); root=workspace.resolve()/"MissionCenter"; root.mkdir(parents=True,exist_ok=True)
    prior_text=(root/"snapshot.md").read_text(encoding="utf-8") if (root/"snapshot.md").is_file() else ""
    prior_attempts=read_recent_attempts(prior_text)
    try: gate=retry_gate(prior_attempts + [json.loads(raw) for raw in args.attempt])
    except (json.JSONDecodeError,ValueError) as error: parser.error(str(error))
    if len(args.hypothesis) != len(args.evidence): parser.error("--hypothesis and --evidence must be supplied in matching pairs")
    diagnosis_evidence=read_diagnosis_evidence(prior_text)
    new_pairs=[{"hypothesis": h.strip(), "evidence": e.strip()} for h,e in zip(args.hypothesis,args.evidence)]
    if any(not item["hypothesis"] or not item["evidence"] or SECRET_PATTERN.search(item["hypothesis"]) or SECRET_PATTERN.search(item["evidence"]) for item in new_pairs): parser.error("diagnosis hypothesis/evidence is empty or secret-like")
    unseen=[item for item in new_pairs if item not in diagnosis_evidence]
    prior_gate_match = re.search(r"^- Retry gate:\s*(\S+)\s*$", prior_text, re.MULTILINE)
    prior_gate = prior_gate_match.group(1) if prior_gate_match else None
    if prior_gate == "verification_required":
        gate={"mode":"verification_required","stopModifyingAndDeploying":True,"recentAttempts":gate["recentAttempts"]}
    if args.verification_result is not None and prior_gate != "verification_required":
        parser.error("verification result is only valid after verification_required")
    verification_record = None
    if args.verification_result is not None:
        evidence = (args.verification_evidence or "").strip()
        if not args.verification_action or not evidence or len(evidence) > 280 or SECRET_PATTERN.search(evidence):
            parser.error("verification result requires a low-cost action and bounded non-secret evidence")
        verification_record = {"action": args.verification_action, "result": args.verification_result, "evidence": evidence}
    if args.verification_result == "pass":
        gate={"mode":"retry","stopModifyingAndDeploying":False,"recentAttempts":[]}
    elif args.verification_result == "fail":
        gate={"mode":"diagnosis","stopModifyingAndDeploying":True,"recentAttempts":gate["recentAttempts"]}
    elif gate["mode"] == "diagnosis" and unseen:
        gate={"mode":"verification_required","stopModifyingAndDeploying":True,"recentAttempts":[]}
        diagnosis_evidence=(diagnosis_evidence+unseen)[-MAX_RECENT_ATTEMPTS:]
    labels=TEXT[detect_language(root)]; facts=canonical_facts(workspace); now=datetime.now().isoformat(timespec="seconds")
    state=facts.get("state", "inactive" if facts["status"] == "Inactive" else "active")
    lines=[f"# {labels['title']}","",f"- State: {state}",f"- {labels['captured_at']}: {now}",f"- {labels['active']}: {facts['active']}",f"- {labels['status']}: {facts['status']}",f"- {labels['revision']}: {facts['revision']}",f"- {labels['fingerprint']}: {facts['fingerprint']}"]
    if state == "inactive" and args.resume: lines += [f"- {labels['resume']}: {labels['inactive']}"]
    else: lines += [f"- {labels['dependencies']}: {facts['dependencies']}",f"- {labels['verification']}: {facts['verification']}",f"- Retry gate: {gate['mode']}",ATTEMPTS_METADATA_PREFIX + json.dumps(gate["recentAttempts"], ensure_ascii=False, separators=(",",":")),DIAGNOSIS_METADATA_PREFIX + json.dumps(diagnosis_evidence, ensure_ascii=False, separators=(",",":")),f"- {labels['attempts']}:"] + ([f"  - {item['phase']} | {item['errorSignature']}" for item in gate['recentAttempts']] if gate['recentAttempts'] else [f"  - {labels['none']}"])
    if verification_record is not None: lines.append(VERIFICATION_METADATA_PREFIX + json.dumps(verification_record, ensure_ascii=False, separators=(",",":")))
    for heading, values in (("Notes",args.note),("Hypotheses",args.hypothesis),("Evidence",args.evidence),("Changes",args.change)):
        if values: lines += [f"- {heading}:"]+[f"  - {value}" for value in values]
    snapshot_path = root / "snapshot.md"
    write_text_lf(snapshot_path, "\n".join(lines) + "\n")
    print(snapshot_path)
    return 0

if __name__ == "__main__": raise SystemExit(main())
