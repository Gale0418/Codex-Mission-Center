//! 實際雙跑 Python oracle 與 Rust policy CLI 的最小 contract corpus。
//! Promotion 沒有 Python 對等 validator，另由 policy crate 的 Rust-only 測試覆蓋。

use std::io::Write;
use std::process::{Command, Stdio};

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
        "mission-center-wave3-python-{}.json",
        std::process::id()
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
