use mission_center_core::sha256_digest;
use mission_center_publish::*;
use serde_json::json;
use std::{
    fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

fn temp_root(label: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let root = std::env::temp_dir().join(format!(
        "mission-center-{label}-{}-{nonce}",
        std::process::id()
    ));
    fs::create_dir_all(&root).unwrap();
    root
}
fn pe_x64(machine: u16) -> Vec<u8> {
    // Synthetic minimum PE header fixture; this is not a runnable binary.
    let mut bytes = vec![0u8; 128];
    bytes[0..2].copy_from_slice(b"MZ");
    bytes[60..64].copy_from_slice(&(64u32).to_le_bytes());
    bytes[64..68].copy_from_slice(b"PE\0\0");
    bytes[68..70].copy_from_slice(&machine.to_le_bytes());
    bytes
}
fn elf_x64() -> Vec<u8> {
    // Synthetic minimum ELF64 little-endian header fixture.
    let mut bytes = vec![0u8; 128];
    bytes[0..4].copy_from_slice(b"\x7fELF");
    bytes[4] = 2;
    bytes[5] = 1;
    bytes[18..20].copy_from_slice(&62u16.to_le_bytes());
    bytes
}
fn macho(cpu: u32) -> Vec<u8> {
    // Synthetic minimum Mach-O 64-bit header fixture.
    let mut bytes = vec![0u8; 128];
    bytes[0..4].copy_from_slice(b"\xcf\xfa\xed\xfe");
    bytes[4..8].copy_from_slice(&cpu.to_le_bytes());
    bytes
}
fn fixture(label: &str) -> (PathBuf, PlatformArtifact) {
    let root = temp_root(label);
    fs::create_dir_all(root.join(".codex-plugin")).unwrap();
    let binary = pe_x64(0x8664);
    let artifact_path = "bin/mission-center.exe";
    fs::create_dir_all(root.join("bin")).unwrap();
    fs::write(root.join(artifact_path), &binary).unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut mode = fs::metadata(root.join(artifact_path))
            .unwrap()
            .permissions();
        mode.set_mode(0o755);
        fs::set_permissions(root.join(artifact_path), mode).unwrap();
    }
    let others = [
        (
            Platform::LinuxX86_64,
            "bin/mission-center-linux",
            elf_x64(),
            "linux",
            "x86_64",
        ),
        (
            Platform::MacosX86_64,
            "bin/mission-center-macos",
            macho(0x01000007),
            "macos",
            "x86_64",
        ),
        (
            Platform::MacosAarch64,
            "bin/mission-center-macos-arm",
            macho(0x0100000c),
            "macos",
            "aarch64",
        ),
    ];
    let mut artifacts = Vec::new();
    for (platform, path, bytes, os, arch) in others {
        fs::write(root.join(path), &bytes).unwrap();
        artifacts.push(PlatformArtifact {
            platform,
            path: path.into(),
            sha256: sha256_digest(&bytes),
            version: "0.5.1".into(),
            os: os.into(),
            arch: arch.into(),
            executable: path.into(),
        });
    }
    let artifact = PlatformArtifact {
        platform: Platform::WindowsX86_64,
        path: artifact_path.into(),
        sha256: sha256_digest(&binary),
        version: "0.5.1".into(),
        os: "windows".into(),
        arch: "x86_64".into(),
        executable: artifact_path.into(),
    };
    let manifest = PlatformManifest {
        schema_version: SCHEMA_VERSION.into(),
        plugin_name: "mission-center".into(),
        version: "0.5.1".into(),
        artifacts: {
            let mut all = vec![artifact.clone()];
            all.extend(artifacts);
            all
        },
    };
    fs::write(
        root.join(PLATFORM_MANIFEST_FILE),
        manifest.to_json().unwrap(),
    )
    .unwrap();
    fs::write(
        root.join(PLUGIN_MANIFEST_FILE),
        br#"{"name":"mission-center","version":"0.5.1"}"#,
    )
    .unwrap();
    (root, artifact)
}
fn frozen_fixture() -> (FrozenPackage, PlatformArtifact) {
    let windows = pe_x64(0x8664);
    let linux = elf_x64();
    let mac_x86 = macho(0x01000007);
    let mac_arm = macho(0x0100000c);
    let specs = [
        (
            Platform::WindowsX86_64,
            "bin/mission-center.exe",
            windows.clone(),
            "windows",
            "x86_64",
        ),
        (
            Platform::LinuxX86_64,
            "bin/mission-center-linux",
            linux,
            "linux",
            "x86_64",
        ),
        (
            Platform::MacosX86_64,
            "bin/mission-center-macos",
            mac_x86,
            "macos",
            "x86_64",
        ),
        (
            Platform::MacosAarch64,
            "bin/mission-center-macos-arm",
            mac_arm,
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
    let manifest = PlatformManifest::new("mission-center", "0.5.1", artifacts.clone());
    let mut files = vec![
        FrozenFile::new(PLATFORM_MANIFEST_FILE, manifest.to_json().unwrap(), false),
        FrozenFile::new(
            PLUGIN_MANIFEST_FILE,
            br#"{"name":"mission-center","version":"0.5.1"}"#.to_vec(),
            false,
        ),
    ];
    for (_, path, bytes, _, _) in specs {
        files.push(FrozenFile::new(path, bytes, true));
    }
    (FrozenPackage::new(files).unwrap(), artifacts[0].clone())
}

#[test]
fn offline_staging_adapter_returns_verified_receipt_and_fails_closed_on_rollback() {
    let (package, _) = frozen_fixture();
    let publish = stage_publish(&package, "wave5-publish", Platform::WindowsX86_64, "0.5.1")
        .expect("verified publish stage");
    assert_eq!(publish.action, StagingAction::Publish);
    assert_eq!(publish.status, StagingStatus::Prepared);
    assert!(!publish.written);
    assert!(!publish.rollback_supported);
    assert_eq!(publish.version, "0.5.1");
    assert_eq!(publish.package_digest.len(), 64);

    let install = stage_install(&package, "wave5-install", Platform::LinuxX86_64, "0.5.1")
        .expect("verified install stage");
    assert_eq!(install.action, StagingAction::Install);
    assert_eq!(
        rollback_staged(&install).unwrap_err().code(),
        ErrorCode::Unsupported
    );

    assert_eq!(
        stage_publish(&package, "bad/id", Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::UnsafePath
    );
    assert_eq!(
        stage_install(&package, "bad-version", Platform::WindowsX86_64, "9.9")
            .unwrap_err()
            .code(),
        ErrorCode::VersionMismatch
    );
}

fn request(root: &PathBuf, id: &str) -> PublishRequest {
    let staging = root.parent().unwrap().join(format!(
        "stage-{}",
        root.file_name().unwrap().to_string_lossy()
    ));
    if !staging.exists() {
        let _ = fs::remove_file(
            root.parent()
                .unwrap()
                .join(format!(".mission-center-transactions/{id}.json")),
        );
    }
    PublishRequest::new(root, staging, id, Platform::WindowsX86_64, "0.5.1")
}
fn cleanup(root: &PathBuf) {
    let _ = fs::remove_dir_all(root);
}
fn filesystem_snapshot(root: &PathBuf) -> Vec<(String, bool, Vec<u8>)> {
    fn walk(root: &PathBuf, current: &PathBuf, out: &mut Vec<(String, bool, Vec<u8>)>) {
        for entry in fs::read_dir(current).unwrap() {
            let path = entry.unwrap().path();
            let name = path
                .strip_prefix(root)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            if path.is_dir() {
                out.push((name, true, Vec::new()));
                walk(root, &path, out);
            } else {
                out.push((name, false, fs::read(&path).unwrap()));
            }
        }
    }
    let mut out = Vec::new();
    if root.exists() {
        walk(root, root, &mut out);
    }
    out.sort_by(|a, b| a.0.cmp(&b.0));
    out
}

#[test]
fn manifest_is_typed_and_round_trips() {
    let (root, _) = fixture("manifest");
    let manifest =
        PlatformManifest::from_json(&fs::read(root.join(PLATFORM_MANIFEST_FILE)).unwrap()).unwrap();
    let decoded = PlatformManifest::from_json(&manifest.to_json().unwrap()).unwrap();
    assert_eq!(decoded, manifest);
    assert!(
        String::from_utf8(manifest.to_json().unwrap())
            .unwrap()
            .contains("windows-x86_64")
    );
    cleanup(&root);
}

#[test]
fn manifest_is_strict_four_platform_and_semver_two() {
    let (root, _) = fixture("strict-manifest");
    let mut value: serde_json::Value =
        serde_json::from_slice(&fs::read(root.join(PLATFORM_MANIFEST_FILE)).unwrap()).unwrap();
    value["unknown"] = json!(true);
    assert_eq!(
        PlatformManifest::from_json(&serde_json::to_vec(&value).unwrap())
            .unwrap_err()
            .code(),
        ErrorCode::InvalidManifest
    );
    let mut missing = value;
    missing.as_object_mut().unwrap().remove("unknown");
    missing["artifacts"].as_array_mut().unwrap().pop();
    assert_eq!(
        PlatformManifest::from_json(&serde_json::to_vec(&missing).unwrap())
            .unwrap_err()
            .code(),
        ErrorCode::MissingBinary
    );
    let mut duplicate = serde_json::from_slice::<serde_json::Value>(
        &fs::read(root.join(PLATFORM_MANIFEST_FILE)).unwrap(),
    )
    .unwrap();
    duplicate["artifacts"][3]["platform"] = json!("windows-x86_64");
    duplicate["artifacts"][3]["os"] = json!("windows");
    duplicate["artifacts"][3]["arch"] = json!("x86_64");
    assert_eq!(
        PlatformManifest::from_json(&serde_json::to_vec(&duplicate).unwrap())
            .unwrap_err()
            .code(),
        ErrorCode::InvalidManifest
    );
    let mut bad_version = serde_json::from_slice::<serde_json::Value>(
        &fs::read(root.join(PLATFORM_MANIFEST_FILE)).unwrap(),
    )
    .unwrap();
    bad_version["version"] = json!("1.02.3");
    assert_eq!(
        PlatformManifest::from_json(&serde_json::to_vec(&bad_version).unwrap())
            .unwrap_err()
            .code(),
        ErrorCode::InvalidManifest
    );
    cleanup(&root);
}

#[test]
fn frozen_package_verifies_all_synthetic_platform_headers() {
    let (package, _) = frozen_fixture();
    for platform in Platform::ALL {
        let report = package.verify(platform, "0.5.1").unwrap();
        assert_eq!(report.manifest.version, "0.5.1");
        assert_eq!(report.artifact.platform, platform);
        assert_eq!(report.digest.len(), 64);
    }
}

#[test]
fn frozen_package_rejects_corrupt_missing_wrong_arch_and_nonexec() {
    let (package, artifact) = frozen_fixture();
    let mut corrupt_other = package.files().to_vec();
    corrupt_other
        .iter_mut()
        .find(|file| file.relative_path == "bin/mission-center-linux")
        .unwrap()
        .bytes = vec![0xde, 0xad, 0xbe, 0xef];
    let corrupt_other = FrozenPackage::new(corrupt_other).unwrap();
    assert_eq!(
        corrupt_other
            .verify(Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::CorruptChecksum
    );
    let missing_other = FrozenPackage::new(
        package
            .files()
            .iter()
            .filter(|file| file.relative_path != "bin/mission-center-linux")
            .cloned()
            .collect(),
    )
    .unwrap();
    assert_eq!(
        missing_other
            .verify(Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::MissingBinary
    );
    let mut empty = package.files().to_vec();
    empty
        .iter_mut()
        .find(|file| file.relative_path == artifact.path)
        .unwrap()
        .bytes
        .clear();
    let empty = FrozenPackage::new(empty).unwrap();
    assert_eq!(
        empty
            .verify(Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::MissingBinary
    );
    let mut wrong_arch = package.files().to_vec();
    let file = wrong_arch
        .iter_mut()
        .find(|file| file.relative_path == artifact.path)
        .unwrap();
    file.bytes = pe_x64(0x014c);
    let wrong_arch_bytes = file.bytes.clone();
    let manifest = wrong_arch
        .iter()
        .find(|file| file.relative_path == PLATFORM_MANIFEST_FILE)
        .unwrap();
    let mut manifest_value: serde_json::Value = serde_json::from_slice(&manifest.bytes).unwrap();
    manifest_value["artifacts"][0]["sha256"] = json!(sha256_digest(&wrong_arch_bytes));
    let manifest = wrong_arch
        .iter_mut()
        .find(|file| file.relative_path == PLATFORM_MANIFEST_FILE)
        .unwrap();
    manifest.bytes = serde_json::to_vec(&manifest_value).unwrap();
    let wrong_arch = FrozenPackage::new(wrong_arch).unwrap();
    assert_eq!(
        wrong_arch
            .verify(Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::WrongPlatform
    );

    let missing = FrozenPackage::new(
        package
            .files()
            .iter()
            .filter(|file| file.relative_path != artifact.path)
            .cloned()
            .collect(),
    )
    .unwrap();
    assert_eq!(
        missing
            .verify(Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::MissingBinary
    );

    let mut nonexec = package.files().to_vec();
    nonexec
        .iter_mut()
        .find(|file| file.relative_path == artifact.path)
        .unwrap()
        .executable = false;
    let nonexec = FrozenPackage::new(nonexec).unwrap();
    assert_eq!(
        nonexec
            .verify(Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::NonExecutable
    );
}

#[test]
fn frozen_package_enforces_paths_bounds_and_python_roles() {
    assert_eq!(
        FrozenPackage::new(vec![FrozenFile::new("", b"x".to_vec(), false)])
            .unwrap_err()
            .code(),
        ErrorCode::UnsafePath
    );
    assert_eq!(
        FrozenPackage::new(vec![FrozenFile::new(
            "x".repeat(4097),
            b"x".to_vec(),
            false
        )])
        .unwrap_err()
        .code(),
        ErrorCode::UnsafePath
    );
    assert_eq!(
        FrozenPackage::new(vec![FrozenFile::new("../escape", b"x".to_vec(), false)])
            .unwrap_err()
            .code(),
        ErrorCode::UnsafePath
    );
    assert_eq!(
        FrozenPackage::new(vec![
            FrozenFile::new("same", b"a".to_vec(), false),
            FrozenFile::new("same", b"b".to_vec(), false),
        ])
        .unwrap_err()
        .code(),
        ErrorCode::UnsafePath
    );
    let deep = (0..MAX_DEPTH_TEST)
        .map(|i| format!("d{i}"))
        .collect::<Vec<_>>()
        .join("/");
    assert_eq!(
        FrozenPackage::new(vec![FrozenFile::new(deep, b"x".to_vec(), false)])
            .unwrap_err()
            .code(),
        ErrorCode::UnsafePath
    );

    let (package, _) = frozen_fixture();
    let base_digest = package
        .verify(Platform::WindowsX86_64, "0.5.1")
        .unwrap()
        .digest;
    let mut marker_files = package.files().to_vec();
    marker_files.push(FrozenFile::new("data/marker", b"same".to_vec(), false));
    let marker_off = FrozenPackage::new(marker_files).unwrap();
    let marker_off_digest = marker_off
        .verify(Platform::WindowsX86_64, "0.5.1")
        .unwrap()
        .digest;
    let mut marker_files = package.files().to_vec();
    marker_files.push(FrozenFile::new("data/marker", b"same".to_vec(), true));
    let marker_on = FrozenPackage::new(marker_files).unwrap();
    let marker_on_digest = marker_on
        .verify(Platform::WindowsX86_64, "0.5.1")
        .unwrap()
        .digest;
    assert_ne!(base_digest, marker_off_digest);
    assert_ne!(marker_off_digest, marker_on_digest);
    let mut files = package.files().to_vec();
    files.push(FrozenFile::new(
        "docs/example.py",
        b"Python is mentioned as prose only.\n".to_vec(),
        false,
    ));
    files.push(FrozenFile::new(
        "README.txt",
        b"python is mentioned as prose only.\n".to_vec(),
        false,
    ));
    let package = FrozenPackage::new(files).unwrap();
    assert!(package.verify(Platform::WindowsX86_64, "0.5.1").is_ok());
    for (index, command) in [
        "command -- python3.12 -m fallback\n",
        "sudo -u root python3 -m fallback\n",
        "nice -n 10 python -m fallback\n",
        "env -- FOO=bar python3 -m fallback\n",
        "exec python -m fallback\n",
        "if command python3; then echo bad; fi\n",
        "echo $(python3 -m fallback)\n",
        "@python3 -m fallback\n",
        "exec \"python3\" -m fallback\n",
        "sh -c python3 -m fallback\n",
        "cmd /c python3 -m fallback\n",
        "powershell -Command $env:PYTHON\n",
    ]
    .into_iter()
    .enumerate()
    {
        let mut wrapper_files = package.files().to_vec();
        wrapper_files.push(FrozenFile::new(
            format!("scripts/wrapper-{index}.sh"),
            command.as_bytes().to_vec(),
            false,
        ));
        let wrapper_package = FrozenPackage::new(wrapper_files).unwrap();
        assert_eq!(
            wrapper_package
                .verify(Platform::WindowsX86_64, "0.5.1")
                .unwrap_err()
                .code(),
            ErrorCode::PythonRuntime
        );
    }
    let mut extensionless = package.files().to_vec();
    extensionless.push(FrozenFile::new(
        "hooks/run",
        b"python3 -m fallback\n".to_vec(),
        false,
    ));
    assert_eq!(
        FrozenPackage::new(extensionless)
            .unwrap()
            .verify(Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::PythonRuntime
    );
    let mut binary = package.files().to_vec();
    binary.push(FrozenFile::new("bin/run", vec![0, 1, 2, 3], true));
    assert!(
        FrozenPackage::new(binary)
            .unwrap()
            .verify(Platform::WindowsX86_64, "0.5.1")
            .is_ok()
    );
    let mut python_files = package.files().to_vec();
    python_files.push(FrozenFile::new(
        "scripts/run.sh",
        b"echo ok; sudo -- python3.12 -m fallback\n".to_vec(),
        false,
    ));
    let package = FrozenPackage::new(python_files).unwrap();
    assert_eq!(
        package
            .verify(Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::PythonRuntime
    );
}

const MAX_DEPTH_TEST: usize = 33;

#[test]
#[cfg(any())]
fn preflight_failures_are_zero_write() {
    let (root, _) = fixture("zero-write");
    let req = request(&root, "zero");
    let target = root.parent().unwrap().join("sentinel");
    fs::write(&target, b"keep").unwrap();
    let wrong_arch = pe_x64(0x014c);
    fs::write(root.join("bin/mission-center.exe"), &wrong_arch).unwrap();
    let manifest = fs::read(root.join(PLATFORM_MANIFEST_FILE)).unwrap();
    let mut value: serde_json::Value = serde_json::from_slice(&manifest).unwrap();
    value["artifacts"][0]["sha256"] = json!(sha256_digest(&wrong_arch));
    fs::write(
        root.join(PLATFORM_MANIFEST_FILE),
        serde_json::to_vec(&value).unwrap(),
    )
    .unwrap();
    let error = preflight_publish(&req).unwrap_err();
    assert_eq!(error.code(), ErrorCode::WrongPlatform);
    assert_eq!(fs::read(&target).unwrap(), b"keep");
    assert!(!req.staging.exists());
    cleanup(&root);
    let _ = fs::remove_file(target);
}

#[test]
#[cfg(any())]
fn missing_and_corrupt_binary_are_rejected() {
    let (root, artifact) = fixture("missing");
    let req = request(&root, "missing");
    fs::remove_file(root.join(&artifact.path)).unwrap();
    assert_eq!(
        preflight_publish(&req).unwrap_err().code(),
        ErrorCode::MissingBinary
    );
    cleanup(&root);
    let (root, _) = fixture("checksum");
    let req = request(&root, "checksum");
    fs::write(root.join("bin/mission-center.exe"), pe_x64(0x8664)).unwrap();
    fs::write(root.join("extra"), b"tampered").unwrap();
    let manifest = fs::read(root.join(PLATFORM_MANIFEST_FILE)).unwrap();
    let mut value: serde_json::Value = serde_json::from_slice(&manifest).unwrap();
    value["artifacts"][0]["sha256"] = json!("0".repeat(64));
    fs::write(
        root.join(PLATFORM_MANIFEST_FILE),
        serde_json::to_vec(&value).unwrap(),
    )
    .unwrap();
    assert_eq!(
        preflight_publish(&req).unwrap_err().code(),
        ErrorCode::CorruptChecksum
    );
    cleanup(&root);
}

#[cfg(unix)]
#[test]
#[cfg(any())]
fn non_executable_binary_is_rejected() {
    use std::os::unix::fs::PermissionsExt;
    let (root, artifact) = fixture("nonexec");
    let req = request(&root, "nonexec");
    let path = root.join(artifact.path);
    let mut mode = fs::metadata(&path).unwrap().permissions();
    mode.set_mode(0o644);
    fs::set_permissions(path, mode).unwrap();
    assert_eq!(
        preflight_publish(&req).unwrap_err().code(),
        ErrorCode::NonExecutable
    );
    cleanup(&root);
}

#[test]
#[cfg(not(windows))]
#[cfg(any())]
fn publish_replay_conflict_and_rollback_are_recoverable() {
    let (root, _) = fixture("transaction");
    let req = request(&root, "op-1");
    let first = publish_package(&req).unwrap();
    assert_eq!(first.status, TransactionStatus::Committed);
    let replay = publish_package(&req).unwrap();
    assert_eq!(replay, first);
    fs::write(root.join("new-file"), b"different digest").unwrap();
    let error = publish_package(&req).unwrap_err();
    assert_eq!(error.code(), ErrorCode::TransactionConflict);
    let restored = rollback_transaction(
        &root
            .parent()
            .unwrap()
            .join(".mission-center-transactions/op-1.json"),
    )
    .unwrap();
    assert_eq!(restored.status, TransactionStatus::Aborted);
    assert!(!req.staging.exists());
    cleanup(&root);
}

#[test]
#[cfg(not(windows))]
#[cfg(any())]
fn corrupt_receipt_and_reconcile_are_safe() {
    let (root, _) = fixture("receipt");
    let req = request(&root, "op-2");
    let tx = root
        .parent()
        .unwrap()
        .join(".mission-center-transactions/op-2.json");
    fs::create_dir_all(tx.parent().unwrap()).unwrap();
    fs::write(&tx, br#"{"schemaVersion":"1.0","unknown":true}"#).unwrap();
    assert_eq!(
        publish_package(&req).unwrap_err().code(),
        ErrorCode::TransactionCorrupt
    );
    fs::write(
        &tx,
        serde_json::to_vec(&TransactionReceipt {
            schema_version: SCHEMA_VERSION.into(),
            operation_id: "op-2".into(),
            digest: sha256_digest(b"x"),
            status: TransactionStatus::Started,
            staging: root
                .parent()
                .unwrap()
                .join("stage")
                .to_string_lossy()
                .into(),
            destinations: vec![],
            backups: vec![],
            transaction_root: root.parent().unwrap().to_string_lossy().into(),
            destination_count: 0,
            targets: vec![],
        })
        .unwrap(),
    )
    .unwrap();
    let local_tx = root.join(".mission-center-transactions");
    fs::create_dir_all(&local_tx).unwrap();
    fs::write(
        local_tx.join("local.json"),
        serde_json::to_vec(&TransactionReceipt {
            schema_version: SCHEMA_VERSION.into(),
            operation_id: "local".into(),
            digest: sha256_digest(b"x"),
            status: TransactionStatus::Started,
            staging: root.join("stage").to_string_lossy().into(),
            destinations: vec![],
            backups: vec![],
            transaction_root: root.to_string_lossy().into(),
            destination_count: 0,
            targets: vec![],
        })
        .unwrap(),
    )
    .unwrap();
    assert_eq!(reconcile_transactions(&root).unwrap().len(), 1);
    cleanup(&root);
}

#[test]
#[cfg(not(windows))]
#[cfg(any())]
fn install_verify_and_rollback_restore_previous_targets() {
    let (root, _) = fixture("install");
    let canonical = root.parent().unwrap().join("canonical-install");
    fs::create_dir_all(&canonical).unwrap();
    fs::write(canonical.join("old.txt"), b"previous").unwrap();
    let request = InstallRequest::new(
        &root,
        vec![canonical.clone()],
        "install-1",
        Platform::WindowsX86_64,
        "0.5.1",
    );
    let mut multi_destination = request.clone();
    multi_destination
        .destinations
        .push(root.parent().unwrap().join("derived-install"));
    assert_eq!(
        preflight_install(&multi_destination).unwrap_err().code(),
        ErrorCode::UnsafePath
    );
    let _ = fs::remove_file(
        root.parent()
            .unwrap()
            .join(".mission-center-transactions/install-1.json"),
    );
    let receipt = install_package(&request).unwrap();
    assert!(canonical.join(PLATFORM_MANIFEST_FILE).is_file());
    verify_package(&canonical, Platform::WindowsX86_64, "0.5.1").unwrap();
    let receipt_path = root
        .parent()
        .unwrap()
        .join(".mission-center-transactions/install-1.json");
    rollback_transaction(&receipt_path).unwrap();
    assert_eq!(fs::read(canonical.join("old.txt")).unwrap(), b"previous");
    assert_eq!(receipt.status, TransactionStatus::Committed);
    let _ = fs::remove_dir_all(canonical);
    cleanup(&root);
}

#[test]
#[cfg(not(windows))]
#[cfg(any())]
fn python_runtime_and_operation_id_are_rejected_before_writes() {
    let (root, _) = fixture("python-gate");
    fs::write(root.join("python3-runner"), b"python3 -m fallback").unwrap();
    let bad_request = request(&root, "bad/id");
    assert_eq!(
        publish_package(&bad_request).unwrap_err().code(),
        ErrorCode::Unsupported
    );
    let valid = request(&root, "safe-id");
    assert_eq!(
        preflight_publish(&valid).unwrap_err().code(),
        ErrorCode::PythonRuntime
    );
    for (index, command) in [
        b"/usr/bin/python3.12 -m fallback\n".as_slice(),
        b"env python -m fallback\n".as_slice(),
        b"py -3 fallback.py\n".as_slice(),
    ]
    .into_iter()
    .enumerate()
    {
        fs::write(root.join(format!("runner-{index}.sh")), command).unwrap();
        assert_eq!(
            preflight_publish(&valid).unwrap_err().code(),
            ErrorCode::PythonRuntime
        );
    }
    fs::create_dir_all(root.join("bin")).unwrap();
    fs::write(root.join("bin/python3.12"), b"not a runtime").unwrap();
    assert_eq!(
        preflight_publish(&valid).unwrap_err().code(),
        ErrorCode::PythonRuntime
    );
    cleanup(&root);
}

#[test]
fn mutation_apis_are_read_only_and_explicitly_unsupported() {
    let root = temp_root("mutation-read-only");
    let source = root.join("source");
    let staging = root.join("staging");
    let destination = root.join("destination");
    let receipt = root.join("receipt.json");
    let publish_request = PublishRequest::new(
        &source,
        &staging,
        "publish-op",
        Platform::WindowsX86_64,
        "0.5.1",
    );
    let install_request = InstallRequest::new(
        &source,
        vec![destination.clone()],
        "install-op",
        Platform::WindowsX86_64,
        "0.5.1",
    );
    let before = filesystem_snapshot(&root);
    let filesystem_errors = [
        preflight_publish(&publish_request).unwrap_err(),
        preflight_install(&install_request).unwrap_err(),
        verify_package(
            PathBuf::from("Z:\\denied\\package").as_path(),
            Platform::WindowsX86_64,
            "0.5.1",
        )
        .unwrap_err(),
        verify(
            PathBuf::from("Z:\\missing\\package").as_path(),
            Platform::WindowsX86_64,
            "0.5.1",
        )
        .unwrap_err(),
    ];
    assert!(
        filesystem_errors
            .iter()
            .all(|error| error.code() == ErrorCode::Unsupported)
    );
    assert!(
        filesystem_errors
            .windows(2)
            .all(|errors| errors[0] == errors[1])
    );
    for result in [
        publish_package(&publish_request).map(|_| ()),
        install_package(&install_request).map(|_| ()),
        install(&install_request).map(|_| ()),
        rollback(&receipt).map(|_| ()),
        rollback_transaction(&receipt).map(|_| ()),
        reconcile(&root).map(|_| ()),
        reconcile_transactions(&root).map(|_| ()),
    ] {
        let error = result.unwrap_err();
        assert_eq!(error.code(), ErrorCode::Unsupported);
        assert_eq!(error.remediation, MUTATION_REMEDIATION);
    }
    assert_eq!(filesystem_snapshot(&root), before);
    assert!(!staging.exists());
    assert!(!destination.exists());
    assert!(!root.join(".mission-center-transactions").exists());
    cleanup(&root);
}

#[test]
#[cfg(any())]
fn python_role_allowlist_avoids_docs_false_positive_but_rejects_tab_bypass() {
    let (root, _) = fixture("python-allowlist");
    fs::create_dir_all(root.join("docs/python")).unwrap();
    fs::write(
        root.join("docs/python/example.py"),
        b"Python is documented here.\n",
    )
    .unwrap();
    let valid = request(&root, "docs-safe");
    assert!(preflight_publish(&valid).is_ok());
    fs::write(root.join("runner.sh"), b"echo ready\npython\t-m fallback\n").unwrap();
    assert_eq!(
        preflight_publish(&valid).unwrap_err().code(),
        ErrorCode::PythonRuntime
    );
    cleanup(&root);
}

#[cfg(windows)]
#[test]
fn windows_writes_are_explicitly_unsupported_and_zero_write() {
    let (root, _) = fixture("windows-unsupported");
    let request = request(&root, "windows-safe");
    assert_eq!(
        publish_package(&request).unwrap_err().code(),
        ErrorCode::Unsupported
    );
    assert!(!request.staging.exists());
    assert!(
        !root
            .parent()
            .unwrap()
            .join(".mission-center-transactions/windows-safe.json")
            .exists()
    );
    cleanup(&root);
}
