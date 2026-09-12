use mission_center_core::{Task, TaskStatus, canonicalize_hash_bytes, sha256_digest};
use mission_center_policy::validate_tasks;
use mission_center_publish::{
    FrozenFile, FrozenPackage, MutationAction, Platform, unsupported_mutation_receipt,
};
use mission_center_runtime::{
    BrowserOpener, EventEnvelope, FrozenHudAssets, HudLauncher, HudServerConfig, LaunchStatus,
    MAX_EVENT_BYTES, MAX_REPLAY_BYTES, MAX_STDIN_BYTES, ProviderCapabilities, RuntimeReducer,
    RuntimeState, SourceStatus, StdioTransport, probe_loopback_health, replay_jsonl_with_allowlist,
    stdio_command, validate_health_payload,
};
use mission_center_workspace::{
    DAILY_LOG_MAX_BYTES, MissionWorkspace, SyncOptions, read_bounded_file, read_bounded_utf8,
};
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
#[cfg(unix)]
use std::os::unix::process::CommandExt;
#[cfg(windows)]
use std::os::windows::fs::MetadataExt;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::{
    collections::HashSet,
    env,
    fmt::Write as _,
    fs::{self, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, ExitCode, Stdio},
    sync::Arc,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const SCHEMA: &str = "1.0";
const MAX_OUTPUT_BYTES: usize = 512 * 1024;
const MAX_JSON_INPUT_BYTES: usize = 8 * 1024 * 1024;
const CLI_ENVELOPE_SCHEMA: &str = include_str!("../schemas/cli-envelope.schema.json");
const RESUME_MAX_BYTES: usize = 16 * 1024;
const EVIDENCE_MAX_BYTES: u64 = 64 * 1024;
const RESUME_TRUNCATED_MARKER: &str = "[TRUNCATED]";
const MAX_EVIDENCE_FILES: usize = 256;
const MAX_EVIDENCE_TOTAL_BYTES: u64 = 8 * 1024 * 1024;
const MAX_EVIDENCE_ERRORS: usize = 32;

// These are deliberately compile-time inclusions.  HUD serving must remain
// independent of the caller's cwd and of mutable output files, especially on
// Windows where the runtime rejects path-based asset loading.
const HUD_VISUAL_SUMMARY: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../skills/mission-center/assets/visual-hub/visual-summary.html"
));
const HUD_VISUAL_STATE: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../skills/mission-center/assets/visual-hub/visual-state.json"
));
const HUD_MISSION_BRIDGE_BACKGROUND: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../skills/mission-center/assets/visual-hub/mission-bridge-background.webp"
));
const HUD_MISSION_BRIDGE_BACKGROUND_META: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../skills/mission-center/assets/visual-hub/mission-bridge-background.webp.json"
));
const HUD_MISSION_FLEET_BRIDGE_BACKGROUND: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../skills/mission-center/assets/visual-hub/mission-fleet-bridge-background.webp"
));
const HUD_MISSION_FLEET_BRIDGE_BACKGROUND_META: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../skills/mission-center/assets/visual-hub/mission-fleet-bridge-background.webp.json"
));
const HUD_MISSION_STARFIELD: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../skills/mission-center/assets/visual-hub/mission-starfield.webp"
));
const HUD_MISSION_STARFIELD_META: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../skills/mission-center/assets/visual-hub/mission-starfield.webp.json"
));

const EMBEDDED_HUD_FILES: &[(&str, &[u8])] = &[
    ("visual-summary.html", HUD_VISUAL_SUMMARY),
    ("visual-state.json", HUD_VISUAL_STATE),
    (
        "mission-bridge-background.webp",
        HUD_MISSION_BRIDGE_BACKGROUND,
    ),
    (
        "mission-bridge-background.webp.json",
        HUD_MISSION_BRIDGE_BACKGROUND_META,
    ),
    (
        "mission-fleet-bridge-background.webp",
        HUD_MISSION_FLEET_BRIDGE_BACKGROUND,
    ),
    (
        "mission-fleet-bridge-background.webp.json",
        HUD_MISSION_FLEET_BRIDGE_BACKGROUND_META,
    ),
    ("mission-starfield.webp", HUD_MISSION_STARFIELD),
    ("mission-starfield.webp.json", HUD_MISSION_STARFIELD_META),
];

fn escape(value: &str) -> String {
    let mut result = String::with_capacity(value.len());
    for character in value.chars() {
        match character {
            '\\' => result.push_str("\\\\"),
            '"' => result.push_str("\\\""),
            '\n' => result.push_str("\\n"),
            '\r' => result.push_str("\\r"),
            '\t' => result.push_str("\\t"),
            '\u{08}' => result.push_str("\\b"),
            '\u{0c}' => result.push_str("\\f"),
            character if character <= '\u{1f}' => {
                let _ = write!(result, "\\u{:04x}", character as u32);
            }
            character => result.push(character),
        }
    }
    result
}

fn json_quote(value: &str) -> String {
    format!("\"{}\"", escape(value))
}
fn remediation(code: &str) -> &'static str {
    match code {
        "argument_error" => "請修正 command、flag 或參數後重試。",
        "unsupported" => "此操作目前僅提供唯讀驗證；請使用受控原生介面。",
        "stdin_too_large" | "replay_byte_limit" | "event_too_large" => {
            "請縮小 stdin payload 或拆分 replay 後重試。"
        }
        "timeout" => "請在 timeout-ms 期限內送出一個合法 HTTP request 後重試。",
        "invalid_json" | "invalid_manifest" | "schema_error" => {
            "請提供符合版本化契約的 JSON 後重試。"
        }
        "asset_unavailable" => "CLI 未內嵌 HUD assets；請由具備 frozen bundle 的 host 執行。",
        "privacy_violation" => "請移除 prompt、reasoning、secret 或個資後重試。",
        _ => "請修正輸入後重試。",
    }
}

fn stable_error_message(code: &str) -> &'static str {
    match code {
        "argument_error" => "參數或指令格式無效。",
        "unsupported" => "此操作目前不支援。",
        "invalid_json" => "輸入 JSON 無效。",
        "validation_failed" => "輸入驗證失敗。",
        "invalid_utf8" => "輸入文字編碼無效。",
        "schema_error" => "資料不符合版本化契約。",
        "privacy_violation" => "輸入含有不允許的敏感內容。",
        "stdin_too_large" | "replay_byte_limit" | "event_too_large" => "輸入超過大小上限。",
        "timeout" => "操作逾時。",
        "asset_unavailable" => "HUD 資產目前不可用。",
        "invalid_manifest" => "套件 manifest 無效。",
        "verification_failed" => "驗證未通過。",
        "write_rejected" => "寫入操作已拒絕。",
        "filesystem_input_forbidden" => "此操作不接受檔案輸入。",
        _ => "指令執行失敗。",
    }
}

fn envelope_value(command: &str, status: &str, data: Value, error_code: Option<&str>) -> Value {
    let mut object = serde_json::Map::new();
    object.insert("schemaVersion".to_owned(), json!(SCHEMA));
    object.insert("command".to_owned(), json!(command));
    object.insert("status".to_owned(), json!(status));
    object.insert("data".to_owned(), data);
    if let Some(code) = error_code {
        object.insert("errorCode".to_owned(), json!(code));
        object.insert(
            "error".to_owned(),
            json!({
                "code":code,
                "message":stable_error_message(code),
                "remediation":remediation(code)
            }),
        );
    }
    Value::Object(object)
}

fn public_command(command: &str) -> &str {
    match command {
        "init" | "sync" | "status" | "resume" | "reconcile" | "doctor" | "runtime" | "publish"
        | "install" | "hud" | "normalize" | "verify" | "snapshot" | "pulse" | "handoff"
        | "closeout" | "project-map" | "claim" | "release-claim" | "transition" | "research"
        | "optimize" | "steelman" | "critic" | "shift-loss" | "security" | "compatibility"
        | "hook" | "help" => command,
        _ => "unknown",
    }
}

const PUBLIC_COMMANDS: &[&str] = &[
    "init",
    "sync",
    "status",
    "resume",
    "reconcile",
    "doctor",
    "runtime",
    "publish",
    "install",
    "hud",
    "normalize",
    "verify",
    "snapshot",
    "pulse",
    "handoff",
    "closeout",
    "project-map",
    "claim",
    "release-claim",
    "transition",
    "research",
    "optimize",
    "steelman",
    "critic",
    "shift-loss",
    "security",
    "compatibility",
    "hook",
];

fn command_usage(command: &str) -> Option<String> {
    if !PUBLIC_COMMANDS.contains(&command) {
        return None;
    }
    Some(match command {
        "sync" => "mission-center sync --root <path> --operation-id <id> --timestamp <RFC3339> [--project <name>] [--cycle <name>] [--goal <text>] [--labels <csv>] [--milestone <text>] [--rewrite-summaries]".to_owned(),
        "status" | "resume" | "reconcile" => {
            format!("mission-center {command} --root <path> [--date <YYYY-MM-DD>]")
        }
        _ => format!("mission-center {command} [options]"),
    })
}

fn help_envelope(command: &str, target: Option<&str>) -> Result<String, String> {
    let usage = match target {
        Some(target) => {
            command_usage(target).ok_or_else(|| format!("unknown command: {target}"))?
        }
        None => "mission-center <command> [options]".to_owned(),
    };
    Ok(value_envelope(
        command,
        "ok",
        json!({
            "usage": usage,
            "target": target,
            "commands": PUBLIC_COMMANDS,
            "help": "mission-center help <command> or mission-center <command> --help"
        }),
    ))
}

fn envelope(command: &str, status: &str, body: &str) -> String {
    let data = serde_json::from_str(body).unwrap_or_else(|_| json!({}));
    serde_json::to_string(&envelope_value(command, status, data, None)).unwrap_or_else(|_| {
        // This branch is unreachable for serde_json::Value, but keep a fixed
        // protocol response if a future serializer ever fails.
        error("cli", "schema_error", "")
    })
}

fn error(command: &str, code: &str, _message: &str) -> String {
    serde_json::to_string(&envelope_value(
        public_command(command),
        "error",
        Value::Null,
        Some(code),
    ))
    .unwrap_or_else(|_| "{\"schemaVersion\":\"1.0\",\"command\":\"cli\",\"status\":\"error\",\"data\":null,\"errorCode\":\"schema_error\",\"error\":{\"code\":\"schema_error\",\"message\":\"資料不符合版本化契約。\",\"remediation\":\"請提供符合版本化契約的 JSON 後重試。\"}}".to_owned())
}

fn error_with_data(command: &str, code: &str, _message: &str, data: Value) -> String {
    serde_json::to_string(&envelope_value(
        public_command(command),
        "error",
        data,
        Some(code),
    ))
    .unwrap_or_else(|_| error(command, "schema_error", ""))
}

fn error_code(message: &str) -> &'static str {
    let lower = message.to_ascii_lowercase();
    if let Some((code, _)) = lower.split_once(':') {
        const STABLE: &[(&str, &str)] = &[
            ("argument_error", "argument_error"),
            ("invalid_json", "invalid_json"),
            ("validation_failed", "validation_failed"),
            ("invalid_utf8", "invalid_utf8"),
            ("schema_error", "schema_error"),
            ("event_too_large", "event_too_large"),
            ("replay_event_limit", "replay_event_limit"),
            ("replay_byte_limit", "replay_byte_limit"),
            ("json_depth_limit", "json_depth_limit"),
            ("json_node_limit", "json_node_limit"),
            ("field_too_long", "field_too_long"),
            ("item_limit", "item_limit"),
            ("duplicate_event", "duplicate_event"),
            ("out_of_order", "out_of_order"),
            ("privacy_violation", "privacy_violation"),
            ("invalid_task_link", "invalid_task_link"),
            ("unknown_task", "unknown_task"),
            ("agent_limit", "agent_limit"),
            ("stale", "stale"),
            ("io_error", "io_error"),
            ("unsupported_transport", "unsupported_transport"),
            ("invalid_host", "invalid_host"),
            ("port_bind_failed", "port_bind_failed"),
            ("health_mismatch", "health_mismatch"),
            ("reuse_rejected", "reuse_rejected"),
            ("version_mismatch", "version_mismatch"),
            ("hook_input_too_large", "hook_input_too_large"),
            ("path_traversal", "path_traversal"),
            ("asset_unavailable", "asset_unavailable"),
            ("unsafe_path", "unsafe_path"),
            ("shutdown_failed", "shutdown_failed"),
            ("browser_unavailable", "browser_unavailable"),
            ("invalid_manifest", "invalid_manifest"),
            ("missing_binary", "missing_binary"),
            ("wrong_platform", "wrong_platform"),
            ("corrupt_checksum", "corrupt_checksum"),
            ("non_executable", "non_executable"),
            ("python_runtime", "python_runtime"),
            ("transaction_conflict", "transaction_conflict"),
            ("transaction_replay", "transaction_replay"),
            ("transaction_corrupt", "transaction_corrupt"),
            ("io", "io"),
            ("not_found", "not_found"),
            ("verification_failed", "verification_failed"),
            ("unsupported", "unsupported"),
            ("stdin_too_large", "stdin_too_large"),
            ("filesystem_input_forbidden", "filesystem_input_forbidden"),
            ("timeout", "timeout"),
        ];
        if let Some((_, stable)) = STABLE.iter().find(|(known, _)| *known == code) {
            return stable;
        }
    }
    if lower.contains("stdin") && lower.contains("large") {
        return "stdin_too_large";
    }
    if lower.contains("filesystem") && lower.contains("input") {
        return "filesystem_input_forbidden";
    }
    if lower.contains("completion passport") || lower.contains("mission-center-passports") {
        return "verification_failed";
    }
    if lower.contains("unknown argument")
        || lower.contains("unknown subcommand")
        || lower.contains("missing required argument")
        || lower.contains("missing value for")
        || lower.contains("repeated argument")
        || lower.contains("boolean flag cannot")
        || lower.contains("mutually exclusive")
    {
        "argument_error"
    } else if lower.contains("incomplete escape") {
        "malformed_row"
    } else if lower.contains("has ") && lower.contains(" cells; expected") {
        "wrong_cell_count"
    } else if lower.contains("does not contain") {
        "missing_table"
    } else if lower.contains("invalid table header") {
        "invalid_header"
    } else if lower.contains("invalid table separator") {
        "invalid_separator"
    } else if lower.contains("unsupported task status") {
        "unsupported_status"
    } else if lower.contains("transition from") {
        "invalid_transition"
    } else if lower.contains("unknown task") {
        "unknown_task"
    } else if lower.contains("completion passport") || lower.contains("mission-center-passports") {
        "verification_failed"
    } else if lower.contains("unknown command") {
        "argument_error"
    } else if lower.contains("write") && (lower.contains("disabled") || lower.contains("rejected"))
    {
        "write_rejected"
    } else if lower.contains("operation") && lower.contains("conflict") {
        "operation_conflict"
    } else if lower.contains("already started") {
        "operation_started"
    } else if lower.contains("recovery unknown") {
        "recovery_unknown"
    } else if lower.contains("claim") {
        "claim_rejected"
    } else {
        "command_error"
    }
}

fn validate_policy_flags(command: &str, args: &[String]) -> Result<(), String> {
    let mode = args.first().map(String::as_str);
    let allowed: &[&str] = match (command, mode) {
        ("research", Some("saturate")) => &[
            "--input",
            "--signals",
            "--hard-constraint-failure",
            "--budget-exhausted",
        ],
        ("research", _) => &["--input", "--portfolio"],
        ("optimize", Some("evaluate" | "shadow")) => &[
            "--manifest",
            "--observations",
            "--output",
            "--write",
            "--commit",
        ],
        ("optimize", _) => &["--input", "--profile"],
        ("steelman", Some("route")) => &["--task-id", "--risk", "--deterministic"],
        ("steelman", _) => &["--input", "--artifact"],
        ("critic", _) => &["--input", "--record"],
        ("shift-loss", Some("compare")) => &["--baseline", "--new", "--current"],
        ("shift-loss", _) => &["--input", "--result"],
        ("security", _) => &["--input"],
        ("compatibility", _) => &["--input", "--matrix"],
        _ => return Ok(()),
    };
    let value_flags: HashSet<&str> = allowed
        .iter()
        .copied()
        .filter(|flag| {
            !matches!(
                *flag,
                "--hard-constraint-failure"
                    | "--budget-exhausted"
                    | "--write"
                    | "--commit"
                    | "--deterministic"
            )
        })
        .collect();
    let mut seen = HashSet::new();
    let mut index = if matches!(command, "research" | "optimize" | "steelman" | "shift-loss")
        && mode.is_some_and(|value| !value.starts_with('-'))
    {
        1
    } else {
        0
    };
    while index < args.len() {
        let token = &args[index];
        if !token.starts_with('-') {
            index += 1;
            continue;
        }
        let name = token.split('=').next().unwrap_or(token).to_owned();
        if !allowed.contains(&name.as_str()) {
            return Err(format!("unknown argument: {name}"));
        }
        if !seen.insert(name.clone()) {
            return Err(format!("repeated argument: {name}"));
        }
        if token.contains('=') && !value_flags.contains(name.as_str()) {
            return Err(format!("boolean flag cannot take a value: {token}"));
        }
        if value_flags.contains(name.as_str()) {
            if token.contains('=') {
                if token
                    .split_once('=')
                    .is_none_or(|(_, value)| value.is_empty())
                {
                    return Err(format!("missing value for {name}"));
                }
            } else if args
                .get(index + 1)
                .is_none_or(|v| v.starts_with('-') && v != "-")
            {
                return Err(format!("missing value for {name}"));
            } else {
                index += 1;
            }
        }
        index += 1;
    }
    if matches!(command, "research" | "optimize" | "steelman" | "shift-loss") && mode.is_none() {
        return Err("missing required subcommand".to_owned());
    }
    Ok(())
}

fn value_envelope(command: &str, status: &str, data: Value) -> String {
    let error_code = (status == "error").then_some("validation_failed");
    let mut output = envelope_value(command, status, data, error_code);
    // `route` predates the versioned envelope and remains an explicitly
    // allowed compatibility field for the Python oracle. It is never copied
    // from input and therefore cannot inject arbitrary root fields.
    if let Some(object) = output.as_object_mut() {
        object.insert("route".to_owned(), json!(command));
    }
    serde_json::to_string(&output).unwrap_or_else(|_| error(command, "schema_error", ""))
}

fn validation_envelope(command: &str, valid: bool, errors: Vec<String>) -> String {
    if valid {
        value_envelope(command, "pass", json!({"valid":true,"errors":[]}))
    } else {
        let mut out = serde_json::from_str::<Value>(&value_envelope(
            command,
            "error",
            json!({"valid":false,"errors":errors}),
        ))
        .unwrap_or_else(|_| json!({}));
        if let Some(map) = out.as_object_mut() {
            map.insert(
                "errorCode".to_owned(),
                Value::String("validation_failed".to_owned()),
            );
            map.insert(
                "error".to_owned(),
                json!({
                    "code":"validation_failed",
                    "message":"輸入驗證失敗",
                    "remediation":remediation("validation_failed")
                }),
            );
        }
        out.to_string()
    }
}

fn json_file_or_stdin(path: Option<&str>) -> Result<Value, String> {
    let bytes = if let Some(path) = path {
        if path == "-" {
            read_stdin_bounded(MAX_JSON_INPUT_BYTES)?
        } else {
            let metadata =
                std::fs::metadata(path).map_err(|_| "io_error: 無法讀取 JSON 輸入".to_owned())?;
            if metadata.len() > MAX_JSON_INPUT_BYTES as u64 {
                return Err("stdin_too_large: JSON 輸入超過大小上限".to_owned());
            }
            std::fs::read(path).map_err(|_| "io_error: 無法讀取 JSON 輸入".to_owned())?
        }
    } else {
        read_stdin_bounded(MAX_JSON_INPUT_BYTES)?
    };
    let value = serde_json::from_slice::<StrictJson>(&bytes).map_err(|error| {
        let message = error.to_string();
        if message.contains("duplicate JSON key") {
            "schema_error: JSON 不得包含重複欄位".to_owned()
        } else {
            "invalid_json: JSON 輸入無效".to_owned()
        }
    })?;
    Ok(value.0)
}

fn input_path(args: &[String], names: &[&str]) -> Option<String> {
    for name in names {
        if let Some(value) = optional_arg(args, name) {
            return Some(value);
        }
    }
    args.iter()
        .find(|arg| {
            !arg.starts_with('-')
                && ![
                    "validate", "saturate", "profile", "route", "evaluate", "compare", "scan",
                ]
                .contains(&arg.as_str())
        })
        .cloned()
}

fn read_stdin_bounded(limit: usize) -> Result<Vec<u8>, String> {
    let mut bytes = Vec::new();
    std::io::stdin()
        .take(limit as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| format!("io_error: stdin read failed: {error}"))?;
    if bytes.len() > limit {
        return Err(format!("stdin_too_large: stdin 超過 {} bytes 上限", limit));
    }
    Ok(bytes)
}

fn strict_new_flags(args: &[String], values: &[&str], booleans: &[&str]) -> Result<(), String> {
    let mut seen = HashSet::new();
    let allowed = values
        .iter()
        .chain(booleans.iter())
        .copied()
        .collect::<HashSet<_>>();
    let boolean_set = booleans.iter().copied().collect::<HashSet<_>>();
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if !token.starts_with('-') {
            return Err(format!("unknown argument: {token}"));
        }
        let name = token.split('=').next().unwrap_or(token);
        if !allowed.contains(name) {
            return Err(format!("unknown argument: {name}"));
        }
        if !seen.insert(name.to_owned()) {
            return Err(format!("repeated argument: {name}"));
        }
        if boolean_set.contains(name) {
            if token.contains('=') {
                return Err(format!("boolean flag cannot take a value: {token}"));
            }
        } else if let Some((_, value)) = token.split_once('=') {
            if value.is_empty() {
                return Err(format!("missing value for {name}"));
            }
        } else {
            let Some(value) = args.get(index + 1) else {
                return Err(format!("missing value for {name}"));
            };
            if value.starts_with('-') && value != "-" {
                return Err(format!("missing value for {name}"));
            }
            index += 1;
        }
        index += 1;
    }
    Ok(())
}

fn flag_value(args: &[String], name: &str) -> Option<String> {
    args.iter().enumerate().find_map(|(index, token)| {
        if token == name {
            args.get(index + 1).cloned()
        } else {
            token
                .strip_prefix(&format!("{name}="))
                .map(ToOwned::to_owned)
        }
    })
}

fn runtime_updated_at(args: &[String]) -> Result<String, String> {
    Ok(flag_value(args, "--updated-at").unwrap_or_else(|| "1970-01-01T00:00:00Z".to_owned()))
}

fn runtime_state_value(state: RuntimeState) -> Result<Value, String> {
    serde_json::to_value(state)
        .map_err(|error| format!("schema_error: runtime state encode failed: {error}"))
}

fn runtime_run(mode: &str, args: &[String]) -> Result<String, String> {
    match mode {
        "capability" => {
            strict_new_flags(args, &[], &[])?;
            Ok(value_envelope(
                "runtime",
                "ok",
                json!({
                    "mode":"capability",
                    "schemaVersion": mission_center_runtime::SCHEMA_VERSION,
                    "transports":{"stdio":true,"replay":true,"state":true,"health":true,"websocket":false},
                    "capabilities":{"approve":false,"reject":false,"focus":false},
                    "persistent":false
                }),
            ))
        }
        "stdio" => {
            strict_new_flags(args, &["--executable", "--updated-at"], &[])?;
            if let Some(executable) = flag_value(args, "--executable") {
                let command = stdio_command(&executable).map_err(|error| error.to_string())?;
                return Ok(value_envelope(
                    "runtime",
                    "ok",
                    json!({
                        "mode":"stdio", "persistent":false, "argv":command
                    }),
                ));
            }
            let bytes = read_stdin_bounded(MAX_REPLAY_BYTES)?;
            let mut transport = StdioTransport::new(std::io::Cursor::new(bytes), Vec::<u8>::new());
            let mut reducer = RuntimeReducer::new();
            loop {
                match transport.recv() {
                    Ok(frame) => {
                        let event = EventEnvelope::from_json_bytes(&frame)
                            .map_err(|error| error.to_string())?;
                        reducer.apply(event).map_err(|error| error.to_string())?;
                    }
                    Err(error) if error.code_str() == "io_error" => break,
                    Err(error) => return Err(error.to_string()),
                }
            }
            let state = reducer
                .runtime_state(&runtime_updated_at(args)?)
                .map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "runtime",
                "ok",
                json!({
                    "mode":"stdio", "persistent":false, "state":runtime_state_value(state)?
                }),
            ))
        }
        "replay" => {
            strict_new_flags(args, &["--updated-at"], &[])?;
            let bytes = read_stdin_bounded(MAX_REPLAY_BYTES)?;
            let reducer = replay_jsonl_with_allowlist(&bytes, &HashSet::new())
                .map_err(|error| error.to_string())?;
            let state = reducer
                .runtime_state(&runtime_updated_at(args)?)
                .map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "runtime",
                "ok",
                json!({
                    "mode":"replay", "persistent":false, "state":runtime_state_value(state)?
                }),
            ))
        }
        "state" => {
            strict_new_flags(args, &["--updated-at"], &[])?;
            let bytes = read_stdin_bounded(16 * 1024 * 1024)?;
            let state_value = serde_json::from_slice::<StrictJson>(&bytes)
                .map_err(|_| "invalid_json: runtime state JSON 無效".to_owned())?
                .0;
            let state: RuntimeState = serde_json::from_value(state_value)
                .map_err(|_| "schema_error: runtime state 欄位無效".to_owned())?;
            let state = state.validate().map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "runtime",
                "ok",
                json!({
                    "mode":"state", "persistent":false, "state":runtime_state_value(state)?
                }),
            ))
        }
        "health" => {
            strict_new_flags(
                args,
                &[
                    "--workspace-fingerprint",
                    "--nonce",
                    "--asset-fingerprint",
                    "--version",
                ],
                &[],
            )?;
            let workspace = flag_value(args, "--workspace-fingerprint")
                .ok_or_else(|| "missing required argument: --workspace-fingerprint".to_owned())?;
            let nonce = flag_value(args, "--nonce")
                .ok_or_else(|| "missing required argument: --nonce".to_owned())?;
            let assets = flag_value(args, "--asset-fingerprint")
                .ok_or_else(|| "missing required argument: --asset-fingerprint".to_owned())?;
            let version = flag_value(args, "--version")
                .ok_or_else(|| "missing required argument: --version".to_owned())?;
            let bytes = read_stdin_bounded(MAX_EVENT_BYTES)?;
            let payload: Value = serde_json::from_slice::<StrictJson>(&bytes)
                .map(|value| value.0)
                .map_err(|error| format!("invalid_json: health payload JSON 無效: {error}"))?;
            if let Some(object) = payload.as_object() {
                for key in object.keys() {
                    if !matches!(
                        key.as_str(),
                        "service"
                            | "status"
                            | "version"
                            | "workspaceFingerprint"
                            | "sessionNonce"
                            | "hudAssetFingerprint"
                    ) {
                        return Err(format!("schema_error: health payload 欄位不支援: {key}"));
                    }
                }
            }
            validate_health_payload(&payload, &workspace, &nonce, &assets, &version)
                .map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "runtime",
                "ok",
                json!({
                    "mode":"health", "valid":true, "persistent":false
                }),
            ))
        }
        _ => Err(format!("unknown subcommand: {mode}")),
    }
}

fn decode_base64(value: &str) -> Result<Vec<u8>, String> {
    let bytes = value.as_bytes();
    if !bytes.len().is_multiple_of(4) {
        return Err("invalid_manifest: bytesBase64 必須是有效 base64".to_owned());
    }
    let mut output = Vec::with_capacity(bytes.len() / 4 * 3);
    let decode = |byte: u8| -> Option<u8> {
        match byte {
            b'A'..=b'Z' => Some(byte - b'A'),
            b'a'..=b'z' => Some(byte - b'a' + 26),
            b'0'..=b'9' => Some(byte - b'0' + 52),
            b'+' => Some(62),
            b'/' => Some(63),
            _ => None,
        }
    };
    let (chunks, remainder) = bytes.as_chunks::<4>();
    debug_assert!(remainder.is_empty());
    for (index, chunk) in chunks.iter().enumerate() {
        let last = index == chunks.len() - 1;
        let a = decode(chunk[0]).ok_or_else(|| "invalid_manifest: bytesBase64 無效".to_owned())?;
        let b = decode(chunk[1]).ok_or_else(|| "invalid_manifest: bytesBase64 無效".to_owned())?;
        let c = if chunk[2] == b'=' {
            0
        } else {
            decode(chunk[2]).ok_or_else(|| "invalid_manifest: bytesBase64 無效".to_owned())?
        };
        let d = if chunk[3] == b'=' {
            0
        } else {
            decode(chunk[3]).ok_or_else(|| "invalid_manifest: bytesBase64 無效".to_owned())?
        };
        if (!last && (chunk[2] == b'=' || chunk[3] == b'='))
            || (chunk[2] == b'=' && chunk[3] != b'=')
        {
            return Err("invalid_manifest: bytesBase64 padding 無效".to_owned());
        }
        if (chunk[2] == b'=' && (b & 0x0f) != 0) || (chunk[3] == b'=' && (c & 0x03) != 0) {
            return Err("invalid_manifest: bytesBase64 含非 canonical unused bits".to_owned());
        }
        output.push((a << 2) | (b >> 4));
        if chunk[2] != b'=' {
            output.push((b << 4) | (c >> 2));
        }
        if chunk[3] != b'=' {
            output.push((c << 6) | d);
        }
    }
    Ok(output)
}

struct StrictJson(Value);
struct StrictJsonVisitor;

impl<'de> Visitor<'de> for StrictJsonVisitor {
    type Value = StrictJson;
    fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("JSON value")
    }
    fn visit_unit<E>(self) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(StrictJson(Value::Null))
    }
    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(StrictJson(Value::Bool(value)))
    }
    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(StrictJson(Value::Number(value.into())))
    }
    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(StrictJson(Value::Number(value.into())))
    }
    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        serde_json::Number::from_f64(value)
            .map(Value::Number)
            .map(StrictJson)
            .ok_or_else(|| E::custom("non-finite number"))
    }
    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(StrictJson(Value::String(value.to_owned())))
    }
    fn visit_string<E>(self, value: String) -> Result<Self::Value, E>
    where
        E: de::Error,
    {
        Ok(StrictJson(Value::String(value)))
    }
    fn visit_seq<A>(self, mut seq: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::new();
        while let Some(value) = seq.next_element::<StrictJson>()? {
            values.push(value.0);
        }
        Ok(StrictJson(Value::Array(values)))
    }
    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut values = serde_json::Map::new();
        while let Some(key) = map.next_key::<String>()? {
            if values.contains_key(&key) {
                return Err(de::Error::custom(format!("duplicate JSON key: {key}")));
            }
            let value = map.next_value::<StrictJson>()?;
            values.insert(key, value.0);
        }
        Ok(StrictJson(Value::Object(values)))
    }
}

impl<'de> Deserialize<'de> for StrictJson {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_any(StrictJsonVisitor)
    }
}

fn frozen_package_from_stdin() -> Result<FrozenPackage, String> {
    let bytes = read_stdin_bounded(256 * 1024 * 1024)?;
    let value: Value = match serde_json::from_slice::<StrictJson>(&bytes) {
        Ok(value) => value.0,
        Err(error) => {
            let message = error.to_string();
            if message.contains("duplicate JSON key") {
                return Err(format!("invalid_manifest: {message}"));
            }
            let encoded = std::str::from_utf8(&bytes)
                .map_err(|_| "invalid_manifest: frozen package 必須是 JSON 或 base64".to_owned())?;
            let decoded = decode_base64(encoded)?;
            serde_json::from_slice::<StrictJson>(&decoded)
                .map(|value| value.0)
                .map_err(|_| "invalid_manifest: base64 內容不是 frozen package JSON".to_owned())?
        }
    };
    let object = value
        .as_object()
        .ok_or_else(|| "invalid_manifest: frozen package 必須是 object".to_owned())?;
    for key in object.keys() {
        if !matches!(key.as_str(), "format" | "schemaVersion" | "files") {
            return Err(format!(
                "invalid_manifest: frozen package 欄位不支援: {key}"
            ));
        }
    }
    if object.get("format").and_then(Value::as_str) != Some("frozen-package-v1") {
        return Err(
            "invalid_manifest: frozen package 必須指定 format=frozen-package-v1".to_owned(),
        );
    }
    if object.get("schemaVersion").and_then(Value::as_str) != Some("1.0") {
        return Err("invalid_manifest: frozen package 必須指定 schemaVersion=1.0".to_owned());
    }
    let files = object
        .get("files")
        .and_then(Value::as_array)
        .ok_or_else(|| "invalid_manifest: frozen package 缺少 files".to_owned())?;
    let mut frozen = Vec::with_capacity(files.len());
    for item in files {
        let file = item
            .as_object()
            .ok_or_else(|| "invalid_manifest: file 必須是 object".to_owned())?;
        for key in file.keys() {
            if !matches!(key.as_str(), "path" | "contentBase64" | "executable") {
                return Err(format!("invalid_manifest: file 欄位不支援: {key}"));
            }
        }
        let path = file
            .get("path")
            .and_then(Value::as_str)
            .ok_or_else(|| "invalid_manifest: file 缺少 path".to_owned())?;
        let bytes = if let Some(encoded) = file.get("contentBase64") {
            decode_base64(
                encoded
                    .as_str()
                    .ok_or_else(|| "invalid_manifest: base64 必須是字串".to_owned())?,
            )?
        } else {
            return Err("invalid_manifest: file 缺少 contentBase64".to_owned());
        };
        let executable = file
            .get("executable")
            .and_then(Value::as_bool)
            .ok_or_else(|| "invalid_manifest: file 缺少 executable boolean".to_owned())?;
        frozen.push(FrozenFile::new(path, bytes, executable));
    }
    FrozenPackage::new(frozen).map_err(|error| error.to_string())
}

fn parse_platform(value: Option<String>) -> Result<Platform, String> {
    match value.as_deref() {
        Some("windows-x86_64") => Ok(Platform::WindowsX86_64),
        Some("linux-x86_64") => Ok(Platform::LinuxX86_64),
        Some("macos-x86_64") => Ok(Platform::MacosX86_64),
        Some("macos-aarch64") => Ok(Platform::MacosAarch64),
        Some(_) => Err("invalid_manifest: platform 不支援".to_owned()),
        None => {
            Platform::host().ok_or_else(|| "invalid_manifest: 無法判定 host platform".to_owned())
        }
    }
}

fn publish_verify(args: &[String]) -> Result<String, String> {
    strict_new_flags(
        args,
        &["--platform", "--version", "--input", "--package"],
        &[],
    )?;
    for name in ["--input", "--package"] {
        if let Some(value) = flag_value(args, name)
            && value != "-"
        {
            return Err(
                "filesystem_input_forbidden: publish verify 僅接受 stdin，不讀取 path".to_owned(),
            );
        }
    }
    let version = flag_value(args, "--version")
        .ok_or_else(|| "missing required argument: --version".to_owned())?;
    let platform = parse_platform(flag_value(args, "--platform"))?;
    let package = frozen_package_from_stdin()?;
    let report = package
        .verify(platform, &version)
        .map_err(|error| error.to_string())?;
    Ok(value_envelope(
        "publish",
        "pass",
        json!({
            "verified":true,
            "digest":report.digest,
            "manifest":report.manifest,
            "artifact":report.artifact
        }),
    ))
}

fn publish_select(args: &[String]) -> Result<String, String> {
    strict_new_flags(
        args,
        &["--platform", "--version", "--input", "--package"],
        &[],
    )?;
    for name in ["--input", "--package"] {
        if let Some(value) = flag_value(args, name)
            && value != "-"
        {
            return Err(
                "filesystem_input_forbidden: publish select 僅接受 stdin，不讀取 path".to_owned(),
            );
        }
    }
    let version = flag_value(args, "--version")
        .ok_or_else(|| "missing required argument: --version".to_owned())?;
    let platform = parse_platform(flag_value(args, "--platform"))?;
    let package = frozen_package_from_stdin()?;
    let artifact = package
        .select_artifact(platform, &version)
        .map_err(|error| error.to_string())?;
    Ok(value_envelope(
        "publish",
        "pass",
        json!({"selected":true,"platform":platform,"os":platform.os(),"arch":platform.arch(),"artifact":artifact}),
    ))
}

fn publish_stage(command: &str, args: &[String]) -> Result<String, String> {
    strict_new_flags(
        args,
        &[
            "--operation-id",
            "--platform",
            "--version",
            "--input",
            "--package",
        ],
        &[],
    )?;
    for name in ["--input", "--package"] {
        if let Some(value) = flag_value(args, name)
            && value != "-"
        {
            return Err("filesystem_input_forbidden: staging 僅接受 stdin，不讀取 path".to_owned());
        }
    }
    let operation_id = flag_value(args, "--operation-id")
        .ok_or_else(|| "missing required argument: --operation-id".to_owned())?;
    let version = flag_value(args, "--version")
        .ok_or_else(|| "missing required argument: --version".to_owned())?;
    let platform = parse_platform(flag_value(args, "--platform"))?;
    let package = frozen_package_from_stdin()?;
    let receipt = match command {
        "publish" => {
            mission_center_publish::stage_publish(&package, &operation_id, platform, &version)
        }
        "install" => {
            mission_center_publish::stage_install(&package, &operation_id, platform, &version)
        }
        _ => unreachable!("staging command is publish or install"),
    }
    .map_err(|error| error.to_string())?;
    Ok(value_envelope(
        command,
        "ok",
        json!({"staged":true,"receipt":receipt}),
    ))
}

fn publish_run(mode: &str, args: &[String]) -> Result<String, String> {
    if mode == "verify" {
        return publish_verify(args);
    }
    if mode == "stage" {
        return publish_stage("publish", args);
    }
    if mode == "select" {
        return publish_select(args);
    }
    if mode != "publish" && mode != "install" {
        return Err(format!("unknown subcommand: {mode}"));
    }
    strict_new_flags(args, &["--operation-id"], &[])?;
    let operation_id = flag_value(args, "--operation-id")
        .ok_or_else(|| "missing required argument: --operation-id".to_owned())?;
    let action = if mode == "publish" {
        MutationAction::Publish
    } else {
        MutationAction::Install
    };
    let receipt = unsupported_mutation_receipt(action, operation_id.clone())
        .map_err(|error| error.to_string())?;
    Ok(error_with_data(
        mode,
        "unsupported",
        "mutation unsupported offline",
        json!({"operationId":operation_id,"written":false,"mutationSupported":false,"receipt":receipt}),
    ))
}

fn native_install_run(mode: &str, args: &[String]) -> Result<String, String> {
    match mode {
        "apply" => {
            strict_new_flags(
                args,
                &[
                    "--package",
                    "--destination",
                    "--operation-id",
                    "--platform",
                    "--version",
                ],
                &[],
            )?;
            let package = required_arg(args, "--package")?;
            let destination = required_arg(args, "--destination")?;
            let operation_id = required_arg(args, "--operation-id")?;
            let version = required_arg(args, "--version")?;
            let platform = parse_platform(flag_value(args, "--platform"))?;
            let receipt = mission_center_publish::native_install_package(
                Path::new(&package),
                &[PathBuf::from(destination)],
                &operation_id,
                platform,
                &version,
            )
            .map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "install",
                "ok",
                json!({"installed":true,"receipt":receipt,"mutationSupported":true}),
            ))
        }
        "rollback" => {
            strict_new_flags(args, &["--receipt"], &[])?;
            let receipt = required_arg(args, "--receipt")?;
            let restored = mission_center_publish::native_rollback_transaction(Path::new(&receipt))
                .map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "install",
                "ok",
                json!({"rolledBack":true,"receipt":restored,"mutationSupported":true}),
            ))
        }
        _ => Err(format!("unknown subcommand: {mode}")),
    }
}

fn native_registration_run(mode: &str, args: &[String]) -> Result<String, String> {
    match mode {
        "apply" => {
            strict_new_flags(
                args,
                &[
                    "--plugin-root",
                    "--marketplace-root",
                    "--operation-id",
                    "--version",
                ],
                &[],
            )?;
            let plugin_root = required_arg(args, "--plugin-root")?;
            let marketplace_root = required_arg(args, "--marketplace-root")?;
            let operation_id = required_arg(args, "--operation-id")?;
            let version = required_arg(args, "--version")?;
            let receipt = mission_center_publish::native_register_marketplace(
                Path::new(&plugin_root),
                Path::new(&marketplace_root),
                &operation_id,
                &version,
            )
            .map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "install",
                "ok",
                json!({"registered":true,"receipt":receipt,"mutationSupported":true}),
            ))
        }
        "rollback" => {
            strict_new_flags(args, &["--receipt"], &[])?;
            let receipt = required_arg(args, "--receipt")?;
            let restored =
                mission_center_publish::native_rollback_registration(Path::new(&receipt))
                    .map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "install",
                "ok",
                json!({"rolledBack":true,"receipt":restored,"mutationSupported":true}),
            ))
        }
        "reconcile" => {
            strict_new_flags(args, &["--marketplace-root"], &[])?;
            let marketplace_root = required_arg(args, "--marketplace-root")?;
            let receipts = mission_center_publish::native_reconcile_registrations(Path::new(
                &marketplace_root,
            ))
            .map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "install",
                "ok",
                json!({"reconciled":true,"receipts":receipts,"mutationSupported":true}),
            ))
        }
        _ => Err(format!("unknown registration subcommand: {mode}")),
    }
}

fn native_publish_run(mode: &str, args: &[String]) -> Result<String, String> {
    match mode {
        "apply" => {
            strict_new_flags(
                args,
                &[
                    "--package",
                    "--destination",
                    "--operation-id",
                    "--platform",
                    "--version",
                ],
                &[],
            )?;
            let package = required_arg(args, "--package")?;
            let destination = required_arg(args, "--destination")?;
            let operation_id = required_arg(args, "--operation-id")?;
            let version = required_arg(args, "--version")?;
            let platform = parse_platform(flag_value(args, "--platform"))?;
            let receipt = mission_center_publish::native_publish_package(
                Path::new(&package),
                &[PathBuf::from(destination)],
                &operation_id,
                platform,
                &version,
            )
            .map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "publish",
                "ok",
                json!({"published":true,"receipt":receipt,"mutationSupported":true}),
            ))
        }
        "rollback" => {
            strict_new_flags(args, &["--receipt"], &[])?;
            let receipt = required_arg(args, "--receipt")?;
            let restored = mission_center_publish::native_rollback_transaction(Path::new(&receipt))
                .map_err(|error| error.to_string())?;
            Ok(value_envelope(
                "publish",
                "ok",
                json!({"rolledBack":true,"receipt":restored,"mutationSupported":true}),
            ))
        }
        _ => Err(format!("unknown subcommand: {mode}")),
    }
}

fn native_reconcile_run(command: &str, root: &Path, args: &[String]) -> Result<String, String> {
    strict_new_flags(args, &[], &[])?;
    let receipts = mission_center_publish::native_reconcile_transactions(root)
        .map_err(|error| error.to_string())?;
    Ok(value_envelope(
        command,
        "ok",
        json!({"reconciled":true,"receipts":receipts,"mutationSupported":true}),
    ))
}

fn policy_run(command: &str, root: &Path, args: &[String]) -> Result<String, String> {
    validate_policy_flags(command, args)?;
    match command {
        "research" => {
            let mode = args.first().map(String::as_str).unwrap_or("validate");
            if mode == "saturate" {
                let input = json_file_or_stdin(
                    input_path(&args[1..], ["--input", "--signals"].as_slice()).as_deref(),
                )?;
                let data = mission_center_policy::route_saturation(
                    &input,
                    args.iter().any(|v| v == "--hard-constraint-failure"),
                    args.iter().any(|v| v == "--budget-exhausted"),
                )?;
                return Ok(value_envelope(command, "ok", data));
            }
            if mode != "validate" {
                return Err(format!("unknown research subcommand: {mode}"));
            }
            let input = json_file_or_stdin(
                input_path(&args[1..], ["--input", "--portfolio"].as_slice()).as_deref(),
            )?;
            let errors = mission_center_policy::validate_research_portfolio(&input, Some(root));
            Ok(validation_envelope(command, errors.is_empty(), errors))
        }
        "optimize" => {
            let mode = args.first().map(String::as_str).unwrap_or("profile");
            if mode == "profile" {
                let input = json_file_or_stdin(
                    input_path(&args[1..], ["--input", "--profile"].as_slice()).as_deref(),
                )?;
                return Ok(value_envelope(
                    command,
                    "ok",
                    mission_center_policy::build_optimization_profile(&input),
                ));
            }
            if mode == "route" {
                let input = json_file_or_stdin(
                    input_path(&args[1..], ["--input", "--profile"].as_slice()).as_deref(),
                )?;
                return Ok(value_envelope(
                    command,
                    "ok",
                    mission_center_policy::route_optimization_profile(&input),
                ));
            }
            if mode == "evaluate" || mode == "shadow" {
                if args.iter().any(|v| v == "--write" || v == "--commit") {
                    return Err("write rejected: shadow evaluation is read-only".to_owned());
                }
                if let Some(output) = optional_arg(args, "--output")
                    && (output == "-"
                        || output.contains("..")
                        || output.contains(":\\")
                        || output.starts_with('/'))
                {
                    return Err(
                        "write rejected: shadow output must be a designated relative path"
                            .to_owned(),
                    );
                }
                // The caller receives a deterministic design only; no implicit filesystem write.
                let manifest = json_file_or_stdin(optional_arg(args, "--manifest").as_deref())?;
                let observations =
                    json_file_or_stdin(optional_arg(args, "--observations").as_deref())?;
                let mut result =
                    mission_center_policy::evaluate_optimization(&manifest, &observations);
                if let Some(output) = optional_arg(args, "--output") {
                    let experiment = result
                        .get("experimentId")
                        .and_then(Value::as_str)
                        .unwrap_or("unknown")
                        .to_owned();
                    if let Some(map) = result.as_object_mut() {
                        map.insert(
                            "shadowOutput".to_owned(),
                            json!({"path":output,"operationId":format!("shadow-{experiment}")}),
                        );
                    }
                }
                let status = if result.get("status").and_then(Value::as_str) == Some("invalid") {
                    "error"
                } else {
                    "ok"
                };
                return Ok(value_envelope(command, status, result));
            }
            Err(format!("unknown optimize subcommand: {mode}"))
        }
        "steelman" => {
            let mode = args.first().map(String::as_str).unwrap_or("validate");
            if mode == "route" {
                let task = required_arg(args, "--task-id").or_else(|_| {
                    args.get(1)
                        .cloned()
                        .ok_or_else(|| "missing required argument: --task-id".to_owned())
                })?;
                let risk = optional_arg(args, "--risk").unwrap_or_else(|| "medium".to_owned());
                return Ok(value_envelope(
                    command,
                    "ok",
                    mission_center_policy::route_steelman(
                        root,
                        &task,
                        &risk,
                        args.iter().any(|v| v == "--deterministic"),
                    )?,
                ));
            }
            let input = json_file_or_stdin(
                input_path(&args[1..], ["--input", "--artifact"].as_slice()).as_deref(),
            )?;
            let errors = mission_center_policy::validate_steelman_artifact(&input, Some(root));
            Ok(validation_envelope(command, errors.is_empty(), errors))
        }
        "critic" => {
            let input = json_file_or_stdin(
                input_path(args, ["--input", "--record"].as_slice()).as_deref(),
            )?;
            let errors = mission_center_policy::validate_critic_record(&input);
            Ok(validation_envelope(command, errors.is_empty(), errors))
        }
        "shift-loss" => {
            let mode = args.first().map(String::as_str).unwrap_or("evaluate");
            if mode == "evaluate" {
                let input = json_file_or_stdin(
                    input_path(&args[1..], ["--input", "--result"].as_slice()).as_deref(),
                )?;
                let result = mission_center_policy::evaluate_shift_loss(&input, Some(root));
                let status = if result.get("valid").and_then(Value::as_bool) == Some(false) {
                    "error"
                } else {
                    "ok"
                };
                return Ok(value_envelope(command, status, result));
            }
            if mode == "compare" {
                let baseline = json_file_or_stdin(optional_arg(args, "--baseline").as_deref())?;
                let current = json_file_or_stdin(
                    optional_arg(args, "--new")
                        .or_else(|| optional_arg(args, "--current"))
                        .as_deref(),
                )?;
                let result =
                    mission_center_policy::compare_shift_loss(&baseline, &current, Some(root));
                let status = if result.get("complete").and_then(Value::as_bool) == Some(false) {
                    "error"
                } else {
                    "ok"
                };
                return Ok(value_envelope(command, status, result));
            }
            Err(format!("unknown shift-loss subcommand: {mode}"))
        }
        "security" => {
            let input = json_file_or_stdin(input_path(args, ["--input"].as_slice()).as_deref())?;
            let errors = mission_center_policy::scan_forbidden_content(&input);
            Ok(validation_envelope(command, errors.is_empty(), errors))
        }
        "compatibility" => {
            let input = json_file_or_stdin(
                input_path(args, ["--input", "--matrix"].as_slice()).as_deref(),
            )?;
            let errors = mission_center_policy::validate_compatibility_matrix(&input);
            Ok(validation_envelope(command, errors.is_empty(), errors))
        }
        _ => Err(format!("unknown command: {command}")),
    }
}
fn option_root(args: &[String]) -> (PathBuf, Vec<String>, Option<String>) {
    let mut root = PathBuf::from(".");
    let mut seen_root = false;
    let mut rest = Vec::new();
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--root" | "-C" => {
                if seen_root {
                    return (root, rest, Some("repeated argument: --root".to_owned()));
                }
                if let Some(value) = args.get(index + 1)
                    && !value.is_empty()
                    && !value.starts_with('-')
                {
                    root = PathBuf::from(value);
                    seen_root = true;
                    index += 2;
                } else {
                    return (
                        root,
                        rest,
                        Some(format!("missing value for {}", args[index])),
                    );
                }
            }
            value if value.starts_with("--root=") => {
                if seen_root {
                    return (root, rest, Some("repeated argument: --root".to_owned()));
                }
                let value = &value[7..];
                if value.is_empty() {
                    return (root, rest, Some("missing value for --root".to_owned()));
                }
                root = PathBuf::from(value);
                seen_root = true;
                index += 1;
            }
            _ => {
                rest.push(args[index].clone());
                index += 1;
            }
        }
    }
    (root, rest, None)
}
fn task_json(task: &mission_center_core::Task) -> String {
    format!(
        "{{\"id\":\"{}\",\"title\":\"{}\",\"status\":\"{}\"}}",
        escape(&task.id),
        escape(&task.title),
        task.status
    )
}

fn date_arg(args: &[String]) -> Option<String> {
    optional_arg(args, "--date")
}
fn marker_fingerprint(text: &str) -> Option<&str> {
    let marker = "source-fingerprint=";
    let start = text.find(marker)? + marker.len();
    let value = text.get(start..start + 64)?;
    (value.as_bytes().iter().all(u8::is_ascii_hexdigit)
        && value.chars().all(|ch| !ch.is_ascii_uppercase()))
    .then_some(value)
}
fn today_utc() -> String {
    let days = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |duration| duration.as_secs() / 86_400);
    let (year, month, day) = civil_date(days as i64);
    format!("{year:04}-{month:02}-{day:02}")
}

fn today_local() -> String {
    #[cfg(windows)]
    let command = Command::new("powershell.exe")
        .args([
            "-NoProfile",
            "-Command",
            "(Get-Date).ToString('yyyy-MM-dd')",
        ])
        .output();
    #[cfg(not(windows))]
    let command = Command::new("date").arg("+%F").output();
    command
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|value| value.trim().to_owned())
        .filter(|value| {
            value.len() == 10 && value.as_bytes()[4] == b'-' && value.as_bytes()[7] == b'-'
        })
        .unwrap_or_else(today_utc)
}

fn valid_date(value: &str) -> bool {
    value.len() == 10
        && value.as_bytes()[4] == b'-'
        && value.as_bytes()[7] == b'-'
        && value
            .bytes()
            .enumerate()
            .all(|(index, byte)| index == 4 || index == 7 || byte.is_ascii_digit())
}
fn civil_date(days_since_epoch: i64) -> (i64, i64, i64) {
    let z = days_since_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let year = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    (year + i64::from(month <= 2), month, day)
}
fn organized_date(text: &str) -> Option<String> {
    text.lines().find_map(|line| {
        let line = line.trim();
        [
            "- 最後整理：",
            "- 最後整理:",
            "- Last organized:",
            "- Last organized：",
        ]
        .iter()
        .find_map(|prefix| {
            line.strip_prefix(prefix)
                .map(|value| value.trim().to_owned())
        })
    })
}

fn bounded_utf8_prefix(value: &str, max_bytes: usize) -> String {
    if value.len() <= max_bytes {
        return value.to_owned();
    }
    let mut end = max_bytes.min(value.len());
    while end > 0 && !value.is_char_boundary(end) {
        end -= 1;
    }
    value[..end].to_owned()
}

fn bounded_utf8_truncated(value: &str, max_bytes: usize) -> String {
    if value.len() <= max_bytes {
        return value.to_owned();
    }
    if max_bytes <= RESUME_TRUNCATED_MARKER.len() {
        return RESUME_TRUNCATED_MARKER[..max_bytes].to_owned();
    }
    let prefix = bounded_utf8_prefix(value, max_bytes - RESUME_TRUNCATED_MARKER.len());
    format!("{prefix}{RESUME_TRUNCATED_MARKER}")
}

fn active_lessons(value: &str) -> String {
    let Some(start) = ["## Active Lessons", "## 主動教訓"]
        .iter()
        .filter_map(|marker| value.find(marker))
        .min()
    else {
        return String::new();
    };
    let tail = &value[start..];
    let end = [
        "## Resolved Index",
        "## Resolved Lessons",
        "## 已解決索引",
        "## 已解決教訓",
    ]
    .iter()
    .filter_map(|marker| tail.find(marker))
    .min()
    .unwrap_or(tail.len());
    tail[..end].trim_end().to_owned()
}

fn public_value_bytes(value: &Value, nodes: &mut usize) -> Option<usize> {
    *nodes = nodes.checked_add(1)?;
    if *nodes > 10_000 {
        return None;
    }
    match value {
        Value::String(text) => Some(text.len()),
        Value::Array(values) => values.iter().try_fold(0usize, |sum, item| {
            sum.checked_add(public_value_bytes(item, nodes)?)
        }),
        Value::Object(values) => values.iter().try_fold(0usize, |sum, (key, item)| {
            *nodes = nodes.checked_add(1)?;
            if *nodes > 10_000 {
                return None;
            }
            sum.checked_add(key.len())?
                .checked_add(public_value_bytes(item, nodes)?)
        }),
        Value::Null => Some(4),
        Value::Bool(value) => Some(if *value { 4 } else { 5 }),
        Value::Number(value) if value.is_i64() || value.is_u64() => Some(value.to_string().len()),
        Value::Number(_) => None,
    }
}

fn read_optional_context(
    ws: &MissionWorkspace,
    locator: &str,
    limit: u64,
    files_read: &mut Vec<String>,
    read_next: &mut Vec<String>,
) -> Option<String> {
    match ws.read_artifact_text(locator, limit) {
        Ok(text) => {
            files_read.push(format!("MissionCenter/{locator}"));
            Some(text)
        }
        Err(mission_center_workspace::WorkspaceError::NotFound { .. }) => {
            read_next.push(locator.to_owned());
            None
        }
        Err(_) => {
            read_next.push(locator.to_owned());
            None
        }
    }
}

fn json_string_array(values: &[String]) -> Value {
    Value::Array(values.iter().cloned().map(Value::String).collect())
}

fn resume_packet(ws: &MissionWorkspace, _tasks: &[Task], date: &str) -> Result<Value, String> {
    let mission = ws.mission_dir();
    let mut files_read = Vec::new();
    let mut read_next = Vec::new();
    let mut stale_reasons = Vec::new();
    let fingerprint = ws.fingerprint().map_err(|error| error.to_string())?;
    let task_source = fs::read(ws.tasks_path()).map_err(|error| error.to_string())?;
    let task_fp = mission_center_core::workspace_fingerprint(&[("tasks.md", Some(&task_source))]);
    let required = [
        "brief.md",
        "working-set.md",
        "guardrails.md",
        "daily-log.md",
        "critical-lessons.md",
    ];
    let missing: Vec<String> = required
        .iter()
        .filter(|name| !ws.artifact_exists(name).unwrap_or(false))
        .map(|name| (*name).to_owned())
        .collect();
    let brief = read_optional_context(ws, "brief.md", 64 * 1024, &mut files_read, &mut read_next);
    let working_set = read_optional_context(
        ws,
        "working-set.md",
        64 * 1024,
        &mut files_read,
        &mut read_next,
    );
    let lessons = read_optional_context(
        ws,
        "critical-lessons.md",
        64 * 1024,
        &mut files_read,
        &mut read_next,
    );
    let daily = read_optional_context(
        ws,
        "daily-log.md",
        DAILY_LOG_MAX_BYTES,
        &mut files_read,
        &mut read_next,
    );
    let source_fresh = missing.is_empty()
        && marker_fingerprint(brief.as_deref().unwrap_or_default()) == Some(fingerprint.as_str())
        && marker_fingerprint(working_set.as_deref().unwrap_or_default()) == Some(task_fp.as_str());
    let date_fresh = organized_date(daily.as_deref().unwrap_or_default()).as_deref() == Some(date);
    if !missing.is_empty() {
        stale_reasons.push("missing_required_files".to_owned());
    }
    if !source_fresh && missing.is_empty() {
        stale_reasons.push("source_fingerprint_mismatch".to_owned());
    }
    if !date_fresh {
        stale_reasons.push("organized_date_mismatch".to_owned());
    }

    let mut ledger_status = "missing";
    let mut ledger_error = None;
    let mut handoff = None;
    if ws
        .artifact_exists("execution-ledger.jsonl")
        .map_err(|e| e.to_string())?
    {
        match ws.validate_execution_ledger() {
            Ok(()) => {
                ledger_status = "ready";
                match ws.handoff_json(None) {
                    Ok(raw) => match serde_json::from_str(&raw) {
                        Ok(value) => handoff = Some(value),
                        Err(error) => {
                            ledger_status = "corrupt";
                            ledger_error = Some(format!("invalid handoff JSON: {error}"));
                            read_next.push("execution-ledger.jsonl".to_owned());
                            read_next.push("handoff".to_owned());
                        }
                    },
                    Err(mission_center_workspace::WorkspaceError::TooLarge { .. }) => {
                        read_next.push("handoff".to_owned());
                    }
                    Err(error) => {
                        ledger_status = "corrupt";
                        ledger_error = Some(error.to_string());
                        read_next.push("execution-ledger.jsonl".to_owned());
                        read_next.push("handoff".to_owned());
                    }
                }
            }
            Err(error) => {
                ledger_status = "corrupt";
                ledger_error = Some(error.to_string());
                read_next.push("execution-ledger.jsonl".to_owned());
                read_next.push("handoff".to_owned());
            }
        }
    }
    let mut snapshot_invalid = false;
    let snapshot = match read_bounded_utf8(&mission.join("snapshot.md"), 64 * 1024) {
        Ok(text)
            if text.lines().any(|line| {
                let value = line.trim().to_ascii_lowercase();
                value == "- state: active" || value == "state: active"
            }) =>
        {
            files_read.push("MissionCenter/snapshot.md".to_owned());
            Some(text)
        }
        Ok(_) => None,
        Err(mission_center_workspace::WorkspaceError::NotFound { .. }) => None,
        Err(error) => {
            snapshot_invalid = true;
            stale_reasons.push("snapshot_unreadable".to_owned());
            read_next.push("snapshot.md".to_owned());
            let _ = error;
            None
        }
    };
    let complete = snapshot.is_none()
        && !snapshot_invalid
        && !_tasks.is_empty()
        && _tasks.iter().all(|task| task.status == TaskStatus::Done);

    let mut sections = vec![
        ("handoff", handoff.as_ref().map(Value::to_string)),
        ("brief", brief),
        ("workingSet", working_set),
        (
            "activeCriticalLessons",
            lessons.map(|value| active_lessons(&value)),
        ),
        ("snapshot", snapshot),
    ];
    let handoff_object = handoff.clone();
    let mut truncated = false;
    let mut truncated_names = Vec::new();
    let make = |sections: &[(&str, Option<String>)],
                handoff_value: Option<Value>,
                truncated: bool,
                truncated_names: &[String]| {
        let content = sections
            .iter()
            .map(|(name, value)| {
                (
                    (*name).to_owned(),
                    value
                        .as_deref()
                        .map(|value| Value::String(value.to_owned()))
                        .unwrap_or(Value::Null),
                )
            })
            .collect::<serde_json::Map<_, _>>();
        let included = sections
            .iter()
            .map(|(name, value)| {
                (
                    (*name).to_owned(),
                    Value::from(value.as_ref().map_or(0usize, String::len) as u64),
                )
            })
            .collect::<serde_json::Map<_, _>>();
        let fallback =
            !source_fresh || !date_fresh || ledger_status == "corrupt" || snapshot_invalid;
        let mut object = serde_json::Map::new();
        object.insert("schemaVersion".to_owned(), Value::String("1.1".to_owned()));
        object.insert("route".to_owned(), Value::String("resume".to_owned()));
        object.insert("sourceFresh".to_owned(), Value::Bool(source_fresh));
        object.insert("dateFresh".to_owned(), Value::Bool(date_fresh));
        object.insert("staleReasons".to_owned(), json_string_array(&stale_reasons));
        object.insert("filesRead".to_owned(), json_string_array(&files_read));
        object.insert("content".to_owned(), Value::Object(content));
        object.insert("handoff".to_owned(), handoff_value.unwrap_or(Value::Null));
        object.insert(
            "ledgerStatus".to_owned(),
            Value::String(ledger_status.to_owned()),
        );
        object.insert(
            "ledgerError".to_owned(),
            ledger_error
                .clone()
                .map(Value::String)
                .unwrap_or(Value::Null),
        );
        object.insert(
            "context".to_owned(),
            json!({"includedBytes": Value::Object(included)}),
        );
        object.insert("bytes".to_owned(), Value::from(0u64));
        object.insert("maxBytes".to_owned(), Value::from(RESUME_MAX_BYTES as u64));
        object.insert("canonicalFallback".to_owned(), Value::Bool(fallback));
        object.insert(
            "fallbackReason".to_owned(),
            if fallback {
                Value::String(
                    if ledger_status == "corrupt" {
                        "execution ledger corrupt"
                    } else {
                        "derived view stale"
                    }
                    .to_owned(),
                )
            } else {
                Value::Null
            },
        );
        object.insert("truncated".to_owned(), Value::Bool(truncated));
        object.insert(
            "truncatedMarker".to_owned(),
            if truncated {
                Value::String(RESUME_TRUNCATED_MARKER.to_owned())
            } else {
                Value::Null
            },
        );
        let mut next = read_next.clone();
        for name in truncated_names {
            if !next.contains(name) {
                next.push(name.clone());
            }
        }
        object.insert("readNext".to_owned(), json_string_array(&next));
        object.insert(
            "legacyRouting".to_owned(),
            json!({
                "route": if complete { "complete" } else { "select_task" },
                "actionableHandoff": false,
            }),
        );
        let mut value = Value::Object(object);
        for _ in 0..4 {
            let mut nodes = 0;
            let bytes = public_value_bytes(&value, &mut nodes).unwrap_or(usize::MAX);
            if let Value::Object(map) = &mut value {
                if map.get("bytes").and_then(Value::as_u64) == Some(bytes as u64) {
                    break;
                }
                map.insert("bytes".to_owned(), Value::from(bytes as u64));
            }
        }
        value
    };
    let mut packet = make(
        &sections,
        handoff_object.clone(),
        truncated,
        &truncated_names,
    );
    for index in (0..sections.len()).rev() {
        while public_value_bytes(&packet, &mut 0).unwrap_or(usize::MAX) > RESUME_MAX_BYTES {
            let current = sections[index].1.as_deref().unwrap_or_default();
            if current.is_empty() {
                break;
            }
            let mut nodes = 0;
            let current_bytes = public_value_bytes(&packet, &mut nodes).unwrap_or(usize::MAX);
            let excess = current_bytes.saturating_sub(RESUME_MAX_BYTES).max(1);
            let target = current.len().saturating_sub(excess + 64);
            sections[index].1 = Some(bounded_utf8_truncated(current, target));
            truncated = true;
            if !truncated_names.iter().any(|name| name == sections[index].0) {
                truncated_names.push(sections[index].0.to_owned());
            }
            packet = make(
                &sections,
                handoff_object.clone(),
                truncated,
                &truncated_names,
            );
            if sections[index].1.as_deref().is_some_and(str::is_empty) {
                break;
            }
        }
    }
    if public_value_bytes(&packet, &mut 0).unwrap_or(usize::MAX) > RESUME_MAX_BYTES {
        packet = make(&sections, None, truncated, &truncated_names);
    }
    let mut nodes = 0;
    let bytes = public_value_bytes(&packet, &mut nodes)
        .ok_or_else(|| "resume packet exceeds bounded node budget".to_owned())?;
    if bytes > RESUME_MAX_BYTES {
        return Err("resume packet metadata exceeds 16 KiB".to_owned());
    }
    Ok(packet)
}
fn ids_json(ids: &[String]) -> String {
    format!(
        "[{}]",
        ids.iter()
            .map(|id| format!("\"{}\"", escape(id)))
            .collect::<Vec<_>>()
            .join(",")
    )
}

fn reconcile_status_rank(status: &str) -> u8 {
    match status {
        "pass" => 0,
        "unknown" => 1,
        "stale" => 2,
        "conflict" => 3,
        "corrupt" => 4,
        _ => 4,
    }
}

fn evidence_path(root: &Path, locator: &str) -> Option<PathBuf> {
    Some(root.join(normalize_locator(locator)?))
}

#[cfg(windows)]
fn metadata_is_reparse(metadata: &fs::Metadata) -> bool {
    metadata.file_attributes() & 0x400 != 0
}

#[cfg(not(windows))]
fn metadata_is_reparse(_metadata: &fs::Metadata) -> bool {
    false
}

fn normalize_locator(locator: &str) -> Option<String> {
    if locator.is_empty()
        || locator.len() > 1024
        || locator.contains("://")
        || locator.starts_with('/')
        || locator.as_bytes().get(1) == Some(&b':')
    {
        return None;
    }
    let normalized = locator.replace('\\', "/");
    let parts = normalized.split('/').collect::<Vec<_>>();
    if parts.is_empty()
        || parts
            .iter()
            .any(|part| part.is_empty() || *part == "." || *part == "..")
    {
        return None;
    }
    Some(parts.join("/"))
}

fn schema_identifier(
    value: Option<&Value>,
    kind: &str,
    errors: &mut Vec<String>,
) -> Option<String> {
    if value
        .and_then(Value::as_str)
        .is_some_and(|text| text != text.trim())
    {
        errors.push(format!("{kind} has invalid surrounding whitespace"));
    }
    let text = evidence_text(value, kind, errors)?;
    let valid = match kind {
        "envelopeId" | "supersedes" => {
            text.chars().count() <= 128
                && text.chars().enumerate().all(|(index, ch)| {
                    ch.is_ascii_alphanumeric() && index == 0
                        || index > 0
                            && (ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | '-'))
                })
        }
        "taskId" => text.rsplit_once('-').is_some_and(|(prefix, suffix)| {
            !prefix.is_empty()
                && prefix.chars().enumerate().all(|(index, ch)| {
                    ch.is_ascii_alphabetic() && index == 0
                        || index > 0 && (ch.is_ascii_alphanumeric() || ch == '_')
                })
                && !suffix.is_empty()
                && suffix.bytes().all(|byte| byte.is_ascii_digit())
        }),
        "checkId" => {
            text.chars().count() <= 128
                && text.chars().enumerate().all(|(index, ch)| {
                    ch.is_ascii_alphanumeric() && index == 0
                        || index > 0
                            && (ch.is_ascii_alphanumeric() || matches!(ch, '.' | ':' | '/' | '-'))
                })
        }
        _ => false,
    };
    if !valid {
        errors.push(format!("{kind} has invalid format"));
    }
    Some(text)
}

fn valid_iso8601_timezone(value: Option<&Value>, errors: &mut Vec<String>) -> bool {
    let Some(text) = strict_evidence_text(value, "recordedAt", errors) else {
        return false;
    };
    let date_time = text.len() >= 20
        && text.as_bytes().get(4) == Some(&b'-')
        && text.as_bytes().get(7) == Some(&b'-')
        && text.as_bytes().get(10) == Some(&b'T')
        && text.as_bytes().get(13) == Some(&b':')
        && text.as_bytes().get(16) == Some(&b':');
    let date_time_digits = [(0, 4), (5, 7), (8, 10), (11, 13), (14, 16), (17, 19)]
        .iter()
        .all(|(start, end)| {
            text.as_bytes()
                .get(*start..*end)
                .is_some_and(|part| part.iter().all(u8::is_ascii_digit))
        });
    let date_time_ranges = if date_time_digits {
        let bytes = text.as_bytes();
        let number = |start: usize, end: usize| {
            bytes[start..end]
                .iter()
                .fold(0u32, |value, byte| value * 10 + u32::from(byte - b'0'))
        };
        let year = number(0, 4);
        let month = number(5, 7);
        let day = number(8, 10);
        let hour = number(11, 13);
        let minute = number(14, 16);
        let second = number(17, 19);
        let days_in_month = match month {
            1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
            4 | 6 | 9 | 11 => 30,
            2 if year % 400 == 0 || (year % 4 == 0 && year % 100 != 0) => 29,
            2 => 28,
            _ => 0,
        };
        (1..=12).contains(&month)
            && (1..=days_in_month).contains(&day)
            && hour <= 23
            && minute <= 59
            && second <= 60
    } else {
        false
    };
    let timezone_start = if text.as_bytes().get(19) == Some(&b'.') {
        let end = text[20..]
            .bytes()
            .position(|byte| matches!(byte, b'Z' | b'+' | b'-'))
            .map(|offset| offset + 20)
            .unwrap_or(0);
        let fraction = text.get(20..end).unwrap_or_default();
        if fraction.is_empty() || !fraction.bytes().all(|byte| byte.is_ascii_digit()) {
            0
        } else {
            end
        }
    } else {
        19
    };
    let timezone = timezone_start > 0
        && (text.get(timezone_start..) == Some("Z")
            || text.get(timezone_start..).is_some_and(|suffix| {
                suffix.len() == 6
                    && matches!(suffix.as_bytes().first(), Some(b'+' | b'-'))
                    && suffix.as_bytes().get(3) == Some(&b':')
                    && suffix[1..]
                        .bytes()
                        .enumerate()
                        .all(|(index, byte)| index == 2 || byte.is_ascii_digit())
                    && suffix
                        .get(1..3)
                        .and_then(|hours| hours.parse::<u32>().ok())
                        .is_some_and(|hours| hours <= 23)
                    && suffix
                        .get(4..6)
                        .and_then(|minutes| minutes.parse::<u32>().ok())
                        .is_some_and(|minutes| minutes <= 59)
            }));
    if !date_time || !date_time_digits || !date_time_ranges || !timezone {
        errors.push("recordedAt must be an ISO-8601 date-time with timezone".to_owned());
    }
    date_time && date_time_digits && date_time_ranges && timezone
}

fn task_id_in_text(text: &str, task_id: &str) -> bool {
    let mut offset = 0;
    while let Some(relative) = text[offset..].find(task_id) {
        let start = offset + relative;
        let end = start + task_id.len();
        let before = text[..start].chars().next_back();
        let after = text[end..].chars().next();
        if !before.is_some_and(|ch| ch.is_ascii_alphanumeric() || ch == '_' || ch == '-')
            && !after.is_some_and(|ch| ch.is_ascii_alphanumeric() || ch == '_' || ch == '-')
        {
            return true;
        }
        offset = end;
        if offset >= text.len() {
            break;
        }
    }
    false
}

fn task_ids_in_text(text: &str, tasks: &[Task]) -> HashSet<String> {
    tasks
        .iter()
        .filter(|task| task_id_in_text(text, &task.id))
        .map(|task| task.id.clone())
        .collect()
}

fn progress_section<'a>(text: &'a str, start: &str, end: &str) -> &'a str {
    let Some(start_index) = text.find(start) else {
        return "";
    };
    let body = &text[start_index + start.len()..];
    body.find(end).map_or(body, |end_index| &body[..end_index])
}

fn closeout_field<'a>(text: &'a str, labels: &[&str]) -> Option<&'a str> {
    text.lines().find_map(|line| {
        let line = line.trim_start();
        labels.iter().find_map(|label| {
            line.strip_prefix(&format!("- {label}:"))
                .or_else(|| line.strip_prefix(&format!("- {label}：")))
                .map(str::trim)
        })
    })
}

fn evidence_text(value: Option<&Value>, field: &str, errors: &mut Vec<String>) -> Option<String> {
    strict_evidence_text(value, field, errors)
}

fn strict_evidence_text(
    value: Option<&Value>,
    field: &str,
    errors: &mut Vec<String>,
) -> Option<String> {
    let text = value.and_then(Value::as_str).filter(|v| !v.is_empty());
    if text.is_none() {
        errors.push(format!("{field} must be a non-empty string"));
    } else if text.is_some_and(|v| v.len() > 1024) {
        errors.push(format!("{field} exceeds 1024 bytes"));
    }
    if text.is_some_and(|v| v != v.trim()) {
        errors.push(format!("{field} has invalid surrounding whitespace"));
    }
    text.map(ToOwned::to_owned)
}

fn inspect_evidence(root: &Path, tasks: &[Task]) -> (&'static str, String) {
    let directory = root.join("output/mission-center-evidence");
    let unknown = || {
        (
            "unknown",
            "evidence envelope directory is absent or empty".to_owned(),
        )
    };
    let metadata = match fs::symlink_metadata(&directory) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return unknown(),
        Err(error) => {
            return (
                "corrupt",
                format!("cannot inspect evidence directory: {error}"),
            );
        }
    };
    if metadata.file_type().is_symlink() || metadata_is_reparse(&metadata) || !metadata.is_dir() {
        return (
            "corrupt",
            "evidence directory is not a safe directory".to_owned(),
        );
    }
    let entries = match fs::read_dir(&directory) {
        Ok(entries) => entries,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return unknown(),
        Err(error) => {
            return (
                "corrupt",
                format!("cannot enumerate evidence directory: {error}"),
            );
        }
    };
    let mut paths = Vec::new();
    let mut total_bytes = 0u64;
    let mut entry_count = 0usize;
    for entry in entries {
        let entry = match entry {
            Ok(entry) => entry,
            Err(error) => {
                return (
                    "corrupt",
                    format!("cannot enumerate evidence entry: {error}"),
                );
            }
        };
        entry_count += 1;
        if entry_count > MAX_EVIDENCE_FILES {
            return (
                "corrupt",
                format!("evidence directory exceeds {MAX_EVIDENCE_FILES} entries"),
            );
        }
        let file_type = match entry.file_type() {
            Ok(file_type) => file_type,
            Err(error) => return ("corrupt", format!("cannot inspect evidence entry: {error}")),
        };
        let entry_metadata = match fs::symlink_metadata(entry.path()) {
            Ok(metadata) => metadata,
            Err(error) => return ("corrupt", format!("cannot inspect evidence entry: {error}")),
        };
        if file_type.is_symlink() || metadata_is_reparse(&entry_metadata) {
            return (
                "corrupt",
                "evidence directory contains a symlink/reparse entry".to_owned(),
            );
        }
        if file_type.is_file() {
            let size = match entry.metadata() {
                Ok(metadata) => metadata.len(),
                Err(error) => return ("corrupt", format!("cannot stat evidence entry: {error}")),
            };
            total_bytes = match total_bytes.checked_add(size) {
                Some(total) if total <= MAX_EVIDENCE_TOTAL_BYTES => total,
                _ => {
                    return (
                        "corrupt",
                        format!("evidence directory exceeds {MAX_EVIDENCE_TOTAL_BYTES} bytes"),
                    );
                }
            };
            if entry.path().extension().is_some_and(|ext| ext == "json") {
                paths.push(entry.path());
            }
        }
    }
    if paths.is_empty() {
        return unknown();
    }
    let task_ids: HashSet<String> = tasks.iter().map(|task| task.id.clone()).collect();
    let mut records = Vec::new();
    let mut statuses = Vec::new();
    let mut errors = Vec::new();
    for path in paths {
        let name = path
            .file_name()
            .and_then(|v| v.to_str())
            .unwrap_or("evidence.json");
        let bytes = match read_bounded_file(&path, EVIDENCE_MAX_BYTES) {
            Ok(bytes) => bytes,
            Err(error) => {
                statuses.push("corrupt");
                errors.push(format!("{name}: {error}"));
                continue;
            }
        };
        let payload: Value = match serde_json::from_slice(&bytes) {
            Ok(value) => value,
            Err(error) => {
                statuses.push("corrupt");
                errors.push(format!("{name}: invalid JSON: {error}"));
                continue;
            }
        };
        let Some(object) = payload.as_object() else {
            statuses.push("corrupt");
            errors.push(format!("{name}: envelope must be an object"));
            continue;
        };
        let allowed = [
            "schemaVersion",
            "artifactType",
            "envelopeId",
            "taskId",
            "checkId",
            "scope",
            "scopeDigest",
            "result",
            "status",
            "artifactLocators",
            "recordedAt",
            "sourceRevision",
            "supersedes",
        ];
        let required = [
            "schemaVersion",
            "artifactType",
            "envelopeId",
            "taskId",
            "checkId",
            "scope",
            "scopeDigest",
            "result",
            "status",
            "artifactLocators",
            "recordedAt",
        ];
        let mut local = Vec::new();
        for key in object.keys() {
            if !allowed.contains(&key.as_str()) {
                local.push(format!("unknown field: {key}"));
            }
        }
        for field in required {
            if !object.contains_key(field) {
                local.push(format!("missing {field}"));
            }
        }
        if object.get("schemaVersion").and_then(Value::as_str) != Some("1.0") {
            local.push("schemaVersion must be 1.0".to_owned());
        }
        if object.get("artifactType").and_then(Value::as_str) != Some("evidence-envelope") {
            local.push("artifactType must be evidence-envelope".to_owned());
        }
        let envelope_id = schema_identifier(object.get("envelopeId"), "envelopeId", &mut local);
        let task_id = schema_identifier(object.get("taskId"), "taskId", &mut local);
        let check_id = schema_identifier(object.get("checkId"), "checkId", &mut local);
        let digest = evidence_text(object.get("scopeDigest"), "scopeDigest", &mut local);
        let _recorded_at = valid_iso8601_timezone(object.get("recordedAt"), &mut local);
        let supersedes = if object.contains_key("supersedes") {
            schema_identifier(object.get("supersedes"), "supersedes", &mut local)
        } else {
            None
        };
        if object.contains_key("sourceRevision") {
            let _ = evidence_text(object.get("sourceRevision"), "sourceRevision", &mut local);
        }
        let result = object.get("result").and_then(Value::as_str);
        let status = object.get("status").and_then(Value::as_str);
        if !matches!(result, Some("pass" | "fail" | "unknown")) {
            local.push("invalid result".to_owned());
        }
        if !matches!(status, Some("current" | "superseded")) {
            local.push("invalid status".to_owned());
        }
        if !digest.as_ref().is_some_and(|value| {
            value.len() == 64
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
        }) {
            local.push("invalid scopeDigest".to_owned());
        }
        let scope = object.get("scope").and_then(Value::as_array);
        let artifacts = object.get("artifactLocators").and_then(Value::as_array);
        let mut scope_files = Vec::new();
        if scope.is_none_or(|v| v.is_empty() || v.len() > 64) {
            local.push("scope must be a non-empty list".to_owned());
        }
        if let Some(values) = scope {
            let mut seen_scope = HashSet::new();
            for value in values {
                let Some(raw_locator) = value.as_str().filter(|v| !v.is_empty()) else {
                    local.push("invalid scope locator".to_owned());
                    continue;
                };
                let Some(locator) = normalize_locator(raw_locator) else {
                    local.push(format!("unsafe scope locator: {raw_locator}"));
                    continue;
                };
                let Some(path) = evidence_path(root, &locator) else {
                    local.push(format!("unsafe scope locator: {raw_locator}"));
                    continue;
                };
                if !seen_scope.insert(locator.to_owned()) {
                    local.push(format!("duplicate scope locator: {locator}"));
                    continue;
                }
                match read_bounded_file(&path, EVIDENCE_MAX_BYTES) {
                    Ok(bytes) => scope_files.push((locator.to_owned(), bytes)),
                    Err(error) => local.push(format!("scope {locator}: {error}")),
                }
            }
        }
        if artifacts.is_none_or(|v| v.is_empty() || v.len() > 64) {
            local.push("artifactLocators must be a non-empty list".to_owned());
        }
        if let Some(values) = artifacts {
            let mut seen_artifacts = HashSet::new();
            for value in values {
                let Some(raw_locator) = value.as_str().filter(|v| !v.is_empty()) else {
                    local.push("invalid artifact locator".to_owned());
                    continue;
                };
                let Some(locator) = normalize_locator(raw_locator) else {
                    local.push(format!("unsafe artifact locator: {raw_locator}"));
                    continue;
                };
                let Some(path) = evidence_path(root, &locator) else {
                    local.push(format!("unsafe artifact locator: {raw_locator}"));
                    continue;
                };
                if !seen_artifacts.insert(locator.to_owned()) {
                    local.push(format!("duplicate artifact locator: {locator}"));
                    continue;
                }
                if let Err(error) = read_bounded_file(&path, EVIDENCE_MAX_BYTES) {
                    local.push(format!("artifact {locator}: {error}"));
                }
            }
        }
        let scope_refs: Vec<(&str, &[u8])> = scope_files
            .iter()
            .map(|(locator, bytes)| (locator.as_str(), bytes.as_slice()))
            .collect();
        if local.is_empty()
            && status != Some("superseded")
            && digest.as_deref()
                != Some(mission_center_publish::scope_digest_files(&scope_refs).as_str())
        {
            statuses.push("stale");
            errors.push(format!("{name}: scopeDigest does not match scope"));
        } else if !local.is_empty() {
            statuses.push("corrupt");
            errors.push(format!("{name}: {}", local.join("; ")));
        }
        records.push((
            envelope_id,
            task_id,
            check_id,
            status.map(ToOwned::to_owned),
            result.map(ToOwned::to_owned),
            supersedes,
        ));
    }
    let mut current_keys = HashSet::new();
    let mut ids = HashSet::new();
    for (id, task, check, status, result, supersedes) in &records {
        if let Some(id) = id
            && !ids.insert(id.clone())
        {
            statuses.push("conflict");
            errors.push(format!("duplicate envelopeId: {id}"));
        }
        if let (Some(task), Some(check)) = (task, check) {
            if !task_ids.contains(task) {
                statuses.push("conflict");
                errors.push(format!("envelope taskId is absent from tasks.md: {task}"));
            }
            if status.as_deref() == Some("current") {
                if !current_keys.insert((task.clone(), check.clone())) {
                    statuses.push("conflict");
                    errors.push(format!(
                        "multiple current envelopes for task/check: {task}/{check}"
                    ));
                }
                if result.as_deref() == Some("fail") {
                    statuses.push("conflict");
                    errors.push(format!("current evidence result is fail: {task}/{check}"));
                }
                if result.as_deref() == Some("unknown") {
                    statuses.push("unknown");
                }
            }
        }
        if let Some(target) = supersedes {
            let target_record = records
                .iter()
                .find(|(id, _, _, _, _, _)| id.as_deref() == Some(target));
            let valid_target =
                target_record.is_some_and(|(_, target_task, target_check, target_status, _, _)| {
                    target_status.as_deref() == Some("superseded")
                        && target_task == task
                        && target_check == check
                });
            if !valid_target {
                statuses.push("conflict");
                errors.push(format!(
                    "supersedes unknown, mismatched, or non-superseded envelope: {target}"
                ));
            }
        }
    }
    for (id, _, _, status, _, _) in &records {
        if status.as_deref() == Some("superseded")
            && !records
                .iter()
                .any(|(_, _, _, candidate_status, _, supersedes)| {
                    candidate_status.as_deref() == Some("current")
                        && supersedes.as_deref() == id.as_deref()
                })
        {
            statuses.push("conflict");
            if let Some(id) = id {
                errors.push(format!(
                    "superseded envelope has no current replacement: {id}"
                ));
            }
        }
    }
    let covered: HashSet<String> = records
        .iter()
        .filter_map(|(_, task, _, status, _, _)| {
            (status.as_deref() == Some("current"))
                .then(|| task.clone())
                .flatten()
        })
        .collect();
    for task in tasks {
        if !covered.contains(&task.id) {
            statuses.push("unknown");
            errors.push(format!(
                "task has no current evidence envelope: {}",
                task.id
            ));
        }
    }
    if statuses.is_empty() {
        return (
            "pass",
            format!("{} evidence envelope(s) are valid", records.len()),
        );
    }
    let status = statuses
        .into_iter()
        .max_by_key(|value| reconcile_status_rank(value))
        .unwrap_or("corrupt");
    let message = errors
        .iter()
        .take(MAX_EVIDENCE_ERRORS)
        .map(|error| bounded_utf8_prefix(error, 512))
        .collect::<Vec<_>>()
        .join("; ");
    (status, message)
}

fn reconcile_workspace_checks(
    ws: &MissionWorkspace,
    tasks: &[Task],
    date: &str,
) -> Result<Value, String> {
    let mut checks = Vec::<Value>::new();
    let ledger = if !ws
        .artifact_exists("execution-ledger.jsonl")
        .map_err(|e| e.to_string())?
    {
        ("unknown", "execution ledger is absent".to_owned())
    } else {
        match ws.validate_execution_ledger() {
            Ok(()) => ("pass", "execution ledger is valid".to_owned()),
            Err(error) => ("corrupt", error.to_string()),
        }
    };
    checks.push(json!({"name":"ledger","status":ledger.0,"message":ledger.1}));
    let mission = ws.mission_dir();
    let progress = match read_bounded_utf8(&mission.join("progress.md"), 64 * 1024) {
        Ok(text)
            if (text.contains("- Active tasks:")
                || text.contains("- 進行中任務:")
                || text.contains("- 進行中任務："))
                && (text.contains("- Blocked by:")
                    || text.contains("- 阻塞原因:")
                    || text.contains("- 阻塞原因：")) =>
        {
            let (percent, mode, active, blocked) = ws.progress_expectations(tasks);
            let active_label = if text.contains("- Active tasks:") {
                "- Active tasks:"
            } else if text.contains("- 進行中任務:") {
                "- 進行中任務:"
            } else {
                "- 進行中任務："
            };
            let blocked_label = if text.contains("- Blocked by:") {
                "- Blocked by:"
            } else if text.contains("- 阻塞原因:") {
                "- 阻塞原因:"
            } else {
                "- 阻塞原因："
            };
            let next_label = if text.contains("- Next update:") {
                "- Next update:"
            } else if text.contains("- 下次更新:") {
                "- 下次更新:"
            } else {
                "- 下次更新："
            };
            let active_section = progress_section(&text, active_label, blocked_label);
            let blocked_section = progress_section(&text, blocked_label, next_label);
            let expected_active: HashSet<String> = active
                .iter()
                .filter_map(|value| value.split_whitespace().next().map(ToOwned::to_owned))
                .collect();
            let expected_blocked: HashSet<String> = blocked
                .iter()
                .filter_map(|value| value.split_whitespace().next().map(ToOwned::to_owned))
                .collect();
            let actual_active = task_ids_in_text(active_section, tasks);
            let actual_blocked = task_ids_in_text(blocked_section, tasks);
            let progress_sets_match =
                actual_active == expected_active && actual_blocked == expected_blocked;
            let blocked_not_active = actual_active.is_disjoint(&actual_blocked)
                && tasks
                    .iter()
                    .filter(|task| task.status == TaskStatus::Blocked)
                    .all(|task| !actual_active.contains(&task.id));
            let status_ok = text.lines().any(|line| {
                let line = line.trim_start();
                line.strip_prefix("- Current status:")
                    .or_else(|| line.strip_prefix("- 目前狀態:"))
                    .or_else(|| line.strip_prefix("- 目前狀態："))
                    .is_some_and(|value| value.trim() == mode)
            });
            let percent_ok = text.lines().any(|line| {
                let line = line.trim_start();
                (line.starts_with("- Progress bar:")
                    || line.starts_with("- 進度條:")
                    || line.starts_with("- 進度條："))
                    && line.contains(&format!("] {percent}%"))
            });
            if progress_sets_match && blocked_not_active && status_ok && percent_ok {
                (
                    "pass",
                    if text.contains("<!-- mission-center-managed-summary v=1 -->") {
                        "managed progress summary matches canonical tasks"
                    } else {
                        "legacy localized progress summary matches canonical tasks"
                    }
                    .to_owned(),
                )
            } else {
                (
                    "conflict",
                    "progress summary does not match canonical tasks".to_owned(),
                )
            }
        }
        Ok(text) if text.contains("<!-- mission-center-managed-summary") => (
            "corrupt",
            "progress summary is missing required fields".to_owned(),
        ),
        Ok(_) => (
            "unknown",
            "legacy progress summary has no managed marker".to_owned(),
        ),
        Err(mission_center_workspace::WorkspaceError::NotFound { .. }) => {
            ("unknown", "progress.md is absent".to_owned())
        }
        Err(error) => ("corrupt", error.to_string()),
    };
    checks.push(json!({"name":"progress","status":progress.0,"message":progress.1}));
    let closeout = match read_bounded_utf8(&mission.join("closeout.md"), 64 * 1024) {
        Ok(text) => {
            let completed = closeout_field(&text, &["Completed", "已完成"]);
            let unfinished = closeout_field(&text, &["Unfinished", "未完成"]);
            if completed.is_none() || unfinished.is_none() {
                (
                    "unknown",
                    "closeout.md is missing Completed or Unfinished".to_owned(),
                )
            } else {
                let completed = completed.unwrap_or("");
                let unfinished = unfinished.unwrap_or("");
                let completed_ids: Vec<&Task> = tasks
                    .iter()
                    .filter(|task| task_id_in_text(completed, &task.id))
                    .collect();
                let unfinished_ids: Vec<&Task> = tasks
                    .iter()
                    .filter(|task| task_id_in_text(unfinished, &task.id))
                    .collect();
                let completed_not_done: Vec<&str> = completed_ids
                    .iter()
                    .filter(|task| task.status != TaskStatus::Done)
                    .map(|task| task.id.as_str())
                    .collect();
                let unfinished_done: Vec<&str> = unfinished_ids
                    .iter()
                    .filter(|task| task.status == TaskStatus::Done)
                    .map(|task| task.id.as_str())
                    .collect();
                let overlap: Vec<&str> = completed_ids
                    .iter()
                    .filter(|task| unfinished_ids.iter().any(|other| other.id == task.id))
                    .map(|task| task.id.as_str())
                    .collect();
                if !completed_not_done.is_empty()
                    || !unfinished_done.is_empty()
                    || !overlap.is_empty()
                {
                    (
                        "conflict",
                        format!(
                            "closeout task contradiction: completed_not_done={completed_not_done:?}; unfinished_done={unfinished_done:?}; overlap={overlap:?}"
                        ),
                    )
                } else if let Some(source) = closeout_field(&text, &["Source fingerprint"]) {
                    let expected = ws
                        .canonical_snapshot_fingerprint()
                        .map_err(|e| e.to_string())?;
                    if source != expected {
                        ("stale", "closeout source fingerprint is stale".to_owned())
                    } else {
                        ("pass", "closeout is current".to_owned())
                    }
                } else {
                    (
                        "pass",
                        "closeout has no source fingerprint; legacy evidence accepted".to_owned(),
                    )
                }
            }
        }
        Err(mission_center_workspace::WorkspaceError::NotFound { .. }) => {
            ("unknown", "closeout.md is absent".to_owned())
        }
        Err(error) => ("corrupt", error.to_string()),
    };
    checks.push(json!({"name":"closeout","status":closeout.0,"message":closeout.1}));
    let fingerprint = ws.fingerprint().map_err(|e| e.to_string())?;
    let task_bytes = fs::read(ws.tasks_path()).map_err(|e| e.to_string())?;
    let task_fp = mission_center_core::workspace_fingerprint(&[("tasks.md", Some(&task_bytes))]);
    let mut derived_status = "pass";
    let mut derived_messages = Vec::new();
    for (name, expected) in [
        ("brief.md", fingerprint),
        ("working-set.md", task_fp.clone()),
        ("focus.md", task_fp),
    ] {
        let result = match read_bounded_utf8(&mission.join(name), 64 * 1024) {
            Ok(text) if marker_fingerprint(&text) == Some(expected.as_str()) => {
                ("pass", "derived view fingerprint is current".to_owned())
            }
            Ok(text) if marker_fingerprint(&text).is_some() => (
                "stale",
                "derived view source fingerprint is stale".to_owned(),
            ),
            Ok(_) => (
                "unknown",
                "legacy derived view has no managed fingerprint".to_owned(),
            ),
            Err(mission_center_workspace::WorkspaceError::NotFound { .. }) => {
                ("unknown", "derived view is absent".to_owned())
            }
            Err(error) => ("corrupt", error.to_string()),
        };
        if reconcile_status_rank(result.0) > reconcile_status_rank(derived_status) {
            derived_status = result.0;
        }
        derived_messages.push(format!("{name}: {}", result.1));
    }
    checks.push(json!({
        "name":"derived_source",
        "status":derived_status,
        "message":derived_messages.join("; ")
    }));
    let date_status = match read_bounded_utf8(&mission.join("daily-log.md"), DAILY_LOG_MAX_BYTES) {
        Ok(text) => {
            organized_date(&text).map_or(
                "stale",
                |value| {
                    if value == date { "pass" } else { "stale" }
                },
            )
        }
        Err(mission_center_workspace::WorkspaceError::NotFound { .. }) => "unknown",
        Err(_) => "corrupt",
    };
    checks.push(
        json!({"name":"derived_date","status":date_status,"message":"daily organization date"}),
    );
    let evidence = inspect_evidence(ws.root(), tasks);
    checks.push(json!({"name":"evidence_envelope","status":evidence.0,"message":evidence.1}));
    let overall = checks
        .iter()
        .filter_map(|check| check["status"].as_str())
        .max_by_key(|status| reconcile_status_rank(status))
        .unwrap_or("unknown");
    Ok(json!({"status":overall,"readOnly":true,"checks":checks}))
}
fn working_set(tasks: &[Task]) -> Vec<String> {
    mission_center_workspace::working_set_ids(tasks)
}
fn task_ids(tasks: &[Task], status: Option<TaskStatus>, priority: Option<&str>) -> Vec<String> {
    tasks
        .iter()
        .filter(|task| {
            status.is_none_or(|value| task.status == value)
                && priority.is_none_or(|value| task.priority.eq_ignore_ascii_case(value))
        })
        .map(|task| task.id.clone())
        .collect()
}

fn required_arg(args: &[String], name: &str) -> Result<String, String> {
    args.windows(2)
        .find_map(|pair| {
            (pair[0] == name && !pair[1].is_empty() && !pair[1].starts_with("--"))
                .then(|| pair[1].clone())
        })
        .or_else(|| {
            let prefix = format!("{name}=");
            args.iter()
                .find_map(|value| value.strip_prefix(&prefix).map(ToOwned::to_owned))
        })
        .ok_or_else(|| format!("missing required argument: {name}"))
}

fn optional_arg(args: &[String], name: &str) -> Option<String> {
    args.windows(2)
        .find_map(|pair| {
            (pair[0] == name && !pair[1].is_empty() && !pair[1].starts_with("--"))
                .then(|| pair[1].clone())
        })
        .or_else(|| {
            let prefix = format!("{name}=");
            args.iter()
                .find_map(|value| value.strip_prefix(&prefix).map(ToOwned::to_owned))
        })
}

fn repeated_arg_values(args: &[String], name: &str) -> Vec<String> {
    let prefix = format!("{name}=");
    let mut values = Vec::new();
    let mut index = 0;
    while index < args.len() {
        if args[index] == name {
            if let Some(value) = args.get(index + 1) {
                values.push(value.clone());
                index += 1;
            }
        } else if let Some(value) = args[index].strip_prefix(&prefix) {
            values.push(value.to_owned());
        }
        index += 1;
    }
    values
}

fn validate_flags(args: &[String], allowed: &[&str]) -> Result<(), String> {
    let mut seen = Vec::new();
    for value in args.iter().filter(|value| value.starts_with("--")) {
        if value.starts_with("--dry-run=")
            || value.starts_with("--verify=")
            || value.starts_with("--archive=")
        {
            return Err(format!("boolean flag cannot take a value: {value}"));
        }
        let name = value.split('=').next().unwrap_or(value);
        if !allowed.contains(&name) {
            return Err(format!("unknown argument: {name}"));
        }
        if seen.iter().any(|item| item == &name) {
            return Err(format!("repeated argument: {name}"));
        }
        seen.push(name);
    }
    if args.iter().any(|value| value == "--dry-run") && args.iter().any(|value| value == "--verify")
    {
        return Err("--dry-run and --verify are mutually exclusive".to_owned());
    }
    Ok(())
}

fn validate_workspace_flags(command: &str, args: &[String]) -> Result<(), String> {
    let (values, booleans, positional_limit): (&[&str], &[&str], usize) = match command {
        "status" | "resume" | "reconcile" => (&["--date"], &[], 0),
        "init" => (
            &["--operation-id", "--timestamp", "--language"],
            &["--force"],
            0,
        ),
        "sync" => (
            &[
                "--operation-id",
                "--timestamp",
                "--project",
                "--cycle",
                "--goal",
                "--labels",
                "--milestone",
            ],
            &["--rewrite-summaries"],
            0,
        ),
        "doctor" | "verify" => (&[], &[], 0),
        "normalize" => (&["--operation-id", "--timestamp"], &[], 0),
        "snapshot" => (
            &[
                "--operation-id",
                "--timestamp",
                "--note",
                "--attempt",
                "--hypothesis",
                "--evidence",
                "--change",
                "--verification-result",
                "--verification-action",
                "--verification-evidence",
            ],
            &[],
            0,
        ),
        "pulse" => (
            &[
                "--operation-id",
                "--pulse-id",
                "--task-id",
                "--phase",
                "--outcome",
                "--evidence-ref",
                "--recorded-at",
                "--timestamp",
                "--next-action",
                "--budget-remaining",
                "--causal-parent",
            ],
            &[],
            0,
        ),
        "handoff" => (&["--task-id"], &[], 0),
        "closeout" => (
            &[
                "--operation-id",
                "--timestamp",
                "--cycle",
                "--summary",
                "--completed",
                "--unfinished",
                "--risks",
                "--smoke-tests",
                "--retro",
            ],
            &["--archive"],
            0,
        ),
        "project-map" => (
            &["--operation-id", "--timestamp"],
            &["--dry-run", "--verify"],
            0,
        ),
        "claim" => (
            &[
                "--owner",
                "--fence",
                "--expires-at",
                "--now",
                "--operation-id",
                "--timestamp",
                "--committed-at",
            ],
            &[],
            1,
        ),
        "release-claim" => (
            &[
                "--owner",
                "--fence",
                "--operation-id",
                "--timestamp",
                "--committed-at",
            ],
            &[],
            1,
        ),
        "transition" => (&["--operation-id", "--timestamp"], &[], 2),
        _ => return Ok(()),
    };
    let allowed = values
        .iter()
        .chain(booleans.iter())
        .copied()
        .collect::<HashSet<_>>();
    let boolean_set = booleans.iter().copied().collect::<HashSet<_>>();
    let mut seen = HashSet::new();
    let mut positional = 0usize;
    let mut index = 0;
    while index < args.len() {
        let token = &args[index];
        if !token.starts_with('-') {
            positional += 1;
            if positional > positional_limit {
                return Err(format!("unknown argument: {token}"));
            }
            index += 1;
            continue;
        }
        let name = token.split('=').next().unwrap_or(token);
        if !allowed.contains(name) {
            return Err(format!("unknown argument: {name}"));
        }
        let repeatable = command == "snapshot"
            && matches!(
                name,
                "--note" | "--attempt" | "--hypothesis" | "--evidence" | "--change"
            );
        if !repeatable && !seen.insert(name.to_owned()) {
            return Err(format!("repeated argument: {name}"));
        }
        if boolean_set.contains(name) {
            if token.contains('=') {
                return Err(format!("boolean flag cannot take a value: {token}"));
            }
        } else if let Some((_, value)) = token.split_once('=') {
            if value.is_empty() {
                return Err(format!("missing value for {name}"));
            }
        } else {
            let Some(value) = args.get(index + 1) else {
                return Err(format!("missing value for {name}"));
            };
            if value.starts_with('-') && value != "-" {
                return Err(format!("missing value for {name}"));
            }
            index += 1;
        }
        index += 1;
    }
    Ok(())
}

fn unavailable_runtime_state() -> RuntimeState {
    RuntimeState {
        schema_version: mission_center_runtime::SCHEMA_VERSION.to_owned(),
        updated_at: "1970-01-01T00:00:00Z".to_owned(),
        source_status: SourceStatus::Disconnected,
        capabilities: ProviderCapabilities {
            approve: false,
            reject: false,
            focus: false,
        },
        attention: Vec::new(),
        agents: Vec::new(),
    }
}

fn hud_state(args: &[String]) -> Result<RuntimeState, String> {
    let Some(source) = flag_value(args, "--state") else {
        return Ok(unavailable_runtime_state());
    };
    if source != "-" {
        return Err(
            "filesystem_input_forbidden: hud --state 僅接受 stdin 的 '-'，不讀取 path".to_owned(),
        );
    }
    let bytes = read_stdin_bounded(MAX_STDIN_BYTES)?;
    let state_value = serde_json::from_slice::<StrictJson>(&bytes)
        .map_err(|_| "invalid_json: runtime state JSON 無效".to_owned())?
        .0;
    let state: RuntimeState = serde_json::from_value(state_value)
        .map_err(|_| "schema_error: runtime state 欄位無效".to_owned())?;
    state.validate().map_err(|error| error.to_string())
}

fn embedded_hud_fingerprint() -> String {
    let mut input = Vec::new();
    for name in mission_center_runtime::HUD_MANAGED_ASSETS {
        let bytes = EMBEDDED_HUD_FILES
            .iter()
            .find_map(|(candidate, bytes)| (*candidate == *name).then_some(*bytes))
            .expect("compile-time HUD managed asset missing");
        input.extend_from_slice(name.as_bytes());
        input.push(0);
        input.extend_from_slice(bytes);
        input.push(0);
    }
    sha256_digest(&input)
}

fn hud_side_panel_intent(
    url: &str,
    workspace_fingerprint: &str,
    hud_asset_fingerprint: &str,
) -> Value {
    // Host-advisory only: Codex currently exposes no public sidebar-focus API.
    // Keep the intent deterministic so a capable host can claim/reuse an exact
    // loopback surface without guessing a tab or opening an external browser.
    json!({
        "type": "mission-center/hud-side-panel",
        "version": "1.0",
        "surface": "codex-sidebar-or-preview",
        "mode": "reuse",
        "reuseKey": format!("mission-center-hud:{workspace_fingerprint}"),
        "url": url,
        "workspaceFingerprint": workspace_fingerprint,
        "hudAssetFingerprint": hud_asset_fingerprint,
        "externalBrowser": false
    })
}

fn frozen_hud_assets(state: &RuntimeState) -> Result<FrozenHudAssets, String> {
    FrozenHudAssets::from_state(
        EMBEDDED_HUD_FILES
            .iter()
            .map(|(name, bytes)| ((*name).to_owned(), (*bytes).to_vec())),
        state.clone(),
    )
    .map_err(|error| error.to_string())
}

const HUD_METADATA_MAX_BYTES: usize = 16 * 1024;
const HUD_CHILD_TTL: Duration = Duration::from_secs(6 * 60 * 60);
const HUD_REUSE_COOLDOWN: Duration = Duration::from_secs(3);

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct HudProcessMetadata {
    schema_version: String,
    version: String,
    pid: u32,
    port: u16,
    url: String,
    workspace_fingerprint: String,
    hud_asset_fingerprint: String,
    session_nonce: String,
    control_file: String,
    last_launch_at: u64,
    last_session_id: Option<String>,
    last_turn_id: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct HudReady {
    version: String,
    port: u16,
    url: String,
    workspace_fingerprint: String,
    hud_asset_fingerprint: String,
    session_nonce: String,
}

struct HudFileLock {
    path: PathBuf,
}

impl HudFileLock {
    fn acquire(path: &Path) -> Result<Self, String> {
        OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)
            .map_err(|_| "hud launcher 正由另一個 hook 使用中".to_owned())?;
        Ok(Self {
            path: path.to_owned(),
        })
    }
}

impl Drop for HudFileLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn hud_absolute_root(root: &Path) -> Result<PathBuf, String> {
    if !root.is_absolute()
        || root.components().any(|component| {
            matches!(
                component,
                std::path::Component::CurDir | std::path::Component::ParentDir
            )
        })
    {
        return Err("unsafe_path: HUD workspace 必須是沒有 traversal 的絕對路徑".to_owned());
    }
    let metadata = fs::symlink_metadata(root)
        .map_err(|_| "asset_unavailable: HUD workspace 不存在".to_owned())?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err("unsafe_path: HUD workspace 不得是 symlink".to_owned());
    }
    let tasks = root.join("MissionCenter").join("tasks.md");
    let tasks_metadata = fs::symlink_metadata(&tasks)
        .map_err(|_| "asset_unavailable: MissionCenter/tasks.md 不存在".to_owned())?;
    if !tasks_metadata.is_file() || tasks_metadata.file_type().is_symlink() {
        return Err("unsafe_path: tasks.md 不得是 symlink".to_owned());
    }
    Ok(root.to_owned())
}

fn hud_runtime_dir(root: &Path) -> Result<PathBuf, String> {
    let output = root.join("output");
    let runtime = output.join("mission-center-runtime");
    fs::create_dir_all(&runtime).map_err(|_| "io_error: 無法建立 HUD runtime 目錄".to_owned())?;
    for path in [&output, &runtime] {
        let metadata = fs::symlink_metadata(path)
            .map_err(|_| "unsafe_path: HUD runtime 目錄不可讀取".to_owned())?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err("unsafe_path: HUD runtime 目錄不得是 symlink".to_owned());
        }
    }
    Ok(runtime)
}

fn read_hud_metadata(path: &Path) -> Result<Option<HudProcessMetadata>, String> {
    let bytes = match fs::read(path) {
        Ok(bytes) => bytes,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err("io_error: HUD metadata 無法讀取".to_owned()),
    };
    if bytes.len() > HUD_METADATA_MAX_BYTES {
        return Err("schema_error: HUD metadata 超過大小上限".to_owned());
    }
    // Metadata is only an optimization for reusing a healthy companion.  A
    // legacy Python record (or a partially written/corrupt record) must never
    // be trusted for reuse, but it should not make the explicit HUD hook a
    // permanent no-op.  Treat parse/schema failures as a cache miss; the
    // caller will launch a fresh Rust companion and atomically replace it.
    Ok(serde_json::from_slice(&bytes).ok())
}

fn write_hud_metadata(path: &Path, metadata: &HudProcessMetadata) -> Result<(), String> {
    let bytes = serde_json::to_vec(metadata)
        .map_err(|_| "schema_error: HUD metadata 序列化失敗".to_owned())?;
    if bytes.len() > HUD_METADATA_MAX_BYTES {
        return Err("schema_error: HUD metadata 超過大小上限".to_owned());
    }
    write_hud_bytes(path, &bytes)
}

fn write_hud_bytes(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if bytes.len() > HUD_METADATA_MAX_BYTES {
        return Err("schema_error: HUD receipt 超過大小上限".to_owned());
    }
    let temporary = path.with_extension(format!("json.tmp-{}", unique_nonce()));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)
        .map_err(|_| "io_error: HUD metadata 暫存檔無法建立".to_owned())?;
    file.write_all(bytes)
        .and_then(|_| file.sync_all())
        .map_err(|_| "io_error: HUD metadata 無法寫入".to_owned())?;
    fs::rename(&temporary, path).map_err(|_| {
        let _ = fs::remove_file(&temporary);
        "io_error: HUD metadata atomic rename 失敗".to_owned()
    })
}

fn unique_nonce() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default()
}

fn valid_hud_url(url: &str, port: u16) -> bool {
    url == format!("http://127.0.0.1:{port}/") && port != 0
}

fn valid_hud_fingerprint(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn valid_hud_metadata(metadata: &HudProcessMetadata, runtime_dir: &Path, now: u64) -> bool {
    metadata.schema_version == SCHEMA
        && metadata.version == mission_center_runtime::HUD_RUNTIME_VERSION
        && valid_hud_url(&metadata.url, metadata.port)
        && valid_hud_fingerprint(&metadata.workspace_fingerprint)
        && valid_hud_fingerprint(&metadata.hud_asset_fingerprint)
        && !metadata.session_nonce.is_empty()
        && metadata.session_nonce.len() <= 128
        && metadata.pid > 0
        && metadata.last_launch_at <= now.saturating_add(60)
        && Path::new(&metadata.control_file).is_absolute()
        && Path::new(&metadata.control_file).parent() == Some(runtime_dir)
}

fn remove_hud_control(metadata: &HudProcessMetadata) {
    let _ = fs::remove_file(&metadata.control_file);
}

fn write_hud_side_panel_manifest(
    runtime_dir: &Path,
    metadata: &HudProcessMetadata,
) -> Result<(), String> {
    let intent = hud_side_panel_intent(
        &metadata.url,
        &metadata.workspace_fingerprint,
        &metadata.hud_asset_fingerprint,
    );
    let bytes = serde_json::to_vec(&intent)
        .map_err(|_| "schema_error: HUD sidebar intent 序列化失敗".to_owned())?;
    write_hud_bytes(&runtime_dir.join("hud-side-panel.json"), &bytes)
}

fn spawn_hud_child(
    root: &Path,
    control_file: &Path,
    ready_file: &Path,
    nonce: &str,
) -> Result<(HudReady, u32), String> {
    let executable =
        env::current_exe().map_err(|_| "io_error: 找不到 mission-center Rust binary".to_owned())?;
    let mut command = Command::new(executable);
    command
        .args([
            "hud",
            "serve",
            "--root",
            root.to_str()
                .ok_or_else(|| "invalid_utf8: workspace path 無效".to_owned())?,
            "--control-file",
            control_file
                .to_str()
                .ok_or_else(|| "invalid_utf8: control path 無效".to_owned())?,
            "--ready-file",
            ready_file
                .to_str()
                .ok_or_else(|| "invalid_utf8: ready path 無效".to_owned())?,
            "--nonce",
            nonce,
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    command.creation_flags(0x00000208);
    #[cfg(unix)]
    command.process_group(0);
    let mut child = command
        .spawn()
        .map_err(|_| "io_error: HUD Rust companion 無法啟動".to_owned())?;
    let child_pid = child.id();
    let deadline = Instant::now() + Duration::from_secs(3);
    let ready = loop {
        if let Ok(bytes) = fs::read(ready_file) {
            if bytes.len() > HUD_METADATA_MAX_BYTES {
                let _ = child.kill();
                let _ = child.wait();
                return Err("schema_error: HUD companion startup receipt 超過大小上限".to_owned());
            }
            match serde_json::from_slice::<HudReady>(&bytes) {
                Ok(ready) => break ready,
                Err(_) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err("schema_error: HUD companion startup receipt 無效".to_owned());
                }
            }
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err("timeout: HUD companion startup 超時".to_owned());
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    let _ = fs::remove_file(ready_file);
    if ready.version != mission_center_runtime::HUD_RUNTIME_VERSION
        || !valid_hud_url(&ready.url, ready.port)
        || !valid_hud_fingerprint(&ready.workspace_fingerprint)
        || !valid_hud_fingerprint(&ready.hud_asset_fingerprint)
        || ready.session_nonce != nonce
    {
        let _ = child.kill();
        let _ = child.wait();
        return Err("health_mismatch: HUD companion identity 驗證失敗".to_owned());
    }
    // Keep the detached child alive after the startup receipt is consumed.
    drop(child);
    Ok((ready, child_pid))
}

fn hud_background_launch(
    root: &Path,
    session_id: Option<&str>,
    turn_id: Option<&str>,
) -> Result<(HudProcessMetadata, &'static str), String> {
    let root = hud_absolute_root(root)?;
    let runtime_dir = hud_runtime_dir(&root)?;
    let metadata_path = runtime_dir.join("hud-autolaunch.json");
    let lock_path = runtime_dir.join("hud-autolaunch.lock");
    let _lock = HudFileLock::acquire(&lock_path)?;
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or_default();
    if let Some(mut previous) = read_hud_metadata(&metadata_path)? {
        if valid_hud_metadata(&previous, &runtime_dir, now)
            && fs::metadata(&previous.control_file).is_ok()
            && probe_loopback_health(
                previous.port,
                &previous.workspace_fingerprint,
                &previous.session_nonce,
                &previous.hud_asset_fingerprint,
                &previous.version,
            )
            .is_ok()
        {
            let status =
                if now.saturating_sub(previous.last_launch_at) < HUD_REUSE_COOLDOWN.as_secs() {
                    "cooldown"
                } else {
                    "reused"
                };
            previous.last_launch_at = now;
            previous.last_session_id = session_id.map(ToOwned::to_owned);
            previous.last_turn_id = turn_id.map(ToOwned::to_owned);
            write_hud_metadata(&metadata_path, &previous)?;
            write_hud_side_panel_manifest(&runtime_dir, &previous)?;
            return Ok((previous, status));
        }
        remove_hud_control(&previous);
        let _ = fs::remove_file(&metadata_path);
        let _ = fs::remove_file(runtime_dir.join("hud-side-panel.json"));
    }
    let nonce = sha256_digest(format!("hud:{now}:{}", unique_nonce()).as_bytes());
    let control_file = runtime_dir.join(format!("hud-{nonce}.control"));
    let ready_file = runtime_dir.join(format!("hud-{nonce}.ready"));
    let mut control = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&control_file)
        .map_err(|_| "transaction_conflict: HUD control file 已存在".to_owned())?;
    control
        .write_all(nonce.as_bytes())
        .and_then(|_| control.sync_all())
        .map_err(|_| "io_error: HUD control file 無法寫入".to_owned())?;
    let (ready, child_pid) = match spawn_hud_child(&root, &control_file, &ready_file, &nonce) {
        Ok(ready) => ready,
        Err(error) => {
            let _ = fs::remove_file(&control_file);
            let _ = fs::remove_file(&ready_file);
            return Err(error);
        }
    };
    let metadata = HudProcessMetadata {
        schema_version: SCHEMA.to_owned(),
        version: ready.version,
        pid: child_pid,
        port: ready.port,
        url: ready.url,
        workspace_fingerprint: ready.workspace_fingerprint,
        hud_asset_fingerprint: ready.hud_asset_fingerprint,
        session_nonce: ready.session_nonce,
        control_file: control_file.to_string_lossy().into_owned(),
        last_launch_at: now,
        last_session_id: session_id.map(ToOwned::to_owned),
        last_turn_id: turn_id.map(ToOwned::to_owned),
    };
    if let Err(error) = write_hud_metadata(&metadata_path, &metadata) {
        let _ = fs::remove_file(&control_file);
        return Err(error);
    }
    if let Err(error) = write_hud_side_panel_manifest(&runtime_dir, &metadata) {
        let _ = fs::remove_file(&metadata_path);
        let _ = fs::remove_file(&control_file);
        return Err(error);
    }
    Ok((metadata, "launched"))
}

fn hud_hook_context(metadata: &HudProcessMetadata, status: &str) -> String {
    let intent = hud_side_panel_intent(
        &metadata.url,
        &metadata.workspace_fingerprint,
        &metadata.hud_asset_fingerprint,
    );
    format!(
        "Mission Center HUD ready at {}. In Codex Desktop, present this loopback URL in the built-in sidebar or preview surface when supported; otherwise keep this clickable URL available. This host-managed Rust hook reuses an exact healthy instance and never opens an external browser. Launch status: {status}. Side-panel intent (advisory): {}",
        metadata.url, intent
    )
}

fn hook_hud() -> String {
    let bytes = match read_stdin_bounded(mission_center_runtime::MAX_HOOK_INPUT_BYTES) {
        Ok(bytes) => bytes,
        Err(_) => return "{}".to_owned(),
    };
    let raw: Value = match serde_json::from_slice(&bytes) {
        Ok(value) => value,
        Err(_) => return "{}".to_owned(),
    };
    let input = match mission_center_runtime::parse_bounded_hook_input(&bytes) {
        Ok(Some(value)) => value,
        _ => return "{}".to_owned(),
    };
    let prompt = raw.get("prompt").and_then(Value::as_str);
    if input.hook_event_name != "UserPromptSubmit"
        || input.permission_mode.as_deref() == Some("plan")
        || !prompt.is_some_and(|value| {
            hook_route_prompt(value, input.cwd.as_deref()) == Some(HookRoute::Explicit)
        })
    {
        return "{}".to_owned();
    }
    let Some(cwd) = input.cwd.as_deref() else {
        return "{}".to_owned();
    };
    let Ok((metadata, status)) = hud_background_launch(
        Path::new(cwd),
        input.session_id.as_deref(),
        input.turn_id.as_deref(),
    ) else {
        return "{}".to_owned();
    };
    json!({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": hud_hook_context(&metadata, status)
        }
    })
    .to_string()
}

fn hud_serve_run(root: PathBuf, args: &[String]) -> Result<String, String> {
    strict_new_flags(
        args,
        &["--control-file", "--ready-file", "--nonce", "--port"],
        &[],
    )?;
    let control_file = required_arg(args, "--control-file")?;
    let ready_file = required_arg(args, "--ready-file")?;
    let nonce = required_arg(args, "--nonce")?;
    if nonce.is_empty() || nonce.len() > 128 {
        return Err("argument_error: --nonce 長度無效".to_owned());
    }
    let control_path = PathBuf::from(&control_file);
    if !control_path.is_absolute()
        || control_path.components().any(|component| {
            matches!(
                component,
                std::path::Component::CurDir | std::path::Component::ParentDir
            )
        })
    {
        return Err("unsafe_path: control file 必須是沒有 traversal 的絕對路徑".to_owned());
    }
    let control_metadata = fs::symlink_metadata(&control_path)
        .map_err(|_| "asset_unavailable: HUD control file 不存在".to_owned())?;
    if !control_metadata.is_file() || control_metadata.file_type().is_symlink() {
        return Err("unsafe_path: HUD control file 不得是 symlink".to_owned());
    }
    let control_contents =
        fs::read(&control_path).map_err(|_| "io_error: HUD control file 無法讀取".to_owned())?;
    if control_contents != nonce.as_bytes() {
        return Err("health_mismatch: HUD control token 不一致".to_owned());
    }
    let ready_path = PathBuf::from(&ready_file);
    if !ready_path.is_absolute()
        || ready_path.components().any(|component| {
            matches!(
                component,
                std::path::Component::CurDir | std::path::Component::ParentDir
            )
        })
        || ready_path.parent() != control_path.parent()
    {
        return Err("unsafe_path: ready file 必須與 control file 同層且沒有 traversal".to_owned());
    }
    if let Ok(metadata) = fs::symlink_metadata(&ready_path) {
        if !metadata.is_file() || metadata.file_type().is_symlink() {
            return Err("unsafe_path: HUD ready file 不得是 symlink".to_owned());
        }
        let _ = fs::remove_file(&ready_path);
    }
    let port = flag_value(args, "--port")
        .map(|value| {
            value
                .parse::<u16>()
                .map_err(|_| "argument_error: --port 必須是整數".to_owned())
        })
        .transpose()?;
    let state = unavailable_runtime_state();
    let assets = frozen_hud_assets(&state)?;
    let config = HudServerConfig::new(root)
        .with_port(port.unwrap_or(0))
        .with_nonce(nonce)
        .with_frozen_assets(assets);
    let launcher = HudLauncher::new();
    let outcome = launcher
        .launch(config, false)
        .map_err(|error| error.to_string())?;
    let ready = HudReady {
        version: outcome.version.clone(),
        port: outcome.server.port(),
        url: outcome.url.clone(),
        workspace_fingerprint: outcome.workspace_fingerprint.clone(),
        hud_asset_fingerprint: outcome.hud_asset_fingerprint.clone(),
        session_nonce: outcome.server.session_nonce().to_owned(),
    };
    let ready_bytes = serde_json::to_vec(&ready)
        .map_err(|_| "schema_error: HUD startup receipt 序列化失敗".to_owned())?;
    write_hud_bytes(&ready_path, &ready_bytes)?;
    let deadline = Instant::now() + HUD_CHILD_TTL;
    while Instant::now() < deadline
        && outcome.server.is_running()
        && fs::metadata(&control_path).is_ok()
    {
        std::thread::sleep(Duration::from_millis(500));
    }
    launcher.shutdown_all().map_err(|error| error.to_string())?;
    Ok(String::new())
}

struct SystemBrowserOpener;

impl BrowserOpener for SystemBrowserOpener {
    fn open(&self, url: &str) -> bool {
        // The URL is generated by the loopback runtime. Never pass arbitrary
        // user input to a shell or to a browser command.
        if !url.starts_with("http://127.0.0.1:")
            || url
                .chars()
                .any(|character| matches!(character, ' ' | '\n' | '\r' | '"'))
        {
            return false;
        }
        #[cfg(windows)]
        {
            Command::new("rundll32.exe")
                .args(["url.dll,FileProtocolHandler", url])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .is_ok()
        }
        #[cfg(target_os = "macos")]
        {
            Command::new("open")
                .arg(url)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .is_ok()
        }
        #[cfg(all(unix, not(target_os = "macos")))]
        {
            Command::new("xdg-open")
                .arg(url)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .is_ok()
        }
    }
}

fn hud_capability() -> String {
    let assets: Vec<Value> = EMBEDDED_HUD_FILES
        .iter()
        .map(|(name, bytes)| json!({"name":name,"bytes":bytes.len()}))
        .collect();
    value_envelope(
        "hud",
        "ok",
        json!({
            "mode":"capability",
            "supported":true,
            "embedded":true,
            "assetsEmbedded":true,
            "assetFingerprint":embedded_hud_fingerprint(),
            "hudAssetFingerprint":embedded_hud_fingerprint(),
            "assets":assets,
            "allowlist":mission_center_runtime::HUD_ALLOWED_ASSETS,
            "runtimeVersion":mission_center_runtime::HUD_RUNTIME_VERSION,
            "persistent":true,
            "crossProcessReuse":true,
            "lifecycle":"managed-child",
            "commands":{"capability":true,"serve":true,"serve-once":false,"launch":true,"hook":true},
            "launch":{"supported":false,"foregroundOnly":true,"reason":"direct_launch_requires_foreground"},
            "managed":{"supported":true,"controlFile":true,"ttlSeconds":21600,"externalBrowser":false},
            "state":{"stdin":true,"flag":"--state -","default":"unavailable","maxBytes":MAX_STDIN_BYTES},
            "transport":{"host":"127.0.0.1","loopbackOnly":true}
        }),
    )
}

/// Describe the Rust hook adapter. Prompt routing and HUD launch are separate
/// bounded stdin contracts; neither persists prompt text or opens a browser.
fn hook_capability() -> String {
    value_envelope(
        "hook",
        "ok",
        json!({
            "mode":"capability",
            "supported":true,
            "transport":"stdin-json",
            "inputMaxBytes":mission_center_runtime::MAX_HOOK_INPUT_BYTES,
            "supportedEvents":["UserPromptSubmit"],
            "promptRetained":false,
            "sideEffects":false,
            "routing":"rust-bounded-semantic",
            "commands":{"capability":true,"adapter":true,"route":true,"hud":true}
        }),
    )
}

// Keep this matcher deliberately small and allocation-local.  The prompt is
// inspected only for the duration of `hook_route`; it is never put in a
// returned value, logged, or passed to a child process.  This mirrors the
// Python router's `QUOTED_SPAN_PATTERN`: an unterminated span is *not* hidden.
fn hook_visible_prompt(prompt: &str) -> String {
    let chars: Vec<char> = prompt.chars().collect();
    let mut visible = String::with_capacity(prompt.len());
    let mut index = 0;
    while index < chars.len() {
        let (closing, width, allow_newline) = if index + 2 < chars.len()
            && chars[index] == '`'
            && chars[index + 1] == '`'
            && chars[index + 2] == '`'
        {
            (Some("```"), 3, true)
        } else {
            match chars[index] {
                '`' => (Some("`"), 1, false),
                '\'' => (Some("'"), 1, false),
                '"' => (Some("\""), 1, false),
                '「' => (Some("」"), 1, false),
                '『' => (Some("』"), 1, false),
                _ => (None, 0, false),
            }
        };
        let Some(closing) = closing else {
            visible.push(chars[index]);
            index += 1;
            continue;
        };
        let mut end = index + width;
        while end < chars.len() {
            if !allow_newline && matches!(chars[end], '\r' | '\n') {
                break;
            }
            let matched = if closing == "```" {
                end + 2 < chars.len()
                    && chars[end] == '`'
                    && chars[end + 1] == '`'
                    && chars[end + 2] == '`'
            } else {
                chars[end].to_string() == closing
            };
            if matched {
                index = if closing == "```" { end + 3 } else { end + 1 };
                visible.push(' ');
                break;
            }
            end += 1;
        }
        if end >= chars.len()
            || (!allow_newline && end < chars.len() && matches!(chars[end], '\r' | '\n'))
        {
            // No regex match: retain the opener and continue scanning.  This
            // matters for a prompt containing an unclosed quote followed by a
            // real, independently closed quoted span.
            visible.push(chars[index]);
            index += 1;
        }
    }
    visible
}

fn hook_boundary(character: Option<char>, before: bool) -> bool {
    match character {
        None => true,
        Some(value) if before => !(value.is_alphanumeric() || value == '_' || value == '\\'),
        Some(value) => !(value.is_alphanumeric() || value == '_' || value == '-'),
    }
}

fn hook_direct_negation(prefix: &str) -> bool {
    let lower = prefix.to_lowercase();
    let compact = lower.trim_end();
    [
        "不要用",
        "不要使用",
        "不要啟動",
        "不要启动",
        "不要開啟",
        "不要开启",
        "不要執行",
        "不要执行",
        "不要呼叫",
        "別用",
        "別使用",
        "勿用",
        "不必用",
        "禁止用",
        "禁止使用",
        "do not use",
        "don't use",
        "dont use",
        "no need to use",
        "do not invoke",
        "don't invoke",
        "dont invoke",
        "do not open",
        "don't open",
        "dont open",
        "do not launch",
        "don't launch",
        "dont launch",
        "do not run",
        "don't run",
        "dont run",
        "do not activate",
        "don't activate",
        "dont activate",
        "やめて",
        "しないで",
        "하지 마",
    ]
    .iter()
    .any(|word| compact.ends_with(word))
}

fn hook_explicit_invocation(prompt: &str) -> bool {
    let lower = prompt.to_lowercase();
    for token in ["$mission-center", "plugin://mission-center"] {
        let mut start = 0;
        while let Some(relative) = lower[start..].find(token) {
            let position = start + relative;
            let before = lower[..position].chars().next_back();
            let after = lower[position + token.len()..].chars().next();
            if hook_boundary(before, true)
                && hook_boundary(after, false)
                && !hook_direct_negation(
                    &lower[..position]
                        .chars()
                        .rev()
                        .take(32)
                        .collect::<String>()
                        .chars()
                        .rev()
                        .collect::<String>(),
                )
            {
                return true;
            }
            start = position + token.len();
        }
    }
    let mut start = 0;
    while let Some(relative) = lower[start..].find("@mission") {
        let position = start + relative;
        let before = lower[..position].chars().next_back();
        if hook_boundary(before, true) {
            let mut center = position + "@mission".len();
            while matches!(lower[center..].chars().next(), Some(' ' | '\t')) {
                center += 1;
            }
            if center > position + "@mission".len() && lower[center..].starts_with("center") {
                let end = center + "center".len();
                let after = lower[end..].chars().next();
                if hook_boundary(after, false)
                    && !hook_direct_negation(
                        &lower[..position]
                            .chars()
                            .rev()
                            .take(32)
                            .collect::<String>()
                            .chars()
                            .rev()
                            .collect::<String>(),
                    )
                {
                    return true;
                }
            }
        }
        start = position + "@mission".len();
    }
    false
}

fn hook_any(text: &str, values: &[&str]) -> bool {
    let lower = text.to_lowercase();
    values
        .iter()
        .any(|value| lower.contains(&value.to_lowercase()))
}

fn hook_pure_explanation(text: &str) -> bool {
    let mut value = text.trim_start().to_lowercase();
    for prefix in [
        "please ",
        "請幫我",
        "請",
        "请帮我",
        "请",
        "説明して",
        "説明を",
        "설명해줘",
    ] {
        if let Some(rest) = value.strip_prefix(&prefix.to_lowercase()) {
            value = rest.to_owned();
            break;
        }
    }
    [
        "explain", "describe", "解釋", "說明", "解释", "说明", "引用", "quote", "인용",
    ]
    .iter()
    .any(|word| value.starts_with(&word.to_lowercase()))
}

fn hook_negated_request(text: &str) -> bool {
    let mut value = text.trim_start().to_lowercase();
    if let Some(rest) = value.strip_prefix("please") {
        if !rest.chars().next().is_some_and(char::is_whitespace) {
            return false;
        }
        value = rest.trim_start().to_owned();
    } else if let Some(rest) = value
        .strip_prefix('請')
        .or_else(|| value.strip_prefix('请'))
    {
        value = rest.trim_start().to_owned();
    }
    [
        "不要",
        "別",
        "勿",
        "不必",
        "禁止",
        "do not",
        "don't",
        "dont",
        "no need to",
        "やめて",
        "しないで",
        "하지 마",
    ]
    .iter()
    .any(|word| value.starts_with(&word.to_lowercase()))
}

fn hook_near(text: &str, left: &[&str], right: &[&str], max_gap: usize) -> bool {
    let lower = text.to_lowercase();
    let chars: Vec<char> = lower.chars().collect();
    for lhs in left {
        let lhs_chars: Vec<char> = lhs.to_lowercase().chars().collect();
        for rhs in right {
            let rhs_chars: Vec<char> = rhs.to_lowercase().chars().collect();
            if lhs_chars.is_empty() || rhs_chars.is_empty() {
                continue;
            }
            for start in 0..=chars.len().saturating_sub(lhs_chars.len()) {
                if chars[start..].starts_with(&lhs_chars) {
                    let gap_start = start + lhs_chars.len();
                    let max_end = (gap_start + max_gap + rhs_chars.len()).min(chars.len());
                    for end in gap_start..=max_end.saturating_sub(rhs_chars.len()) {
                        if chars[end..].starts_with(&rhs_chars)
                            && !chars[gap_start..end].contains(&'\n')
                        {
                            return true;
                        }
                    }
                }
            }
        }
    }
    false
}

fn hook_standalone_go(text: &str) -> bool {
    let compact: String = text
        .chars()
        .filter(|character| !character.is_whitespace())
        .collect();
    let lower = compact.to_lowercase();
    !lower.is_empty()
        && lower.chars().all(|character| {
            matches!(
                character,
                'g' | 'o'
                    | 'k'
                    | '.'
                    | '!'
                    | '?'
                    | ';'
                    | ':'
                    | ','
                    | '。'
                    | '！'
                    | '？'
                    | '；'
                    | '：'
                    | '，'
                    | '、'
                    | '…'
            )
        })
        && (lower == "go" || lower == "ok" || lower.starts_with("go") || lower.starts_with("ok"))
}

fn hook_resume(text: &str) -> bool {
    let lower = text.to_lowercase();
    hook_any(
        &lower,
        &[
            "恢復",
            "恢复",
            "繼續任務",
            "继续任务",
            "繼續工作區",
            "继续工作区",
            "再開",
            "再開する",
            "続き",
            "재개",
            "계속",
        ],
    ) || hook_near(
        &lower,
        &[
            "resume", "continue", "pick up", "carry on", "recover", "restart",
        ],
        &[
            "missioncenter",
            "mission center",
            "mission",
            "workspace",
            "work",
        ],
        24,
    ) || hook_near(
        &lower,
        &[
            "missioncenter",
            "mission center",
            "mission",
            "workspace",
            "work",
        ],
        &["resume", "continue", "recover", "restart"],
        24,
    )
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum HookRoute {
    Explicit,
    Semantic,
    Resume,
}

fn hook_route_prompt(prompt: &str, cwd: Option<&str>) -> Option<HookRoute> {
    if prompt.is_empty() || prompt.chars().count() > 12_000 {
        return None;
    }
    let visible = hook_visible_prompt(prompt);
    if visible.trim().is_empty() || hook_pure_explanation(&visible) {
        return None;
    }
    if hook_explicit_invocation(&visible) {
        return Some(HookRoute::Explicit);
    }
    if hook_negated_request(&visible) {
        return None;
    }
    let high_impact = hook_any(
        &visible,
        &[
            "高影響",
            "高風險",
            "重大",
            "關鍵",
            "嚴重",
            "高影响",
            "高风险",
            "关键",
            "严重",
            "high-impact",
            "high impact",
            "high-risk",
            "high risk",
            "critical",
            "security",
            "production",
            "migration",
            "高い影響",
            "重要",
            "高リスク",
            "重大な",
            "높은 영향",
            "고위험",
            "중요",
            "보안",
            "마이그레이션",
        ],
    );
    let multi_step = hook_any(
        &visible,
        &[
            "多步驟",
            "多階段",
            "跨模組",
            "跨團隊",
            "跨專案",
            "多步骤",
            "多阶段",
            "跨模块",
            "跨团队",
            "跨项目",
            "multi-step",
            "multi step",
            "multi-phase",
            "multi phase",
            "multiple steps",
            "several steps",
            "cross-team",
            "cross team",
            "cross-module",
            "cross project",
            "複数ステップ",
            "複数段階",
            "複数の工程",
            "複数フェーズ",
            "여러 단계",
            "다단계",
            "여러 작업",
        ],
    );
    let planning = hook_any(
        &visible,
        &[
            "專案規劃",
            "專案計畫",
            "任務規劃",
            "任務計畫",
            "项目规划",
            "项目计划",
            "任务规划",
            "里程碑",
            "路线图",
            "project planning",
            "project plan",
            "roadmap",
            "milestone",
            "plan a project",
            "プロジェクト計画",
            "計画を立て",
            "ロードマップ",
            "マイルストーン",
            "프로젝트 계획",
            "로드맵",
            "마일스톤",
        ],
    ) || hook_near(&visible, &["規劃"], &["專案", "目標", "任務"], 12)
        || hook_near(&visible, &["專案", "目標", "任務"], &["規劃"], 12)
        || hook_near(&visible, &["规划"], &["项目", "目标", "任务"], 12)
        || hook_near(&visible, &["项目", "目标", "任务"], &["规划"], 12);
    if (high_impact || multi_step) && planning {
        return Some(HookRoute::Semantic);
    }
    if (hook_resume(&visible) || hook_standalone_go(&visible))
        && cwd.is_some_and(|value| {
            Path::new(value)
                .join("MissionCenter")
                .join("tasks.md")
                .is_file()
        })
    {
        return Some(HookRoute::Resume);
    }
    None
}

fn hook_route() -> String {
    let bytes = match read_stdin_bounded(mission_center_runtime::MAX_HOOK_INPUT_BYTES) {
        Ok(bytes) => bytes,
        Err(_) => return "{}".to_owned(),
    };
    let raw: Value = match serde_json::from_slice(&bytes) {
        Ok(value) => value,
        Err(_) => return "{}".to_owned(),
    };
    let prompt = raw.get("prompt").and_then(Value::as_str);
    let input = match mission_center_runtime::parse_bounded_hook_input(&bytes) {
        Ok(Some(value)) => value,
        _ => return "{}".to_owned(),
    };
    let Some(route) = prompt.and_then(|value| hook_route_prompt(value, input.cwd.as_deref()))
    else {
        return "{}".to_owned();
    };
    if input.hook_event_name != "UserPromptSubmit" {
        return "{}".to_owned();
    }
    let context = if route == HookRoute::Explicit {
        "Explicit Mission Center request detected; follow bounded intake, approval, and evidence gates."
    } else if route == HookRoute::Resume {
        "An existing MissionCenter workspace is present; consider bounded Mission Center resume routing before changing task state."
    } else {
        "This appears to be a high-impact or multi-step project request; consider Mission Center intake, research, approval, and evidence gates."
    };
    json!({"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":context}})
        .to_string()
}

/// Validate one bounded host hook payload and return a fixed, non-sensitive
/// result.  The `route` mode is the only host-facing semantic path; it
/// inspects prompt text transiently and never returns, logs, or persists it.
/// The adapter/validate modes remain a non-routing capability probe.
fn hook_run(mode: &str, args: &[String]) -> Result<String, String> {
    if mode == "capability" {
        strict_new_flags(args, &[], &[])?;
        return Ok(hook_capability());
    }
    if mode == "route" {
        strict_new_flags(args, &[], &[])?;
        return Ok(hook_route());
    }
    if mode == "hud" {
        strict_new_flags(args, &[], &[])?;
        return Ok(hook_hud());
    }
    if !matches!(mode, "adapter" | "validate") {
        return Err(format!("unknown subcommand: {mode}"));
    }
    strict_new_flags(args, &[], &[])?;
    let input = mission_center_runtime::parse_bounded_hook_input(&read_stdin_bounded(
        mission_center_runtime::MAX_HOOK_INPUT_BYTES,
    )?)
    .map_err(|error| error.to_string())?;
    let Some(input) = input else {
        return Ok(value_envelope(
            "hook",
            "ignored",
            json!({
                "mode":"adapter",
                "accepted":false,
                "reason":"empty-input",
                "promptRetained":false,
                "sideEffects":false
            }),
        ));
    };
    if input.hook_event_name != "UserPromptSubmit" {
        return Ok(value_envelope(
            "hook",
            "ignored",
            json!({
                "mode":"adapter",
                "accepted":false,
                "reason":"invalid-hook-event",
                "promptRetained":false,
                "sideEffects":false
            }),
        ));
    }
    Ok(value_envelope(
        "hook",
        "ok",
        json!({
            "mode":"adapter",
            "accepted":true,
            "event":"UserPromptSubmit",
            "route":"deferred",
            "reason":"prompt-routing-owned-by-host",
            "promptRetained":false,
            "sideEffects":false
        }),
    ))
}

fn hud_run(mode: &str, root: PathBuf, args: &[String]) -> Result<String, String> {
    if mode == "capability" {
        strict_new_flags(args, &[], &[])?;
        return Ok(hud_capability());
    }
    if mode == "serve" {
        return hud_serve_run(root, args);
    }
    if !matches!(mode, "serve-once" | "launch") {
        return Err(format!("unknown subcommand: {mode}"));
    }
    strict_new_flags(
        args,
        &[
            "--host",
            "--nonce",
            "--operation-id",
            "--port",
            "--state",
            "--timeout-ms",
        ],
        &["--foreground", "--open"],
    )?;
    let foreground = mode == "launch" && args.iter().any(|value| value == "--foreground");
    if mode == "launch" && !foreground {
        return Ok(error_with_data(
            "hud",
            "unsupported",
            "hud launch 需要 --foreground；process 結束後 server 無法存活",
            json!({
                "mode":"launch",
                "supported":false,
                "foregroundOnly":true,
                "persistent":false,
                "reused":false,
                "opened":false,
                "operationId":flag_value(args,"--operation-id"),
                "written":false
            }),
        ));
    }
    if mode == "serve-once" {
        return Ok(error_with_data(
            "hud",
            "unsupported",
            "hud serve-once 無法以單一 envelope 表達 serving 與 terminal 結果",
            json!({
                "mode": "serve-once",
                "supported": false,
                "persistent": false,
                "written": false
            }),
        ));
    }
    if mode == "serve-once" && args.iter().any(|value| value == "--open") {
        return Err(
            "argument_error: hud serve-once 不支援 --open；請用 hud launch --foreground".to_owned(),
        );
    }
    if foreground && flag_value(args, "--state").as_deref() == Some("-") {
        return Err(
            "argument_error: hud launch --foreground 不可與 --state - 組合；stdin 用於 shutdown"
                .to_owned(),
        );
    }
    let timeout_millis = flag_value(args, "--timeout-ms")
        .map(|value| {
            let millis = value
                .parse::<u64>()
                .map_err(|_| "argument_error: --timeout-ms 必須是整數".to_owned())?;
            if !(100..=30_000).contains(&millis) {
                return Err("argument_error: --timeout-ms 必須介於 100..30000".to_owned());
            }
            Ok(millis)
        })
        .transpose()?;
    if foreground && timeout_millis.is_some() {
        return Err("argument_error: --timeout-ms 僅適用於 hud serve-once".to_owned());
    }
    let host = flag_value(args, "--host").unwrap_or_else(|| "127.0.0.1".to_owned());
    mission_center_runtime::validate_loopback_host(&host).map_err(|error| error.to_string())?;
    if host != "127.0.0.1" {
        return Err("invalid_host: HUD server 僅支援 127.0.0.1".to_owned());
    }
    let port = flag_value(args, "--port")
        .map(|value| {
            value
                .parse::<u16>()
                .map_err(|_| "argument_error: --port 必須是 0..65535".to_owned())
        })
        .transpose()?;
    let nonce = flag_value(args, "--nonce");
    if nonce
        .as_ref()
        .is_some_and(|value| value.is_empty() || value.len() > 128)
    {
        return Err("argument_error: --nonce 長度無效".to_owned());
    }
    let operation_id = flag_value(args, "--operation-id");
    if operation_id
        .as_ref()
        .is_some_and(|value| value.is_empty() || value.len() > 128)
    {
        return Err("argument_error: --operation-id 長度無效".to_owned());
    }
    let state = hud_state(args)?;
    let assets = frozen_hud_assets(&state)?;
    let mut config = HudServerConfig::new(root)
        .with_port(port.unwrap_or(0))
        .with_state(state)
        .with_frozen_assets(assets);
    if let Some(nonce) = nonce {
        config = config.with_nonce(nonce);
    }
    let launcher = if args.iter().any(|value| value == "--open") {
        HudLauncher::with_opener(Arc::new(SystemBrowserOpener))
    } else {
        HudLauncher::new()
    };
    let outcome = launcher
        .launch(config, args.iter().any(|value| value == "--open"))
        .map_err(|error| error.to_string())?;
    let reused = matches!(
        outcome.status,
        LaunchStatus::Reused | LaunchStatus::Cooldown
    );
    let data = json!({
        "mode":mode,
        "phase":"serving",
        "requestScope":if mode == "serve-once" { "single_health_state_or_asset_fetch" } else { "foreground_session" },
        "supported":true,
        "lifecycle":"foreground",
        "persistent":false,
        "launchStatus":outcome.status,
        "url":outcome.url,
        "port":outcome.server.port(),
        "loopback":true,
        "reused":reused,
        "opened":outcome.browser_opened,
        "browserStatus":outcome.browser_status,
        "sidePanelIntent":hud_side_panel_intent(
            &outcome.url,
            &outcome.workspace_fingerprint,
            &outcome.hud_asset_fingerprint
        ),
        "presentation": {
            "status": if args.iter().any(|value| value == "--open") { "not_supported" } else { "not_requested" },
            "surface": "codex-sidebar-or-preview",
            "externalBrowserRequested": args.iter().any(|value| value == "--open")
        },
        "workspaceFingerprint":outcome.workspace_fingerprint,
        "hudAssetFingerprint":outcome.hud_asset_fingerprint,
        "assetFingerprint":outcome.hud_asset_fingerprint,
        "version":outcome.version,
        "operationId":operation_id
    });
    let output = value_envelope("hud", "ok", data);
    let wait_result = read_stdin_bounded(MAX_STDIN_BYTES);
    let shutdown_result = launcher.shutdown_all();
    shutdown_result.map_err(|error| error.to_string())?;
    wait_result.map(|_| ())?;
    Ok(output)
}

fn run(command: &str, root: PathBuf, args: &[String]) -> Result<String, String> {
    if command == "help" {
        if args.len() > 1 {
            return Err("help accepts at most one command".to_owned());
        }
        return help_envelope(command, args.first().map(String::as_str));
    }
    if args
        .iter()
        .any(|value| matches!(value.as_str(), "--help" | "-h"))
    {
        if args.len() != 1 {
            return Err("--help cannot be combined with other arguments".to_owned());
        }
        return help_envelope(command, Some(command));
    }
    if command == "hook" {
        let mode = args.first().map(String::as_str).unwrap_or("capability");
        let flags = if !args.is_empty() { &args[1..] } else { args };
        return hook_run(mode, flags);
    }
    if command == "runtime" {
        let mode = args.first().map(String::as_str).unwrap_or("capability");
        let flags = args.get(1..).unwrap_or(&[]);
        return runtime_run(mode, flags);
    }
    if command == "hud" {
        let mode = args.first().map(String::as_str).unwrap_or("capability");
        let flags = if !args.is_empty() { &args[1..] } else { args };
        return hud_run(mode, root, flags);
    }
    if command == "publish" {
        let has_mode = args.first().is_some_and(|value| !value.starts_with('-'));
        let mode = if has_mode {
            args.first().map(String::as_str).unwrap_or("publish")
        } else {
            "publish"
        };
        if matches!(mode, "apply" | "rollback") {
            return native_publish_run(mode, if has_mode { &args[1..] } else { args });
        }
        if mode == "reconcile" {
            return native_reconcile_run(
                "publish",
                &root,
                if has_mode { &args[1..] } else { args },
            );
        }
        return publish_run(mode, if has_mode { &args[1..] } else { args });
    }
    if command == "install" {
        if args.first().map(String::as_str) == Some("register") {
            let mode = args.get(1).map(String::as_str).unwrap_or("apply");
            return native_registration_run(mode, &args[2..]);
        }
        if args.first().map(String::as_str) == Some("stage") {
            return publish_stage("install", &args[1..]);
        }
        if matches!(args.first().map(String::as_str), Some("apply" | "rollback")) {
            return native_install_run(args.first().map(String::as_str).unwrap(), &args[1..]);
        }
        if args.first().map(String::as_str) == Some("reconcile") {
            return native_reconcile_run("install", &root, &args[1..]);
        }
        // The final CLI contract uses `install --package ...` as the native
        // installer form. Keep a bare `install` fail-closed for compatibility,
        // but never route an explicit package request through the old
        // non-mutating staging adapter.
        if args.iter().any(|value| value == "--package") {
            return native_install_run("apply", args);
        }
        return publish_run("install", args);
    }
    if command == "reconcile"
        && args
            .iter()
            .any(|value| value == "--transaction-root" || value.starts_with("--transaction-root="))
    {
        strict_new_flags(args, &["--transaction-root"], &[])?;
        let transaction_root = required_arg(args, "--transaction-root")?;
        return native_reconcile_run("reconcile", Path::new(&transaction_root), &[]);
    }
    if matches!(
        command,
        "research"
            | "optimize"
            | "steelman"
            | "critic"
            | "shift-loss"
            | "security"
            | "compatibility"
    ) {
        return policy_run(command, &root, args);
    }
    validate_workspace_flags(command, args)?;
    let ws = MissionWorkspace::new(root);
    if command == "init" {
        let operation_id = required_arg(args, "--operation-id")?;
        let timestamp = required_arg(args, "--timestamp")?;
        let language = optional_arg(args, "--language").unwrap_or_else(|| "auto".to_owned());
        let force = args.iter().any(|value| value == "--force");
        let before = ws.operation_status(&operation_id).ok().as_deref() == Some("committed");
        let outcome = ws
            .init(&operation_id, &timestamp, &language, force)
            .map_err(|error| error.to_string())?;
        return Ok(envelope(
            command,
            if before || outcome == mission_center_workspace::WriteOutcome::Unchanged {
                "replay"
            } else {
                "committed"
            },
            &format!(
                "{{\"changed\":{},\"operationId\":\"{}\",\"hudAssets\":\"unsupported\"}}",
                outcome == mission_center_workspace::WriteOutcome::Changed,
                escape(&operation_id)
            ),
        ));
    }
    if command == "normalize" {
        let operation_id = required_arg(args, "--operation-id")?;
        let timestamp = required_arg(args, "--timestamp")?;
        let outcome = ws
            .normalize_tasks(&operation_id, &timestamp)
            .map_err(|error| error.to_string())?;
        return Ok(envelope(
            command,
            if outcome == mission_center_workspace::WriteOutcome::Unchanged {
                "replay"
            } else {
                "committed"
            },
            &format!(
                "{{\"changed\":{}}}",
                outcome == mission_center_workspace::WriteOutcome::Changed
            ),
        ));
    }
    // Transition reads and validates the canonical task table under the
    // workspace writer lock. Avoid a pre-lock task snapshot for this command;
    // it could report a task as unknown or return a stale `from` status when
    // another writer updates tasks.md between the two reads.
    let (text, tasks) = if command == "transition" {
        (String::new(), Vec::new())
    } else {
        ws.read_tasks().map_err(|e| e.to_string())?
    };
    match command {
        "sync" => {
            let operation_id = required_arg(args, "--operation-id")?;
            let timestamp = required_arg(args, "--timestamp")?;
            let options = SyncOptions {
                project: optional_arg(args, "--project"),
                cycle: optional_arg(args, "--cycle"),
                goal: optional_arg(args, "--goal"),
                labels: optional_arg(args, "--labels"),
                milestone: optional_arg(args, "--milestone"),
                rewrite_summaries: args.iter().any(|value| value == "--rewrite-summaries"),
            };
            let before = ws.operation_status(&operation_id).ok().as_deref() == Some("committed");
            let outcome = ws
                .sync_with_options(&operation_id, &timestamp, &options)
                .map_err(|error| error.to_string())?;
            Ok(envelope(
                command,
                if before || outcome == mission_center_workspace::WriteOutcome::Unchanged {
                    "replay"
                } else {
                    "committed"
                },
                &format!(
                    "{{\"changed\":{},\"operationId\":\"{}\",\"tasksSource\":\"MissionCenter/tasks.md\",\"hudState\":\"unsupported\"}}",
                    outcome == mission_center_workspace::WriteOutcome::Changed,
                    escape(&operation_id)
                ),
            ))
        }
        "status" => {
            let mut values = String::new();
            for (index, task) in tasks.iter().enumerate() {
                if index > 0 {
                    values.push(',');
                }
                values.push_str(&task_json(task));
            }
            let date = date_arg(args).unwrap_or_else(today_local);
            if !valid_date(&date) {
                return Err("--date must use YYYY-MM-DD".to_owned());
            }
            let mission = ws.mission_dir();
            let required = [
                "brief.md",
                "working-set.md",
                "guardrails.md",
                "daily-log.md",
                "critical-lessons.md",
            ];
            let missing: Vec<String> = required
                .iter()
                .filter(|name| !ws.artifact_exists(name).unwrap_or(false))
                .map(|name| (*name).to_owned())
                .collect();
            let fingerprint = ws.fingerprint().map_err(|e| e.to_string())?;
            let task_fp =
                mission_center_core::workspace_fingerprint(&[("tasks.md", Some(text.as_bytes()))]);
            let brief = ws
                .read_path_text(&mission.join("brief.md"), 64 * 1024)
                .map_err(|e| e.to_string())?
                .unwrap_or_default();
            let working = ws
                .read_path_text(&mission.join("working-set.md"), 64 * 1024)
                .map_err(|e| e.to_string())?
                .unwrap_or_default();
            let source_fresh = missing.is_empty()
                && marker_fingerprint(&brief) == Some(fingerprint.as_str())
                && marker_fingerprint(&working) == Some(task_fp.as_str());
            let daily = ws
                .read_path_text(&mission.join("daily-log.md"), DAILY_LOG_MAX_BYTES)
                .map_err(|e| e.to_string())?
                .unwrap_or_default();
            let date_fresh = organized_date(&daily).as_deref() == Some(date.as_str());
            let mut stale_reasons = Vec::new();
            if !missing.is_empty() {
                stale_reasons.push("missing_required_files");
            }
            if !source_fresh && missing.is_empty() {
                stale_reasons.push("source_fingerprint_mismatch");
            }
            if !date_fresh {
                stale_reasons.push("organized_date_mismatch");
            }
            let work = working_set(&tasks);
            let focus_ids: Vec<String> = tasks
                .iter()
                .filter(|task| {
                    task.priority.eq_ignore_ascii_case("P0") && task.status != TaskStatus::Done
                })
                .map(|task| task.id.clone())
                .collect();
            let active: Vec<String> = tasks
                .iter()
                .filter(|task| task.status != TaskStatus::Done)
                .map(|task| task.id.clone())
                .collect();
            let blocked = task_ids(&tasks, Some(TaskStatus::Blocked), None);
            let body = format!(
                "{{\"taskCount\":{},\"tasks\":[{}],\"date\":\"{}\",\"sourceFresh\":{},\"dateFresh\":{},\"stale\":{},\"staleReasons\":[{}],\"missing\":{},\"fingerprint\":\"{}\",\"workingSetTasks\":{},\"focusTasks\":{},\"workingSetCount\":{},\"activeTasks\":{},\"blockedTasks\":{},\"briefBytes\":{}}}",
                tasks.len(),
                values,
                date,
                source_fresh,
                date_fresh,
                !source_fresh || !date_fresh,
                stale_reasons
                    .iter()
                    .map(|reason| format!("\"{reason}\""))
                    .collect::<Vec<_>>()
                    .join(","),
                ids_json(&missing),
                fingerprint,
                ids_json(&work),
                ids_json(&focus_ids),
                work.len(),
                ids_json(&active),
                ids_json(&blocked),
                brief.len()
            );
            Ok(envelope(
                command,
                if !source_fresh || !date_fresh {
                    "stale"
                } else {
                    "ok"
                },
                &body,
            ))
        }
        "resume" => {
            let date = date_arg(args).unwrap_or_else(today_local);
            if !valid_date(&date) {
                return Err("--date must use YYYY-MM-DD".to_owned());
            }
            let packet = resume_packet(&ws, &tasks, &date)?;
            Ok(value_envelope(command, "ok", packet))
        }
        "doctor" => {
            validate_tasks(&tasks).map_err(|e| e.to_string())?;
            let mut passport_status = "pass";
            let mut passport_detail = Vec::new();
            let done_tasks = tasks
                .iter()
                .filter(|task| task.status == TaskStatus::Done)
                .collect::<Vec<_>>();
            if done_tasks.is_empty() {
                passport_status = "unknown";
                passport_detail.push("no Done tasks require a completion passport".to_owned());
            }
            for task in done_tasks {
                match ws.completion_passport_check(task) {
                    Ok(None) => {
                        if passport_status != "error" {
                            passport_status = "unknown";
                        }
                        passport_detail.push(format!(
                            "{} has no completion passport (legacy warning)",
                            task.id
                        ));
                    }
                    Ok(Some(errors)) if errors.is_empty() => {}
                    Ok(Some(errors)) => {
                        passport_status = "error";
                        passport_detail.push(format!("{}: {}", task.id, errors.join("; ")));
                    }
                    Err(error) => {
                        passport_status = "error";
                        passport_detail.push(format!("{}: {error}", task.id));
                    }
                }
            }
            let passport_check = json!({
                "name": "completion_passport",
                "status": passport_status,
                "details": passport_detail,
            });
            let lock_recovery = ws
                .writer_lock_recovery_artifact()
                .map_err(|error| error.to_string())?;
            let lock_status = if lock_recovery.is_some() {
                "error"
            } else {
                "pass"
            };
            let lock_check = json!({
                "name": "writer_lock_recovery",
                "status": lock_status,
                "details": lock_recovery
                    .map(|path| vec![format!("recovery tombstone requires explicit reconciliation: {}", path.display())])
                    .unwrap_or_default(),
            });
            let report = json!({
                "checks": [
                    {"name":"tasks","status":"pass"},
                    passport_check,
                    lock_check,
                ],
                "taskCount": tasks.len(),
            });
            if passport_status == "error" || lock_status == "error" {
                Ok(value_envelope(command, "error", report))
            } else {
                Ok(envelope(
                    command,
                    "pass",
                    &serde_json::to_string(&report).map_err(|error| error.to_string())?,
                ))
            }
        }
        "reconcile" => {
            let date = date_arg(args).unwrap_or_else(today_local);
            if !valid_date(&date) {
                return Err("--date must use YYYY-MM-DD".to_owned());
            }
            let report = reconcile_workspace_checks(&ws, &tasks, &date)?;
            let overall = report["status"].as_str().unwrap_or("unknown").to_owned();
            Ok(value_envelope(command, &overall, report))
        }
        "verify" => Ok(envelope(
            command,
            "pass",
            &format!(
                "{{\"digest\":\"{}\",\"algorithm\":\"sha256\"}}",
                sha256_digest(&canonicalize_hash_bytes(text.as_bytes()))
            ),
        )),
        "snapshot" => {
            let operation_id = required_arg(args, "--operation-id")?;
            let timestamp = required_arg(args, "--timestamp")?;
            let note = repeated_arg_values(args, "--note").last().cloned();
            let attempts = repeated_arg_values(args, "--attempt")
                .into_iter()
                .map(|raw| {
                    serde_json::from_str::<Value>(&raw)
                        .map_err(|error| format!("invalid attempt JSON: {error}"))
                })
                .collect::<Result<Vec<_>, _>>()?;
            let hypotheses = repeated_arg_values(args, "--hypothesis");
            let evidences = repeated_arg_values(args, "--evidence");
            let verification_result = optional_arg(args, "--verification-result");
            let verification_action = optional_arg(args, "--verification-action");
            let verification_evidence = optional_arg(args, "--verification-evidence");
            let before = ws.operation_status(&operation_id).ok().as_deref() == Some("committed");
            let outcome = ws
                .write_snapshot_with_options(
                    &operation_id,
                    &timestamp,
                    mission_center_workspace::SnapshotOptions {
                        note,
                        attempts,
                        hypotheses,
                        evidences,
                        verification_result,
                        verification_action,
                        verification_evidence,
                    },
                )
                .map_err(|error| error.to_string())?;
            Ok(envelope(
                command,
                if before || outcome == mission_center_workspace::WriteOutcome::Unchanged {
                    "replay"
                } else {
                    "committed"
                },
                "{\"written\":true}",
            ))
        }
        "pulse" => {
            let task_id_owned = optional_arg(args, "--task-id")
                .or_else(|| {
                    args.first()
                        .filter(|value| !value.starts_with('-'))
                        .cloned()
                })
                .ok_or_else(|| "pulse requires --task-id TASK_ID".to_owned())?;
            let task_id = task_id_owned.as_str();
            let operation_id = required_arg(args, "--operation-id")?;
            let pulse_id = optional_arg(args, "--pulse-id").unwrap_or_else(|| {
                format!(
                    "pulse-{}",
                    mission_center_core::sha256_digest(operation_id.as_bytes())
                )
            });
            let phase = required_arg(args, "--phase")?;
            let pulse_outcome = required_arg(args, "--outcome")?;
            let evidence_ref = optional_arg(args, "--evidence-ref").unwrap_or_default();
            let recorded_at = optional_arg(args, "--recorded-at")
                .or_else(|| optional_arg(args, "--timestamp"))
                .ok_or_else(|| "missing required argument: --recorded-at".to_owned())?;
            let next_action = required_arg(args, "--next-action")?;
            let budget = optional_arg(args, "--budget-remaining")
                .unwrap_or_else(|| "0".to_owned())
                .parse::<u64>()
                .map_err(|_| "invalid --budget-remaining".to_owned())?;
            let parent = optional_arg(args, "--causal-parent");
            let outcome = ws
                .append_pulse_full(
                    &operation_id,
                    &pulse_id,
                    task_id,
                    &phase,
                    &pulse_outcome,
                    &next_action,
                    &evidence_ref,
                    &recorded_at,
                    budget,
                    parent.as_deref(),
                )
                .map_err(|error| error.to_string())?;
            Ok(envelope(
                command,
                if outcome == mission_center_workspace::OperationOutcome::Replay {
                    "replay"
                } else {
                    "committed"
                },
                &format!(
                    "{{\"pulseId\":\"{}\",\"taskId\":\"{}\"}}",
                    escape(&pulse_id),
                    escape(task_id)
                ),
            ))
        }
        "handoff" => {
            let task_id_owned = optional_arg(args, "--task-id").or_else(|| {
                args.first()
                    .filter(|value| !value.starts_with('-'))
                    .cloned()
            });
            let body = ws
                .handoff_json(task_id_owned.as_deref())
                .map_err(|error| error.to_string())?;
            Ok(envelope(command, "ok", &body))
        }
        "closeout" => {
            validate_flags(
                args,
                &[
                    "--operation-id",
                    "--timestamp",
                    "--cycle",
                    "--archive",
                    "--summary",
                    "--completed",
                    "--unfinished",
                    "--risks",
                    "--smoke-tests",
                    "--retro",
                ],
            )?;
            let operation_id = required_arg(args, "--operation-id")?;
            let timestamp = required_arg(args, "--timestamp")?;
            let cycle = required_arg(args, "--cycle")?;
            let archive = args.iter().any(|value| value == "--archive");
            let summary = required_arg(args, "--summary")?;
            let detail_values = [
                ("Summary", Some(summary)),
                ("Completed", optional_arg(args, "--completed")),
                ("Unfinished", optional_arg(args, "--unfinished")),
                ("Risks", optional_arg(args, "--risks")),
                ("Smoke tests", optional_arg(args, "--smoke-tests")),
                ("Retro", optional_arg(args, "--retro")),
            ];
            let details = detail_values
                .iter()
                .filter_map(|(key, value)| value.as_deref().map(|value| (*key, value)))
                .collect::<Vec<_>>();
            let replay = ws.operation_status(&operation_id).ok().as_deref() == Some("committed");
            let outcome = ws
                .closeout_with_details(&operation_id, &timestamp, &cycle, archive, &details)
                .map_err(|error| error.to_string())?;
            Ok(envelope(
                command,
                if replay || outcome == mission_center_workspace::OperationOutcome::Replay {
                    "replay"
                } else {
                    "committed"
                },
                &format!(
                    "{{\"cycle\":\"{}\",\"archive\":{}}}",
                    escape(&cycle),
                    if archive { "true" } else { "false" }
                ),
            ))
        }
        "project-map" => {
            validate_flags(
                args,
                &["--operation-id", "--timestamp", "--dry-run", "--verify"],
            )?;
            let dry_run = args.iter().any(|value| value == "--dry-run");
            let verify = args.iter().any(|value| value == "--verify");
            if dry_run && verify {
                return Err("--dry-run and --verify are mutually exclusive".to_owned());
            }
            let operation_id = optional_arg(args, "--operation-id");
            let timestamp = optional_arg(args, "--timestamp");
            if verify {
                ws.verify_project_map().map_err(|error| error.to_string())?;
                return Ok(envelope(command, "ok", "{\"verified\":true}"));
            }
            let replay = operation_id
                .as_deref()
                .and_then(|id| ws.operation_status(id).ok())
                .is_some_and(|status| status == "committed");
            let body = ws
                .project_map(operation_id.as_deref(), timestamp.as_deref(), dry_run)
                .map_err(|error| error.to_string())?;
            Ok(envelope(
                command,
                if dry_run {
                    "ok"
                } else if replay {
                    "replay"
                } else {
                    "committed"
                },
                &body,
            ))
        }
        "claim" => {
            let task_id = args
                .first()
                .ok_or_else(|| "claim requires TASK_ID".to_owned())?;
            let owner = required_arg(args, "--owner")?;
            let fence = required_arg(args, "--fence")?
                .parse::<u64>()
                .map_err(|_| "invalid --fence".to_owned())?;
            let expires_at = required_arg(args, "--expires-at")?;
            let now = required_arg(args, "--now")?;
            let operation_id = required_arg(args, "--operation-id")?;
            let timestamp = optional_arg(args, "--timestamp")
                .or_else(|| optional_arg(args, "--committed-at"))
                .ok_or_else(|| "missing required argument: --timestamp".to_owned())?;
            let replay = ws.operation_status(&operation_id).ok().as_deref() == Some("committed");
            let record = ws
                .claim(
                    task_id,
                    &owner,
                    fence,
                    &expires_at,
                    &now,
                    &operation_id,
                    &timestamp,
                )
                .map_err(|e| e.to_string())?;
            Ok(envelope(
                command,
                if replay { "replay" } else { "committed" },
                &format!(
                    "{{\"taskId\":\"{}\",\"owner\":\"{}\",\"fence\":{},\"expiresAt\":\"{}\",\"operationId\":\"{}\"}}",
                    escape(&record.task_id),
                    escape(&record.owner),
                    record.fence,
                    escape(&record.expires_at),
                    escape(&record.operation_id)
                ),
            ))
        }
        "release-claim" => {
            let task_id = args
                .first()
                .ok_or_else(|| "release-claim requires TASK_ID".to_owned())?;
            let owner = required_arg(args, "--owner")?;
            let fence = required_arg(args, "--fence")?
                .parse::<u64>()
                .map_err(|_| "invalid --fence".to_owned())?;
            let operation_id = required_arg(args, "--operation-id")?;
            let timestamp = optional_arg(args, "--timestamp")
                .or_else(|| optional_arg(args, "--committed-at"))
                .ok_or_else(|| "missing required argument: --timestamp".to_owned())?;
            let replay = ws.operation_status(&operation_id).ok().as_deref() == Some("committed");
            ws.release_claim(task_id, &owner, fence, &operation_id, &timestamp)
                .map_err(|e| e.to_string())?;
            Ok(envelope(
                command,
                if replay { "replay" } else { "committed" },
                &format!(
                    "{{\"taskId\":\"{}\",\"owner\":\"{}\",\"fence\":{},\"operationId\":\"{}\"}}",
                    escape(task_id),
                    escape(&owner),
                    fence,
                    escape(&operation_id)
                ),
            ))
        }
        "transition" => {
            let task_id = args
                .first()
                .ok_or_else(|| "transition requires TASK_ID and STATUS".to_owned())?;
            let target = args
                .get(1)
                .ok_or_else(|| "transition requires TASK_ID and STATUS".to_owned())?;
            let target = TaskStatus::parse(target).map_err(|e| e.to_string())?;
            let operation_id = required_arg(args, "--operation-id")?;
            let timestamp = required_arg(args, "--timestamp")?;
            let result = ws
                .transition_task_with_status(&operation_id, task_id, target, &timestamp)
                .map_err(|e| e.to_string())?;
            Ok(envelope(
                command,
                if result.outcome == mission_center_workspace::WriteOutcome::Unchanged {
                    "replay"
                } else {
                    "committed"
                },
                &format!(
                    "{{\"taskId\":{},\"from\":{},\"to\":{},\"written\":{},\"operationId\":{}}}",
                    json_quote(task_id),
                    json_quote(result.from.as_str()),
                    json_quote(result.to.as_str()),
                    result.outcome == mission_center_workspace::WriteOutcome::Changed,
                    json_quote(&operation_id)
                ),
            ))
        }
        _ => Err(format!("unknown command: {command}")),
    }
}

fn contains_sensitive_output(value: &Value) -> bool {
    match value {
        Value::Array(values) => values.iter().any(contains_sensitive_output),
        Value::Object(object) => object.iter().any(|(key, value)| {
            let key = key.to_ascii_lowercase();
            key == "secret"
                || key == "secrets"
                || key == "token"
                || key == "password"
                || key == "authorization"
                || key == "credential"
                || key == "credentials"
                || contains_sensitive_output(value)
        }),
        Value::String(text) => {
            let lower = text.to_ascii_lowercase();
            bearer_value_is_sensitive(&lower)
                || lower.contains("api_key=")
                || lower.contains("token=")
                || lower.contains("password=")
                || lower.contains("-----begin ")
        }
        _ => false,
    }
}

fn bearer_value_is_sensitive(lower: &str) -> bool {
    lower.match_indices("bearer ").any(|(index, marker)| {
        let rest = &lower[index + marker.len()..];
        rest.split_whitespace()
            .next()
            .is_some_and(|value| !value.eq_ignore_ascii_case("key"))
    })
}

// Keep the machine ABI validator driven by the checked-in schema.  This small
// interpreter intentionally implements the JSON-Schema keywords used by the
// envelope so the binary and the fixture cannot silently drift apart.
fn schema_value_matches(value: &Value, schema: &Value) -> bool {
    if let Some(expected) = schema.get("const")
        && value != expected
    {
        return false;
    }
    if let Some(values) = schema.get("enum").and_then(Value::as_array)
        && !values.iter().any(|expected| expected == value)
    {
        return false;
    }
    if let Some(kind) = schema.get("type").and_then(Value::as_str) {
        let matches = match kind {
            "null" => value.is_null(),
            "boolean" => value.is_boolean(),
            "object" => value.is_object(),
            "array" => value.is_array(),
            "string" => value.is_string(),
            "number" => value.is_number(),
            "integer" => value.as_i64().is_some() || value.as_u64().is_some(),
            _ => false,
        };
        if !matches {
            return false;
        }
    }
    if let Some(text) = value.as_str()
        && (schema
            .get("minLength")
            .and_then(Value::as_u64)
            .is_some_and(|limit| text.chars().count() < limit as usize)
            || schema
                .get("maxLength")
                .and_then(Value::as_u64)
                .is_some_and(|limit| text.chars().count() > limit as usize))
    {
        return false;
    }
    if let Some(object) = value.as_object() {
        if schema
            .get("required")
            .and_then(Value::as_array)
            .is_some_and(|required| {
                required
                    .iter()
                    .any(|key| key.as_str().is_none_or(|key| !object.contains_key(key)))
            })
        {
            return false;
        }
        if let Some(properties) = schema.get("properties").and_then(Value::as_object) {
            for (key, property_schema) in properties {
                if let Some(child) = object.get(key)
                    && !schema_value_matches(child, property_schema)
                {
                    return false;
                }
            }
            if schema.get("additionalProperties") == Some(&Value::Bool(false))
                && object.keys().any(|key| !properties.contains_key(key))
            {
                return false;
            }
        }
    }
    if let Some(one_of) = schema.get("oneOf").and_then(Value::as_array)
        && one_of
            .iter()
            .filter(|branch| schema_value_matches(value, branch))
            .count()
            != 1
    {
        return false;
    }
    if let Some(any_of) = schema.get("anyOf").and_then(Value::as_array)
        && !any_of
            .iter()
            .any(|branch| schema_value_matches(value, branch))
    {
        return false;
    }
    if let Some(negated) = schema.get("not")
        && schema_value_matches(value, negated)
    {
        return false;
    }
    true
}

fn parse_machine_envelope(output: &str) -> Result<Value, &'static str> {
    if output.len() > MAX_OUTPUT_BYTES {
        return Err("output_too_large");
    }
    let value = serde_json::from_slice::<StrictJson>(output.as_bytes())
        .map_err(|_| "schema_error")?
        .0;
    let schema = serde_json::from_str::<Value>(CLI_ENVELOPE_SCHEMA).map_err(|_| "schema_error")?;
    if !schema_value_matches(&value, &schema) {
        return Err("schema_error");
    }
    if value.get("status").and_then(Value::as_str) == Some("error")
        && value.get("errorCode") != value.get("error").and_then(|error| error.get("code"))
    {
        return Err("schema_error");
    }
    if contains_sensitive_output(&value) {
        return Err("privacy_violation");
    }
    Ok(value)
}

fn validate_machine_envelope(output: &str) -> Result<(), &'static str> {
    parse_machine_envelope(output).map(|_| ())
}

fn machine_failed(command: &str, value: &Value) -> bool {
    let Some(object) = value.as_object() else {
        return true;
    };
    if object.get("status").and_then(Value::as_str) == Some("error") {
        return true;
    }
    let data = object.get("data").unwrap_or(&Value::Null);
    match command {
        "status" => object.get("status").and_then(Value::as_str) == Some("stale"),
        "reconcile" => data
            .get("status")
            .and_then(Value::as_str)
            .is_some_and(|status| matches!(status, "conflict" | "corrupt")),
        "research" | "optimize" | "steelman" | "critic" | "shift-loss" | "security"
        | "compatibility" => {
            data.get("valid").and_then(Value::as_bool) == Some(false)
                || data.get("complete").and_then(Value::as_bool) == Some(false)
                || data.get("status").and_then(Value::as_str) == Some("invalid")
        }
        _ => false,
    }
}

fn main() -> ExitCode {
    let all: Vec<String> = env::args().skip(1).collect();
    let command = match all.first().map(String::as_str).unwrap_or("status") {
        "--help" | "-h" => "help",
        "release_claim" => "release-claim",
        "project_map" => "project-map",
        "shift_loss" => "shift-loss",
        _ => all.first().map(String::as_str).unwrap_or("status"),
    };
    // `hook route` is the host-facing UserPromptSubmit contract, which is a
    // raw `{hookSpecificOutput:...}` object rather than the CLI envelope used
    // by every other command.  Keep this exception explicit and bounded.
    let raw_host_output = (command == "hook"
        && matches!(all.get(1).map(String::as_str), Some("route" | "hud")))
        || (command == "hud" && all.get(1).map(String::as_str) == Some("serve"));
    let (root, args, option_error) = option_root(all.get(1..).unwrap_or(&[]));
    if raw_host_output {
        let output = match option_error {
            Some(_) => "{}".to_owned(),
            None => run(command, root, &args).unwrap_or_else(|_| "{}".to_owned()),
        };
        if !output.is_empty() {
            println!("{output}");
        }
        return ExitCode::SUCCESS;
    }
    let output = match option_error {
        Some(message) => error(command, "argument_error", &message),
        None => match run(command, root, &args) {
            Ok(value) => value,
            Err(message)
                if command == "transition"
                    && (message.to_ascii_lowercase().contains("completion passport")
                        || message
                            .to_ascii_lowercase()
                            .contains("mission-center-passports")) =>
            {
                error_with_data(
                    command,
                    error_code(&message),
                    &message,
                    json!({"gate":"completion-passport","reason":message}),
                )
            }
            Err(message) => error(command, error_code(&message), &message),
        },
    };
    let output = match validate_machine_envelope(&output) {
        Ok(()) => output,
        Err(code) => error(command, code, ""),
    };
    let parsed = parse_machine_envelope(&output).unwrap_or_else(|_| {
        json!({
            "status": "error",
            "errorCode": "schema_error"
        })
    });
    if !output.is_empty() {
        println!("{output}");
    }
    let failed = machine_failed(command, &parsed);
    if parsed.get("errorCode").and_then(Value::as_str) == Some("argument_error") {
        ExitCode::from(2)
    } else if failed {
        ExitCode::from(1)
    } else {
        ExitCode::SUCCESS
    }
}

#[cfg(test)]
mod envelope_schema_tests {
    use super::*;

    fn envelope_with(field: &str, value: Value) -> String {
        let mut envelope = json!({
            "schemaVersion": "1.0",
            "command": "status",
            "status": "ok",
            "data": {}
        });
        envelope
            .as_object_mut()
            .expect("object")
            .insert(field.to_owned(), value);
        envelope.to_string()
    }

    #[test]
    fn schema_max_lengths_reject_route_status_and_error_code() {
        let schema: Value = serde_json::from_str(CLI_ENVELOPE_SCHEMA).expect("schema");
        let properties = schema["properties"].as_object().expect("properties");
        for field in ["route", "status"] {
            let max = properties[field]["maxLength"].as_u64().expect("maxLength");
            assert!(
                parse_machine_envelope(&envelope_with(
                    field,
                    Value::String("x".repeat(max as usize + 1)),
                ))
                .is_err(),
                "overlong {field} must be rejected"
            );
        }

        let max = properties["errorCode"]["maxLength"]
            .as_u64()
            .expect("maxLength");
        let code = "x".repeat(max as usize + 1);
        let envelope = json!({
            "schemaVersion": "1.0",
            "command": "status",
            "status": "error",
            "data": {},
            "errorCode": code,
            "error": {
                "code": code,
                "message": "輸入驗證失敗",
                "remediation": "請修正輸入後重試"
            }
        });
        assert!(parse_machine_envelope(&envelope.to_string()).is_err());

        let message_max = schema["properties"]["error"]["properties"]["message"]["maxLength"]
            .as_u64()
            .expect("message maxLength");
        let envelope = json!({
            "schemaVersion": "1.0",
            "command": "status",
            "status": "error",
            "data": {},
            "errorCode": "validation_failed",
            "error": {
                "code": "validation_failed",
                "message": "x".repeat(message_max as usize + 1),
                "remediation": "請修正輸入後重試"
            }
        });
        assert!(parse_machine_envelope(&envelope.to_string()).is_err());
    }

    #[test]
    fn recovery_unknown_has_a_stable_error_code() {
        assert_eq!(
            error_code("recovery unknown: claim restore failed"),
            "recovery_unknown"
        );
    }
}

#[cfg(test)]
mod hook_route_tests {
    use super::*;

    #[test]
    fn semantic_route_vectors_match_python_contract() {
        let vectors = [
            ("$mission-center", HookRoute::Explicit),
            ("$MISSION-CENTER", HookRoute::Explicit),
            ("plugin://MISSION-CENTER/skills", HookRoute::Explicit),
            ("@Mission\tCenter", HookRoute::Explicit),
            ("請規劃一個高影響的多步驟專案", HookRoute::Semantic),
            (
                "Create a project plan for a high-impact multi-step migration",
                HookRoute::Semantic,
            ),
        ];
        for (prompt, expected) in vectors {
            assert_eq!(
                hook_route_prompt(prompt, Some(".")),
                Some(expected),
                "{prompt}"
            );
        }
        for prompt in [
            "Explain `$mission-center`",
            "引用 \"$mission-center\"",
            "不要用 $mission-center",
            "Do not invoke @Mission Center",
            "請 不要用 $mission-center",
            "請幫我解釋高影響專案規劃",
            "plan this",
        ] {
            assert_eq!(hook_route_prompt(prompt, Some(".")), None, "{prompt}");
        }
    }

    #[test]
    fn quoted_span_and_resume_distance_are_bounded_like_python() {
        assert_eq!(hook_route_prompt("`$mission-center`", Some(".")), None);
        // An unterminated quoted span is not a Python regex match, so the
        // invocation remains visible to the router.
        assert_eq!(
            hook_route_prompt("`unterminated $mission-center", Some(".")),
            Some(HookRoute::Explicit)
        );
        assert!(hook_resume("resume xxxxxxxxxxxxxxxxxxxxxx mission"));
        assert!(!hook_resume("resume xxxxxxxxxxxxxxxxxxxxxxx mission"));
    }

    #[test]
    fn legacy_or_corrupt_hud_metadata_is_a_cache_miss() {
        let path = std::env::temp_dir().join(format!(
            "mission-center-hud-metadata-test-{}.json",
            unique_nonce()
        ));
        std::fs::write(&path, br#"{"instanceKey":"legacy-python"}"#).expect("write");
        assert!(read_hud_metadata(&path).expect("read").is_none());
        let _ = std::fs::remove_file(path);
    }
}
