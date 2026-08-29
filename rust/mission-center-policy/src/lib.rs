//! Fail-closed lifecycle policy。
use mission_center_core::{CoreError, Task, TaskStatus, can_transition, canonical_task_digest};
use serde_json::{Map, Value, json};
use std::{
    collections::{HashMap, HashSet},
    path::{Path, PathBuf},
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PolicyDecision {
    Allow,
    Deny,
}

pub fn transition_decision(from: TaskStatus, to: TaskStatus) -> PolicyDecision {
    if can_transition(from, to) {
        PolicyDecision::Allow
    } else {
        PolicyDecision::Deny
    }
}
pub fn validate_tasks(tasks: &[Task]) -> Result<(), CoreError> {
    for task in tasks {
        if task.id.trim().is_empty() {
            return Err(CoreError::MissingField {
                row: 0,
                field: "ID",
            });
        }
    }
    Ok(())
}
pub fn require_read_only_write_rejection(write_requested: bool) -> Result<(), CoreError> {
    if write_requested {
        Err(CoreError::InvalidTransition {
            from: TaskStatus::Done,
            to: TaskStatus::Done,
        })
    } else {
        Ok(())
    }
}

/// Wave 3 的資料分類。未知輸入一律落在 `Unknown`，不以猜測補值。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FactKind {
    ObservedFact,
    SourcedFact,
    Inference,
    Proposal,
    Unknown,
}
impl FactKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ObservedFact => "ObservedFact",
            Self::SourcedFact => "SourcedFact",
            Self::Inference => "Inference",
            Self::Proposal => "Proposal",
            Self::Unknown => "Unknown",
        }
    }
    pub fn parse(value: &str) -> Self {
        match value {
            "ObservedFact" => Self::ObservedFact,
            "SourcedFact" => Self::SourcedFact,
            "Inference" => Self::Inference,
            "Proposal" => Self::Proposal,
            _ => Self::Unknown,
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Freshness {
    Current,
    Stale,
    Superseded,
    Unverifiable,
}
impl Freshness {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Current => "current",
            Self::Stale => "stale",
            Self::Superseded => "superseded",
            Self::Unverifiable => "unverifiable",
        }
    }
    pub fn parse(value: &str) -> Self {
        match value {
            "current" => Self::Current,
            "stale" => Self::Stale,
            "superseded" => Self::Superseded,
            _ => Self::Unverifiable,
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Authority {
    Canonical,
    Primary,
    Secondary,
    External,
    Unknown,
}
impl Authority {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Canonical => "canonical",
            Self::Primary => "primary",
            Self::Secondary => "secondary",
            Self::External => "external",
            Self::Unknown => "unknown",
        }
    }
    pub fn parse(value: &str) -> Self {
        match value {
            "canonical" => Self::Canonical,
            "primary" => Self::Primary,
            "secondary" => Self::Secondary,
            "external" => Self::External,
            _ => Self::Unknown,
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConflictStatus {
    None,
    Potential,
    Confirmed,
    Unknown,
}
impl ConflictStatus {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Potential => "potential",
            Self::Confirmed => "confirmed",
            Self::Unknown => "unknown",
        }
    }
    pub fn parse(value: &str) -> Self {
        match value {
            "none" => Self::None,
            "potential" => Self::Potential,
            "confirmed" => Self::Confirmed,
            _ => Self::Unknown,
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LicenseStatus {
    Known,
    Compatible,
    Incompatible,
    Unknown,
    NotApplicable,
}
impl LicenseStatus {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Known => "known",
            Self::Compatible => "compatible",
            Self::Incompatible => "incompatible",
            Self::Unknown => "unknown",
            Self::NotApplicable => "not_applicable",
        }
    }
    pub fn parse(value: &str) -> Self {
        match value {
            "known" => Self::Known,
            "compatible" => Self::Compatible,
            "incompatible" => Self::Incompatible,
            "not_applicable" => Self::NotApplicable,
            _ => Self::Unknown,
        }
    }
}

pub const POLICY_SCHEMA_VERSION: &str = "1.0";

fn obj(value: &Value) -> Option<&Map<String, Value>> {
    value.as_object()
}
fn strv(value: Option<&Value>) -> Option<&str> {
    value
        .and_then(Value::as_str)
        .filter(|v| !v.trim().is_empty())
}
fn boolv(value: Option<&Value>) -> Option<bool> {
    value.and_then(Value::as_bool)
}
fn finite_num(value: Option<&Value>) -> Option<f64> {
    value.and_then(Value::as_f64).filter(|v| v.is_finite())
}
fn arr(value: Option<&Value>) -> Option<&Vec<Value>> {
    value.and_then(Value::as_array)
}
fn push_unknown(errors: &mut Vec<String>, object: &Map<String, Value>, allowed: &[&str]) {
    let known: HashSet<&str> = allowed.iter().copied().collect();
    for key in object.keys().filter(|k| !known.contains(k.as_str())) {
        errors.push(format!("unknown field: {key}"));
    }
}

#[allow(clippy::collapsible_if)]
fn secret_assignment(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    for name in [
        "password", "secret", "token", "api_key", "api-key", "apikey",
    ] {
        let mut start = 0;
        while let Some(offset) = lower[start..].find(name) {
            let pos = start + offset;
            let before_ok = pos == 0
                || !lower.as_bytes()[pos - 1].is_ascii_alphanumeric()
                    && lower.as_bytes()[pos - 1] != b'_'
                    && lower.as_bytes()[pos - 1] != b'-';
            let end = pos + name.len();
            let after_ok = end == lower.len()
                || !lower.as_bytes()[end].is_ascii_alphanumeric()
                    && lower.as_bytes()[end] != b'_'
                    && lower.as_bytes()[end] != b'-';
            if before_ok && after_ok {
                let rest = lower[end..].trim_start();
                if let Some(rest) = rest.strip_prefix(':').or_else(|| rest.strip_prefix('=')) {
                    if !rest.trim().is_empty() {
                        return true;
                    }
                }
            }
            start = end;
        }
    }
    false
}

fn structured_jwt(text: &str) -> bool {
    let parts: Vec<&str> = text.split('.').collect();
    parts.len() == 3
        && parts.iter().all(|part| {
            part.len() >= 6
                && part
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"-_".contains(&byte))
        })
        && parts[0]
            .get(..3)
            .is_some_and(|header| header.eq_ignore_ascii_case("eyj"))
}

/// 對所有可接收的結構化輸入做 bounded、fail-closed 隱私掃描。
pub fn scan_forbidden_content(value: &Value) -> Vec<String> {
    let mut errors = Vec::new();
    let mut stack: Vec<(&Value, String, usize)> = vec![(value, "$".to_owned(), 0)];
    let mut nodes = 0usize;
    let mut scalar_bytes = 0usize;
    while let Some((current, path, depth)) = stack.pop() {
        if depth > 1000 {
            errors.push(format!("{path} exceeds security scanner depth limit"));
            break;
        }
        nodes += 1;
        if nodes > 10_000 {
            errors.push(format!("{path} exceeds security scanner node limit"));
            break;
        }
        match current {
            Value::Object(map) => {
                for (key, nested) in map {
                    scalar_bytes = scalar_bytes.saturating_add(key.len());
                    if scalar_bytes > 1_000_000 {
                        errors.push(format!("{path} exceeds security scanner scalar byte limit"));
                        return errors;
                    }
                    let lower = key.to_ascii_lowercase();
                    let compact: String = lower
                        .chars()
                        .filter(|c| c.is_ascii_alphanumeric())
                        .collect();
                    let forbidden = [
                        "prompt",
                        "toolargs",
                        "tool_args",
                        "rawlogs",
                        "raw_logs",
                        "command",
                        "secret",
                        "password",
                        "accesstoken",
                        "access_token",
                        "bearer",
                        "apikey",
                        "api_key",
                        "credential",
                    ]
                    .iter()
                    .any(|needle| lower.contains(needle))
                        || ["toolargs", "rawlogs", "accesstoken", "apikey"]
                            .iter()
                            .any(|needle| compact.contains(needle));
                    let nested_path = format!("{path}.{key}");
                    if forbidden {
                        errors.push(format!("{nested_path} is forbidden privacy content"));
                    }
                    stack.push((nested, nested_path, depth + 1));
                }
            }
            Value::Array(items) => {
                for (index, nested) in items.iter().enumerate().rev() {
                    stack.push((nested, format!("{path}[{index}]"), depth + 1));
                }
            }
            Value::String(text) => {
                scalar_bytes = scalar_bytes.saturating_add(text.len());
                if scalar_bytes > 1_000_000 {
                    errors.push(format!("{path} exceeds security scanner scalar byte limit"));
                    break;
                }
                let lower = text.to_ascii_lowercase();
                let secret = lower.contains("-----begin ")
                    || secret_assignment(&lower)
                    || structured_jwt(text)
                    || lower.contains("bearer ")
                    || lower.contains("sk-")
                    || lower.contains("ghp-")
                    || lower.contains("xox");
                if secret {
                    errors.push(format!("{path} contains secret-like content"));
                }
            }
            _ => {}
        }
    }
    errors
}

fn canonical_task_exists(workspace: Option<&Path>, task_id: &str) -> bool {
    let Some(root) = workspace else {
        return false;
    };
    let ws = mission_center_workspace_path(root);
    let text = std::fs::read_to_string(ws.join("MissionCenter").join("tasks.md")).ok();
    let Some(text) = text else {
        return false;
    };
    mission_center_core::parse_tasks_markdown(&text)
        .map(|tasks| {
            tasks
                .iter()
                .any(|task| task.id.eq_ignore_ascii_case(task_id))
        })
        .unwrap_or(false)
}
fn mission_center_workspace_path(root: &Path) -> PathBuf {
    if root
        .file_name()
        .is_some_and(|v| v.to_string_lossy().eq_ignore_ascii_case("MissionCenter"))
    {
        root.parent().unwrap_or(root).to_path_buf()
    } else {
        root.to_path_buf()
    }
}
fn relative_locator(locator: &str, workspace: Option<&Path>, require_file: bool) -> Option<String> {
    if locator.is_empty()
        || locator.contains("://")
        || Path::new(locator).is_absolute()
        || locator
            .replace('\\', "/")
            .split('/')
            .any(|part| part == ".." || part.is_empty() && locator.starts_with('/'))
    {
        return Some("must be a relative path inside workspace".to_owned());
    }
    let Some(root) = workspace else {
        return Some("requires workspace verification".to_owned());
    };
    let root = mission_center_workspace_path(root);
    let root = root.canonicalize().unwrap_or(root);
    let candidate = root.join(locator);
    let Ok(real) = candidate
        .canonicalize()
        .or_else(|_| Ok::<PathBuf, std::io::Error>(candidate.clone()))
    else {
        return Some("cannot resolve locator".to_owned());
    };
    if !real.starts_with(&root) {
        return Some("must resolve inside workspace".to_owned());
    }
    if require_file && !real.is_file() {
        return Some("must reference an existing file".to_owned());
    }
    None
}

#[allow(clippy::collapsible_if)]
fn validate_source_ledger(
    entries: Option<&Value>,
    errors: &mut Vec<String>,
    workspace: Option<&Path>,
) -> (HashSet<String>, HashSet<String>, HashSet<String>) {
    let mut locators = HashSet::new();
    let mut untrusted = HashSet::new();
    let mut unverifiable = HashSet::new();
    let Some(items) = arr(entries) else {
        errors.push("sourceLedger must be a list".to_owned());
        return (locators, untrusted, unverifiable);
    };
    if items.len() > 32 {
        errors.push("sourceLedger may contain at most 32 entries".to_owned());
    }
    for (i, item) in items.iter().enumerate() {
        let Some(source) = obj(item) else {
            errors.push(format!("sourceLedger[{i}] must be an object"));
            continue;
        };
        push_unknown(
            &mut *errors,
            source,
            &[
                "locator",
                "sourceType",
                "provenance",
                "trustStatus",
                "licenseStatus",
                "retrievedAt",
                "status",
            ],
        );
        let locator = strv(source.get("locator"));
        for field in [
            "locator",
            "sourceType",
            "provenance",
            "trustStatus",
            "licenseStatus",
            "retrievedAt",
            "status",
        ] {
            if strv(source.get(field)).is_none() {
                errors.push(format!("sourceLedger[{i}].{field} is required"));
            }
        }
        let trust = strv(source.get("trustStatus")).unwrap_or("");
        let license_value = source.get("licenseStatus");
        let source_type = strv(source.get("sourceType")).unwrap_or("");
        let status = strv(source.get("status")).unwrap_or("");
        if locator.is_none() {
            errors.push(format!(
                "sourceLedger[{i}].locator must be a non-empty string"
            ));
        }
        if locator.is_some_and(|v| v.len() > 1024)
            || strv(source.get("provenance")).is_some_and(|v| v.len() > 1024)
            || strv(source.get("sourceType")).is_some_and(|v| v.len() > 128)
            || strv(source.get("retrievedAt")).is_some_and(|v| v.len() > 128)
        {
            errors.push(format!("sourceLedger[{i}] contains an overlong field"));
        }
        if !["trusted_local", "untrusted_external_evidence", "unverified"].contains(&trust) {
            errors.push(format!("sourceLedger[{i}].trustStatus is invalid"));
        }
        if ![
            "discovered",
            "verified",
            "rejected",
            "advisory_only",
            "promoted",
        ]
        .contains(&status)
        {
            errors.push(format!("sourceLedger[{i}].status is invalid"));
        }
        if let Some(locator) = locator {
            if !locators.insert(locator.to_owned()) {
                errors.push(format!("sourceLedger has duplicate locator: {locator}"));
            }
            let local = ["local", "repo", "workspace", "fixture"].contains(&source_type);
            if local {
                if workspace.is_none() {
                    unverifiable.insert(locator.to_owned());
                }
                if let Some(reason) = relative_locator(
                    locator,
                    workspace,
                    trust == "trusted_local" || status == "promoted",
                ) {
                    errors.push(format!("sourceLedger[{i}].locator {reason}"));
                }
            } else {
                if trust != "untrusted_external_evidence" {
                    errors.push(format!(
                        "sourceLedger[{i}] external content must be untrusted_external_evidence"
                    ));
                }
                if status == "promoted" {
                    errors.push(format!(
                        "sourceLedger[{i}] untrusted external evidence cannot be promoted"
                    ));
                }
            }
            if trust == "untrusted_external_evidence" {
                untrusted.insert(locator.to_owned());
            }
        }
        if let Some(value) = license_value {
            if !matches!(
                strv(Some(value)),
                Some("known" | "compatible" | "incompatible" | "unknown" | "not_applicable")
            ) {
                errors.push(format!("sourceLedger[{i}].licenseStatus is invalid"));
            }
        }
    }
    (locators, untrusted, unverifiable)
}

/// Python research_portfolio 的 bounded parity validator。
#[allow(clippy::collapsible_if)]
pub fn validate_research_portfolio(record: &Value, workspace: Option<&Path>) -> Vec<String> {
    let Some(record) = obj(record) else {
        return vec!["portfolio must be an object".to_owned()];
    };
    let mut errors = scan_forbidden_content(&Value::Object(record.clone()));
    let allowed = [
        "schemaVersion",
        "artifactType",
        "taskId",
        "initialHypothesisAllocation",
        "allocationKind",
        "hypotheses",
        "sourceLedger",
        "saturationSignals",
        "selectedAction",
        "hardConstraintFailure",
        "budgetExhausted",
        "promotionStatus",
    ];
    push_unknown(&mut errors, record, &allowed);
    if strv(record.get("schemaVersion")) != Some(POLICY_SCHEMA_VERSION) {
        errors.push("schemaVersion must be 1.0".to_owned());
    }
    if strv(record.get("artifactType")) != Some("research-portfolio") {
        errors.push("artifactType must be research-portfolio".to_owned());
    }
    let task_id = strv(record.get("taskId"));
    if task_id.is_none() {
        errors.push("taskId must be a non-empty string".to_owned());
    } else if let Some(task_id) = task_id
        && workspace.is_some()
        && !canonical_task_exists(workspace, task_id)
    {
        errors.push("taskId is not present in canonical tasks.md".to_owned());
    }
    let allocation = obj(record
        .get("initialHypothesisAllocation")
        .unwrap_or(&Value::Null));
    if allocation.is_none()
        || allocation.unwrap().len() != 3
        || !["exploit", "adjacent_explore", "moonshot"]
            .iter()
            .all(|key| finite_num(allocation.unwrap().get(*key)).is_some_and(|v| v >= 0.0))
        || allocation
            .unwrap_or(&Map::new())
            .values()
            .filter_map(|v| finite_num(Some(v)))
            .sum::<f64>()
            != 100.0
    {
        errors.push("initialHypothesisAllocation must contain exploit, adjacent_explore, moonshot totaling 100".to_owned());
    }
    if let Some(allocation) = allocation {
        push_unknown(
            &mut errors,
            allocation,
            &["exploit", "adjacent_explore", "moonshot"],
        );
    }
    if strv(record.get("allocationKind")) != Some("initial_hypothesis_allocation") {
        errors.push(
            "allocationKind must be initial_hypothesis_allocation, not an optimality claim"
                .to_owned(),
        );
    }
    let (locators, untrusted, unverifiable) =
        validate_source_ledger(record.get("sourceLedger"), &mut errors, workspace);
    let hypotheses = arr(record.get("hypotheses"));
    if hypotheses.is_none_or(Vec::is_empty) {
        errors.push("hypotheses must be a non-empty list".to_owned());
    }
    if hypotheses.is_some_and(|items| items.len() > 12) {
        errors.push("hypotheses may contain at most 12 items".to_owned());
    }
    let mut kinds = HashSet::new();
    let mut ids = HashSet::new();
    for (i, value) in hypotheses.into_iter().flatten().enumerate() {
        let Some(h) = obj(value) else {
            errors.push(format!("hypotheses[{i}] must be an object"));
            continue;
        };
        let id = strv(h.get("id"));
        if id.is_none() || !ids.insert(id.unwrap().to_owned()) {
            errors.push(format!("hypotheses[{i}].id must be unique non-empty text"));
        }
        if let Some(kind) = strv(h.get("kind")) {
            if ["exploit", "adjacent_explore", "moonshot"].contains(&kind) {
                kinds.insert(kind.to_owned());
            } else {
                errors.push(format!("hypotheses[{i}].kind is invalid"));
            }
        } else {
            errors.push(format!("hypotheses[{i}].kind is invalid"));
        }
        for field in [
            "question",
            "mechanism",
            "smallestDiscriminatingTest",
            "expectedObservation",
            "successNextAction",
            "failureKnowledge",
            "revalidateWhen",
        ] {
            if strv(h.get(field)).is_none() {
                errors.push(format!(
                    "hypotheses[{i}].{field} must be a non-empty string"
                ));
            }
        }
        for field in [
            "question",
            "mechanism",
            "smallestDiscriminatingTest",
            "expectedObservation",
            "successNextAction",
            "failureKnowledge",
            "revalidateWhen",
        ] {
            if strv(h.get(field)).is_some_and(|v| v.len() > 2048) {
                errors.push(format!("hypotheses[{i}].{field} exceeds 2048 characters"));
            }
        }
        for field in ["falsificationConditions", "dependencies", "risks"] {
            if arr(h.get(field)).is_none() {
                errors.push(format!("hypotheses[{i}].{field} must be a list"));
            }
        }
        if arr(h.get("falsificationConditions")).is_some_and(Vec::is_empty) {
            errors.push(format!(
                "hypotheses[{i}].falsificationConditions must not be empty"
            ));
        }
        if arr(h.get("currentEvidenceRefs")).is_some_and(|refs| {
            refs.iter()
                .any(|v| strv(Some(v)).is_none_or(|r| r.len() > 1024))
        }) {
            errors.push(format!(
                "hypotheses[{i}].currentEvidenceRefs contains invalid locator"
            ));
        }
        for field in ["token", "tool", "time"] {
            if finite_num(obj(h.get("budget").unwrap_or(&Value::Null)).and_then(|v| v.get(field)))
                .is_none_or(|n| n < 0.0)
            {
                errors.push(format!("hypotheses[{i}].budget.{field} must be a non-negative number (zero is explicit)"));
            }
        }
        if let Some(refs) = arr(h.get("currentEvidenceRefs")) {
            for r in refs {
                if let Some(r) = r.as_str() {
                    if !locators.contains(r) {
                        errors.push(format!(
                            "hypotheses[{i}] references unknown source locator: {r}"
                        ));
                    }
                }
            }
        } else {
            errors.push(format!(
                "hypotheses[{i}].currentEvidenceRefs must be a list"
            ));
        }
        let status = strv(h.get("status")).unwrap_or("");
        if ![
            "unverified",
            "research_needed",
            "active",
            "promoted",
            "rejected",
            "stopped",
        ]
        .contains(&status)
        {
            errors.push(format!("hypotheses[{i}].status is invalid"));
        }
        let refs = arr(h.get("currentEvidenceRefs")).map_or(0, Vec::len);
        if refs == 0 && !["unverified", "research_needed"].contains(&status) {
            errors.push(format!(
                "hypotheses[{i}] empty evidenceRefs require unverified or research_needed status"
            ));
        }
        if status == "promoted" {
            if arr(h.get("currentEvidenceRefs"))
                .into_iter()
                .flatten()
                .filter_map(Value::as_str)
                .any(|r| untrusted.contains(r) || unverifiable.contains(r))
            {
                errors.push(format!(
                    "hypotheses[{i}] cannot promote untrusted or unverifiable evidence"
                ));
            }
        }
    }
    if let Some(items) = hypotheses {
        for value in items {
            if let Some(h) = obj(value) {
                push_unknown(
                    &mut errors,
                    h,
                    &[
                        "id",
                        "kind",
                        "question",
                        "mechanism",
                        "currentEvidenceRefs",
                        "smallestDiscriminatingTest",
                        "expectedObservation",
                        "falsificationConditions",
                        "dependencies",
                        "risks",
                        "budget",
                        "successNextAction",
                        "failureKnowledge",
                        "revalidateWhen",
                        "status",
                    ],
                );
                if let Some(budget) = obj(h.get("budget").unwrap_or(&Value::Null)) {
                    push_unknown(&mut errors, budget, &["token", "tool", "time"]);
                }
            }
        }
    }
    for kind in ["exploit", "adjacent_explore", "moonshot"] {
        if !kinds.contains(kind) {
            errors.push(format!(
                "hypotheses must include at least one {kind} hypothesis"
            ));
        }
    }
    let signals = record
        .get("saturationSignals")
        .cloned()
        .unwrap_or(Value::Null);
    for field in ["hardConstraintFailure", "budgetExhausted"] {
        if record.get(field).is_some() && boolv(record.get(field)).is_none() {
            errors.push(format!("{field} must be boolean"));
        }
    }
    let hard = boolv(record.get("hardConstraintFailure")).unwrap_or(false);
    let budget = boolv(record.get("budgetExhausted")).unwrap_or(false);
    match route_saturation(&signals, hard, budget) {
        Ok(route) => {
            let expected = route
                .get("selectedAction")
                .and_then(Value::as_str)
                .unwrap_or("");
            let selected = strv(record.get("selectedAction"));
            if selected != Some(expected)
                && !(expected == "stop" && matches!(selected, Some("stop" | "human_decision")))
            {
                errors.push(format!(
                    "selectedAction must match deterministic route: {expected}"
                ));
            }
        }
        Err(e) => errors.push(e),
    }
    if let Some(promotion) = strv(record.get("promotionStatus")) {
        if !["advisory_only", "not_promoted", "promoted"].contains(&promotion) {
            errors.push("promotionStatus is invalid".to_owned());
        }
        if promotion == "promoted" && (!untrusted.is_empty() || !unverifiable.is_empty()) {
            errors.push(
                "portfolio with untrusted or unverifiable evidence cannot be promoted".to_owned(),
            );
        }
    }
    errors
}

pub fn default_initial_allocation() -> Value {
    json!({"exploit":60,"adjacent_explore":30,"moonshot":10})
}
pub fn route_saturation(
    signals: &Value,
    hard_constraint_failure: bool,
    budget_exhausted: bool,
) -> Result<Value, String> {
    let Some(s) = obj(signals) else {
        return Err("saturation signals must be an object".to_owned());
    };
    let names = [
        "repeatedRootCause",
        "renamedHypothesis",
        "metricStalled",
        "budgetBurning",
        "sharedUnverifiedPremise",
    ];
    if let Some(key) = s
        .keys()
        .find(|k| !names.contains(&k.as_str()) && k.as_str() != "lowMarginalGainCount")
    {
        return Err(format!("saturation signals unknown field: {key}"));
    }
    let mut count = 0;
    for key in names {
        if boolv(s.get(key)) != Some(false) && boolv(s.get(key)) != Some(true) {
            return Err(format!("{key} must be boolean"));
        }
        if boolv(s.get(key)) == Some(true) {
            count += 1;
        }
    }
    if !s.contains_key("lowMarginalGainCount") {
        return Err("lowMarginalGainCount is required".to_owned());
    }
    let Some(marginal) = s.get("lowMarginalGainCount").and_then(Value::as_i64) else {
        return Err("lowMarginalGainCount must be a non-negative integer".to_owned());
    };
    if marginal < 0 {
        return Err("lowMarginalGainCount must be a non-negative integer".to_owned());
    }
    if marginal > 0 {
        count += 1;
    }
    let (action, reason) = if hard_constraint_failure || budget_exhausted {
        ("stop", "hard constraint failure or budget exhausted")
    } else if count >= 2 {
        ("broaden_search", "at least two explicit saturation signals")
    } else {
        ("continue", "fewer than two explicit saturation signals")
    };
    Ok(
        json!({"schemaVersion":"1.0","route":"saturation","selectedAction":action,"signalCount":count,"reason":reason,"hardConstraintFailure":hard_constraint_failure,"budgetExhausted":budget_exhausted}),
    )
}

pub fn build_optimization_profile(raw: &Value) -> Value {
    let mut profile = Map::new();
    profile.insert("schemaVersion".to_owned(), json!("1.0"));
    profile.insert("taskType".to_owned(), json!("research"));
    profile.insert("parameterShape".to_owned(), json!("none"));
    profile.insert("measurement".to_owned(), json!("none"));
    profile.insert("noise".to_owned(), json!("unknown"));
    profile.insert("reversibility".to_owned(), json!("unknown"));
    profile.insert("risk".to_owned(), json!("medium"));
    profile.insert(
        "budget".to_owned(),
        json!({"trials":0,"tokens":0,"wallClockSeconds":0}),
    );
    profile.insert("objectives".to_owned(), json!([]));
    profile.insert("differentiable".to_owned(), json!(false));
    profile.insert("factorCount".to_owned(), json!(0));
    profile.insert("localCases".to_owned(), json!([]));
    profile.insert("unknowns".to_owned(), json!([]));
    if let Some(input) = obj(raw) {
        for (k, v) in input {
            profile.insert(k.clone(), v.clone());
        }
    }
    if profile
        .get("measurement")
        .and_then(Value::as_str)
        .is_some_and(|v| v == "none" || v == "subjective")
    {
        let unknowns = profile
            .get("unknowns")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        let mut names: Vec<String> = unknowns
            .iter()
            .filter_map(Value::as_str)
            .map(ToOwned::to_owned)
            .collect();
        if !names.iter().any(|v| v == "repeatable_metric") {
            names.push("repeatable_metric".to_owned());
        }
        names.sort();
        names.dedup();
        profile.insert(
            "unknowns".to_owned(),
            Value::Array(names.into_iter().map(Value::String).collect()),
        );
    }
    Value::Object(profile)
}
pub fn build_profile(raw: &Value) -> Value {
    build_optimization_profile(raw)
}

pub fn route_optimization_profile(profile: &Value) -> Value {
    let p = obj(profile);
    let task = p
        .and_then(|m| strv(m.get("taskType")))
        .unwrap_or("research");
    let shape = p
        .and_then(|m| strv(m.get("parameterShape")))
        .unwrap_or("none");
    let measurement = p.and_then(|m| strv(m.get("measurement"))).unwrap_or("none");
    let factors = p
        .and_then(|m| finite_num(m.get("factorCount")))
        .unwrap_or(0.0) as i64;
    let budget_trials = p
        .and_then(|m| {
            finite_num(
                m.get("budget")
                    .and_then(|v| obj(v))
                    .and_then(|m| m.get("trials")),
            )
        })
        .unwrap_or(0.0) as i64;
    let objectives = p.and_then(|m| arr(m.get("objectives"))).map_or(0, Vec::len);
    let local_cases = p
        .and_then(|m| arr(m.get("localCases")))
        .is_some_and(|v| !v.is_empty());
    let risk = p.and_then(|m| strv(m.get("risk"))).unwrap_or("medium");
    let (mode, strategy, reason, missing) = if task == "deterministic" || shape == "none" {
        (
            "skip",
            "direct_verification",
            vec!["The task is deterministic or has no tunable parameters"],
            vec![],
        )
    } else if shape == "discrete" && (measurement == "none" || measurement == "subjective") {
        if local_cases {
            (
                "decision",
                "trade_study_scenario_stress",
                vec!["Comparable qualitative evidence supports a discrete trade study"],
                vec![],
            )
        } else {
            (
                "research_spike",
                "evidence_collection",
                vec!["Discrete qualitative choices need comparable decision evidence"],
                vec!["comparable_decision_evidence"],
            )
        }
    } else if measurement == "none" || measurement == "subjective" {
        (
            "research_spike",
            "evidence_collection",
            vec!["No repeatable measurement is available"],
            vec!["repeatable_metric"],
        )
    } else if budget_trials < 1 {
        (
            "research_spike",
            "budget_definition",
            vec!["Experiment budget is missing"],
            vec!["positive_trial_budget"],
        )
    } else if objectives > 1 || shape == "multi_objective" {
        (
            "experimental",
            if budget_trials >= 20 {
                "pareto_nsga2"
            } else {
                "pareto_trade_study"
            },
            vec!["Multiple objectives must remain separate"],
            vec![],
        )
    } else if p.and_then(|m| strv(m.get("noise"))) == Some("high") {
        (
            "experimental",
            "robust_doe_taguchi",
            vec!["High measurement noise"],
            vec![],
        )
    } else if risk == "high" {
        (
            "hybrid",
            "bounded_trade_study",
            vec!["High-risk decisions require bounded comparison"],
            vec![],
        )
    } else if shape == "mixed" || shape == "categorical" {
        (
            "experimental",
            "tpe",
            vec!["Categorical or mixed parameters"],
            vec![],
        )
    } else if shape == "continuous" && boolv(p.and_then(|m| m.get("differentiable"))) == Some(true)
    {
        (
            "experimental",
            "gradient_method",
            vec!["Continuous differentiable objective"],
            vec![],
        )
    } else if shape == "continuous" && measurement == "expensive" && factors <= 12 {
        (
            "experimental",
            "bayesian_optimization",
            vec!["Few expensive black-box parameters"],
            vec![],
        )
    } else if factors >= 4 {
        (
            "experimental",
            "screening_doe",
            vec!["Many factors require screening"],
            vec![],
        )
    } else if shape == "discrete" {
        (
            if risk == "low" { "decision" } else { "hybrid" },
            "trade_study_scenario_stress",
            vec!["Few discrete alternatives"],
            vec![],
        )
    } else {
        (
            "hybrid",
            "bounded_trade_study",
            vec!["Evidence supports only bounded comparison"],
            vec![],
        )
    };
    json!({"schemaVersion":"1.0","mode":mode,"strategy":strategy,"reason":reason,"missingEvidence":missing,"promotionPolicy":"manual_review_only"})
}
pub fn route_profile(profile: &Value) -> Value {
    route_optimization_profile(profile)
}

pub fn validate_optimization_manifest(manifest: &Value) -> Vec<String> {
    let Some(m) = obj(manifest) else {
        return vec!["manifest must be an object".to_owned()];
    };
    let mut errors = Vec::new();
    push_unknown(
        &mut errors,
        m,
        &[
            "schemaVersion",
            "experimentId",
            "kind",
            "candidates",
            "cases",
            "metrics",
            "hardConstraints",
            "budget",
            "stoppingConditions",
            "validation",
            "promotionState",
            "normalization",
            "weights",
            "baselineCandidate",
        ],
    );
    for f in [
        "experimentId",
        "kind",
        "candidates",
        "cases",
        "metrics",
        "hardConstraints",
        "budget",
        "stoppingConditions",
        "validation",
        "promotionState",
    ] {
        if !m.contains_key(f) {
            errors.push(format!("missing:{f}"));
        }
    }
    let budget = obj(m.get("budget").unwrap_or(&Value::Null));
    for field in ["candidates", "cases", "metrics", "stoppingConditions"] {
        if arr(m.get(field)).is_none_or(Vec::is_empty) {
            errors.push(format!("invalid:{field}"));
        }
    }
    if arr(m.get("hardConstraints")).is_none() {
        errors.push("invalid:hardConstraints".to_owned());
    }
    if let Some(budget) = budget {
        push_unknown(
            &mut errors,
            budget,
            &[
                "trials",
                "tokens",
                "wallClockSeconds",
                "maxConcurrency",
                "retriesPerTrial",
            ],
        );
    }
    for f in ["trials", "tokens", "wallClockSeconds"] {
        let valid = budget
            .and_then(|b| b.get(f))
            .and_then(Value::as_i64)
            .is_some_and(|n| n >= 1);
        if !valid {
            errors.push(format!("invalid_budget:{f}"));
        }
    }
    for (f, limit) in [("maxConcurrency", 2i64), ("retriesPerTrial", 1i64)] {
        if let Some(value) = budget.and_then(|b| b.get(f)) {
            let minimum = if f == "maxConcurrency" { 1 } else { 0 };
            if value.as_i64().is_none_or(|n| n < minimum || n > limit) {
                errors.push(format!("invalid_budget:{f}"));
            }
        }
    }
    if strv(m.get("promotionState")) != Some("shadow") {
        errors.push("promotionState_must_be_shadow".to_owned());
    }
    let experiment = strv(m.get("experimentId"));
    if experiment.is_none_or(|id| {
        id.len() > 64
            || id.is_empty()
            || !id
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
    }) {
        errors.push("invalid:experimentId".to_owned());
    }
    let metrics = arr(m.get("metrics"));
    if metrics.is_none_or(Vec::is_empty)
        || metrics.is_some_and(|items| {
            items.iter().any(|v| {
                obj(v).is_none_or(|x| {
                    strv(x.get("name")).is_none()
                        || strv(x.get("unit")).is_none()
                        || !matches!(strv(x.get("direction")), Some("minimize" | "maximize"))
                })
            })
        })
    {
        errors.push("invalid:metrics".to_owned());
        return errors;
    }
    let metric_names: Vec<&str> = metrics
        .unwrap()
        .iter()
        .filter_map(|v| obj(v).and_then(|m| strv(m.get("name"))))
        .collect();
    let unique: HashSet<&str> = metric_names.iter().copied().collect();
    if unique.len() != metric_names.len() {
        errors.push("invalid:metrics".to_owned());
        return errors;
    }
    let normalization = m.get("normalization");
    let weights = m.get("weights");
    if normalization.is_none() && weights.is_none() {
        return errors;
    }
    if obj(normalization.unwrap_or(&Value::Null)).is_none()
        || obj(weights.unwrap_or(&Value::Null)).is_none()
    {
        errors.push("invalid:composite_configuration".to_owned());
        return errors;
    }
    let norm = obj(normalization.unwrap()).unwrap();
    let weight = obj(weights.unwrap()).unwrap();
    let expected_names: HashSet<&str> = metric_names.iter().copied().collect();
    if weight.keys().map(String::as_str).collect::<HashSet<_>>() != expected_names {
        errors.push("invalid:weights_alignment".to_owned());
    }
    if norm.keys().map(String::as_str).collect::<HashSet<_>>() != expected_names {
        errors.push("invalid:normalization_alignment".to_owned());
    }
    for name in &metric_names {
        let Some(bounds) = obj(norm.get(*name).unwrap_or(&Value::Null)) else {
            errors.push(format!("invalid:normalization:{name}"));
            continue;
        };
        if finite_num(bounds.get("min"))
            .is_none_or(|low| finite_num(bounds.get("max")).is_none_or(|high| high <= low))
        {
            errors.push(format!("invalid:normalization:{name}"));
        }
    }
    let total: f64 = weight
        .values()
        .filter_map(|v| finite_num(Some(v)).filter(|n| *n >= 0.0))
        .sum();
    for (name, v) in weight {
        if finite_num(Some(v)).is_none_or(|n| n < 0.0) {
            errors.push(format!("invalid:weight:{name}"));
        }
    }
    if errors.is_empty() && total <= 0.0 {
        errors.push("invalid:weights_sum".to_owned());
    }
    errors
}

fn json_number(value: Option<&Value>) -> Option<f64> {
    finite_num(value)
}
fn passes_constraints(item: &Map<String, Value>, constraints: &[Value]) -> bool {
    let values = obj(item.get("metrics").unwrap_or(&Value::Null));
    constraints.iter().all(|rule| {
        let r = obj(rule);
        let value = r
            .and_then(|r| strv(r.get("metric")))
            .and_then(|name| values.and_then(|v| json_number(v.get(name))));
        value.is_some_and(|v| {
            r.is_none_or(|r| {
                r.get("min")
                    .and_then(Value::as_f64)
                    .is_none_or(|min| v >= min)
                    && r.get("max")
                        .and_then(Value::as_f64)
                        .is_none_or(|max| v <= max)
            })
        })
    })
}

#[allow(clippy::collapsible_if)]
pub fn evaluate_optimization(manifest: &Value, observations: &Value) -> Value {
    let errors = validate_optimization_manifest(manifest);
    let m = obj(manifest);
    let experiment = m
        .and_then(|v| strv(v.get("experimentId")))
        .unwrap_or("unknown");
    if !errors.is_empty() {
        return empty_optimization(experiment, "invalid", errors);
    }
    let observation_items = arr(Some(observations)).or_else(|| {
        obj(observations).and_then(|map| {
            if map.keys().all(|key| key == "observations") {
                arr(map.get("observations"))
            } else {
                None
            }
        })
    });
    let Some(items) = observation_items else {
        return empty_optimization(experiment, "stopped", vec!["no_experiment_data".to_owned()]);
    };
    let budget = obj(m.unwrap().get("budget").unwrap());
    let trials = budget
        .and_then(|v| v.get("trials"))
        .and_then(Value::as_i64)
        .unwrap_or(0) as usize;
    let tokens_limit = budget
        .and_then(|v| v.get("tokens"))
        .and_then(Value::as_i64)
        .unwrap_or(0) as f64;
    let seconds_limit = budget
        .and_then(|v| v.get("wallClockSeconds"))
        .and_then(Value::as_f64)
        .unwrap_or(0.0);
    let retries = budget
        .and_then(|v| v.get("retriesPerTrial"))
        .and_then(Value::as_i64)
        .unwrap_or(1) as usize;
    let mut accepted = Vec::new();
    let mut attempts: HashMap<(String, String), usize> = HashMap::new();
    let mut used_tokens = 0f64;
    let mut used_seconds = 0f64;
    let mut exhausted = false;
    for item in items {
        let Some(row) = obj(item) else { continue };
        let key = (
            row.get("candidate")
                .and_then(Value::as_str)
                .unwrap_or("unknown")
                .to_owned(),
            row.get("case")
                .and_then(Value::as_str)
                .unwrap_or("default")
                .to_owned(),
        );
        let count = attempts.entry(key).or_insert(0);
        *count += 1;
        if *count > retries + 1 {
            continue;
        }
        let tok = json_number(row.get("tokens")).unwrap_or(0.0);
        let sec = json_number(row.get("wallClockSeconds")).unwrap_or(0.0);
        if accepted.len() >= trials
            || used_tokens + tok > tokens_limit
            || used_seconds + sec > seconds_limit
        {
            exhausted = true;
            break;
        }
        accepted.push(row.clone());
        used_tokens += tok;
        used_seconds += sec;
    }
    if accepted.is_empty() {
        return empty_optimization(experiment, "stopped", vec!["no_experiment_data".to_owned()]);
    }
    let metrics = arr(m.unwrap().get("metrics")).unwrap();
    let constraints = arr(m.unwrap().get("hardConstraints")).unwrap();
    let mut valid = Vec::new();
    let mut unknowns = Vec::new();
    for row in &accepted {
        let values = obj(row.get("metrics").unwrap_or(&Value::Null));
        let missing: Vec<String> = metrics
            .iter()
            .filter_map(|metric| {
                let name = obj(metric).and_then(|mm| strv(mm.get("name")))?;
                if values.and_then(|v| json_number(v.get(name))).is_none() {
                    Some(name.to_owned())
                } else {
                    None
                }
            })
            .collect();
        if !missing.is_empty() {
            unknowns.push(format!(
                "{}:{}",
                row.get("candidate")
                    .and_then(Value::as_str)
                    .unwrap_or("unknown"),
                missing.join(",")
            ));
        } else if passes_constraints(row, constraints) {
            valid.push(row.clone());
        }
    }
    let mut pareto = Vec::new();
    for candidate in &valid {
        let dominated = valid.iter().any(|other| {
            if other == candidate {
                return false;
            }
            let no_worse = metrics.iter().all(|metric| {
                let mm = obj(metric).unwrap();
                let name = strv(mm.get("name")).unwrap();
                let a = json_number(obj(other.get("metrics").unwrap()).unwrap().get(name)).unwrap();
                let b =
                    json_number(obj(candidate.get("metrics").unwrap()).unwrap().get(name)).unwrap();
                if strv(mm.get("direction")) == Some("maximize") {
                    a >= b
                } else {
                    a <= b
                }
            });
            let better = metrics.iter().any(|metric| {
                let mm = obj(metric).unwrap();
                let name = strv(mm.get("name")).unwrap();
                let a = json_number(obj(other.get("metrics").unwrap()).unwrap().get(name)).unwrap();
                let b =
                    json_number(obj(candidate.get("metrics").unwrap()).unwrap().get(name)).unwrap();
                if strv(mm.get("direction")) == Some("maximize") {
                    a > b
                } else {
                    a < b
                }
            });
            no_worse && better
        });
        if !dominated {
            if let Some(id) = candidate.get("candidate").and_then(Value::as_str) {
                pareto.push(id.to_owned());
            }
        }
    }
    pareto.sort();
    pareto.dedup();
    let mut baseline_delta = Map::new();
    if let Some(base_id) = m.unwrap().get("baselineCandidate").and_then(Value::as_str) {
        if let Some(base) = valid
            .iter()
            .find(|row| row.get("candidate").and_then(Value::as_str) == Some(base_id))
        {
            for row in &valid {
                if row.get("candidate").and_then(Value::as_str) == Some(base_id) {
                    continue;
                }
                let mut delta = Map::new();
                for metric in metrics {
                    let mm = obj(metric).unwrap();
                    let name = strv(mm.get("name")).unwrap();
                    let current =
                        json_number(obj(row.get("metrics").unwrap()).unwrap().get(name)).unwrap();
                    let old =
                        json_number(obj(base.get("metrics").unwrap()).unwrap().get(name)).unwrap();
                    delta.insert(name.to_owned(), json!(current - old));
                }
                if let Some(id) = row.get("candidate").and_then(Value::as_str) {
                    baseline_delta.insert(id.to_owned(), Value::Object(delta));
                }
            }
        }
    }
    let mut composite = Value::Null;
    if let (Some(norm), Some(weights)) = (
        obj(m.unwrap().get("normalization").unwrap_or(&Value::Null)),
        obj(m.unwrap().get("weights").unwrap_or(&Value::Null)),
    ) {
        let mut values = Map::new();
        for row in &valid {
            let mut total = 0.0;
            let mut valid_score = true;
            for metric in metrics {
                let mm = obj(metric).unwrap();
                let name = strv(mm.get("name")).unwrap();
                let bounds = obj(norm.get(name).unwrap_or(&Value::Null));
                let low = bounds.and_then(|b| finite_num(b.get("min")));
                let high = bounds.and_then(|b| finite_num(b.get("max")));
                let value = json_number(obj(row.get("metrics").unwrap()).unwrap().get(name));
                let weight = finite_num(weights.get(name));
                if let (Some(low), Some(high), Some(value), Some(weight)) =
                    (low, high, value, weight)
                {
                    let normalized = (value - low) / (high - low);
                    let loss = if strv(mm.get("direction")) == Some("maximize") {
                        1.0 - normalized
                    } else {
                        normalized
                    };
                    total += loss * weight;
                } else {
                    valid_score = false;
                }
            }
            if valid_score {
                values.insert(
                    row.get("candidate")
                        .and_then(Value::as_str)
                        .unwrap_or("unknown")
                        .to_owned(),
                    json!((total * 1_000_000.0).round() / 1_000_000.0),
                );
            }
        }
        composite = Value::Object(values);
    }
    let recommendation = if !pareto.is_empty() && unknowns.is_empty() {
        "review"
    } else {
        "insufficient_evidence"
    };
    let mut out = json!({"schemaVersion":"1.0","experimentId":experiment,"status":if exhausted {"budget_exhausted"} else {"completed"},"baselineDelta":baseline_delta,"paretoCandidates":pareto,"confidence":if accepted.len()>=20 {"high"} else if accepted.len()>=8 {"medium"} else {"low"},"sampleCount":accepted.len(),"unknowns":unknowns,"compositeLoss":composite,"promotionRecommendation":recommendation,"promotionState":if recommendation=="review" {"review"} else {"shadow"},"budgetUsed":{"trials":accepted.len(),"tokens":used_tokens,"wallClockSeconds":used_seconds},"scoreBasis":"heuristic"});
    if let Some(map) = out.as_object_mut() {
        map.insert(
            "evaluatedAt".to_owned(),
            Value::String("1970-01-01T00:00:00Z".to_owned()),
        );
    }
    out
}
pub fn evaluate_observations(manifest: &Value, observations: &Value) -> Value {
    evaluate_optimization(manifest, observations)
}
fn empty_optimization(experiment: &str, status: &str, unknowns: Vec<String>) -> Value {
    json!({"schemaVersion":"1.0","experimentId":experiment,"status":status,"baselineDelta":{},"paretoCandidates":[],"confidence":"none","sampleCount":0,"unknowns":unknowns,"compositeLoss":null,"promotionRecommendation":"insufficient_evidence","promotionState":"shadow","budgetUsed":{"trials":0,"tokens":0,"wallClockSeconds":0.0},"scoreBasis":"heuristic","evaluatedAt":"1970-01-01T00:00:00Z"})
}

pub fn route_steelman(
    workspace: &Path,
    task_id: &str,
    risk: &str,
    deterministic: bool,
) -> Result<Value, String> {
    if !canonical_task_exists(Some(workspace), task_id) {
        return Err(format!(
            "taskId is not present in canonical tasks.md: {task_id}"
        ));
    }
    let selected = risk.trim().to_ascii_lowercase();
    if !["low", "medium", "high"].contains(&selected.as_str()) {
        return Err("risk must be low, medium, or high".to_owned());
    }
    let (route, rounds, reason) = if deterministic && selected == "low" {
        ("skip", 0, "deterministic low-risk change")
    } else if selected == "high" {
        (
            "steelman_full",
            2,
            "high-risk decision requires complete steelman",
        )
    } else {
        (
            "steelman_lite",
            1,
            "material trade-off requires bounded steelman",
        )
    };
    Ok(
        json!({"schemaVersion":"1.0","artifactType":"steelman-evolution","taskId":task_id,"lifecycleSource":"tasks.md","selectedRoute":route,"maxRounds":rounds,"reason":reason,"artifactRequired":route!="skip","perspectivesAreSimulatedByDefault":true,"realSubagentsCompleted":false}),
    )
}

pub fn validate_steelman_artifact(record: &Value, workspace: Option<&Path>) -> Vec<String> {
    let Some(r) = obj(record) else {
        return vec!["artifact must be an object".to_owned()];
    };
    let mut errors = scan_forbidden_content(record);
    let version = strv(r.get("schemaVersion")).unwrap_or("");
    let route = strv(r.get("selectedRoute"))
        .or_else(|| strv(r.get("route")))
        .unwrap_or("");
    if version != "1.0" {
        errors.push("schemaVersion must be 1.0".to_owned());
    }
    push_unknown(
        &mut errors,
        r,
        &[
            "schemaVersion",
            "artifactType",
            "taskId",
            "selectedRoute",
            "route",
            "maxRounds",
            "perspectives",
            "realSubagentsCompleted",
            "skipReason",
            "trueGoal",
            "currentBest",
            "strongestOpposition",
            "thirdRoute",
            "smallestDiscriminatingTest",
            "flipVariables",
            "materialDissent",
            "reopenConditions",
            "evidenceRefs",
            "qualityContract",
            "architectureContract",
            "unknowns",
            "authorization",
            "budgets",
        ],
    );
    if strv(r.get("artifactType")) != Some("steelman-evolution") {
        errors.push("artifactType must be steelman-evolution".to_owned());
    }
    for f in [
        "taskId",
        "selectedRoute",
        "maxRounds",
        "perspectives",
        "realSubagentsCompleted",
    ] {
        if !r.contains_key(f) {
            errors.push(format!("{f} is required"));
        }
    }
    if route == "skip" {
        if r.get("maxRounds").and_then(Value::as_i64) != Some(0) {
            errors.push("skip requires maxRounds 0".to_owned());
        }
        if strv(r.get("skipReason")).is_none() {
            errors.push("skip requires skipReason".to_owned());
        }
        if boolv(r.get("realSubagentsCompleted")) == Some(true) {
            errors.push("skip cannot report completed real subagents".to_owned());
        }
    } else if route == "steelman_lite" && r.get("maxRounds").and_then(Value::as_i64) != Some(1) {
        errors.push("steelman_lite requires exactly one round".to_owned());
    } else if route == "steelman_full"
        && r.get("maxRounds")
            .and_then(Value::as_i64)
            .is_none_or(|v| !(1..=2).contains(&v))
    {
        errors.push("steelman_full maxRounds must be from 1 through 2".to_owned());
    }
    if route == "steelman_lite" || route == "steelman_full" {
        for field in [
            "trueGoal",
            "currentBest",
            "strongestOpposition",
            "thirdRoute",
            "smallestDiscriminatingTest",
        ] {
            if strv(r.get(field)).is_none() {
                errors.push(format!("{field} is required for {route}"));
            }
        }
        for field in [
            "flipVariables",
            "materialDissent",
            "reopenConditions",
            "evidenceRefs",
        ] {
            if arr(r.get(field)).is_none_or(Vec::is_empty) {
                errors.push(format!("{field} must be a non-empty list"));
            }
        }
        if arr(r.get("unknowns")).is_none() {
            errors.push("unknowns must be a list".to_owned());
        }
        if let Some(dissent) = arr(r.get("materialDissent")) {
            for (i, item) in dissent.iter().enumerate() {
                let valid = strv(Some(item)).is_some_and(|text| text.len() <= 4096)
                    || obj(item).is_some_and(|map| {
                        map.len() == 3
                            && map.keys().all(|key| {
                                ["position", "impact", "resolution"].contains(&key.as_str())
                            })
                            && ["position", "impact", "resolution"].iter().all(|field| {
                                strv(map.get(*field)).is_some_and(|text| text.len() <= 4096)
                            })
                    });
                if !valid {
                    errors.push(format!("materialDissent[{i}] must be a bounded string or position/impact/resolution object"));
                }
            }
        }
        for field in ["qualityContract", "architectureContract"] {
            if strv(r.get(field)).is_none()
                && !r
                    .get(field)
                    .is_some_and(|v| obj(v).is_some_and(|m| !m.is_empty()))
            {
                errors.push(format!("{field} must be a non-empty string or object"));
            }
        }
        if boolv(r.get("realSubagentsCompleted")) == Some(true) {
            let auth = obj(r.get("authorization").unwrap_or(&Value::Null));
            if boolv(auth.and_then(|a| a.get("explicitAuthorization"))) != Some(true) {
                errors.push("real subagent completion requires explicitAuthorization".to_owned());
            }
            let budgets = obj(r.get("budgets").unwrap_or(&Value::Null));
            if budgets.is_none()
                || ["total", "tool", "wallClock"]
                    .iter()
                    .any(|f| finite_num(budgets.and_then(|b| b.get(*f))).is_none_or(|n| n <= 0.0))
            {
                errors.push("real subagent completion requires positive budgets".to_owned());
            }
        }
    }
    let perspectives = arr(r.get("perspectives"));
    let min = if route == "steelman_full" { 3 } else { 2 };
    if route != "skip" && perspectives.is_none_or(|p| p.len() < min) {
        errors.push(format!("{route} requires at least {min} perspectives"));
    }
    let mut ids = HashSet::new();
    let mut completed = false;
    for (i, v) in perspectives.into_iter().flatten().enumerate() {
        let Some(p) = obj(v) else {
            errors.push(format!("perspectives[{i}] must be an object"));
            continue;
        };
        if strv(p.get("id")).is_none_or(|id| !ids.insert(id.to_owned())) {
            errors.push(format!("perspectives[{i}] needs a unique id"));
        }
        for field in ["observation", "blindSpot", "recommendation"] {
            if strv(p.get(field)).is_none() {
                errors.push(format!(
                    "perspectives[{i}].{field} must be a non-empty string"
                ));
            }
        }
        if let Some(kind) = strv(p.get("kind")) {
            if !["simulated", "real_subagent"].contains(&kind) {
                errors.push(format!("perspectives[{i}] kind is invalid"));
            }
            if kind == "real_subagent" {
                if !["planned", "not_dispatched", "completed"]
                    .contains(&strv(p.get("status")).unwrap_or(""))
                {
                    errors.push(format!("perspectives[{i}] real_subagent status is invalid"));
                }
                if strv(p.get("status")) == Some("completed") {
                    completed = true;
                    if arr(p.get("evidenceRefs")).is_none_or(Vec::is_empty) {
                        errors.push(format!(
                            "perspectives[{i}].evidenceRefs must be a non-empty list"
                        ));
                    }
                }
            }
        } else {
            errors.push(format!(
                "perspectives[{i}] kind must be simulated or real_subagent"
            ));
        }
    }
    if boolv(r.get("realSubagentsCompleted")) != Some(completed) {
        errors.push(
            "realSubagentsCompleted must match completed real_subagent perspectives".to_owned(),
        );
    }
    if completed
        && boolv(
            r.get("authorization")
                .and_then(|v| obj(v))
                .and_then(|m| m.get("explicitAuthorization")),
        ) != Some(true)
    {
        errors.push("real subagent completion requires explicitAuthorization".to_owned());
    }
    if workspace.is_some()
        && strv(r.get("taskId")).is_some_and(|id| !canonical_task_exists(workspace, id))
    {
        errors.push("taskId is not present in canonical tasks.md".to_owned());
    }
    errors
}

/// Validate the minimal Completion Passport consumed by the lifecycle Done gate.
///
/// The passport is an attestation over the task's identity fields; `status` is
/// excluded by `canonical_task_digest`, so the canonical `tasks.md` table
/// remains the sole lifecycle source of truth.
pub fn validate_completion_passport(
    record: &Value,
    task: &Task,
    workspace: Option<&Path>,
) -> Vec<String> {
    let mut errors = Vec::new();
    let Some(root) = obj(record) else {
        return vec!["completion passport must be an object".to_owned()];
    };
    push_unknown(
        &mut errors,
        root,
        &[
            "schemaVersion",
            "artifactType",
            "taskId",
            "taskDigest",
            "status",
            "verification",
            "findings",
        ],
    );
    if strv(root.get("schemaVersion")) != Some("1.0") {
        errors.push("schemaVersion must be 1.0".to_owned());
    }
    if strv(root.get("artifactType")) != Some("completion-passport") {
        errors.push("artifactType must be completion-passport".to_owned());
    }
    let task_id = strv(root.get("taskId"));
    if task_id != Some(task.id.as_str()) {
        errors.push("taskId does not match canonical task".to_owned());
    }
    let digest = strv(root.get("taskDigest"));
    if digest != Some(canonical_task_digest(task).as_str()) {
        errors.push("taskDigest does not match canonical task identity".to_owned());
    }
    if strv(root.get("status")) != Some("current") {
        errors.push("status must be current".to_owned());
    }

    let Some(verification) = obj(root.get("verification").unwrap_or(&Value::Null)) else {
        errors.push("verification must be an object".to_owned());
        return errors;
    };
    push_unknown(&mut errors, verification, &["result", "evidenceRefs"]);
    if strv(verification.get("result")) != Some("pass") {
        errors.push("verification.result must be pass".to_owned());
    }
    let Some(refs) = arr(verification.get("evidenceRefs")) else {
        errors.push("verification.evidenceRefs must be a non-empty list".to_owned());
        return errors;
    };
    if refs.is_empty() || refs.len() > 64 {
        errors.push("verification.evidenceRefs must contain 1 to 64 entries".to_owned());
    }
    for (index, value) in refs.iter().enumerate() {
        let Some(locator) = strv(Some(value)) else {
            errors.push(format!(
                "verification.evidenceRefs[{index}] must be a string"
            ));
            continue;
        };
        if let Some(reason) = validate_passport_locator(locator, workspace) {
            errors.push(format!("verification.evidenceRefs[{index}] {reason}"));
        }
    }

    let Some(findings) = arr(root.get("findings")) else {
        errors.push("findings must be a list".to_owned());
        return errors;
    };
    if findings.len() > 256 {
        errors.push("findings may contain at most 256 entries".to_owned());
    }
    let mut finding_ids = HashSet::new();
    for (index, value) in findings.iter().enumerate() {
        let Some(finding) = obj(value) else {
            errors.push(format!("findings[{index}] must be an object"));
            continue;
        };
        push_unknown(
            &mut errors,
            finding,
            &["id", "severity", "disposition", "humanAcceptance"],
        );
        let id = strv(finding.get("id"));
        if id.is_none() {
            errors.push(format!("findings[{index}].id is required"));
        } else if !finding_ids.insert(id.unwrap_or_default().to_owned()) {
            errors.push(format!("findings[{index}].id must be unique"));
        }
        let severity = strv(finding.get("severity"));
        if !matches!(severity, Some("Critical" | "High" | "Medium" | "Low")) {
            errors.push(format!("findings[{index}].severity is invalid"));
        }
        let disposition = strv(finding.get("disposition"));
        if !matches!(
            disposition,
            Some("fixed" | "rejected-with-counterevidence" | "deferred" | "accepted")
        ) {
            errors.push(format!("findings[{index}].disposition is invalid"));
        }
        if severity == Some("Critical")
            && !matches!(disposition, Some("fixed" | "rejected-with-counterevidence"))
        {
            errors.push(format!(
                "findings[{index}] Critical must be fixed or rejected-with-counterevidence"
            ));
        }
        let needs_acceptance = disposition == Some("accepted")
            || (severity == Some("High") && disposition == Some("deferred"));
        if needs_acceptance {
            validate_human_acceptance(finding.get("humanAcceptance"), &mut errors, index);
        } else if let Some(acceptance) = finding.get("humanAcceptance")
            && !acceptance.is_null()
        {
            errors.push(format!(
                "findings[{index}].humanAcceptance is only allowed for accepted/deferred findings"
            ));
        }
    }
    errors.extend(scan_forbidden_content(record));
    errors
}

fn validate_human_acceptance(value: Option<&Value>, errors: &mut Vec<String>, index: usize) {
    let Some(acceptance) = value.and_then(obj) else {
        errors.push(format!("findings[{index}].humanAcceptance is required"));
        return;
    };
    let fields = [
        "approverIdentity",
        "approvalTime",
        "scope",
        "reason",
        "expiry",
        "reopenTrigger",
    ];
    push_unknown(errors, acceptance, &fields);
    for field in fields {
        if strv(acceptance.get(field)).is_none() {
            errors.push(format!(
                "findings[{index}].humanAcceptance.{field} is required"
            ));
        }
    }
}

fn validate_passport_locator(locator: &str, workspace: Option<&Path>) -> Option<String> {
    let path = Path::new(locator);
    if locator.len() > 512
        || locator.is_empty()
        || locator.contains('\\')
        || locator.contains("://")
        || path.is_absolute()
        || path.components().any(|part| {
            matches!(
                part,
                std::path::Component::ParentDir | std::path::Component::RootDir
            )
        })
    {
        return Some("must be a safe relative locator".to_owned());
    }
    let root = workspace?;
    let root = mission_center_workspace_path(root);
    let root = root.canonicalize().unwrap_or(root);
    let candidate = root.join(locator);
    let Ok(metadata) = std::fs::symlink_metadata(&candidate) else {
        return Some("must reference an existing file".to_owned());
    };
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Some("must reference a regular file".to_owned());
    }
    let Ok(real) = candidate.canonicalize() else {
        return Some("cannot resolve locator".to_owned());
    };
    if !real.starts_with(&root) {
        return Some("must resolve inside workspace".to_owned());
    }
    None
}

pub fn validate_critic_record(record: &Value) -> Vec<String> {
    let Some(r) = obj(record) else {
        return vec!["record must be an object".to_owned()];
    };
    let mut errors = scan_forbidden_content(record);
    let version = strv(r.get("schemaVersion")).unwrap_or("");
    let route = strv(r.get("route"))
        .or_else(|| strv(r.get("selectedRoute")))
        .unwrap_or("");
    if version == "1.1" {
        push_unknown(
            &mut errors,
            r,
            &[
                "schemaVersion",
                "selectedRoute",
                "executionStatus",
                "requiredByPolicy",
                "taskId",
                "chairRecordLocator",
                "reason",
                "route",
            ],
        );
        if !["skip", "critic_lite", "critic_full"].contains(&route) {
            errors.push("selectedRoute must be skip, critic_lite, or critic_full".to_owned());
        }
        if !["skipped", "not_dispatched", "completed"]
            .contains(&strv(r.get("executionStatus")).unwrap_or(""))
        {
            errors.push("executionStatus must be skipped, not_dispatched, or completed".to_owned());
        }
        if boolv(r.get("requiredByPolicy")).is_none() {
            errors.push("requiredByPolicy must be boolean".to_owned());
        }
        if strv(r.get("taskId")).is_none() {
            errors.push("taskId is required".to_owned());
        }
        if strv(r.get("chairRecordLocator")).is_none() {
            errors.push("chairRecordLocator is required".to_owned());
        } else if !strv(r.get("chairRecordLocator"))
            .unwrap()
            .replace('\\', "/")
            .starts_with("output/mission-center-critique/")
        {
            errors.push("chairRecordLocator must use output/mission-center-critique/".to_owned());
        }
        let state = strv(r.get("executionStatus")).unwrap_or("");
        if boolv(r.get("requiredByPolicy")) == Some(true) && state != "completed" {
            errors.push("requiredByPolicy records must be completed".to_owned());
        }
        if ["skipped", "not_dispatched"].contains(&state) && strv(r.get("reason")).is_none() {
            errors.push(format!("{state} requires reason"));
        }
        if state == "completed" {
            let mut projected = r.clone();
            projected.insert("schemaVersion".to_owned(), json!("1.0"));
            projected.insert("route".to_owned(), json!(route));
            for key in [
                "selectedRoute",
                "executionStatus",
                "requiredByPolicy",
                "reason",
            ] {
                projected.remove(key);
            }
            errors.extend(validate_critic_record(&Value::Object(projected)));
        }
        return errors;
    }
    push_unknown(
        &mut errors,
        r,
        &[
            "schemaVersion",
            "route",
            "selectedRoute",
            "taskId",
            "chairRecordLocator",
            "artifactManifest",
            "snapshots",
            "authorization",
            "budgets",
            "critics",
            "outcome",
            "lanes",
            "arbiter",
            "smokePassedByCouncil",
            "findings",
            "notDispatched",
            "dispatchStatus",
        ],
    );
    if version != "1.0" {
        errors.push("schemaVersion must be 1.0 or 1.1".to_owned());
    }
    if !["skip", "critic_lite", "critic_full"].contains(&route) {
        errors.push("route must be skip, critic_lite, or critic_full".to_owned());
        return errors;
    }
    if strv(r.get("taskId")).is_none() {
        errors.push("taskId is required".to_owned());
    }
    if strv(r.get("chairRecordLocator")).is_none() {
        errors.push("chairRecordLocator is required".to_owned());
    } else if !strv(r.get("chairRecordLocator"))
        .unwrap()
        .replace('\\', "/")
        .starts_with("output/mission-center-critique/")
    {
        errors.push("chairRecordLocator must use output/mission-center-critique/".to_owned());
    }
    let manifest = r.get("artifactManifest").and_then(|v| {
        if v.is_array() {
            Some(v)
        } else {
            obj(v).and_then(|m| m.get("entries").or_else(|| m.get("artifacts")))
        }
    });
    let mut manifest_lanes = Vec::new();
    if arr(manifest).is_none_or(Vec::is_empty) {
        errors.push("artifactManifest must contain entries".to_owned());
    } else {
        for (i, v) in arr(manifest).unwrap().iter().enumerate() {
            if let Some(e) = obj(v) {
                push_unknown(
                    &mut errors,
                    e,
                    &["locator", "sha256", "laneId", "version", "archiveLocator"],
                );
                if strv(e.get("locator")).is_none() {
                    errors.push(format!("artifactManifest entry {i} needs locator"));
                }
                if let Some(lane) = strv(e.get("laneId")) {
                    manifest_lanes.push(lane.to_owned());
                } else {
                    errors.push(format!("artifactManifest entry {i} needs laneId"));
                }
                let hash_ok = strv(e.get("sha256"))
                    .is_some_and(|h| h.len() == 64 && h.bytes().all(|b| b.is_ascii_hexdigit()));
                if strv(e.get("sha256")).is_some() && !hash_ok {
                    errors.push(format!("artifactManifest entry {i} has invalid sha256"));
                }
                if !hash_ok
                    && strv(e.get("version")).is_none()
                    && strv(e.get("archiveLocator")).is_none()
                {
                    errors.push(format!(
                        "artifactManifest entry {i} needs sha256, version, or archiveLocator"
                    ));
                }
            } else {
                errors.push(format!("artifactManifest entry {i} needs locator"));
            }
        }
    }
    let snapshots = arr(r.get("snapshots"));
    if snapshots.is_none_or(|v| v.is_empty() || v.len() > 2) {
        errors.push("snapshots must contain one or two snapshots".to_owned());
    } else if snapshots.unwrap().iter().all(|v| obj(v).is_some()) {
        let first = obj(&snapshots.unwrap()[0]).unwrap();
        if first
            .get("parent")
            .is_some_and(|v| !v.is_null() && strv(Some(v)) != Some(""))
        {
            errors.push("first snapshot must not have a parent".to_owned());
        }
        let mut seen = HashSet::new();
        let first_id = strv(first.get("id")).or_else(|| strv(first.get("snapshotId")));
        for (i, v) in snapshots.unwrap().iter().enumerate() {
            let s = obj(v).unwrap();
            push_unknown(
                &mut errors,
                s,
                &[
                    "id",
                    "snapshotId",
                    "parent",
                    "revision",
                    "hash",
                    "evidenceLinks",
                ],
            );
            let id = strv(s.get("id")).or_else(|| strv(s.get("snapshotId")));
            if id.is_none_or(|x| !seen.insert(x.to_owned())) {
                errors.push(format!("snapshot {i} needs a unique id"));
            }
            for f in ["revision", "hash"] {
                if strv(s.get(f)).is_none() {
                    errors.push(format!("snapshot {i} needs {f}"));
                }
            }
            if arr(s.get("evidenceLinks")).is_none_or(Vec::is_empty) {
                errors.push(format!("snapshot {i} needs evidenceLinks"));
            }
        }
        if snapshots.unwrap().len() == 2
            && strv(obj(&snapshots.unwrap()[1]).unwrap().get("parent")) != first_id
        {
            errors.push("delta snapshot parent must reference first snapshot".to_owned());
        }
    } else {
        errors.push("each snapshot must be an object".to_owned());
    }
    if route != "skip" {
        if boolv(
            r.get("authorization")
                .and_then(|v| obj(v))
                .and_then(|m| m.get("explicitApproval")),
        ) != Some(true)
        {
            errors.push("critic routes require explicit authorization".to_owned());
        }
        let budgets = r.get("budgets").and_then(|v| obj(v));
        if budgets.is_none()
            || ["total", "perSeat", "tool", "wallClock"]
                .iter()
                .any(|f| finite_num(budgets.and_then(|b| b.get(*f))).is_none_or(|n| n <= 0.0))
        {
            errors.push(
                "critic routes require positive total, perSeat, tool, and wallClock budgets"
                    .to_owned(),
            );
        }
        let critics = arr(r.get("critics"));
        let min = if route == "critic_full" { 3 } else { 2 };
        let mut critic_ids = HashSet::new();
        if critics.is_none_or(|v| v.len() < min) {
            errors.push("route has insufficient critic seats".to_owned());
        } else {
            for c in critics.unwrap() {
                if let Some(cmap) = obj(c) {
                    push_unknown(&mut errors, cmap, &["id", "name", "role", "laneIds"]);
                }
                if let Some(id) = obj(c).and_then(|m| strv(m.get("id"))) {
                    if !critic_ids.insert(id.to_owned()) {
                        errors.push("critic seats need unique ids".to_owned());
                    }
                } else {
                    errors.push("critic seats need unique ids".to_owned());
                }
            }
        }
        if !["passed", "limited", "blocked"].contains(&strv(r.get("outcome")).unwrap_or("")) {
            errors.push("critic routes require passed, limited, or blocked outcome".to_owned());
        }
        let lanes = arr(r.get("lanes"));
        let mut lane_ids = HashSet::new();
        let mut uncovered = false;
        if lanes.is_none_or(Vec::is_empty) {
            errors.push("critic routes require non-empty lanes".to_owned());
        } else {
            for (i, v) in lanes.unwrap().iter().enumerate() {
                let Some(l) = obj(v) else {
                    errors.push(format!("lane {i} must be an object"));
                    continue;
                };
                push_unknown(
                    &mut errors,
                    l,
                    &[
                        "id",
                        "kind",
                        "required",
                        "seatId",
                        "evidenceLocator",
                        "coverageStatus",
                        "capabilityReason",
                        "journeyCoverage",
                    ],
                );
                let id = strv(l.get("id"));
                if id.is_none_or(|x| !lane_ids.insert(x.to_owned())) {
                    errors.push(format!("lane {i} needs a unique id"));
                }
                if strv(l.get("kind")).is_none() {
                    errors.push(format!("lane {i} needs kind"));
                }
                if boolv(l.get("required")).is_none() {
                    errors.push(format!("lane {i} needs boolean required"));
                }
                let status = strv(l.get("coverageStatus")).unwrap_or("");
                if !["covered", "unknown", "not_applicable"].contains(&status) {
                    errors.push(format!("lane {i} has invalid coverageStatus"));
                }
                if status == "covered" {
                    if !critic_ids.contains(l.get("seatId").and_then(Value::as_str).unwrap_or("")) {
                        errors.push(format!("lane {i} needs an assigned critic seat"));
                    }
                    if strv(l.get("evidenceLocator")).is_none() {
                        errors.push(format!("lane {i} needs evidenceLocator"));
                    }
                } else if strv(l.get("capabilityReason")).is_none() {
                    errors.push(format!("lane {i} needs capabilityReason"));
                }
                if boolv(l.get("required")) == Some(true) && status != "covered" {
                    uncovered = true;
                }
            }
        }
        for id in manifest_lanes {
            if !lane_ids.contains(&id) {
                errors.push(format!("artifactManifest references unknown lane {id}"));
            }
        }
        if uncovered && strv(r.get("outcome")) == Some("passed") {
            errors.push("required unknown coverage prevents passed outcome".to_owned());
        }
        if route == "critic_full"
            && obj(r.get("arbiter").unwrap_or(&Value::Null))
                .and_then(|a| strv(a.get("id")))
                .is_none_or(|id| critic_ids.contains(id))
        {
            errors.push("critic_full requires an independent arbiter".to_owned());
        }
        if r.get("notDispatched") == Some(&Value::Bool(true))
            || strv(r.get("dispatchStatus")) == Some("notDispatched")
        {
            errors.push("critic routes cannot be notDispatched".to_owned());
        }
    }
    if boolv(r.get("smokePassedByCouncil")) == Some(true) {
        errors.push("council evidence cannot be smoke evidence".to_owned());
    }
    if let Some(findings) = arr(r.get("findings")) {
        let mut seen = HashSet::new();
        for (i, v) in findings.iter().enumerate() {
            let Some(f) = obj(v) else {
                errors.push(format!("finding {i} must be an object"));
                continue;
            };
            push_unknown(
                &mut errors,
                f,
                &[
                    "id",
                    "severity",
                    "category",
                    "observation",
                    "evidenceLocator",
                    "reproOrReadPath",
                    "impact",
                    "confidence",
                    "unknown",
                    "recommendation",
                    "criticProposedDisposition",
                    "chairFinalDisposition",
                    "humanAcceptance",
                    "counterevidence",
                    "counterEvidenceRefs",
                ],
            );
            let id = strv(f.get("id"));
            if !critic_finding_id(f.get("id")) || id.is_none_or(|x| !seen.insert(x.to_owned())) {
                errors.push(format!("finding {i} needs a unique stable id"));
            }
            if !["Critical", "High", "Medium", "Low"]
                .contains(&strv(f.get("severity")).unwrap_or(""))
            {
                errors.push(format!("finding {i} has invalid severity"));
            }
            for field in [
                "category",
                "observation",
                "evidenceLocator",
                "reproOrReadPath",
                "impact",
                "confidence",
                "recommendation",
            ] {
                if strv(f.get(field)).is_none() {
                    errors.push(format!("finding {i} needs {field}"));
                }
            }
            if !f.contains_key("unknown") {
                errors.push(format!("finding {i} needs unknown"));
            }
            if ![
                "fixed",
                "rejected-with-counterevidence",
                "deferred",
                "accepted",
            ]
            .contains(&strv(f.get("criticProposedDisposition")).unwrap_or(""))
            {
                errors.push(format!("finding {i} needs criticProposedDisposition"));
            }
            let disposition = strv(f.get("chairFinalDisposition")).unwrap_or("");
            if ![
                "fixed",
                "rejected-with-counterevidence",
                "deferred",
                "accepted",
            ]
            .contains(&disposition)
            {
                errors.push(format!("finding {i} has invalid chairFinalDisposition"));
            }
            let severity = strv(f.get("severity")).unwrap_or("");
            if severity == "Critical" && disposition == "accepted" {
                errors.push(format!("finding {i}: Critical cannot be human accepted"));
            }
            if severity == "Critical"
                && !["fixed", "rejected-with-counterevidence"].contains(&disposition)
            {
                errors.push(format!("finding {i}: unresolved Critical finding"));
            }
            if disposition == "rejected-with-counterevidence"
                && f.get("counterevidence")
                    .or_else(|| f.get("counterEvidenceRefs"))
                    .is_none_or(|value| match value {
                        Value::String(text) => text.trim().is_empty(),
                        Value::Array(items) => items.is_empty(),
                        _ => true,
                    })
            {
                errors.push(format!(
                    "finding {i}: rejected-with-counterevidence needs counterevidence"
                ));
            }
            if severity == "High"
                && disposition == "deferred"
                && !valid_human_acceptance(f.get("humanAcceptance"))
            {
                errors.push(format!(
                    "finding {i}: deferred High finding needs complete humanAcceptance"
                ));
            }
            if disposition == "accepted" && !valid_human_acceptance(f.get("humanAcceptance")) {
                errors.push(format!(
                    "finding {i}: accepted finding needs complete humanAcceptance"
                ));
            }
        }
    } else if r.contains_key("findings") {
        errors.push("findings must be a list".to_owned());
    }
    errors
}

const SHIFT_METRICS: [&str; 8] = [
    "HRA",
    "TFCA",
    "SMIR",
    "WBR",
    "TVP",
    "EvidenceCoverage",
    "FalseDone",
    "RecoveryDistance",
];
fn bounded_identifier(value: Option<&Value>, max: usize) -> bool {
    let Some(text) = strv(value) else {
        return false;
    };
    text.len() <= max
        && text
            .as_bytes()
            .first()
            .is_some_and(u8::is_ascii_alphanumeric)
        && text
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
}

fn critic_finding_id(value: Option<&Value>) -> bool {
    let Some(id) = strv(value) else {
        return false;
    };
    let Some(rest) = id.strip_prefix("CACC-") else {
        return false;
    };
    let pieces: Vec<&str> = rest.split('-').collect();
    if pieces.len() < 4 {
        return false;
    }
    let hex = pieces[pieces.len() - 2];
    let ordinal = pieces[pieces.len() - 1];
    !pieces[..pieces.len() - 2].is_empty()
        && pieces[..pieces.len() - 2].iter().all(|part| {
            !part.is_empty()
                && part
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        })
        && hex.len() == 8
        && hex
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        && ordinal
            .as_bytes()
            .first()
            .is_some_and(|byte| (b'1'..=b'9').contains(byte))
        && ordinal.bytes().all(|byte| byte.is_ascii_digit())
}

fn timezone_aware_time(value: Option<&Value>) -> bool {
    iso_timestamp(value)
}

fn valid_human_acceptance(value: Option<&Value>) -> bool {
    let Some(map) = value.and_then(obj) else {
        return false;
    };
    let fields = [
        "approverIdentity",
        "approvalTime",
        "scope",
        "reason",
        "expiry",
        "reopenTrigger",
    ];
    map.len() == fields.len()
        && map.keys().all(|key| fields.contains(&key.as_str()))
        && fields
            .iter()
            .all(|field| strv(map.get(*field)).is_some_and(|text| text.len() <= 512))
        && timezone_aware_time(map.get("approvalTime"))
        && timezone_aware_time(map.get("expiry"))
}
pub fn validate_shift_loss(record: &Value, workspace: Option<&Path>) -> Vec<String> {
    let Some(r) = obj(record) else {
        return vec!["result must be an object".to_owned()];
    };
    let mut errors = scan_forbidden_content(record);
    push_unknown(
        &mut errors,
        r,
        &[
            "schemaVersion",
            "artifactType",
            "taskId",
            "variant",
            "cases",
        ],
    );
    for f in [
        "schemaVersion",
        "artifactType",
        "taskId",
        "variant",
        "cases",
    ] {
        if !r.contains_key(f) {
            errors.push(format!("result.{f} is required"));
        }
    }
    if strv(r.get("schemaVersion")) != Some("1.0") {
        errors.push("schemaVersion must be 1.0".to_owned());
    }
    if strv(r.get("artifactType")) != Some("shift-loss-eval") {
        errors.push("artifactType must be shift-loss-eval".to_owned());
    }
    let task = strv(r.get("taskId"));
    if task.is_none() {
        errors.push("result.taskId must be bounded non-empty text".to_owned());
    } else if let Some(task) = task
        && workspace.is_some()
        && !canonical_task_exists(workspace, task)
    {
        errors.push("result.taskId is not present in canonical tasks.md".to_owned());
    }
    let variant = strv(r.get("variant"));
    if !bounded_identifier(r.get("variant"), 64) {
        errors.push("result.variant must match the bounded identifier pattern".to_owned());
    }
    let cases = arr(r.get("cases"));
    if cases.is_none_or(Vec::is_empty) {
        errors.push("result.cases must be a non-empty list".to_owned());
        return errors;
    }
    if cases.is_some_and(|items| items.len() > 128) {
        errors.push("result.cases may contain at most 128 items".to_owned());
    }
    let mut ids = HashSet::new();
    for (i, v) in cases.unwrap().iter().enumerate() {
        let Some(c) = obj(v) else {
            errors.push(format!("cases[{i}] must be an object"));
            continue;
        };
        push_unknown(
            &mut errors,
            c,
            &[
                "caseId",
                "taskId",
                "variant",
                "shouldRecall",
                "shouldIgnore",
                "shouldSupersede",
                "actualRecall",
                "actualIgnore",
                "actualSupersede",
                "firstCorrectActionMs",
                "staleMemoryInjected",
                "wrongBranch",
                "tokensUsed",
                "verifiedProgress",
                "evidenceClaims",
                "evidenceBackedClaims",
                "falseDone",
                "recoveryDistance",
                "unverifiedDestructiveAction",
                "activeGuardrailWithoutSource",
                "multipleWritersSameBranch",
            ],
        );
        for f in [
            "caseId",
            "taskId",
            "variant",
            "shouldRecall",
            "shouldIgnore",
            "shouldSupersede",
            "actualRecall",
            "actualIgnore",
            "actualSupersede",
            "firstCorrectActionMs",
            "staleMemoryInjected",
            "wrongBranch",
            "tokensUsed",
            "verifiedProgress",
            "evidenceClaims",
            "evidenceBackedClaims",
            "falseDone",
            "recoveryDistance",
            "unverifiedDestructiveAction",
            "activeGuardrailWithoutSource",
            "multipleWritersSameBranch",
        ] {
            if !c.contains_key(f) {
                errors.push(format!("cases[{i}].{f} is required"));
            }
        }
        let id = strv(c.get("caseId"));
        if !bounded_identifier(c.get("caseId"), 128) {
            errors.push(format!(
                "cases[{i}].caseId must match the bounded identifier pattern"
            ));
        } else if !ids.insert(id.unwrap().to_owned()) {
            errors.push(format!("duplicate caseId: {}", id.unwrap()));
        }
        if c.get("taskId").and_then(Value::as_str) != task {
            errors.push(format!("cases[{i}].taskId must match result.taskId"));
        }
        if c.get("variant").and_then(Value::as_str) != variant {
            errors.push(format!("cases[{i}].variant must match result.variant"));
        }
        let targets = ["shouldRecall", "shouldIgnore", "shouldSupersede"];
        if !targets.iter().any(|f| boolv(c.get(*f)) == Some(true)) {
            errors.push(format!("cases[{i}] must have at least one true shouldRecall/shouldIgnore/shouldSupersede target"));
        }
        for f in [
            "shouldRecall",
            "shouldIgnore",
            "shouldSupersede",
            "actualRecall",
            "actualIgnore",
            "actualSupersede",
            "staleMemoryInjected",
            "wrongBranch",
            "verifiedProgress",
            "falseDone",
            "unverifiedDestructiveAction",
            "activeGuardrailWithoutSource",
            "multipleWritersSameBranch",
        ] {
            if c.get(f).and_then(Value::as_bool).is_none() {
                errors.push(format!("cases[{i}].{f} must be boolean"));
            }
        }
        for f in ["tokensUsed", "evidenceClaims", "evidenceBackedClaims"] {
            if c.get(f).and_then(Value::as_i64).is_none_or(|n| n < 0) {
                errors.push(format!("cases[{i}].{f} must be a non-negative integer"));
            }
        }
        if c.get("evidenceBackedClaims").and_then(Value::as_i64)
            > c.get("evidenceClaims").and_then(Value::as_i64)
        {
            errors.push(format!(
                "cases[{i}].evidenceBackedClaims cannot exceed evidenceClaims"
            ));
        }
        for f in ["firstCorrectActionMs", "recoveryDistance"] {
            if c.get(f).is_some_and(|v| !v.is_null())
                && finite_num(c.get(f)).is_none_or(|n| n < 0.0)
            {
                errors.push(format!("cases[{i}].{f} must be a non-negative number"));
            }
        }
    }
    errors
}
fn ratio(n: f64, d: f64) -> Value {
    if d == 0.0 { Value::Null } else { json!(n / d) }
}
pub fn aggregate_shift_cases(cases: &[Value]) -> Result<Value, Vec<String>> {
    let mut validation_errors = Vec::new();
    for (index, value) in cases.iter().enumerate() {
        let Some(case) = obj(value) else {
            validation_errors.push(format!("cases[{index}] must be an object"));
            continue;
        };
        for field in [
            "shouldRecall",
            "shouldIgnore",
            "shouldSupersede",
            "actualRecall",
            "actualIgnore",
            "actualSupersede",
            "firstCorrectActionMs",
            "staleMemoryInjected",
            "wrongBranch",
            "tokensUsed",
            "verifiedProgress",
            "evidenceClaims",
            "evidenceBackedClaims",
            "falseDone",
            "recoveryDistance",
            "unverifiedDestructiveAction",
            "activeGuardrailWithoutSource",
            "multipleWritersSameBranch",
        ] {
            if !case.contains_key(field) {
                validation_errors.push(format!("cases[{index}].{field} is required"));
            }
        }
        for field in [
            "shouldRecall",
            "shouldIgnore",
            "shouldSupersede",
            "actualRecall",
            "actualIgnore",
            "actualSupersede",
            "staleMemoryInjected",
            "wrongBranch",
            "verifiedProgress",
            "falseDone",
            "unverifiedDestructiveAction",
            "activeGuardrailWithoutSource",
            "multipleWritersSameBranch",
        ] {
            if boolv(case.get(field)).is_none() {
                validation_errors.push(format!("cases[{index}].{field} must be boolean"));
            }
        }
        for field in ["tokensUsed", "evidenceClaims", "evidenceBackedClaims"] {
            if case
                .get(field)
                .and_then(Value::as_i64)
                .is_none_or(|value| value < 0)
            {
                validation_errors.push(format!(
                    "cases[{index}].{field} must be a non-negative integer"
                ));
            }
        }
        for field in ["firstCorrectActionMs", "recoveryDistance"] {
            if case.get(field).is_some_and(|value| {
                !value.is_null() && finite_num(Some(value)).is_none_or(|number| number < 0.0)
            }) {
                validation_errors.push(format!(
                    "cases[{index}].{field} must be a non-negative number or null"
                ));
            }
        }
    }
    if !validation_errors.is_empty() {
        return Err(validation_errors);
    }
    let total = cases.len() as f64;
    let mut targets = 0f64;
    let mut correct = 0f64;
    let mut action_sum = 0f64;
    let mut action_count = 0f64;
    let mut stale = 0f64;
    let mut wrong = 0f64;
    let mut tokens = 0f64;
    let mut verified = 0f64;
    let mut claims = 0f64;
    let mut backed = 0f64;
    let mut false_done = 0f64;
    let mut recovery = 0f64;
    let mut recovery_count = 0f64;
    let mut destructive = 0f64;
    let mut guardrail = 0f64;
    let mut writers = 0f64;
    for v in cases {
        let Some(c) = obj(v) else {
            continue;
        };
        let b = |f: &str| boolv(c.get(f)) == Some(true);
        targets += b("shouldRecall") as i32 as f64
            + b("shouldIgnore") as i32 as f64
            + b("shouldSupersede") as i32 as f64;
        correct += (b("shouldRecall") && b("actualRecall")) as i32 as f64
            + (b("shouldIgnore") && b("actualIgnore")) as i32 as f64
            + (b("shouldSupersede") && b("actualSupersede")) as i32 as f64;
        if let Some(n) = finite_num(c.get("firstCorrectActionMs")) {
            action_sum += n;
            action_count += 1.0;
        }
        stale += b("staleMemoryInjected") as i32 as f64;
        wrong += b("wrongBranch") as i32 as f64;
        tokens += finite_num(c.get("tokensUsed")).unwrap_or(0.0);
        verified += b("verifiedProgress") as i32 as f64;
        claims += finite_num(c.get("evidenceClaims")).unwrap_or(0.0);
        backed += finite_num(c.get("evidenceBackedClaims")).unwrap_or(0.0);
        false_done += b("falseDone") as i32 as f64;
        if let Some(n) = finite_num(c.get("recoveryDistance")) {
            recovery += n;
            recovery_count += 1.0;
        }
        destructive += b("unverifiedDestructiveAction") as i32 as f64;
        guardrail += b("activeGuardrailWithoutSource") as i32 as f64;
        writers += b("multipleWritersSameBranch") as i32 as f64;
    }
    let hard = json!({"FalseDone":false_done,"UnverifiedDestructiveAction":destructive,"ActiveGuardrailWithoutSource":guardrail,"MultipleWritersSameBranch":writers});
    let hard_ok = false_done == 0.0 && destructive == 0.0 && guardrail == 0.0 && writers == 0.0;
    Ok(
        json!({"caseCount":cases.len(),"metrics":{"HRA":ratio(correct,targets),"TFCA":ratio(action_sum,action_count),"SMIR":ratio(stale,total),"WBR":ratio(wrong,total),"TVP":ratio(tokens,verified),"EvidenceCoverage":ratio(backed,claims),"FalseDone":false_done,"RecoveryDistance":ratio(recovery,recovery_count)},"denominators":{"HRA":targets,"TFCA":action_count,"SMIR":total,"WBR":total,"TVP":verified,"total":total,"EvidenceCoverage":claims,"RecoveryDistance":recovery_count},"hardConstraints":hard,"hardConstraintsPassed":hard_ok,"overallStatus":if !hard_ok{"failed_hard_constraint"}else if cases.is_empty(){"incomplete"}else{"passed"}}),
    )
}
pub fn aggregate_cases(cases: &[Value]) -> Result<Value, Vec<String>> {
    aggregate_shift_cases(cases)
}
pub fn evaluate_shift_loss(record: &Value, workspace: Option<&Path>) -> Value {
    let errors = validate_shift_loss(record, workspace);
    if !errors.is_empty() {
        return json!({"schemaVersion":"1.0","artifactType":"shift-loss-eval","valid":false,"errors":errors});
    }
    let r = obj(record).unwrap();
    let mut out = match aggregate_shift_cases(arr(r.get("cases")).unwrap()) {
        Ok(value) => value,
        Err(errors) => {
            return json!({"schemaVersion":"1.0","artifactType":"shift-loss-eval","valid":false,"errors":errors});
        }
    };
    if let Some(m) = out.as_object_mut() {
        m.insert("schemaVersion".to_owned(), json!("1.0"));
        m.insert("artifactType".to_owned(), json!("shift-loss-eval"));
        m.insert("taskId".to_owned(), r.get("taskId").cloned().unwrap());
        m.insert("variant".to_owned(), r.get("variant").cloned().unwrap());
        m.insert("valid".to_owned(), json!(true));
    }
    out
}
pub fn compare_shift_loss(baseline: &Value, new: &Value, workspace: Option<&Path>) -> Value {
    let be = validate_shift_loss(baseline, workspace);
    let ne = validate_shift_loss(new, workspace);
    if !be.is_empty() || !ne.is_empty() {
        return json!({"complete":false,"improvementClaim":false,"errors":{"baseline":be,"new":ne}});
    }
    let b = obj(baseline).unwrap();
    let n = obj(new).unwrap();
    if b.get("taskId") != n.get("taskId") {
        return json!({"complete":false,"improvementClaim":false,"errors":{"pair":["baseline and new taskId must match"]}});
    }
    let bm: HashMap<String, Value> = arr(b.get("cases"))
        .unwrap()
        .iter()
        .filter_map(|v| {
            obj(v).and_then(|m| strv(m.get("caseId")).map(|id| (id.to_owned(), v.clone())))
        })
        .collect();
    let nm: HashMap<String, Value> = arr(n.get("cases"))
        .unwrap()
        .iter()
        .filter_map(|v| {
            obj(v).and_then(|m| strv(m.get("caseId")).map(|id| (id.to_owned(), v.clone())))
        })
        .collect();
    let mut shared: Vec<String> = bm
        .keys()
        .filter(|id| nm.contains_key(*id))
        .cloned()
        .collect();
    let mut missing_b: Vec<String> = nm
        .keys()
        .filter(|id| !bm.contains_key(*id))
        .cloned()
        .collect();
    let mut missing_n: Vec<String> = bm
        .keys()
        .filter(|id| !nm.contains_key(*id))
        .cloned()
        .collect();
    shared.sort();
    missing_b.sort();
    missing_n.sort();
    let complete = missing_b.is_empty() && missing_n.is_empty();
    let mut out = json!({"taskId":b.get("taskId"),"baselineVariant":b.get("variant"),"newVariant":n.get("variant"),"sharedCaseIds":shared,"missingBaseline":missing_b,"missingNew":missing_n,"complete":complete,"improvementClaim":false});
    if complete {
        let old = match aggregate_shift_cases(
            &shared.iter().map(|id| bm[id].clone()).collect::<Vec<_>>(),
        ) {
            Ok(value) => value,
            Err(errors) => {
                return json!({"complete":false,"improvementClaim":false,"errors":errors});
            }
        };
        let cur = match aggregate_shift_cases(
            &shared.iter().map(|id| nm[id].clone()).collect::<Vec<_>>(),
        ) {
            Ok(value) => value,
            Err(errors) => {
                return json!({"complete":false,"improvementClaim":false,"errors":errors});
            }
        };
        let mut del = Map::new();
        for name in SHIFT_METRICS {
            let a = old
                .get("metrics")
                .and_then(|v| obj(v))
                .and_then(|m| m.get(name));
            let c = cur
                .get("metrics")
                .and_then(|v| obj(v))
                .and_then(|m| m.get(name));
            del.insert(
                name.to_owned(),
                if a.is_none_or(Value::is_null) || c.is_none_or(Value::is_null) {
                    Value::Null
                } else {
                    json!(c.unwrap().as_f64().unwrap() - a.unwrap().as_f64().unwrap())
                },
            );
        }
        out.as_object_mut()
            .unwrap()
            .insert("metricDeltas".to_owned(), Value::Object(del));
    } else {
        out.as_object_mut()
            .unwrap()
            .insert("status".to_owned(), json!("incomplete_paired_cases"));
    }
    out
}

/// Validate the bounded timestamp contract used by probe records.
///
/// Python's `datetime.fromisoformat` accepts arbitrary fractional precision;
/// Rust deliberately caps it at nine digits to keep input size deterministic.
/// The differential corpus uses invalid clock/offset values, while the
/// precision cap remains a Rust contract edge.
fn iso_timestamp(value: Option<&Value>) -> bool {
    let Some(text) = strv(value) else {
        return false;
    };
    const MAX_TIMESTAMP_BYTES: usize = 64;
    if text.is_empty() || text.len() > MAX_TIMESTAMP_BYTES {
        return false;
    }
    let bytes = text.as_bytes();
    if bytes.len() < 20
        || bytes.get(4) != Some(&b'-')
        || bytes.get(7) != Some(&b'-')
        || bytes.get(10) != Some(&b'T')
        || bytes.get(13) != Some(&b':')
        || bytes.get(16) != Some(&b':')
        || !valid_calendar_date(text.get(0..10))
    {
        return false;
    }
    let Some(hour) = parse_two_digits(bytes, 11) else {
        return false;
    };
    let Some(minute) = parse_two_digits(bytes, 14) else {
        return false;
    };
    let Some(second) = parse_two_digits(bytes, 17) else {
        return false;
    };
    if hour > 23 || minute > 59 || second > 59 {
        return false;
    }
    let mut cursor = 19;
    if bytes.get(cursor) == Some(&b'.') {
        cursor += 1;
        let start = cursor;
        while bytes.get(cursor).is_some_and(u8::is_ascii_digit) {
            cursor += 1;
        }
        let fractional_digits = cursor - start;
        if !(1..=9).contains(&fractional_digits) {
            return false;
        }
    }
    if bytes.get(cursor) == Some(&b'Z') {
        cursor += 1;
    } else {
        if bytes.len() != cursor + 6
            || !matches!(bytes.get(cursor), Some(b'+') | Some(b'-'))
            || bytes.get(cursor + 3) != Some(&b':')
        {
            return false;
        }
        let Some(offset_hour) = parse_two_digits(bytes, cursor + 1) else {
            return false;
        };
        let Some(offset_minute) = parse_two_digits(bytes, cursor + 4) else {
            return false;
        };
        if offset_hour > 23 || offset_minute > 59 {
            return false;
        }
        cursor += 6;
    }
    cursor == bytes.len()
}

fn parse_two_digits(bytes: &[u8], start: usize) -> Option<u8> {
    let high = *bytes.get(start)?;
    let low = *bytes.get(start + 1)?;
    if !high.is_ascii_digit() || !low.is_ascii_digit() {
        return None;
    }
    Some((high - b'0') * 10 + (low - b'0'))
}

fn valid_calendar_date(value: Option<&str>) -> bool {
    let Some(value) = value else {
        return false;
    };
    if value.len() != 10
        || value.as_bytes().get(4) != Some(&b'-')
        || value.as_bytes().get(7) != Some(&b'-')
        || !value
            .bytes()
            .enumerate()
            .all(|(i, b)| matches!(i, 4 | 7) || b.is_ascii_digit())
    {
        return false;
    }
    let Ok(year) = value[0..4].parse::<u32>() else {
        return false;
    };
    let Ok(month) = value[5..7].parse::<u32>() else {
        return false;
    };
    let Ok(day) = value[8..10].parse::<u32>() else {
        return false;
    };
    if year == 0 {
        return false;
    }
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if leap => 29,
        2 => 28,
        _ => 0,
    };
    (1..=days).contains(&day)
}

pub fn validate_compatibility_matrix(matrix: &Value) -> Vec<String> {
    let Some(m) = obj(matrix) else {
        return vec!["matrix must be an object".to_owned()];
    };
    let mut e = Vec::new();
    push_unknown(
        &mut e,
        m,
        &[
            "schemaVersion",
            "spike",
            "title",
            "observedAt",
            "scope",
            "officialSources",
            "localProbe",
            "probeRecords",
            "matrix",
            "decision",
        ],
    );
    for f in [
        "schemaVersion",
        "spike",
        "title",
        "observedAt",
        "scope",
        "officialSources",
        "localProbe",
        "probeRecords",
        "matrix",
        "decision",
    ] {
        if !m.contains_key(f) {
            e.push(format!("matrix missing required fields: {f}"));
        }
    }
    if strv(m.get("schemaVersion")) != Some("1.0") {
        e.push("schemaVersion must be 1.0".to_owned());
    }
    if strv(m.get("spike")) != Some("MC-044") {
        e.push("spike must be MC-044".to_owned());
    }
    if strv(m.get("title")).is_none_or(|v| {
        v.trim().is_empty() || v.len() > 256 || v.contains('\n') || v.contains('\r')
    }) {
        e.push("title must be a bounded string".to_owned());
    }
    let date = |v: Option<&Value>| valid_calendar_date(strv(v));
    if !date(m.get("observedAt")) {
        e.push("observedAt must be an ISO date".to_owned());
    }
    if strv(m.get("scope")).is_none_or(|scope| {
        scope.trim().is_empty() || scope.len() > 512 || scope.contains('\n') || scope.contains('\r')
    }) {
        e.push("scope must be a bounded string".to_owned());
    }
    let sources = arr(m.get("officialSources"));
    if sources.is_none_or(Vec::is_empty) {
        e.push("officialSources must be a non-empty list".to_owned());
    } else {
        for (i, source) in sources.unwrap().iter().enumerate() {
            let Some(s) = obj(source) else {
                e.push(format!("officialSources[{i}] must be an object"));
                continue;
            };
            push_unknown(&mut e, s, &["topic", "url", "evidence"]);
            for field in ["topic", "url", "evidence"] {
                if strv(s.get(field)).is_none() {
                    e.push(format!("officialSources[{i}] missing {field}"));
                }
                if strv(s.get(field)).is_none_or(|value| {
                    value.trim().is_empty()
                        || value.len() > 1024
                        || value.contains('\n')
                        || value.contains('\r')
                }) {
                    e.push(format!("officialSources[{i}].{field} is overlong"));
                }
            }
        }
    }
    let safe_locator = |value: Option<&Value>| {
        let Some(s) = strv(value) else {
            return false;
        };
        let path = s.split('#').next().unwrap_or("").replace('\\', "/");
        let bytes = path.as_bytes();
        let windows_drive = bytes.len() >= 3
            && bytes[1] == b':'
            && bytes[0].is_ascii_alphabetic()
            && (bytes[2] == b'/' || bytes[2] == b'\\');
        !s.trim().is_empty()
            && !s.contains('\n')
            && !s.contains('\r')
            && !path.is_empty()
            && !windows_drive
            && !path.starts_with('/')
            && !s.starts_with('\\')
            && !s.contains("://")
            && !path
                .split('/')
                .any(|part| part == ".." || part == "." || part.is_empty())
            && s.len() <= 512
    };
    if let Some(probe) = obj(m.get("localProbe").unwrap_or(&Value::Null)) {
        push_unknown(
            &mut e,
            probe,
            &[
                "platform",
                "command",
                "observedPath",
                "packageEvidence",
                "cliExecution",
                "cliExecutionEvidence",
                "wslShell",
                "wslShellEvidence",
                "wslExecution",
                "wslExecutionEvidence",
                "nonDestructiveProbe",
                "nonDestructiveProbeEvidence",
            ],
        );
        for field in [
            "platform",
            "command",
            "observedPath",
            "packageEvidence",
            "cliExecution",
            "cliExecutionEvidence",
            "wslShell",
            "wslShellEvidence",
            "wslExecution",
            "wslExecutionEvidence",
            "nonDestructiveProbe",
            "nonDestructiveProbeEvidence",
        ] {
            if strv(probe.get(field)).is_none() {
                e.push(format!("localProbe missing {field}"));
            }
        }
    } else {
        e.push("localProbe must be an object".to_owned());
    }
    if !m.get("decision").is_some_and(|v| obj(v).is_some()) {
        e.push("decision must be an object".to_owned());
    }
    let mut probe_ids = HashSet::new();
    if arr(m.get("probeRecords")).is_none_or(Vec::is_empty) {
        e.push("probeRecords must be a non-empty list".to_owned());
    }
    for (i, v) in arr(m.get("probeRecords")).into_iter().flatten().enumerate() {
        if let Some(p) = obj(v) {
            push_unknown(
                &mut e,
                p,
                &[
                    "id",
                    "command",
                    "platform",
                    "recordedAt",
                    "exitCode",
                    "resultCategory",
                    "evidenceLocator",
                ],
            );
            for f in [
                "id",
                "command",
                "platform",
                "recordedAt",
                "exitCode",
                "resultCategory",
                "evidenceLocator",
            ] {
                if !p.contains_key(f) {
                    e.push(format!("probeRecords[{i}] missing required fields: {f}"));
                }
            }
            if !["Windows", "WSL"].contains(&strv(p.get("platform")).unwrap_or("")) {
                e.push(format!("probeRecords[{i}].platform has an invalid value"));
            }
            if strv(p.get("id")).is_none_or(|id| {
                id.trim().is_empty() || id.len() > 128 || id.contains('\n') || id.contains('\r')
            }) {
                e.push(format!("probeRecords[{i}].id must be a bounded string"));
            } else if strv(p.get("id")).is_some_and(|id| !probe_ids.insert(id.to_owned())) {
                e.push(format!("probeRecords[{i}].id must be unique"));
            }
            if strv(p.get("command")).is_none_or(|c| {
                c.trim().is_empty() || c.len() > 256 || c.contains('\n') || c.contains('\r')
            }) {
                e.push(format!("probeRecords[{i}].command is invalid"));
            }
            if !iso_timestamp(p.get("recordedAt")) {
                e.push(format!(
                    "probeRecords[{i}].recordedAt must be a timezone-aware ISO timestamp"
                ));
            }
            if p.get("exitCode")
                .is_some_and(|v| !v.is_null() && v.as_i64().is_none())
            {
                e.push(format!(
                    "probeRecords[{i}].exitCode must be integer or null"
                ));
            }
            if !["pass", "blocked", "not-executed", "local-unverified"]
                .contains(&strv(p.get("resultCategory")).unwrap_or(""))
            {
                e.push(format!(
                    "probeRecords[{i}].resultCategory has an invalid value"
                ));
            }
            if !safe_locator(p.get("evidenceLocator")) {
                e.push(format!(
                    "probeRecords[{i}].evidenceLocator must be a safe relative locator"
                ));
            }
        } else {
            e.push(format!("probeRecords[{i}] must be an object"));
        }
    }
    for (i, v) in arr(m.get("matrix")).into_iter().flatten().enumerate() {
        if let Some(x) = obj(v) {
            push_unknown(
                &mut e,
                x,
                &[
                    "surface",
                    "officialCommand",
                    "localCommand",
                    "localEvidence",
                    "status",
                    "probeRecordIds",
                ],
            );
            if strv(x.get("surface")).is_none_or(|surface| {
                surface.trim().is_empty()
                    || surface.len() > 128
                    || surface.contains('\n')
                    || surface.contains('\r')
            }) {
                e.push(format!("matrix[{i}].surface must be a bounded string"));
            }
            if ![
                "observed-install",
                "blocked-local",
                "officially-documented-local-unverified",
                "officially-documented-not-executed",
                "repo-source-and-test-verified",
            ]
            .contains(&strv(x.get("status")).unwrap_or(""))
            {
                e.push(format!("matrix[{i}].status has an invalid value"));
            }
            let command_count = ["officialCommand", "localCommand"]
                .iter()
                .filter(|f| strv(x.get(**f)).is_some())
                .count();
            if command_count != 1 {
                e.push(format!(
                    "matrix[{i}] requires exactly one officialCommand/localCommand"
                ));
            }
            if strv(x.get("localEvidence")).is_none_or(|v| {
                v.trim().is_empty() || v.len() > 256 || v.contains('\n') || v.contains('\r')
            }) {
                e.push(format!("matrix[{i}].localEvidence must be bounded"));
            }
            if strv(x.get("officialCommand")).is_some_and(|v| {
                v.trim().is_empty() || v.len() > 256 || v.contains('\n') || v.contains('\r')
            }) || strv(x.get("localCommand")).is_some_and(|v| {
                v.trim().is_empty() || v.len() > 256 || v.contains('\n') || v.contains('\r')
            }) {
                e.push(format!("matrix[{i}] command field must be bounded"));
            }
            if arr(x.get("probeRecordIds")).is_none_or(Vec::is_empty) {
                e.push(format!(
                    "matrix[{i}].probeRecordIds must be a non-empty string list"
                ));
            } else if arr(x.get("probeRecordIds")).unwrap().iter().any(|id| {
                strv(Some(id)).is_none_or(|id| {
                    id.trim().is_empty()
                        || id.len() > 128
                        || id.contains('\n')
                        || id.contains('\r')
                        || !probe_ids.contains(id)
                })
            }) {
                e.push(format!(
                    "matrix[{i}].probeRecordIds references an unknown probe"
                ));
            }
        } else {
            e.push(format!("matrix[{i}] must be an object"));
        }
    }
    if arr(m.get("matrix")).is_none_or(Vec::is_empty) {
        e.push("matrix must be a non-empty list".to_owned());
    }
    if let Some(decision) = obj(m.get("decision").unwrap_or(&Value::Null)) {
        push_unknown(
            &mut e,
            decision,
            &["retainCompatibilityLayer", "reason", "nextVerification"],
        );
        if boolv(decision.get("retainCompatibilityLayer")).is_none() {
            e.push("decision.retainCompatibilityLayer must be boolean".to_owned());
        }
        for field in ["reason", "nextVerification"] {
            if strv(decision.get(field)).is_none() {
                e.push(format!("decision missing {field}"));
            }
            if strv(decision.get(field)).is_none_or(|value| {
                value.trim().is_empty()
                    || value.len() > 1024
                    || value.contains('\n')
                    || value.contains('\r')
            }) {
                e.push(format!("decision.{field} is overlong"));
            }
        }
    }
    e
}
pub fn validate_matrix(matrix: &Value) -> Vec<String> {
    validate_compatibility_matrix(matrix)
}

/// Promotion is an explicit human operation, never an automatic side effect.
/// Unknown/incompatible external evidence is always denied.
pub fn promotion_decision(source: &Value) -> Value {
    let map = obj(source);
    let source_type = strv(map.and_then(|m| m.get("sourceType"))).unwrap_or("unknown");
    let authority = strv(map.and_then(|m| m.get("authority"))).unwrap_or("unknown");
    let external = authority == "external"
        || !["local", "repo", "workspace", "fixture"].contains(&source_type);
    let freshness = strv(map.and_then(|m| m.get("freshness"))).unwrap_or("unverifiable");
    let conflict = strv(map.and_then(|m| m.get("conflictStatus").or_else(|| m.get("conflict"))))
        .unwrap_or("unknown");
    let license = strv(map.and_then(|m| m.get("licenseStatus").or_else(|| m.get("license"))))
        .unwrap_or("unknown");
    let task_evidence = map
        .and_then(|m| {
            m.get("taskEvidence")
                .or_else(|| m.get("taskEvidenceVerified"))
        })
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let eligible = !external
        && freshness == "current"
        && conflict == "none"
        && ["known", "compatible", "not_applicable"].contains(&license)
        && task_evidence;
    let reason = if external {
        "external evidence is never auto-promoted"
    } else if freshness != "current" {
        "freshness must be current"
    } else if conflict != "none" {
        "conflict status must be none"
    } else if !["known", "compatible", "not_applicable"].contains(&license) {
        "license must be known, compatible, or not_applicable"
    } else if !task_evidence {
        "current local task evidence is required"
    } else {
        "eligible for explicit human review only"
    };
    json!({"allowed":false,"eligibleForManualReview":eligible,"promotionEligibility":"manual_review_only","decision":if eligible {"manual_review_required"} else {"deny"},"reason":reason})
}

/// 分類與篩選是可測的決策輸出；兩者都不會執行 promotion side effect。
pub fn classify_promotion_source(source: &Value) -> Value {
    let map = obj(source);
    let source_type = strv(map.and_then(|m| m.get("sourceType"))).unwrap_or("unknown");
    let authority = strv(map.and_then(|m| m.get("authority"))).unwrap_or("unknown");
    let class = if ["local", "repo", "workspace", "fixture"].contains(&source_type)
        && authority != "external"
    {
        "local_current_or_candidate"
    } else if authority == "external" || source_type == "unknown" {
        "external_or_unknown"
    } else {
        "noncanonical"
    };
    json!({"class":class,"promotionEligibility":"manual_review_only","autoAdopt":false})
}

pub fn filter_promotion_sources(sources: &Value) -> Value {
    let decisions = arr(Some(sources))
        .map(|items| {
            items
                .iter()
                .map(|source| {
                    let mut decision = promotion_decision(source);
                    if let Some(map) = decision.as_object_mut() {
                        map.insert(
                            "classification".to_owned(),
                            classify_promotion_source(source),
                        );
                    }
                    decision
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    json!({"promotionEligibility":"manual_review_only","autoAdopt":false,"decisions":decisions})
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn passport_task() -> Task {
        Task {
            id: "MC-1".to_owned(),
            title: "Review".to_owned(),
            kind: String::new(),
            parent: String::new(),
            priority: String::new(),
            status: TaskStatus::Review,
            assignee: String::new(),
            dependencies: Vec::new(),
            next_action: String::new(),
            verification: String::new(),
            estimate: String::new(),
            tags: Vec::new(),
            notes: String::new(),
        }
    }

    fn passport(task: &Task) -> Value {
        json!({
            "schemaVersion":"1.0",
            "artifactType":"completion-passport",
            "taskId":task.id,
            "taskDigest":canonical_task_digest(task),
            "status":"current",
            "verification":{"result":"pass","evidenceRefs":["output/evidence.md"]},
            "findings":[]
        })
    }

    #[test]
    fn completion_passport_contract_is_strict_and_task_bound() {
        let task = passport_task();
        assert!(validate_completion_passport(&passport(&task), &task, None).is_empty());

        let mut stale = passport(&task);
        stale["taskDigest"] = json!("0".repeat(64));
        assert!(
            validate_completion_passport(&stale, &task, None)
                .iter()
                .any(|error| error.contains("taskDigest"))
        );

        let mut unsafe_ref = passport(&task);
        unsafe_ref["verification"]["evidenceRefs"][0] = json!("../secret.txt");
        assert!(!validate_completion_passport(&unsafe_ref, &task, None).is_empty());

        let mut critical = passport(&task);
        critical["findings"] = json!([{"id":"F-1","severity":"Critical","disposition":"accepted"}]);
        assert!(
            validate_completion_passport(&critical, &task, None)
                .iter()
                .any(|error| error.contains("Critical"))
        );

        let mut unknown = passport(&task);
        unknown["secret"] = json!("token=do-not-accept");
        assert!(!validate_completion_passport(&unknown, &task, None).is_empty());
    }

    #[test]
    fn done_requires_review_path() {
        assert_eq!(
            transition_decision(TaskStatus::InProgress, TaskStatus::Done),
            PolicyDecision::Deny
        );
        assert_eq!(
            transition_decision(TaskStatus::Review, TaskStatus::Done),
            PolicyDecision::Allow
        );
    }

    #[test]
    fn unknown_facts_and_secret_scans_fail_closed() {
        assert_eq!(FactKind::parse("future"), FactKind::Unknown);
        assert!(
            scan_forbidden_content(&json!({"value":"token=abc123"}))
                .iter()
                .any(|e| e.contains("secret-like"))
        );
    }

    #[test]
    fn shift_loss_zero_denominators_are_null() {
        let case = json!({"shouldRecall":true,"shouldIgnore":false,"shouldSupersede":false,"actualRecall":true,"actualIgnore":false,"actualSupersede":false,"firstCorrectActionMs":null,"staleMemoryInjected":false,"wrongBranch":false,"tokensUsed":1,"verifiedProgress":false,"evidenceClaims":0,"evidenceBackedClaims":0,"falseDone":false,"recoveryDistance":null,"unverifiedDestructiveAction":false,"activeGuardrailWithoutSource":false,"multipleWritersSameBranch":false});
        let metrics = aggregate_shift_cases(&[case])
            .unwrap()
            .get("metrics")
            .cloned()
            .unwrap();
        assert!(metrics.get("TFCA").is_some_and(Value::is_null));
        assert!(metrics.get("TVP").is_some_and(Value::is_null));
    }

    #[test]
    fn wave3_strict_edges_are_fail_closed() {
        assert!(
            !scan_forbidden_content(&json!({"note": "eyJhbGciOiJIUzI1NiJ9.payload.signature"}))
                .is_empty()
        );
        assert!(validate_shift_loss(&json!({"schemaVersion":"1.0","artifactType":"shift-loss-eval","taskId":"T1","variant":"bad variant","cases":[]}), None).iter().any(|e| e.contains("variant")));
        assert!(
            validate_steelman_artifact(&json!({"schemaVersion":"1.1"}), None)
                .iter()
                .any(|e| e.contains("schemaVersion"))
        );
        assert_eq!(promotion_decision(&json!({"sourceType":"fixture","freshness":"current","conflictStatus":"none","licenseStatus":"compatible","taskEvidence":true})).get("allowed"), Some(&json!(false)));
    }

    #[test]
    fn optimizer_noise_precedes_high_risk() {
        let route = route_optimization_profile(
            &json!({"taskType":"research","parameterShape":"continuous","measurement":"repeatable","noise":"high","risk":"high","budget":{"trials":10}}),
        );
        assert_eq!(
            route.get("strategy").and_then(Value::as_str),
            Some("robust_doe_taguchi")
        );
    }
}
