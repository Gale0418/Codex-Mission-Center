use serde_json::Value;
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static WORKSPACE_SEQUENCE: AtomicU64 = AtomicU64::new(0);
const FIXTURE_DATE: &str = "2026-09-12";
const RESUME_MAX_BYTES: usize = 16 * 1024;
const RESUME_MAX_VALUE_NODES: usize = 10_000;
const TASK_HEADER: &str = concat!(
    "# Tasks\n\n",
    "| ID | Title | Type | Parent | Priority | Status | Owner | Depends on | ",
    "Next action | Verification | Estimate | Labels | Comments |\n",
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n",
);

fn task_row(id: &str, status: &str) -> String {
    format!(
        "| {id} | Fixture {id} | Task | | P1 | {status} | Codex | | Continue | local test | 1 | | fixture |\n"
    )
}

fn workspace() -> PathBuf {
    let suffix = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    let temp = std::env::temp_dir();
    #[cfg(target_os = "macos")]
    let temp = temp.canonicalize().expect("canonical temporary directory");
    let sequence = WORKSPACE_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let root = temp.join(format!(
        "mission-center-052-contract-{}-{suffix}-{sequence}",
        std::process::id()
    ));
    fs::create_dir_all(&root).expect("create fixture root");
    root
}

fn run(root: &Path, args: &[&str]) -> (Output, Value) {
    let output = Command::new(env!("CARGO_BIN_EXE_mission-center"))
        .args(args)
        .args(["--root", root.to_str().expect("utf8 root")])
        .output()
        .expect("run mission-center");
    assert!(
        output.stderr.is_empty(),
        "machine command must not emit stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload = serde_json::from_slice(&output.stdout).expect("machine JSON");
    (output, payload)
}

fn initialize(root: &Path, operation: &str) {
    let (output, payload) = run(
        root,
        &[
            "init",
            "--operation-id",
            operation,
            "--timestamp",
            "2026-09-12T08:00:00Z",
            "--language",
            "en",
        ],
    );
    assert!(output.status.success(), "init failed: {payload}");
}

fn sync(root: &Path, operation: &str) {
    let (output, payload) = run(
        root,
        &[
            "sync",
            "--operation-id",
            operation,
            "--timestamp",
            "2026-09-12T08:00:01Z",
        ],
    );
    assert!(output.status.success(), "sync failed: {payload}");
}

fn check_status<'a>(payload: &'a Value, name: &str) -> Option<&'a str> {
    payload["data"]["checks"]
        .as_array()?
        .iter()
        .find(|check| check["name"] == name)?["status"]
        .as_str()
}

fn public_packet_bytes(value: &Value, nodes: &mut usize) -> Option<usize> {
    *nodes = nodes.checked_add(1)?;
    if *nodes > RESUME_MAX_VALUE_NODES {
        return None;
    }
    match value {
        Value::String(text) => Some(text.len()),
        Value::Array(items) => {
            let mut total = 0usize;
            for item in items {
                total = total.checked_add(public_packet_bytes(item, nodes)?)?;
            }
            Some(total)
        }
        Value::Object(object) => {
            let mut total = 0usize;
            for (key, item) in object {
                *nodes = nodes.checked_add(1)?;
                if *nodes > RESUME_MAX_VALUE_NODES {
                    return None;
                }
                total = total.checked_add(key.len())?;
                total = total.checked_add(public_packet_bytes(item, nodes)?)?;
            }
            Some(total)
        }
        Value::Null => Some(4),
        Value::Bool(value) => Some(if *value { 4 } else { 5 }),
        Value::Number(number) => Some(number.to_string().len()),
    }
}

fn assert_resume_public_contract(payload: &Value) {
    let data = payload["data"].as_object().expect("resume data object");
    assert_eq!(data["schemaVersion"], "1.1", "resume data schema must be explicit");
    assert_eq!(data["route"], "resume");
    for field in [
        "sourceFresh",
        "dateFresh",
        "canonicalFallback",
        "truncated",
    ] {
        assert!(data[field].is_boolean(), "{field} must be boolean");
    }
    for field in ["staleReasons", "filesRead", "readNext"] {
        assert!(
            data[field]
                .as_array()
                .is_some_and(|items| items.iter().all(Value::is_string)),
            "{field} must be a string array"
        );
    }
    for field in ["ledgerError", "fallbackReason", "truncatedMarker"] {
        assert!(
            data[field].is_null() || data[field].is_string(),
            "{field} must be nullable string"
        );
    }
    assert!(
        matches!(data["ledgerStatus"].as_str(), Some("missing" | "ready" | "corrupt")),
        "ledgerStatus must use the documented vocabulary"
    );
    assert!(
        data["handoff"].is_null() || data["handoff"].is_object(),
        "handoff must be nullable object"
    );

    let context = data["context"].as_object().expect("resume context object");
    let included = context["includedBytes"]
        .as_object()
        .expect("includedBytes object");
    assert!(
        included.values().all(|value| value.as_u64().is_some()),
        "includedBytes must contain non-negative integers"
    );

    let content = data["content"].as_object().expect("content object");
    for field in [
        "handoff",
        "brief",
        "workingSet",
        "activeCriticalLessons",
        "snapshot",
    ] {
        assert!(content.contains_key(field), "missing content field {field}");
        assert!(
            content[field].is_null() || content[field].is_string(),
            "content.{field} must be nullable string"
        );
    }
    assert!(
        content["brief"].as_str().is_some_and(|value| !value.is_empty()),
        "brief must contain actual text"
    );
    assert!(
        content["workingSet"]
            .as_str()
            .is_some_and(|value| !value.is_empty()),
        "workingSet must contain actual text"
    );

    let mut nodes = 0usize;
    let actual = public_packet_bytes(&payload["data"], &mut nodes)
        .expect("resume packet must remain within public node bounds");
    let declared = data["bytes"].as_u64().expect("declared bytes") as usize;
    let maximum = data["maxBytes"].as_u64().expect("declared maxBytes") as usize;
    assert_eq!(
        declared, actual,
        "declared bytes must include every public JSON key/string/scalar representation"
    );
    assert!(actual <= maximum && maximum <= RESUME_MAX_BYTES);
}

#[test]
fn resume_returns_actual_context_with_one_shared_utf8_budget() {
    let root = workspace();
    initialize(&root, "resume-init");
    let mission = root.join("MissionCenter");
    fs::write(
        mission.join("tasks.md"),
        format!("{TASK_HEADER}{}", task_row("MC-052", "In Progress")),
    )
    .expect("write tasks");
    sync(&root, "resume-sync");

    // Keep the canonical file below its own read limit while forcing the resume
    // packet to exercise the shared 16 KiB fuse at UTF-8 boundaries.
    fs::write(
        mission.join("critical-lessons.md"),
        format!("# Critical Lessons\n\n## Active Lessons\n\n{}", "教訓".repeat(8_000)),
    )
    .expect("write lessons");

    let tasks_before = fs::read(mission.join("tasks.md")).expect("read tasks");
    let (output, payload) = run(&root, &["resume", "--date", FIXTURE_DATE]);
    assert!(output.status.success(), "resume failed: {payload}");
    assert_resume_public_contract(&payload);

    let data = payload["data"].as_object().expect("resume data object");
    assert!(
        data["truncated"].as_bool() == Some(true)
            || !data["readNext"].as_array().expect("readNext array").is_empty(),
        "overflow must be visible"
    );
    assert_eq!(
        fs::read(mission.join("tasks.md")).expect("read tasks after resume"),
        tasks_before,
        "resume must remain read-only"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn resume_fails_closed_on_corrupt_ledger_without_calling_it_ready() {
    let root = workspace();
    initialize(&root, "resume-corrupt-init");
    let mission = root.join("MissionCenter");
    fs::write(
        mission.join("tasks.md"),
        format!("{TASK_HEADER}{}", task_row("MC-052", "In Progress")),
    )
    .expect("write tasks");
    sync(&root, "resume-corrupt-sync");
    fs::write(mission.join("execution-ledger.jsonl"), "{not-json}\n").expect("write ledger");
    let tasks_before = fs::read(mission.join("tasks.md")).expect("read tasks");

    let (output, payload) = run(&root, &["resume", "--date", FIXTURE_DATE]);
    assert!(output.status.success(), "safe corrupt-ledger resume should return a packet: {payload}");
    assert_resume_public_contract(&payload);
    let data = payload["data"].as_object().expect("resume data object");
    assert_eq!(data["ledgerStatus"], "corrupt");
    assert!(data["ledgerError"].is_string(), "corruption must be explicit");
    assert!(data["handoff"].is_null(), "corrupt ledger cannot yield trusted handoff");
    assert_eq!(data["canonicalFallback"], true);
    assert!(data["fallbackReason"].is_string());
    assert_eq!(
        fs::read(mission.join("tasks.md")).expect("read tasks after corrupt resume"),
        tasks_before,
        "resume must remain read-only when ledger is corrupt"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn reconcile_rejects_corrupt_ledger_and_empty_evidence_directory() {
    let root = workspace();
    initialize(&root, "reconcile-init");
    let mission = root.join("MissionCenter");
    fs::write(
        mission.join("tasks.md"),
        format!("{TASK_HEADER}{}", task_row("MC-052", "In Progress")),
    )
    .expect("write tasks");
    sync(&root, "reconcile-sync");
    fs::write(mission.join("execution-ledger.jsonl"), "{not-json}\n").expect("write ledger");
    fs::create_dir_all(root.join("output/mission-center-evidence")).expect("create evidence dir");
    let tasks_before = fs::read(mission.join("tasks.md")).expect("read tasks");

    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert!(
        matches!(
            check_status(&payload, "ledger"),
            Some("error" | "corrupt" | "invalid" | "fail" | "failed")
        ),
        "malformed ledger must not pass: {payload}"
    );
    assert_ne!(
        check_status(&payload, "evidence_envelope"),
        Some("pass"),
        "empty directory is not verified evidence"
    );
    assert_eq!(
        fs::read(mission.join("tasks.md")).expect("read tasks after reconcile"),
        tasks_before,
        "reconcile must remain read-only"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn doctor_passport_error_is_order_independent() {
    let root = workspace();
    initialize(&root, "doctor-init");
    let mission = root.join("MissionCenter");
    let passports = root.join("output/mission-center-passports");
    fs::create_dir_all(&passports).expect("create passports");
    fs::write(
        passports.join("MC-001.json"),
        r#"{"schemaVersion":"incorrect"}"#,
    )
    .expect("write corrupt passport");

    let first = task_row("MC-001", "Done");
    let second = task_row("MC-002", "Done");
    for rows in [format!("{first}{second}"), format!("{second}{first}")] {
        fs::write(mission.join("tasks.md"), format!("{TASK_HEADER}{rows}"))
            .expect("write ordered tasks");
        let (output, payload) = run(&root, &["doctor"]);
        assert_eq!(
            output.status.code(),
            Some(1),
            "invalid passport must fail regardless of row order: {payload}"
        );
        assert_eq!(check_status(&payload, "completion_passport"), Some("error"));
    }
    let _ = fs::remove_dir_all(root);
}
