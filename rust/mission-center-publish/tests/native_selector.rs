use mission_center_core::sha256_digest;
use mission_center_publish::{
    ErrorCode, FrozenFile, FrozenPackage, MutationAction, MutationStatus, PLATFORM_MANIFEST_FILE,
    PLUGIN_MANIFEST_FILE, Platform, PlatformArtifact, PlatformManifest,
    unsupported_mutation_receipt,
};

fn pe() -> Vec<u8> {
    let mut bytes = vec![0; 128];
    bytes[0..2].copy_from_slice(b"MZ");
    bytes[60..64].copy_from_slice(&(64u32).to_le_bytes());
    bytes[64..68].copy_from_slice(b"PE\0\0");
    bytes[68..70].copy_from_slice(&0x8664u16.to_le_bytes());
    bytes
}
fn elf() -> Vec<u8> {
    let mut bytes = vec![0; 128];
    bytes[0..4].copy_from_slice(b"\x7fELF");
    bytes[4] = 2;
    bytes[5] = 1;
    bytes[18..20].copy_from_slice(&62u16.to_le_bytes());
    bytes
}
fn macho(cpu: u32) -> Vec<u8> {
    let mut bytes = vec![0; 128];
    bytes[0..4].copy_from_slice(b"\xcf\xfa\xed\xfe");
    bytes[4..8].copy_from_slice(&cpu.to_le_bytes());
    bytes
}

fn fixture() -> FrozenPackage {
    let specs = [
        (
            Platform::WindowsX86_64,
            "bin/win",
            pe(),
            "windows",
            "x86_64",
        ),
        (Platform::LinuxX86_64, "bin/linux", elf(), "linux", "x86_64"),
        (
            Platform::MacosX86_64,
            "bin/mac",
            macho(0x01000007),
            "macos",
            "x86_64",
        ),
        (
            Platform::MacosAarch64,
            "bin/mac-arm",
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
    let manifest = PlatformManifest::new("mission-center", "0.5.1", artifacts);
    let mut files = vec![
        FrozenFile::new(PLATFORM_MANIFEST_FILE, manifest.to_json().unwrap(), false),
        FrozenFile::new(
            PLUGIN_MANIFEST_FILE,
            br#"{"name":"mission-center","version":"0.5.1"}"#.to_vec(),
            false,
        ),
    ];
    files.extend(
        specs
            .into_iter()
            .map(|(_, path, bytes, _, _)| FrozenFile::new(path, bytes, true)),
    );
    FrozenPackage::new(files).unwrap()
}

#[test]
fn selector_resolves_only_declared_platform_pair() {
    assert_eq!(Platform::parse("linux-x86_64"), Some(Platform::LinuxX86_64));
    assert_eq!(
        Platform::from_os_arch("macos", "aarch64"),
        Some(Platform::MacosAarch64)
    );
    assert_eq!(Platform::parse("linux-aarch64"), None);
    let artifact = fixture()
        .select_artifact(Platform::LinuxX86_64, "0.5.1")
        .unwrap();
    assert_eq!(artifact.platform, Platform::LinuxX86_64);
    assert_eq!(artifact.os, "linux");
    assert_eq!(artifact.arch, "x86_64");
}

#[test]
fn selector_rejects_missing_binary_and_bad_checksum_before_any_mutation() {
    let package = fixture();
    let missing = FrozenPackage::new(
        package
            .files()
            .iter()
            .filter(|file| file.relative_path != "bin/linux")
            .cloned()
            .collect(),
    )
    .unwrap();
    assert_eq!(
        missing
            .select_artifact(Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::MissingBinary
    );

    let mut files = package.files().to_vec();
    let binary = files
        .iter_mut()
        .find(|file| file.relative_path == "bin/linux")
        .unwrap();
    binary.bytes[20] ^= 1;
    let corrupt = FrozenPackage::new(files).unwrap();
    assert_eq!(
        corrupt
            .select_artifact(Platform::WindowsX86_64, "0.5.1")
            .unwrap_err()
            .code(),
        ErrorCode::CorruptChecksum
    );
}

#[test]
fn filesystem_mutation_has_explicit_unsupported_receipt() {
    let receipt =
        unsupported_mutation_receipt(MutationAction::Install, "native-install-1").unwrap();
    assert_eq!(receipt.status, MutationStatus::Unsupported);
    assert!(!receipt.written);
    assert!(!receipt.rollback_supported);
    assert_eq!(receipt.operation_id, "native-install-1");
    assert_eq!(
        unsupported_mutation_receipt(MutationAction::Rollback, "bad/id")
            .unwrap_err()
            .code(),
        ErrorCode::UnsafePath
    );
}
