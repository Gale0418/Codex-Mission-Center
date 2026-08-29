use mission_center_publish::{
    RegistrationStatus, native_register_marketplace, native_rollback_registration,
};
use std::{
    fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

fn temp_root() -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let root = std::env::temp_dir().join(format!("mission-center-registration-{nonce}"));
    fs::create_dir_all(&root).unwrap();
    root
}

fn plugin_tree(root: &std::path::Path, display_name: &str) -> PathBuf {
    let plugin = root.join("plugins").join("mission-center");
    let manifest_dir = plugin.join(".codex-plugin");
    fs::create_dir_all(&manifest_dir).unwrap();
    let json = format!(
        r#"{{"name":"mission-center","version":"0.5.1","interface":{{"displayName":"{display_name}"}}}}"#
    );
    fs::write(manifest_dir.join("plugin.json"), json).unwrap();
    plugin
}

#[test]
fn registration_is_atomic_replayable_and_rollbackable() {
    let root = temp_root();
    let plugin = plugin_tree(&root, "Mission Center");
    let first = native_register_marketplace(&plugin, &root, "registration-1", "0.5.1").unwrap();
    assert_eq!(first.status, RegistrationStatus::Committed);
    let target = root.join(".agents/plugins/marketplace.json");
    let manifest: serde_json::Value = serde_json::from_slice(&fs::read(&target).unwrap()).unwrap();
    assert_eq!(manifest["name"], "mission-center-local");
    assert_eq!(
        manifest["plugins"][0]["source"]["path"],
        "./plugins/mission-center"
    );

    let replay = native_register_marketplace(&plugin, &root, "registration-1", "0.5.1").unwrap();
    assert_eq!(replay, first);

    let receipt_path = PathBuf::from(&first.transaction_root).join("registration-1.json");
    let rolled_back = native_rollback_registration(&receipt_path).unwrap();
    assert_eq!(rolled_back.status, RegistrationStatus::RolledBack);
    assert!(!target.exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn registration_rejects_same_operation_with_different_manifest() {
    let root = temp_root();
    let plugin = plugin_tree(&root, "Mission Center");
    native_register_marketplace(&plugin, &root, "registration-2", "0.5.1").unwrap();
    fs::write(
        plugin.join(".codex-plugin/plugin.json"),
        br#"{"name":"mission-center","version":"0.5.1","interface":{"displayName":"Changed"}}"#,
    )
    .unwrap();
    let error = native_register_marketplace(&plugin, &root, "registration-2", "0.5.1").unwrap_err();
    assert_eq!(
        error.code,
        mission_center_publish::ErrorCode::TransactionConflict
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn registration_binds_operation_to_requested_version() {
    let root = temp_root();
    let plugin = plugin_tree(&root, "Mission Center");
    native_register_marketplace(&plugin, &root, "registration-version", "0.5.1").unwrap();
    fs::write(
        plugin.join(".codex-plugin/plugin.json"),
        br#"{"name":"mission-center","version":"0.5.2","interface":{"displayName":"Mission Center"}}"#,
    )
    .unwrap();
    let error =
        native_register_marketplace(&plugin, &root, "registration-version", "0.5.2").unwrap_err();
    assert_eq!(
        error.code,
        mission_center_publish::ErrorCode::TransactionConflict
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn registration_reconcile_aborts_started_receipt_without_guessing() {
    let root = temp_root();
    let plugin = plugin_tree(&root, "Mission Center");
    let receipt = native_register_marketplace(&plugin, &root, "registration-3", "0.5.1").unwrap();
    let receipt_path = PathBuf::from(&receipt.transaction_root).join("registration-3.json");
    let mut started: serde_json::Value =
        serde_json::from_slice(&fs::read(&receipt_path).unwrap()).unwrap();
    started["status"] = serde_json::Value::String("started".to_owned());
    fs::write(&receipt_path, serde_json::to_vec(&started).unwrap()).unwrap();
    let reconciled = mission_center_publish::native_reconcile_registrations(&root).unwrap();
    assert_eq!(reconciled[0].status, RegistrationStatus::Aborted);
    assert!(!root.join(".agents/plugins/marketplace.json").exists());
    let _ = fs::remove_dir_all(root);
}
