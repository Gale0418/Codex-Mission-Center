use mission_center_core::sha256_digest;
use mission_center_workspace::{
    ExternalOperationStatus, MissionWorkspace, OperationOutcome, WorkspaceError,
};
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

fn fixture() -> (MissionWorkspace, PathBuf) {
    let suffix = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let root = PathBuf::from(format!(
        "./.mission-center-external-{suffix}-{}",
        COUNTER.fetch_add(1, Ordering::Relaxed)
    ));
    let workspace = MissionWorkspace::new(&root);
    workspace
        .init("fixture-init", "2026-09-13T00:00:00Z", "en", false)
        .unwrap();
    fs::write(
        workspace.tasks_path(),
        "# Tasks\n\n| ID | Title | Type | Parent | Priority | Status | Owner | Depends on | Next action | Verification | Estimate | Labels | Comments |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| MC-001 | External | task |  | P1 | Ready | worker |  | Check provider | local | S |  |  |\n",
    )
    .unwrap();
    (workspace, root)
}

fn digests() -> (String, String) {
    (sha256_digest(b"scope"), sha256_digest(b"receipt"))
}

#[test]
fn prepare_replay_and_task_binding_are_durable() {
    let (workspace, root) = fixture();
    let (scope, receipt) = digests();
    let before = fs::read(workspace.tasks_path()).unwrap();
    let first = workspace
        .prepare_external_operation(
            "provider-1",
            "MC-001",
            &scope,
            &receipt,
            "2026-09-13T00:01:00Z",
        )
        .unwrap();
    assert_eq!(first.outcome, OperationOutcome::Committed);
    assert_eq!(first.record.status, ExternalOperationStatus::Pending);
    let replay = workspace
        .prepare_external_operation(
            "provider-1",
            "MC-001",
            &scope,
            &receipt,
            "2026-09-13T00:02:00Z",
        )
        .unwrap();
    assert_eq!(replay.outcome, OperationOutcome::Replay);
    assert_eq!(replay.record.digest, first.record.digest);
    assert_eq!(fs::read(workspace.tasks_path()).unwrap(), before);
    let restarted = MissionWorkspace::new(&root);
    let after_restart = restarted.read_external_operation("provider-1").unwrap();
    assert_eq!(after_restart, first.record);
    let changed_pending = restarted.update_external_operation(
        "provider-1",
        "MC-001",
        &scope,
        &receipt,
        "pending",
        None,
        None,
        "2026-09-13T00:03:00Z",
    );
    assert!(matches!(changed_pending, Err(WorkspaceError::Conflict(_))));
    let conflict = workspace.prepare_external_operation(
        "provider-1",
        "MC-001",
        &sha256_digest(b"other"),
        &receipt,
        "2026-09-13T00:03:00Z",
    );
    assert!(matches!(conflict, Err(WorkspaceError::Conflict(_))));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn transitions_require_evidence_after_unknown_and_terminal_is_final() {
    let (workspace, root) = fixture();
    let (scope, receipt) = digests();
    workspace
        .prepare_external_operation(
            "provider-2",
            "MC-001",
            &scope,
            &receipt,
            "2026-09-13T00:01:00Z",
        )
        .unwrap();
    workspace
        .reconcile_external_operation(
            "provider-2",
            "MC-001",
            &scope,
            &receipt,
            ExternalOperationStatus::Unknown,
            None,
            None,
            "2026-09-13T00:02:00Z",
        )
        .unwrap();
    let no_evidence = workspace.reconcile_external_operation(
        "provider-2",
        "MC-001",
        &scope,
        &receipt,
        ExternalOperationStatus::Confirmed,
        None,
        None,
        "2026-09-13T00:03:00Z",
    );
    assert!(matches!(no_evidence, Err(WorkspaceError::ClaimRejected(_))));
    fs::write(
        workspace.mission_dir().join("current.json"),
        b"current provider result",
    )
    .unwrap();
    let evidence_digest = sha256_digest(b"current provider result");
    let confirmed = workspace
        .update_external_operation(
            "provider-2",
            "MC-001",
            &scope,
            &receipt,
            "confirmed",
            Some("current.json"),
            Some(&evidence_digest),
            "2026-09-13T00:04:00Z",
        )
        .unwrap();
    assert_eq!(confirmed.record.status, ExternalOperationStatus::Confirmed);
    let terminal_conflict = workspace.update_external_operation(
        "provider-2",
        "MC-001",
        &scope,
        &receipt,
        "failed",
        Some("current.json"),
        Some(&evidence_digest),
        "2026-09-13T00:05:00Z",
    );
    assert!(matches!(
        terminal_conflict,
        Err(WorkspaceError::Conflict(_))
    ));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn evidence_paths_digest_and_secret_inputs_fail_closed() {
    let (workspace, root) = fixture();
    let (scope, receipt) = digests();
    workspace
        .prepare_external_operation(
            "provider-3",
            "MC-001",
            &scope,
            &receipt,
            "2026-09-13T00:01:00Z",
        )
        .unwrap();
    for locator in [
        "/tmp/current",
        "C:/current",
        r"current\result",
        "current:stream",
        "../current",
    ] {
        let result = workspace.update_external_operation(
            "provider-3",
            "MC-001",
            &scope,
            &receipt,
            "confirmed",
            Some(locator),
            Some(&scope),
            "2026-09-13T00:02:00Z",
        );
        assert!(matches!(result, Err(WorkspaceError::InvalidLocator(_))));
    }
    let secret = workspace.prepare_external_operation(
        "provider-token=x",
        "MC-001",
        &scope,
        &receipt,
        "2026-09-13T00:03:00Z",
    );
    assert!(secret.is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn query_is_read_only_and_corrupt_or_oversized_records_are_rejected() {
    let (workspace, root) = fixture();
    let (scope, receipt) = digests();
    workspace
        .prepare_external_operation(
            "provider-4",
            "MC-001",
            &scope,
            &receipt,
            "2026-09-13T00:01:00Z",
        )
        .unwrap();
    let before = fs::read(workspace.tasks_path()).unwrap();
    let records = workspace.query_external_operations().unwrap();
    assert_eq!(records.len(), 1);
    assert_eq!(fs::read(workspace.tasks_path()).unwrap(), before);
    let path = workspace.external_operation_path("provider-4").unwrap();
    fs::write(
        &path,
        b"{\"schemaVersion\":\"1.0\",\"schemaVersion\":\"1.0\"}",
    )
    .unwrap();
    assert!(matches!(
        workspace.read_external_operation("provider-4"),
        Err(WorkspaceError::InvalidReceipt(_))
    ));
    fs::write(&path, vec![b'x'; 16 * 1024 + 1]).unwrap();
    assert!(matches!(
        workspace.query_external_operations(),
        Err(WorkspaceError::TooLarge { .. })
    ));
    fs::remove_dir_all(root).unwrap();
}

#[cfg(unix)]
#[test]
fn evidence_symlink_is_rejected() {
    let (workspace, root) = fixture();
    let (scope, receipt) = digests();
    workspace
        .prepare_external_operation(
            "provider-5",
            "MC-001",
            &scope,
            &receipt,
            "2026-09-13T00:01:00Z",
        )
        .unwrap();
    fs::write(root.join("outside.txt"), b"outside").unwrap();
    std::os::unix::fs::symlink(
        root.join("outside.txt"),
        workspace.mission_dir().join("link.txt"),
    )
    .unwrap();
    let result = workspace.update_external_operation(
        "provider-5",
        "MC-001",
        &scope,
        &receipt,
        "confirmed",
        Some("link.txt"),
        Some(&sha256_digest(b"outside")),
        "2026-09-13T00:02:00Z",
    );
    assert!(matches!(result, Err(WorkspaceError::UnsafePath { .. })));
    fs::remove_dir_all(root).unwrap();
}
