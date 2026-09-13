use mission_center_policy::{validate_context_manifest, validate_research_portfolio};
use serde_json::{Value, json};

fn context_card(id: &str, anchor: &str) -> Value {
    json!({
        "id": id,
        "context": "resume",
        "scope": {"taskId": "T1", "component": "policy"},
        "source": {
            "locator": "MissionCenter/decisions.md",
            "anchor": anchor,
            "digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        },
        "validity": "active",
        "requiredVerification": ["recheck current task scope"]
    })
}

#[test]
fn context_manifest_accepts_index_and_rejects_duplicate_or_unsafe_sources() {
    let manifest = json!({
        "schemaVersion": "1.0",
        "artifactType": "context-manifest",
        "cards": [context_card("CTX-resume-1", "L10")]
    });
    assert!(validate_context_manifest(&manifest, None).is_empty());

    let mut duplicate = manifest.clone();
    duplicate["cards"] = json!([
        context_card("CTX-resume-1", "L10"),
        context_card("CTX-resume-2", "L10")
    ]);
    assert!(
        validate_context_manifest(&duplicate, None)
            .iter()
            .any(|error| error.contains("duplicates source locator and anchor"))
    );

    let mut unsafe_locator = manifest;
    unsafe_locator["cards"][0]["source"]["locator"] = json!("../secrets:ads");
    assert!(
        validate_context_manifest(&unsafe_locator, None)
            .iter()
            .any(|error| error.contains("safe relative locator"))
    );

    let mut outside_mission_center = context_card("CTX-resume-3", "L11");
    outside_mission_center["source"]["locator"] = json!("guardrails.md");
    let outside_manifest = json!({
        "schemaVersion": "1.0",
        "artifactType": "context-manifest",
        "cards": [outside_mission_center]
    });
    assert!(
        validate_context_manifest(&outside_manifest, None)
            .iter()
            .any(|error| error.contains("safe relative locator"))
    );
}

#[test]
fn context_manifest_rejects_active_conflict_and_supersedes_cycle() {
    let first = context_card("CTX-first", "L1");
    let mut second = context_card("CTX-second", "L2");
    second["supersedes"] = json!("CTX-first");
    let manifest = json!({
        "schemaVersion": "1.0", "artifactType": "context-manifest", "cards": [first, second]
    });
    let errors = validate_context_manifest(&manifest, None);
    assert!(
        errors
            .iter()
            .any(|error| error.contains("active card in the same scope"))
    );

    let mut cycle = manifest;
    cycle["cards"][0]["supersedes"] = json!("CTX-second");
    assert!(
        validate_context_manifest(&cycle, None)
            .iter()
            .any(|error| error.contains("graph contains a cycle"))
    );
}

fn portfolio() -> Value {
    let hypothesis = |id: &str, kind: &str| {
        json!({
            "id": id, "kind": kind, "question": "q", "mechanism": "m",
            "currentEvidenceRefs": [],
            "smallestDiscriminatingTest": "test", "expectedObservation": "obs",
            "falsificationConditions": ["counter"], "dependencies": [], "risks": [],
            "budget": {"token": 0, "tool": 0, "time": 0},
            "successNextAction": "record", "failureKnowledge": "retain", "revalidateWhen": "new evidence",
            "status": "research_needed"
        })
    };
    json!({
        "schemaVersion":"1.0", "artifactType":"research-portfolio", "taskId":"T1",
        "initialHypothesisAllocation":{"exploit":60,"adjacent_explore":30,"moonshot":10},
        "allocationKind":"initial_hypothesis_allocation",
        "hypotheses":[hypothesis("h1","exploit"),hypothesis("h2","adjacent_explore"),hypothesis("h3","moonshot")],
        "sourceLedger":[],
        "saturationSignals":{"repeatedRootCause":false,"renamedHypothesis":false,"metricStalled":false,"budgetBurning":false,"sharedUnverifiedPremise":false,"lowMarginalGainCount":0},
        "selectedAction":"continue"
    })
}

#[test]
fn research_findings_are_optional_but_fail_closed_when_present() {
    let mut record = portfolio();
    assert!(validate_research_portfolio(&record, None).is_empty());
    record["findings"] = json!([{
        "id":"F-1", "kind":"verified-fact", "sourceRefs":["missing-source"],
        "provenance":"local fixture", "evidenceDigest":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "counterexamples":[], "nextDistinguishingTest":"recheck task", "status":"current"
    }]);
    assert!(
        validate_research_portfolio(&record, None)
            .iter()
            .any(|error| error.contains("trusted local evidence"))
    );
    record["findings"][0]["kind"] = json!("hypothesis");
    assert!(
        validate_research_portfolio(&record, None)
            .iter()
            .any(|error| error.contains("unknown source locator"))
    );
    record["findings"][0]["status"] = json!("bad");
    assert!(
        validate_research_portfolio(&record, None)
            .iter()
            .any(|error| error.contains("findings[0].status is invalid"))
    );
}
