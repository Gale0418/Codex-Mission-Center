use mission_center_core::sha256_digest;
use mission_center_publish::*;
use std::{
    fs,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

fn temp_root(label: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let temp = std::env::temp_dir();
    #[cfg(target_os = "macos")]
    let temp = temp.canonicalize().expect("canonical temporary directory");
    let root = temp.join(format!("mission-center-native-{label}-{nonce}"));
    fs::create_dir_all(&root).unwrap();
    root
}

fn pe_x64() -> Vec<u8> {
    let mut bytes = vec![0u8; 128];
    bytes[0..2].copy_from_slice(b"MZ");
    bytes[60..64].copy_from_slice(&(64u32).to_le_bytes());
    bytes[64..68].copy_from_slice(b"PE\0\0");
    bytes[68..70].copy_from_slice(&0x8664u16.to_le_bytes());
    bytes
}

fn elf_x64() -> Vec<u8> {
    let mut bytes = vec![0u8; 128];
    bytes[0..4].copy_from_slice(b"\x7fELF");
    bytes[4] = 2;
    bytes[5] = 1;
    bytes[18..20].copy_from_slice(&62u16.to_le_bytes());
    bytes
}

fn macho(cpu: u32) -> Vec<u8> {
    let mut bytes = vec![0u8; 128];
    bytes[0..4].copy_from_slice(b"\xcf\xfa\xed\xfe");
    bytes[4..8].copy_from_slice(&cpu.to_le_bytes());
    bytes
}

fn write_executable(path: &Path, bytes: &[u8]) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, bytes).unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut mode = fs::metadata(path).unwrap().permissions();
        mode.set_mode(0o755);
        fs::set_permissions(path, mode).unwrap();
    }
}

fn package(root: &Path) {
    let specs = [
        (
            Platform::WindowsX86_64,
            "bin/windows-x86_64/mission-center.exe",
            pe_x64(),
            "windows",
            "x86_64",
        ),
        (
            Platform::LinuxX86_64,
            "bin/linux-x86_64/mission-center",
            elf_x64(),
            "linux",
            "x86_64",
        ),
        (
            Platform::MacosX86_64,
            "bin/macos-x86_64/mission-center",
            macho(0x01000007),
            "macos",
            "x86_64",
        ),
        (
            Platform::MacosAarch64,
            "bin/macos-aarch64/mission-center",
            macho(0x0100000c),
            "macos",
            "aarch64",
        ),
    ];
    let artifacts = specs
        .iter()
        .map(|(platform, path, bytes, os, arch)| PlatformArtifact {
            platform: *platform,
            path: (*path).into(),
            sha256: sha256_digest(bytes),
            version: "0.5.1".into(),
            os: (*os).into(),
            arch: (*arch).into(),
            executable: (*path).into(),
        })
        .collect::<Vec<_>>();
    for (_, path, bytes, _, _) in specs {
        write_executable(&root.join(path), &bytes);
    }
    fs::create_dir_all(root.join(".codex-plugin")).unwrap();
    fs::write(
        root.join(PLATFORM_MANIFEST_FILE),
        PlatformManifest::new("mission-center", "0.5.1", artifacts)
            .to_json()
            .unwrap(),
    )
    .unwrap();
    fs::write(
        root.join(PLUGIN_MANIFEST_FILE),
        br#"{"name":"mission-center","version":"0.5.1"}"#,
    )
    .unwrap();
}

#[test]
fn native_install_replays_and_rolls_back_a_verified_package() {
    let root = temp_root("install");
    let package_root = root.join("package");
    package(&package_root);
    let destination = root.join("installed");
    fs::create_dir_all(&destination).unwrap();
    fs::write(destination.join("old.txt"), b"old").unwrap();
    let platform = Platform::host().expect("test host must be supported");
    let first = native_install_package(
        &package_root,
        std::slice::from_ref(&destination),
        "native-install-1",
        platform,
        "0.5.1",
    )
    .unwrap();
    assert_eq!(first.status, TransactionStatus::Committed);
    assert!(destination.join(PLATFORM_MANIFEST_FILE).is_file());
    assert!(!destination.join("old.txt").exists());
    let replay = native_install_package(
        &package_root,
        std::slice::from_ref(&destination),
        "native-install-1",
        platform,
        "0.5.1",
    )
    .unwrap();
    assert_eq!(replay, first);
    let restored = native_rollback_transaction(
        &root
            .join(".mission-center-transactions")
            .join("native-install-1.json"),
    )
    .unwrap();
    assert_eq!(restored.status, TransactionStatus::Aborted);
    assert!(destination.join("old.txt").is_file());
    assert!(!destination.join(PLATFORM_MANIFEST_FILE).exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn native_publish_uses_the_same_verified_transaction_path() {
    let root = temp_root("publish");
    let package_root = root.join("package");
    package(&package_root);
    let destination = root.join("published");
    let platform = Platform::host().expect("test host must be supported");
    let receipt = native_publish_package(
        &package_root,
        std::slice::from_ref(&destination),
        "native-publish-1",
        platform,
        "0.5.1",
    )
    .unwrap();
    assert_eq!(receipt.status, TransactionStatus::Committed);
    assert!(destination.join(PLUGIN_MANIFEST_FILE).is_file());
    let restored = native_rollback_transaction(
        &root
            .join(".mission-center-transactions")
            .join("native-publish-1.json"),
    )
    .unwrap();
    assert_eq!(restored.status, TransactionStatus::Aborted);
    assert!(!destination.exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn native_install_rejects_traversal_before_writing() {
    let root = temp_root("reject");
    let package_root = root.join("package");
    package(&package_root);
    let outside = root.join("outside");
    let destination = root.join("parent").join("..").join("outside");
    let platform = Platform::host().expect("test host must be supported");
    let error = native_install_package(
        &package_root,
        &[destination],
        "native-install-2",
        platform,
        "0.5.1",
    )
    .unwrap_err();
    assert_eq!(error.code(), ErrorCode::UnsafePath);
    assert!(!outside.exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn native_rollback_refuses_a_tampered_destination() {
    let root = temp_root("tamper");
    let package_root = root.join("package");
    package(&package_root);
    let destination = root.join("installed");
    fs::create_dir_all(&destination).unwrap();
    let platform = Platform::host().expect("test host must be supported");
    native_install_package(
        &package_root,
        std::slice::from_ref(&destination),
        "native-install-3",
        platform,
        "0.5.1",
    )
    .unwrap();
    fs::write(destination.join("tampered.txt"), b"external change").unwrap();
    let receipt = root
        .join(".mission-center-transactions")
        .join("native-install-3.json");
    let error = native_rollback_transaction(&receipt).unwrap_err();
    assert_eq!(error.code(), ErrorCode::TransactionConflict);
    assert!(destination.join("tampered.txt").is_file());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn native_install_validates_all_destinations_before_creating_parents() {
    let root = temp_root("preflight");
    let package_root = root.join("package");
    package(&package_root);
    let first_parent = root.join("new-parent");
    let first = first_parent.join("installed");
    let invalid = root.join("bad").join("..").join("escape");
    let platform = Platform::host().expect("test host must be supported");
    let error = native_install_package(
        &package_root,
        &[first, invalid],
        "native-install-4",
        platform,
        "0.5.1",
    )
    .unwrap_err();
    assert_eq!(error.code(), ErrorCode::UnsafePath);
    assert!(!first_parent.exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn native_reconcile_rolls_back_started_receipt_after_crash() {
    let root = temp_root("reconcile");
    let package_root = root.join("package");
    package(&package_root);
    let destination = root.join("installed");
    fs::create_dir_all(&destination).unwrap();
    fs::write(destination.join("old.txt"), b"old").unwrap();
    let platform = Platform::host().expect("test host must be supported");
    native_install_package(
        &package_root,
        std::slice::from_ref(&destination),
        "native-reconcile-1",
        platform,
        "0.5.1",
    )
    .unwrap();
    let receipt_path = root
        .join(".mission-center-transactions")
        .join("native-reconcile-1.json");
    let mut json: serde_json::Value =
        serde_json::from_slice(&fs::read(&receipt_path).unwrap()).unwrap();
    json["status"] = serde_json::Value::String("started".into());
    fs::write(&receipt_path, serde_json::to_vec(&json).unwrap()).unwrap();

    let receipts = native_reconcile_transactions(&root).unwrap();
    assert_eq!(receipts.len(), 1);
    assert_eq!(receipts[0].status, TransactionStatus::Aborted);
    assert!(destination.join("old.txt").is_file());
    assert!(!destination.join(PLATFORM_MANIFEST_FILE).exists());
    let _ = fs::remove_dir_all(root);
}

#[test]
fn native_reconcile_rejects_malformed_receipt_without_writing() {
    let root = temp_root("reconcile-corrupt");
    let transactions = root.join(".mission-center-transactions");
    fs::create_dir_all(&transactions).unwrap();
    fs::write(
        transactions.join("broken.json"),
        br#"{"schemaVersion":"1.0"}"#,
    )
    .unwrap();
    let error = native_reconcile_transactions(&root).unwrap_err();
    assert_eq!(error.code(), ErrorCode::TransactionCorrupt);
    assert_eq!(
        fs::read(transactions.join("broken.json")).unwrap(),
        br#"{"schemaVersion":"1.0"}"#
    );
    let _ = fs::remove_dir_all(root);
}

#[test]
fn native_reconcile_rejects_unexpected_transaction_artifact() {
    let root = temp_root("reconcile-artifact");
    let transactions = root.join(".mission-center-transactions");
    fs::create_dir_all(&transactions).unwrap();
    fs::write(transactions.join("receipt.json.tmp"), b"partial").unwrap();
    let error = native_reconcile_transactions(&root).unwrap_err();
    assert_eq!(error.code(), ErrorCode::TransactionCorrupt);
    assert!(transactions.join("receipt.json.tmp").is_file());
    let _ = fs::remove_dir_all(root);
}
