use mission_center_core::sha256_digest;
use mission_center_policy::{scan_forbidden_content, validate_context_manifest};
use mission_center_workspace::MissionWorkspace;
use serde_json::{Value, json};

pub const CONTEXT_MAX_OUTPUT_BYTES: usize = 16 * 1024;
const CONTEXT_SOURCE_MAX_BYTES: u64 = 64 * 1024;

fn card_scope_matches(card: &Value, requested: &serde_json::Map<String, Value>) -> bool {
    card.get("scope")
        .and_then(Value::as_object)
        .is_some_and(|scope| {
            scope.iter().all(|(key, value)| {
                value.as_str().is_some_and(|expected| {
                    requested.get(key).and_then(Value::as_str) == Some(expected)
                })
            })
        })
}

fn anchor_excerpt(text: &str, anchor: &str) -> Option<String> {
    let lines = text.lines().collect::<Vec<_>>();
    let start = lines.iter().position(|line| line.trim() == anchor.trim())?;
    let heading_level = lines[start]
        .trim_start()
        .bytes()
        .take_while(|byte| *byte == b'#')
        .count();
    let mut end = (start + 16).min(lines.len());
    if (1..=6).contains(&heading_level)
        && lines[start].trim_start().as_bytes().get(heading_level) == Some(&b' ')
    {
        for (index, line) in lines.iter().enumerate().skip(start + 1) {
            let candidate = line
                .trim_start()
                .bytes()
                .take_while(|byte| *byte == b'#')
                .count();
            if (1..=heading_level).contains(&candidate)
                && line.trim_start().as_bytes().get(candidate) == Some(&b' ')
            {
                end = index;
                break;
            }
        }
    }
    Some(lines[start..end].join("\n").trim().to_owned())
}

fn status_rank(status: &str) -> u8 {
    match status {
        "pass" => 0,
        "unknown" => 1,
        "stale" => 2,
        "corrupt" => 3,
        _ => 3,
    }
}

fn bounded_result(mut result: Value, max_bytes: usize) -> Result<Value, String> {
    loop {
        for _ in 0..4 {
            let encoded = serde_json::to_vec(&result).map_err(|error| error.to_string())?;
            let Some(object) = result.as_object_mut() else {
                break;
            };
            if object.get("bytes").and_then(Value::as_u64) == Some(encoded.len() as u64) {
                break;
            }
            object.insert("bytes".to_owned(), Value::from(encoded.len() as u64));
        }
        let encoded = serde_json::to_vec(&result).map_err(|error| error.to_string())?;
        if encoded.len() <= max_bytes {
            return Ok(result);
        }
        let cards = result
            .get_mut("cards")
            .and_then(Value::as_array_mut)
            .ok_or_else(|| "context result has no bounded card list".to_owned())?;
        if cards.pop().is_none() {
            return Err("context result metadata exceeds 16 KiB".to_owned());
        }
        if let Some(object) = result.as_object_mut() {
            object.insert("truncated".to_owned(), Value::Bool(true));
        }
    }
}

pub fn recall(
    ws: &MissionWorkspace,
    manifest: &Value,
    context: &str,
    scope: &Value,
    max_bytes: usize,
) -> Result<Value, String> {
    if !matches!(
        context,
        "resume" | "enter-review" | "before-deploy" | "before-migration" | "after-repeated-failure"
    ) {
        return Err("unsupported context".to_owned());
    }
    if max_bytes == 0 || max_bytes > CONTEXT_MAX_OUTPUT_BYTES {
        return Err("max-bytes must be between 1 and 16384".to_owned());
    }
    let requested = scope
        .as_object()
        .ok_or_else(|| "scope must be a JSON object".to_owned())?;
    // Structural errors are corrupt. Source freshness is classified below so a
    // digest drift remains stale rather than being collapsed into corruption.
    let errors = validate_context_manifest(manifest, None);
    if !errors.is_empty() {
        return bounded_result(
            json!({"status":"corrupt","context":context,"cards":[],"errors":errors,"readOnly":true,"maxBytes":max_bytes,"bytes":0}),
            max_bytes,
        );
    }
    let mut cards = Vec::new();
    let mut overall = "pass";
    for card in manifest
        .get("cards")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter(|card| card.get("context").and_then(Value::as_str) == Some(context))
        .filter(|card| card_scope_matches(card, requested))
    {
        let validity = card
            .get("validity")
            .and_then(Value::as_str)
            .unwrap_or("incompatible");
        let mut item = json!({
            "id":card.get("id"),
            "validity":validity,
            "reason":card.get("reason").cloned().unwrap_or(Value::Null),
            "requiredVerification":card.get("requiredVerification").cloned().unwrap_or_else(|| json!([])),
        });
        if validity != "active" {
            let state = if validity == "superseded" {
                "stale"
            } else {
                validity
            };
            item["status"] = Value::String(state.to_owned());
            if status_rank("stale") > status_rank(overall) {
                overall = "stale";
            }
            cards.push(item);
            continue;
        }
        let source = card
            .get("source")
            .and_then(Value::as_object)
            .expect("validated source");
        let locator = source
            .get("locator")
            .and_then(Value::as_str)
            .expect("validated locator");
        let anchor = source
            .get("anchor")
            .and_then(Value::as_str)
            .expect("validated anchor");
        let expected = source
            .get("digest")
            .and_then(Value::as_str)
            .expect("validated digest");
        match ws.read_artifact(locator, CONTEXT_SOURCE_MAX_BYTES) {
            Ok(bytes) if sha256_digest(&bytes) != expected => {
                item["status"] = json!("stale");
                item["error"] = json!("source digest mismatch");
                if status_rank("stale") > status_rank(overall) {
                    overall = "stale";
                }
            }
            Ok(bytes) => match String::from_utf8(bytes) {
                Err(_) => {
                    item["status"] = json!("corrupt");
                    item["error"] = json!("source is not UTF-8");
                    overall = "corrupt";
                }
                Ok(text) => match anchor_excerpt(&text, anchor) {
                    None => {
                        item["status"] = json!("stale");
                        item["error"] = json!("source anchor is absent");
                        if status_rank("stale") > status_rank(overall) {
                            overall = "stale";
                        }
                    }
                    Some(excerpt) if !scan_forbidden_content(&json!(excerpt)).is_empty() => {
                        item["status"] = json!("corrupt");
                        item["error"] = json!("source excerpt contains forbidden privacy content");
                        overall = "corrupt";
                    }
                    Some(excerpt) => {
                        item["status"] = json!("covered");
                        item["source"] =
                            json!({"locator":locator,"anchor":anchor,"digest":expected});
                        item["excerpt"] = json!(excerpt);
                    }
                },
            },
            Err(error) => {
                item["status"] = json!("corrupt");
                item["error"] = json!(error.to_string());
                overall = "corrupt";
            }
        }
        cards.push(item);
    }
    if cards.is_empty() {
        overall = "unknown";
    }
    bounded_result(
        json!({"status":overall,"context":context,"cards":cards,"errors":[],"readOnly":true,"maxBytes":max_bytes,"bytes":0}),
        max_bytes,
    )
}

pub fn preflight(
    ws: &MissionWorkspace,
    manifest: &Value,
    context: &str,
    scope: &Value,
) -> Result<Value, String> {
    let recalled = recall(ws, manifest, context, scope, CONTEXT_MAX_OUTPUT_BYTES)?;
    let status = recalled
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or("corrupt");
    let covered = recalled
        .get("cards")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter(|card| card.get("status").and_then(Value::as_str) == Some("covered"))
        .collect::<Vec<_>>();
    let mut required = covered
        .iter()
        .flat_map(|card| {
            card.get("requiredVerification")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
        })
        .filter_map(Value::as_str)
        .map(ToOwned::to_owned)
        .collect::<Vec<_>>();
    required.sort();
    required.dedup();
    let (coverage, decision) = if matches!(status, "corrupt" | "stale") {
        ("unknown", "blocked")
    } else if covered.is_empty() {
        ("not-covered", "unknown")
    } else {
        ("covered", "advisory-only")
    };
    Ok(json!({
        "status":status,
        "context":context,
        "coverage":coverage,
        "decision":decision,
        "requiredVerification":required,
        "cards":recalled.get("cards").cloned().unwrap_or_else(|| json!([])),
        "readOnly":true,
    }))
}

#[cfg(test)]
mod tests {
    use super::{CONTEXT_MAX_OUTPUT_BYTES, anchor_excerpt, bounded_result};
    use serde_json::{Value, json};

    #[test]
    fn heading_excerpt_stops_at_same_level() {
        let source = "# A\n## Target\nkeep\n### Child\nkeep child\n## Next\nexclude";
        assert_eq!(
            anchor_excerpt(source, "## Target").as_deref(),
            Some("## Target\nkeep\n### Child\nkeep child")
        );
    }

    #[test]
    fn bounded_result_bytes_converge_across_number_width_boundaries() {
        for payload_len in 0..512 {
            let result = bounded_result(
                json!({"payload":"x".repeat(payload_len),"cards":[],"bytes":0}),
                CONTEXT_MAX_OUTPUT_BYTES,
            )
            .expect("bounded result");
            let encoded = serde_json::to_vec(&result).expect("encoded result");
            assert_eq!(
                result.get("bytes").and_then(Value::as_u64),
                Some(encoded.len() as u64)
            );
        }
    }
}
