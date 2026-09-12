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
        Value::Number(number) => {
            if number.is_i64() || number.is_u64() {
                Some(number.to_string().len())
            } else {
                None
            }
        }
    }
}

fn assert_resume_public_contract(payload: &Value) {
    let data = payload["data"].as_object().expect("resume data object");
    assert_eq!(
        data["schemaVersion"], "1.1",
        "resume data schema must be explicit"
    );
    assert_eq!(data["route"], "resume");
    for field in ["sourceFresh", "dateFresh", "canonicalFallback", "truncated"] {
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
        matches!(
            data["ledgerStatus"].as_str(),
            Some("missing" | "ready" | "corrupt")
        ),
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
        content["brief"]
            .as_str()
            .is_some_and(|value| !value.is_empty()),
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
        .expect("resume packet must contain only bounded supported public scalar types");
    let declared = data["bytes"].as_u64().expect("declared bytes") as usize;
    let maximum = data["maxBytes"].as_u64().expect("declared maxBytes") as usize;
    assert_eq!(
        declared, actual,
        "declared bytes must include every public JSON key/string/scalar representation"
    );
    assert!(actual <= maximum && maximum <= RESUME_MAX_BYTES);
}

#[test]
fn resume_budget_metric_rejects_floating_point_metadata() {
    let packet = serde_json::json!({
        "schemaVersion": "1.1",
        "route": "resume",
        "handoff": {"ratio": 1.5}
    });
    let mut nodes = 0usize;
    assert_eq!(public_packet_bytes(&packet, &mut nodes), None);
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
    let (pulse_output, pulse_payload) = run(
        &root,
        &[
            "pulse",
            "--task-id",
            "MC-052",
            "--operation-id",
            "resume-pulse",
            "--pulse-id",
            "resume-pulse-1",
            "--phase",
            "execute",
            "--outcome",
            "continue",
            "--next-action",
            "run native checks",
            "--recorded-at",
            "2026-09-12T08:00:02Z",
        ],
    );
    assert!(
        pulse_output.status.success(),
        "pulse failed: {pulse_payload}"
    );

    // Keep the canonical file below its own read limit while forcing the resume
    // packet to exercise the shared 16 KiB fuse at UTF-8 boundaries.
    fs::write(
        mission.join("critical-lessons.md"),
        format!(
            "# Critical Lessons\n\n## Active Lessons\n\n{}",
            "教訓".repeat(8_000)
        ),
    )
    .expect("write lessons");

    let tasks_before = fs::read(mission.join("tasks.md")).expect("read tasks");
    let (output, payload) = run(&root, &["resume", "--date", FIXTURE_DATE]);
    assert!(output.status.success(), "resume failed: {payload}");
    assert_resume_public_contract(&payload);

    let data = payload["data"].as_object().expect("resume data object");
    assert_eq!(data["ledgerStatus"], "ready");
    assert!(
        data["filesRead"]
            .as_array()
            .expect("filesRead")
            .iter()
            .any(|item| item == "MissionCenter/execution-ledger.jsonl")
    );
    assert!(
        data["truncated"].as_bool() == Some(true)
            || !data["readNext"]
                .as_array()
                .expect("readNext array")
                .is_empty(),
        "overflow must be visible"
    );
    if data["truncated"] == true {
        assert_eq!(data["truncatedMarker"], "[TRUNCATED]");
        let content = data["content"].as_object().expect("content");
        let included = data["context"]["includedBytes"]
            .as_object()
            .expect("included bytes");
        let truncated_sections = ["brief", "workingSet", "activeCriticalLessons", "snapshot"];
        for section in truncated_sections {
            if let Some(value) = content[section].as_str()
                && value.ends_with("[TRUNCATED]")
            {
                assert_eq!(included[section], value.len());
            }
        }
    }
    assert_eq!(
        fs::read(mission.join("tasks.md")).expect("read tasks after resume"),
        tasks_before,
        "resume must remain read-only"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn resume_only_includes_active_critical_lessons_and_marks_snapshot_errors() {
    let root = workspace();
    initialize(&root, "resume-lessons-init");
    let mission = root.join("MissionCenter");
    fs::write(
        mission.join("critical-lessons.md"),
        "# Critical Lessons\n\n## Active Lessons\n\nkeep this\n\n## Resolved Index\n\nDO NOT INCLUDE THIS\n",
    )
    .expect("write lessons");
    sync(&root, "resume-lessons-sync");
    fs::write(mission.join("snapshot.md"), [0xff, 0xfe]).expect("write invalid snapshot");
    let (output, payload) = run(&root, &["resume", "--date", FIXTURE_DATE]);
    assert!(output.status.success(), "resume failed: {payload}");
    let data = payload["data"].as_object().expect("resume data");
    let lessons = data["content"]["activeCriticalLessons"]
        .as_str()
        .expect("active lessons");
    assert!(lessons.contains("keep this"));
    assert!(!lessons.contains("DO NOT INCLUDE THIS"));
    assert_eq!(data["canonicalFallback"], true);
    assert!(
        data["readNext"]
            .as_array()
            .expect("readNext")
            .iter()
            .any(|item| item == "snapshot.md")
    );
    fs::write(
        mission.join("critical-lessons.md"),
        "# Critical Lessons\n\nNo heading means the whole file remains visible.\n",
    )
    .expect("write headingless lessons");
    let (output, payload) = run(&root, &["resume", "--date", FIXTURE_DATE]);
    assert!(output.status.success(), "resume failed: {payload}");
    assert!(payload["data"]["content"]["activeCriticalLessons"]
        .as_str()
        .is_some_and(|value| value.contains("No heading means the whole file remains visible.")));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn reconcile_checks_progress_content_and_daily_date_states() {
    let root = workspace();
    initialize(&root, "reconcile-derived-init");
    let mission = root.join("MissionCenter");
    fs::write(
        mission.join("tasks.md"),
        format!("{TASK_HEADER}{}", task_row("MC-052", "In Progress")),
    )
    .expect("write tasks");
    sync(&root, "reconcile-derived-sync");
    fs::remove_file(mission.join("daily-log.md")).expect("remove daily log");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "derived_date"), Some("unknown"));
    sync(&root, "reconcile-derived-sync-refresh");
    let progress = fs::read_to_string(mission.join("progress.md")).expect("read progress");
    let spaced_labels = progress
        .replace("- Active tasks:", "-    Active tasks:")
        .replace("- Blocked by:", "-      Blocked by:")
        .replace("- Current status:", "-   Current status:")
        .replace("- Progress bar:", "-    Progress bar:")
        .replace("- Next update:", "-  Next update:");
    fs::write(mission.join("progress.md"), spaced_labels).expect("write spaced progress labels");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "progress"), Some("pass"));
    let progress = fs::read_to_string(mission.join("progress.md")).expect("read progress");
    fs::write(
        mission.join("progress.md"),
        progress.replace("MC-052", "MC-999"),
    )
    .expect("write stale progress");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "progress"), Some("conflict"));

    fs::remove_file(mission.join("daily-log.md")).expect("remove daily log");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "derived_date"), Some("unknown"));
    fs::write(mission.join("daily-log.md"), [0xff, 0xfe]).expect("write invalid daily log");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "derived_date"), Some("corrupt"));
    fs::write(
        mission.join("daily-log.md"),
        "# Daily Log\n\n- Last organized: 1970-01-01\n",
    )
    .expect("write stale daily log");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "derived_date"), Some("stale"));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn reconcile_rejects_mismatched_evidence_supersedes_and_bad_schema_fields() {
    let root = workspace();
    initialize(&root, "reconcile-evidence-init");
    let mission = root.join("MissionCenter");
    fs::write(
        mission.join("tasks.md"),
        format!("{TASK_HEADER}{}", task_row("MC-052", "In Progress")),
    )
    .expect("write tasks");
    sync(&root, "reconcile-evidence-sync");
    let evidence = root.join("output/mission-center-evidence");
    fs::create_dir_all(&evidence).expect("create evidence");
    let scope = "MissionCenter/tasks.md";
    let task_bytes = fs::read(mission.join("tasks.md")).expect("read tasks");
    let digest = mission_center_publish::scope_digest_files(&[(scope, task_bytes.as_slice())]);
    let old = serde_json::json!({
        "schemaVersion":"1.0","artifactType":"evidence-envelope",
        "envelopeId":"old-1","taskId":"MC-999","checkId":"smoke",
        "scope":[scope],"scopeDigest":digest.clone(),"result":"pass","status":"superseded",
        "artifactLocators":[scope],"recordedAt":"2026-09-12T08:00:00Z"
    });
    let current = serde_json::json!({
        "schemaVersion":"1.0","artifactType":"evidence-envelope",
        "envelopeId":"current-1","taskId":"MC-052","checkId":"smoke",
        "scope":[scope],"scopeDigest":digest.clone(),"result":"pass","status":"current",
        "artifactLocators":[scope],"recordedAt":"2026-09-12T08:00:01Z","supersedes":"old-1"
    });
    fs::write(evidence.join("old.json"), old.to_string()).expect("write old envelope");
    fs::write(evidence.join("current.json"), current.to_string()).expect("write current envelope");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(
        check_status(&payload, "evidence_envelope"),
        Some("conflict")
    );
    let mut non_string_supersedes = current;
    non_string_supersedes["supersedes"] = serde_json::json!(17);
    fs::remove_file(evidence.join("old.json")).expect("remove superseded envelope");
    fs::write(
        evidence.join("current.json"),
        non_string_supersedes.to_string(),
    )
    .expect("write non-string supersedes envelope");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(
        check_status(&payload, "evidence_envelope"),
        Some("corrupt"),
        "present non-string supersedes must fail closed"
    );
    let valid = serde_json::json!({
        "schemaVersion":"1.0","artifactType":"evidence-envelope",
        "envelopeId":"valid-1","taskId":"MC-052","checkId":"smoke",
        "scope":[scope],"scopeDigest":digest.clone(),"result":"pass","status":"current",
        "artifactLocators":[scope],"recordedAt":"2026-09-12T08:00:01Z"
    });
    fs::write(evidence.join("current.json"), valid.to_string()).expect("write valid envelope");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "evidence_envelope"), Some("pass"));
    let mut whitespace_recorded_at = valid;
    whitespace_recorded_at["recordedAt"] = serde_json::json!(" 2026-09-12T08:00:01Z");
    fs::write(
        evidence.join("current.json"),
        whitespace_recorded_at.to_string(),
    )
    .expect("write whitespace recordedAt envelope");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "evidence_envelope"), Some("corrupt"));
    let mut whitespace_digest = serde_json::json!({
        "schemaVersion":"1.0","artifactType":"evidence-envelope",
        "envelopeId":"valid-2","taskId":"MC-052","checkId":"smoke",
        "scope":[scope],"scopeDigest":format!(" {digest} "),"result":"pass","status":"current",
        "artifactLocators":[scope],"recordedAt":"2026-09-12T08:00:01Z"
    });
    whitespace_digest["scopeDigest"] = serde_json::json!(format!(" {digest} "));
    fs::write(evidence.join("current.json"), whitespace_digest.to_string())
        .expect("write whitespace scopeDigest envelope");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "evidence_envelope"), Some("corrupt"));
    let colon_locator = serde_json::json!({
        "schemaVersion":"1.0","artifactType":"evidence-envelope",
        "envelopeId":"colon-1","taskId":"MC-052","checkId":"smoke",
        "scope":[scope],"scopeDigest":digest.clone(),"result":"pass","status":"current",
        "artifactLocators":["foo:bar"],"recordedAt":"2026-09-12T08:00:01Z"
    });
    fs::write(evidence.join("current.json"), colon_locator.to_string())
        .expect("write colon locator envelope");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(
        check_status(&payload, "evidence_envelope"),
        Some("corrupt"),
        "colon/ADS-like locator must be rejected"
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn reconcile_rejects_blocked_task_in_active_progress_set() {
    let root = workspace();
    initialize(&root, "reconcile-progress-blocked-init");
    let mission = root.join("MissionCenter");
    fs::write(
        mission.join("tasks.md"),
        format!(
            "{TASK_HEADER}{}{}",
            task_row("MC-052", "In Progress"),
            task_row("MC-053", "Blocked")
        ),
    )
    .expect("write tasks");
    sync(&root, "reconcile-progress-blocked-sync");
    let progress = fs::read_to_string(mission.join("progress.md")).expect("read progress");
    let poisoned = progress.replace(
        "  - MC-052 Fixture MC-052 (In Progress)",
        "  - MC-052 Fixture MC-052 (In Progress)\n  - MC-053 leaked into active",
    );
    fs::write(mission.join("progress.md"), poisoned).expect("write poisoned progress");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "progress"), Some("conflict"));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn reconcile_overall_uses_monotonic_check_max_without_unknown_date_override() {
    let root = workspace();
    initialize(&root, "reconcile-overall-monotonic-init");
    let mission = root.join("MissionCenter");
    for name in [
        "progress.md",
        "closeout.md",
        "brief.md",
        "working-set.md",
        "focus.md",
        "daily-log.md",
        "execution-ledger.jsonl",
    ] {
        let _ = fs::remove_file(mission.join(name));
    }
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "derived_date"), Some("unknown"));
    assert_ne!(payload["data"]["status"], "stale");
    assert_eq!(payload["data"]["status"], "unknown");
    let _ = fs::remove_dir_all(root);
}

#[test]
fn reconcile_fails_closed_on_evidence_directory_limits() {
    let root = workspace();
    initialize(&root, "reconcile-evidence-limit-init");
    let mission = root.join("MissionCenter");
    fs::write(
        mission.join("tasks.md"),
        format!("{TASK_HEADER}{}", task_row("MC-052", "In Progress")),
    )
    .expect("write tasks");
    sync(&root, "reconcile-evidence-limit-sync");
    let evidence = root.join("output/mission-center-evidence");
    fs::create_dir_all(&evidence).expect("create evidence");
    let scope = "MissionCenter/tasks.md";
    let task_bytes = fs::read(mission.join("tasks.md")).expect("read tasks");
    let digest = mission_center_publish::scope_digest_files(&[(scope, task_bytes.as_slice())]);
    for index in 0..128 {
        let check_id = format!("limit-{index}");
        let old = serde_json::json!({
            "schemaVersion":"1.0","artifactType":"evidence-envelope",
            "envelopeId":format!("old-{index}"),"taskId":"MC-052","checkId":check_id,
            "scope":[scope],"scopeDigest":digest.clone(),"result":"pass","status":"superseded",
            "artifactLocators":[scope],"recordedAt":"2026-09-12T08:00:00Z"
        });
        let current = serde_json::json!({
            "schemaVersion":"1.0","artifactType":"evidence-envelope",
            "envelopeId":format!("current-{index}"),"taskId":"MC-052","checkId":format!("limit-{index}"),
            "scope":[scope],"scopeDigest":digest.clone(),"result":"pass","status":"current",
            "artifactLocators":[scope],"recordedAt":"2026-09-12T08:00:01Z",
            "supersedes":format!("old-{index}")
        });
        fs::write(evidence.join(format!("old-{index}.json")), old.to_string())
            .expect("write valid superseded envelope");
        fs::write(
            evidence.join(format!("current-{index}.json")),
            current.to_string(),
        )
        .expect("write valid current envelope");
    }
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(
        check_status(&payload, "evidence_envelope"),
        Some("pass"),
        "256 schema-valid evidence files must be accepted"
    );
    fs::write(
        evidence.join("overflow.json"),
        serde_json::json!({
            "schemaVersion":"1.0","artifactType":"evidence-envelope",
            "envelopeId":"overflow","taskId":"MC-052","checkId":"overflow",
            "scope":[scope],"scopeDigest":digest,"result":"pass","status":"current",
            "artifactLocators":[scope],"recordedAt":"2026-09-12T08:00:02Z"
        })
        .to_string(),
    )
    .expect("write overflow envelope");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "evidence_envelope"), Some("corrupt"));
    let message = payload["data"]["checks"]
        .as_array()
        .and_then(|checks| {
            checks
                .iter()
                .find(|check| check["name"] == "evidence_envelope")
        })
        .and_then(|check| check["message"].as_str())
        .expect("evidence limit message");
    assert!(message.contains("exceeds 256 entries"));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn reconcile_evidence_budget_caches_duplicate_nested_locators() {
    let root = workspace();
    initialize(&root, "reconcile-evidence-nested-init");
    let mission = root.join("MissionCenter");
    fs::write(
        mission.join("tasks.md"),
        format!("{TASK_HEADER}{}", task_row("MC-052", "In Progress")),
    )
    .expect("write tasks");
    sync(&root, "reconcile-evidence-nested-sync");
    let evidence = root.join("output/mission-center-evidence");
    let nested = root.join("nested-evidence");
    fs::create_dir_all(&evidence).expect("create evidence");
    fs::create_dir_all(&nested).expect("create nested evidence");
    let nested_bytes = vec![b'x'; 64 * 1024];
    for index in 0..64 {
        let locator = format!("nested-evidence/{index}.bin");
        fs::write(root.join(&locator), &nested_bytes).expect("write nested evidence");
        let digest = mission_center_publish::scope_digest_files(&[(&locator, &nested_bytes)]);
        let envelope = serde_json::json!({
            "schemaVersion":"1.0","artifactType":"evidence-envelope",
            "envelopeId":format!("nested-{index}"),"taskId":"MC-052",
            "checkId":format!("nested-{index}"),"scope":[locator],"scopeDigest":digest,
            "result":"pass","status":"current","artifactLocators":[format!("nested-evidence/{index}.bin")],
            "recordedAt":"2026-09-12T08:00:00Z"
        });
        fs::write(
            evidence.join(format!("nested-{index}.json")),
            envelope.to_string(),
        )
        .expect("write nested envelope");
    }
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(
        check_status(&payload, "evidence_envelope"),
        Some("pass"),
        "duplicate scope/artifact locators must be charged once via cache"
    );
    for index in 64..129 {
        let locator = format!("nested-evidence/{index}.bin");
        fs::write(root.join(&locator), &nested_bytes).expect("write nested evidence");
        let digest = mission_center_publish::scope_digest_files(&[(&locator, &nested_bytes)]);
        let envelope = serde_json::json!({
            "schemaVersion":"1.0","artifactType":"evidence-envelope",
            "envelopeId":format!("nested-{index}"),"taskId":"MC-052",
            "checkId":format!("nested-{index}"),"scope":[locator],"scopeDigest":digest,
            "result":"pass","status":"current","artifactLocators":[format!("nested-evidence/{index}.bin")],
            "recordedAt":"2026-09-12T08:00:00Z"
        });
        fs::write(
            evidence.join(format!("nested-{index}.json")),
            envelope.to_string(),
        )
        .expect("write nested envelope");
    }
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "evidence_envelope"), Some("corrupt"));
    let message = payload["data"]["checks"]
        .as_array()
        .and_then(|checks| {
            checks
                .iter()
                .find(|check| check["name"] == "evidence_envelope")
        })
        .and_then(|check| check["message"].as_str())
        .expect("nested aggregate limit message");
    assert!(message.contains("aggregate exceeds"));
    let _ = fs::remove_dir_all(root);
}

#[test]
fn reconcile_accepts_legacy_localized_closeout_and_checks_task_contradictions() {
    let root = workspace();
    initialize(&root, "reconcile-legacy-closeout-init");
    let mission = root.join("MissionCenter");
    fs::write(
        mission.join("tasks.md"),
        format!(
            "{TASK_HEADER}{}{}",
            task_row("MC-052", "Done"),
            task_row("MC-053", "Ready")
        ),
    )
    .expect("write tasks");
    sync(&root, "reconcile-legacy-closeout-sync");
    let legacy =
        "# 收尾\n\n- 摘要: 舊版 fixture\n-    已完成: MC-052X, MC-052\n-      未完成: MC-053\n";
    fs::write(mission.join("closeout.md"), legacy).expect("write legacy closeout");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "closeout"), Some("pass"));

    fs::write(
        mission.join("closeout.md"),
        "# 收尾\n\n- 摘要: 缺少未完成欄位\n- 已完成: MC-052\n",
    )
    .expect("write incomplete closeout");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "closeout"), Some("unknown"));

    fs::write(
        mission.join("closeout.md"),
        "# 收尾\n\n- 摘要: 矛盾\n- 已完成: MC-052\n- 未完成: MC-052, MC-053\n",
    )
    .expect("write contradictory closeout");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "closeout"), Some("conflict"));
    let _ = fs::remove_dir_all(root);
}

#[cfg(unix)]
#[test]
fn reconcile_rejects_evidence_directory_symlink() {
    use std::os::unix::fs::symlink;

    let root = workspace();
    initialize(&root, "reconcile-evidence-symlink-init");
    let output = root.join("output");
    fs::create_dir_all(&output).expect("create output");
    let target = workspace();
    fs::create_dir_all(target.join("evidence")).expect("create target");
    symlink(
        target.join("evidence"),
        output.join("mission-center-evidence"),
    )
    .expect("create evidence symlink");
    let (_output, payload) = run(&root, &["reconcile", "--date", FIXTURE_DATE]);
    assert_eq!(check_status(&payload, "evidence_envelope"), Some("corrupt"));
    let _ = fs::remove_dir_all(root);
    let _ = fs::remove_dir_all(target);
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
    assert!(
        output.status.success(),
        "safe corrupt-ledger resume should return a packet: {payload}"
    );
    assert_resume_public_contract(&payload);
    let data = payload["data"].as_object().expect("resume data object");
    assert_eq!(data["ledgerStatus"], "corrupt");
    assert!(
        data["ledgerError"].is_string(),
        "corruption must be explicit"
    );
    assert!(
        data["handoff"].is_null(),
        "corrupt ledger cannot yield trusted handoff"
    );
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
