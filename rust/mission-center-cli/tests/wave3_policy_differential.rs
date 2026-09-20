//! 實際雙跑 Python oracle 與 Rust policy CLI 的最小 contract corpus。
//! Promotion 沒有 Python 對等 validator，另由 policy crate 的 Rust-only 測試覆蓋。

use std::io::Write;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

static PYTHON_INPUT_ID: AtomicU64 = AtomicU64::new(0);

fn repo_root() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}

fn rust_run(command: &str, mode: Option<&str>, input: &str, files: &[(&str, &str)]) -> i32 {
    let root = repo_root();
    let mut paths = Vec::new();
    for (name, content) in files {
        let path = std::env::temp_dir().join(format!(
            "mission-center-wave3-{}-{}",
            std::process::id(),
            name
        ));
        std::fs::write(&path, content).unwrap();
        paths.push(path);
    }
    let mut child = Command::new(env!("CARGO_BIN_EXE_mission-center"));
    child.current_dir(root).arg(command);
    if let Some(mode) = mode {
        child.arg(mode);
    }
    if command == "optimize" {
        child.args([
            "--manifest",
            paths[0].to_str().unwrap(),
            "--observations",
            paths[1].to_str().unwrap(),
        ]);
    }
    if command == "research" && mode == Some("validate") && !files.is_empty() {
        child.args(["--input", paths[0].to_str().unwrap()]);
    }
    if command == "steelman" && mode == Some("validate") && !files.is_empty() {
        child.args(["--input", paths[0].to_str().unwrap()]);
    }
    if command == "critic" && !files.is_empty() {
        child.args(["--input", paths[0].to_str().unwrap()]);
    }
    if command == "shift-loss" && !files.is_empty() {
        child.args(["--input", paths[0].to_str().unwrap()]);
    }
    if command == "compatibility" && !files.is_empty() {
        child.args(["--input", paths[0].to_str().unwrap()]);
    }
    let mut child = child
        .stdin(if files.is_empty() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::null())
        .spawn()
        .unwrap();
    if files.is_empty() {
        child
            .stdin
            .as_mut()
            .unwrap()
            .write_all(input.as_bytes())
            .unwrap();
    }
    let status = child.wait().unwrap();
    for path in paths {
        let _ = std::fs::remove_file(path);
    }
    status.code().unwrap_or(1)
}

fn python_run(module: &str, expression: &str, input: &str) -> i32 {
    let path = std::env::temp_dir().join(format!(
        "mission-center-wave3-python-{}-{}.json",
        std::process::id(),
        PYTHON_INPUT_ID.fetch_add(1, Ordering::Relaxed)
    ));
    std::fs::write(&path, input).unwrap();
    let script_dir = repo_root()
        .join("skills")
        .join("mission-center")
        .join("scripts");
    let code = format!(
        "import json,sys; sys.path.insert(0, r'{}'); from {} import *; value=json.loads(open(sys.argv[1], encoding='utf-8').read()); errors={}; raise SystemExit(1 if errors else 0)",
        script_dir.display(),
        module,
        expression
    );
    let status = Command::new("python")
        .args(["-c", &code, path.to_str().unwrap()])
        .current_dir(repo_root())
        .status()
        .unwrap();
    let _ = std::fs::remove_file(path);
    status.code().unwrap_or(1)
}

#[test]
fn critic_convergence_matches_python_through_cli() {
    use serde_json::json;
    let base = json!({
        "schemaVersion":"1.0", "route":"critic_lite", "taskId":"T1",
        "chairRecordLocator":"output/mission-center-critique/T1.json",
        "artifactManifest":[{"locator":"artifact.zip","sha256":"a".repeat(64),"laneId":"main"}],
        "snapshots":[
            {"id":"s1","revision":"r1","hash":"h1","evidenceLinks":["e1.log"]},
            {"id":"s2","parent":"s1","revision":"r2","hash":"h2","evidenceLinks":["e2.log"]},
            {"id":"s3","parent":"s2","revision":"r3","hash":"h3","evidenceLinks":["e3.log"]}
        ],
        "loopPolicy":{"mode":"converge","stopCondition":"all_findings_resolved",
            "closure":{"snapshotId":"s3","evidenceLocator":"closure.log","reviews":[
                {"seatId":"a","snapshotId":"s3","evidenceLocator":"a.log","sha256":"b".repeat(64)},
                {"seatId":"b","snapshotId":"s3","evidenceLocator":"b.log","sha256":"c".repeat(64)}
            ]}},
        "authorization":{"explicitApproval":true},
        "budgets":{"total":10,"perSeat":3,"tool":2,"wallClock":60},
        "critics":[{"id":"a"},{"id":"b"}], "outcome":"passed",
        "lanes":[{"id":"main","kind":"CLI/API/library","required":true,
            "seatId":"a","evidenceLocator":"review.log","coverageStatus":"covered"}],
        "findings":[]
    });
    for (name, expected) in [
        ("valid", 0),
        ("broken_chain", 1),
        ("stale_closure", 1),
        ("missing_ledger", 1),
        ("legacy_bound", 1),
        ("completed_v11", 0),
        ("interrupted_stale_closure", 1),
        ("interrupted_low_deferred", 0),
        ("interrupted_low_accepted", 1),
        ("legacy_non_dispatch_passed", 1),
        ("unknown_policy_field", 1),
        ("unknown_closure_field", 1),
        ("unknown_review_field", 1),
    ] {
        let mut record = base.clone();
        match name {
            "broken_chain" => record["snapshots"][2]["parent"] = json!("s1"),
            "unknown_policy_field" => record["loopPolicy"]["maxWaves"] = json!(2),
            "unknown_closure_field" => record["loopPolicy"]["closure"]["clean"] = json!(true),
            "unknown_review_field" => {
                record["loopPolicy"]["closure"]["reviews"][0]["clean"] = json!(true)
            }
            "stale_closure" => record["loopPolicy"]["closure"]["snapshotId"] = json!("s2"),
            "missing_ledger" => {
                record.as_object_mut().unwrap().remove("findings");
            }
            "legacy_bound" => {
                record.as_object_mut().unwrap().remove("loopPolicy");
            }
            "completed_v11" => {
                record["schemaVersion"] = json!("1.1");
                record["selectedRoute"] = json!("critic_lite");
                record["executionStatus"] = json!("completed");
                record["requiredByPolicy"] = json!(true);
                record.as_object_mut().unwrap().remove("route");
            }
            "interrupted_stale_closure" => {
                record["outcome"] = json!("blocked");
                record["loopPolicy"]["closure"]["snapshotId"] = json!("s1");
            }
            "interrupted_low_deferred" | "interrupted_low_accepted" => {
                record["outcome"] = json!("blocked");
                record["loopPolicy"]
                    .as_object_mut()
                    .unwrap()
                    .remove("closure");
                let disposition = if name.ends_with("accepted") {
                    "accepted"
                } else {
                    "deferred"
                };
                record["findings"] = json!([{
                    "id":"CACC-T1-quality-1234abcd-1", "severity":"Low", "category":"quality",
                    "observation":"defect", "evidenceLocator":"artifact:3", "reproOrReadPath":"read line 3",
                    "impact":"incorrect result", "confidence":"high", "unknown":"none",
                    "recommendation":"repair", "criticProposedDisposition":disposition,
                    "chairFinalDisposition":disposition,
                    "humanAcceptance":{"approverIdentity":"reviewer", "approvalTime":"2026-09-20T12:00:00Z",
                        "scope":"finding", "reason":"test", "expiry":"2026-10-20T12:00:00Z", "reopenTrigger":"new evidence"}
                }]);
            }
            "legacy_non_dispatch_passed" => {
                record = json!({"schemaVersion":"1.1", "selectedRoute":"skip", "executionStatus":"skipped",
                    "requiredByPolicy":false, "taskId":"T1", "chairRecordLocator":"output/mission-center-critique/pending.json",
                    "reason":"not applicable", "outcome":"passed"});
            }
            _ => {}
        }
        let input = record.to_string();
        let rust_status = rust_run("critic", None, &input, &[("converge.json", &input)]);
        let python_status = python_run("critic_contract", "validate_critic_record(value)", &input);
        assert_eq!(rust_status, expected, "Rust: {name}");
        assert_eq!(python_status, expected, "Python: {name}");
    }
}

#[test]
fn policy_commands_match_python_reject_or_pass_status() {
    let vectors = [
        (
            "security_secret_key",
            "security",
            None,
            r#"{"token":"abc"}"#,
            "security_scanner",
            "scan_forbidden_content(value)",
        ),
        (
            "research_missing_low_marginal",
            "research",
            Some("saturate"),
            r#"{"repeatedRootCause":false,"renamedHypothesis":false,"metricStalled":false,"budgetBurning":false,"sharedUnverifiedPremise":false}"#,
            "research_portfolio",
            "route_saturation(value)",
        ),
        (
            "critic_malformed",
            "critic",
            None,
            "{}",
            "critic_contract",
            "validate_critic_record(value)",
        ),
        (
            "shift_missing_required",
            "shift-loss",
            Some("evaluate"),
            "{}",
            "shift_loss_eval",
            "validate_shift_loss(value, None)",
        ),
        (
            "steelman_malformed",
            "steelman",
            Some("validate"),
            "{}",
            "steelman_contract",
            "validate_steelman_artifact(value, None)",
        ),
        (
            "compatibility_malformed",
            "compatibility",
            Some("validate"),
            "{}",
            "validate_codex_cli_compatibility",
            "validate_matrix(value)",
        ),
    ];
    for (name, command, mode, input, module, expression) in vectors {
        let rust = rust_run(command, mode, input, &[]);
        let python = python_run(module, expression, input);
        assert_eq!(
            rust == 0,
            python == 0,
            "{name} ({command} {mode:?}): Rust={rust}, Python={python}"
        );
    }
    let manifest = r#"{"schemaVersion":"1.0","experimentId":"e","kind":"evaluator","candidates":[{"id":"a"}],"cases":[{"id":"c"}],"metrics":[{"name":"m","direction":"maximize","unit":"ratio"}],"hardConstraints":[],"budget":{"trials":1,"tokens":1,"wallClockSeconds":1},"stoppingConditions":[{"type":"budget"}],"validation":{},"promotionState":"shadow"}"#;
    let rust = rust_run(
        "optimize",
        Some("evaluate"),
        "",
        &[
            ("manifest.json", manifest),
            (
                "observations.json",
                "{\"observations\":[{\"candidate\":\"a\",\"metrics\":{\"m\":1}}]}",
            ),
        ],
    );
    let python = python_run("optimization_core", "validate_manifest(value)", manifest);
    assert_eq!(
        rust == 0,
        python == 0,
        "optimizer: Rust={rust}, Python={python}"
    );

    let mut compatibility: serde_json::Value = serde_json::from_str(include_str!(
        "../../../skills/mission-center/references/codex-cli-plugin-compatibility-matrix.json"
    ))
    .unwrap();
    compatibility["probeRecords"][0]["recordedAt"] = serde_json::json!("2024-01-01T99:99:99+00:00");
    let compatibility_input = serde_json::to_string(&compatibility).unwrap();
    let rust = rust_run("compatibility", Some("validate"), &compatibility_input, &[]);
    let python = python_run(
        "validate_codex_cli_compatibility",
        "validate_matrix(value)",
        &compatibility_input,
    );
    assert_eq!(
        rust == 0,
        python == 0,
        "compatibility_invalid_timestamp: Rust={rust}, Python={python}"
    );
}

#[test]
fn policy_cli_unknown_and_duplicate_flags_exit_two() {
    let exe = env!("CARGO_BIN_EXE_mission-center");
    for args in [
        &["security", "--unknown"][..],
        &["security", "--input", "-", "--input", "-"][..],
    ] {
        let status = Command::new(exe).args(args).output().unwrap();
        assert_eq!(status.status.code(), Some(2), "args={args:?}");
    }
}
