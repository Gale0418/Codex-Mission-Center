use mission_center_policy::*;
use serde_json::json;

#[test]
fn research_rejects_unknown_and_overlarge_hypotheses() {
    let mut record = json!({"schemaVersion":"1.0","artifactType":"research-portfolio","taskId":"T1","initialHypothesisAllocation":{"exploit":60,"adjacent_explore":30,"moonshot":10},"allocationKind":"initial_hypothesis_allocation","hypotheses":[],"sourceLedger":[],"saturationSignals":{},"selectedAction":"continue","extra":true});
    assert!(!validate_research_portfolio(&record, None).is_empty());
    record["hypotheses"] = json!((0..13).map(|_| json!({})).collect::<Vec<_>>());
    assert!(
        validate_research_portfolio(&record, None)
            .iter()
            .any(|error| error.contains("at most 12"))
    );
}

#[test]
fn research_requires_low_marginal_gain_count() {
    let errors = route_saturation(
        &json!({
            "repeatedRootCause": false,
            "renamedHypothesis": false,
            "metricStalled": false,
            "budgetBurning": false,
            "sharedUnverifiedPremise": false
        }),
        false,
        false,
    )
    .expect_err("missing required signal must fail closed");
    assert!(errors.contains("lowMarginalGainCount"));

    let errors = route_saturation(
        &json!({
            "repeatedRootCause": false,
            "renamedHypothesis": false,
            "metricStalled": false,
            "budgetBurning": false,
            "sharedUnverifiedPremise": false,
            "lowMarginalGainCount": -1
        }),
        false,
        false,
    )
    .expect_err("negative marginal gain count must fail closed");
    assert!(errors.contains("non-negative integer"));
}

#[test]
fn compatibility_rejects_invalid_calendar_and_absolute_locator() {
    let mut matrix: serde_json::Value = serde_json::from_str(include_str!(
        "../../../skills/mission-center/references/codex-cli-plugin-compatibility-matrix.json"
    ))
    .unwrap();
    matrix["observedAt"] = json!("2024-02-30");
    matrix["probeRecords"][0]["evidenceLocator"] = json!("C:/outside");
    let errors = validate_compatibility_matrix(&matrix);
    assert!(errors.iter().any(|error| error.contains("observedAt")));
    assert!(
        errors
            .iter()
            .any(|error| error.contains("safe relative locator"))
    );
    matrix["observedAt"] = json!("2024-01-01");
    matrix["probeRecords"][0]["evidenceLocator"] = json!(".");
    assert!(
        validate_compatibility_matrix(&matrix)
            .iter()
            .any(|error| error.contains("safe relative locator"))
    );
    matrix["probeRecords"][0]["evidenceLocator"] = json!("evidence.log");
    matrix["probeRecords"][0]["recordedAt"] = json!("2024-02-30T00:00:00+00:00");
    assert!(
        validate_compatibility_matrix(&matrix)
            .iter()
            .any(|error| error.contains("recordedAt"))
    );
    for timestamp in [
        "2024-01-01T99:99:99+00:00",
        "2024-01-01T00:00:00+99:00",
        "2024-01-01T00:00:00.1234567890+00:00",
    ] {
        matrix["probeRecords"][0]["recordedAt"] = json!(timestamp);
        assert!(
            validate_compatibility_matrix(&matrix)
                .iter()
                .any(|error| error.contains("recordedAt")),
            "{timestamp}"
        );
    }
}

#[test]
fn security_compatibility_shift_optimizer_steelman_promotion_fail_closed() {
    assert!(
        !scan_forbidden_content(&json!({"value":"Authorization: Bearer abcdefghijkl"})).is_empty()
    );
    assert!(!validate_compatibility_matrix(&json!({"schemaVersion":"1.0","spike":"MC-044","observedAt":"bad","officialSources":[],"localProbe":{},"probeRecords":[],"matrix":[],"decision":{},"unknown":true})).is_empty());
    assert!(!validate_shift_loss(&json!({"schemaVersion":"1.0","artifactType":"shift-loss-eval","taskId":"T1","variant":"bad variant","cases":[]}), None).is_empty());
    assert!(!validate_optimization_manifest(&json!({"schemaVersion":"1.0","experimentId":"e","kind":"evaluator","candidates":[],"cases":[],"metrics":[],"hardConstraints":[],"budget":{"trials":1,"tokens":1,"wallClockSeconds":1,"maxConcurrency":0},"stoppingConditions":[],"validation":{},"promotionState":"shadow"})).is_empty());
    assert!(!validate_steelman_artifact(&json!({"schemaVersion":"1.1"}), None).is_empty());
    let decision = promotion_decision(
        &json!({"sourceType":"external","freshness":"current","conflictStatus":"none","licenseStatus":"compatible","taskEvidence":true}),
    );
    assert_eq!(decision["allowed"], false);
    assert_eq!(decision["promotionEligibility"], "manual_review_only");
}

#[test]
fn critic_finding_disposition_and_acceptance_gates() {
    let mut record = json!({
        "schemaVersion":"1.0", "route":"critic_lite", "taskId":"T1",
        "chairRecordLocator":"output/mission-center-critique/T1.json",
        "artifactManifest":[{"locator":"artifact.zip","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","laneId":"main"}],
        "snapshots":[{"id":"s1","revision":"r1","hash":"h1","evidenceLinks":["evidence.log"]}],
        "authorization":{"explicitApproval":true}, "budgets":{"total":10,"perSeat":3,"tool":2,"wallClock":60},
        "critics":[{"id":"a"},{"id":"b"}], "outcome":"limited",
        "lanes":[{"id":"main","kind":"article/nonfiction","required":true,"seatId":"a","evidenceLocator":"review.md","coverageStatus":"covered"}],
        "findings":[]
    });
    let finding = json!({"id":"CACC-MC-005-quality-1234abcd-1","severity":"Critical","category":"quality","observation":"defect","evidenceLocator":"artifact.md:3","reproOrReadPath":"Read line 3","impact":"breaks acceptance","confidence":"high","unknown":"none","recommendation":"repair","criticProposedDisposition":"fixed","chairFinalDisposition":"fixed"});
    record["findings"] = json!([finding.clone()]);
    assert!(validate_critic_record(&record).is_empty());
    record["findings"][0]["chairFinalDisposition"] = json!("accepted");
    assert!(
        validate_critic_record(&record)
            .iter()
            .any(|error| error.contains("Critical cannot"))
    );
    record["findings"][0]["chairFinalDisposition"] = json!("fixed");
    record["findings"][0]["criticProposedDisposition"] = json!("future");
    assert!(
        validate_critic_record(&record)
            .iter()
            .any(|error| error.contains("criticProposedDisposition"))
    );

    record["findings"][0]["severity"] = json!("High");
    record["findings"][0]["criticProposedDisposition"] = json!("deferred");
    record["findings"][0]["chairFinalDisposition"] = json!("deferred");
    record["findings"][0]["humanAcceptance"] = json!({
        "approverIdentity":"reviewer",
        "approvalTime":"2026-08-29T10:00:00+08:00",
        "scope":"finding",
        "reason":"bounded exception",
        "expiry":"2026-09-01T10:00:00+08:00",
        "reopenTrigger":"new evidence"
    });
    assert!(validate_critic_record(&record).is_empty());
    record["findings"][0]["humanAcceptance"]["approvalTime"] = json!("not-a-time");
    assert!(
        validate_critic_record(&record)
            .iter()
            .any(|error| error.contains("humanAcceptance"))
    );
}
