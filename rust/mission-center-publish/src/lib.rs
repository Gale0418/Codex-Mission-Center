//! Offline, Rust-only read-only publish/install verifier.
use mission_center_core::sha256_digest;
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::HashSet,
    fmt,
    fmt::Write as _,
    fs::{self, OpenOptions},
    io::Write,
    path::{Component, Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

pub const SCHEMA_VERSION: &str = "1.0";
pub const PLATFORM_MANIFEST_FILE: &str = "platform-manifest.json";
pub const PLUGIN_MANIFEST_FILE: &str = ".codex-plugin/plugin.json";
/// Publish/install/rollback/reconcile mutation is intentionally unavailable
/// until a native handle adapter can prove durable, reparse-safe replacement.
pub const MUTATION_SUPPORTED: bool = false;
pub const MUTATION_REMEDIATION: &str =
    "mutationSupported:false；請由受控 native handle adapter 執行 mutation。";
pub const FILESYSTEM_VERIFIER_REMEDIATION: &str =
    "filesystem verifier 已停用；請由 native handle adapter 建立 FrozenPackage。";

pub const fn mutation_supported() -> bool {
    MUTATION_SUPPORTED
}
const MAX_FILE_BYTES: u64 = 128 * 1024 * 1024;
const MAX_TOTAL_BYTES: u64 = 256 * 1024 * 1024;
const MAX_FILES: usize = 4096;
const MAX_DEPTH: usize = 32;
const MAX_PATH_BYTES: usize = 4096;
const MAX_TRANSACTION_RECEIPTS: usize = 256;
const MAX_TRANSACTION_TARGETS: usize = 64;

struct StrictJson(Value);
struct StrictJsonVisitor;

impl<'de> Visitor<'de> for StrictJsonVisitor {
    type Value = StrictJson;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
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
                return Err(de::Error::custom("duplicate JSON key"));
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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Platform {
    #[serde(rename = "windows-x86_64")]
    WindowsX86_64,
    #[serde(rename = "linux-x86_64")]
    LinuxX86_64,
    #[serde(rename = "macos-x86_64")]
    MacosX86_64,
    #[serde(rename = "macos-aarch64")]
    MacosAarch64,
}
impl Platform {
    pub const ALL: [Self; 4] = [
        Self::WindowsX86_64,
        Self::LinuxX86_64,
        Self::MacosX86_64,
        Self::MacosAarch64,
    ];
    pub const fn os(self) -> &'static str {
        match self {
            Self::WindowsX86_64 => "windows",
            Self::LinuxX86_64 => "linux",
            Self::MacosX86_64 | Self::MacosAarch64 => "macos",
        }
    }
    pub const fn arch(self) -> &'static str {
        match self {
            Self::MacosAarch64 => "aarch64",
            _ => "x86_64",
        }
    }

    /// Parse the only platform identifiers accepted by the release manifest.
    /// Keeping this conversion in the publish crate prevents callers from
    /// constructing an OS/architecture pair that is not covered by the
    /// signed artifact set.
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "windows-x86_64" => Some(Self::WindowsX86_64),
            "linux-x86_64" => Some(Self::LinuxX86_64),
            "macos-x86_64" => Some(Self::MacosX86_64),
            "macos-aarch64" => Some(Self::MacosAarch64),
            _ => None,
        }
    }

    /// Resolve a platform from separately supplied OS and architecture
    /// fields. Unknown combinations remain unknown; they are never mapped to
    /// a nearby binary or to a downloaded fallback.
    pub fn from_os_arch(os: &str, arch: &str) -> Option<Self> {
        Self::ALL
            .into_iter()
            .find(|platform| platform.os() == os && platform.arch() == arch)
    }
    pub fn host() -> Option<Self> {
        #[cfg(all(target_os = "windows", target_arch = "x86_64"))]
        {
            return Some(Self::WindowsX86_64);
        }
        #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
        {
            return Some(Self::LinuxX86_64);
        }
        #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
        {
            return Some(Self::MacosX86_64);
        }
        #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
        {
            return Some(Self::MacosAarch64);
        }
        #[allow(unreachable_code)]
        None
    }

    #[allow(non_upper_case_globals)]
    pub const MacOSX86_64: Self = Self::MacosX86_64;
    #[allow(non_upper_case_globals)]
    pub const MacOSAarch64: Self = Self::MacosAarch64;
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[serde(deny_unknown_fields)]
pub struct PlatformArtifact {
    pub platform: Platform,
    pub path: String,
    pub sha256: String,
    pub version: String,
    pub os: String,
    pub arch: String,
    pub executable: String,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
#[serde(deny_unknown_fields)]
pub struct PlatformManifest {
    pub schema_version: String,
    pub plugin_name: String,
    pub version: String,
    pub artifacts: Vec<PlatformArtifact>,
}
impl PlatformManifest {
    pub fn new(
        plugin_name: impl Into<String>,
        version: impl Into<String>,
        artifacts: Vec<PlatformArtifact>,
    ) -> Self {
        Self {
            schema_version: SCHEMA_VERSION.into(),
            plugin_name: plugin_name.into(),
            version: version.into(),
            artifacts,
        }
    }
    pub fn validate(&self) -> Result<(), PublishError> {
        if self.schema_version != SCHEMA_VERSION || self.plugin_name != "mission-center" {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "平台 manifest schema/name 不正確，請使用 plugin-creator 與受控 release 產物。",
            ));
        }
        if semver(&self.version).is_err() {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "平台 manifest version 不是合法 SemVer，請重新產生套件。",
            ));
        }
        if self.artifacts.len() != Platform::ALL.len() {
            return Err(PublishError::stable(
                ErrorCode::MissingBinary,
                "平台 manifest 必須精確包含四個平台 artifact，請補齊四平台產物。",
            ));
        }
        let mut seen = HashSet::new();
        for a in &self.artifacts {
            a.validate(&self.version)?;
            if !seen.insert(a.platform) {
                return Err(PublishError::stable(
                    ErrorCode::InvalidManifest,
                    "平台 manifest 含重複平台，請每平台保留一份 artifact。",
                ));
            }
        }
        if Platform::ALL
            .iter()
            .any(|platform| !seen.contains(platform))
        {
            return Err(PublishError::stable(
                ErrorCode::MissingBinary,
                "平台 manifest 缺少 windows-x86_64、linux-x86_64、macos-x86_64 或 macos-aarch64 artifact。",
            ));
        }
        Ok(())
    }
    pub fn for_platform(&self, p: Platform) -> Result<&PlatformArtifact, PublishError> {
        self.artifacts
            .iter()
            .find(|a| a.platform == p)
            .ok_or_else(|| {
                PublishError::stable(
                    ErrorCode::MissingBinary,
                    "找不到目前平台 artifact，請提供對應執行檔。",
                )
            })
    }

    /// Return a validated artifact for the requested platform and release
    /// version. The clone makes the selected value independent of the input
    /// manifest after the validation boundary.
    pub fn select_artifact(
        &self,
        platform: Platform,
        version: &str,
    ) -> Result<PlatformArtifact, PublishError> {
        self.validate()?;
        if self.version != version {
            return Err(PublishError::stable(
                ErrorCode::VersionMismatch,
                "要求版本與 platform manifest 不同。",
            ));
        }
        self.for_platform(platform).cloned()
    }
    pub fn from_json(bytes: &[u8]) -> Result<Self, PublishError> {
        let v: Self = serde_json::from_slice::<StrictJson>(bytes)
            .map_err(|_| {
                PublishError::stable(
                    ErrorCode::InvalidManifest,
                    "平台 manifest JSON 損壞，請重新打包。",
                )
            })
            .and_then(|value| {
                serde_json::from_value(value.0).map_err(|_| {
                    PublishError::stable(
                        ErrorCode::InvalidManifest,
                        "平台 manifest 欄位不符合契約，請重新打包。",
                    )
                })
            })?;
        v.validate()?;
        Ok(v)
    }
    pub fn to_json(&self) -> Result<Vec<u8>, PublishError> {
        serde_json::to_vec_pretty(self).map_err(|_| {
            PublishError::stable(ErrorCode::InvalidManifest, "平台 manifest 無法序列化。")
        })
    }
}
impl PlatformArtifact {
    fn validate(&self, version: &str) -> Result<(), PublishError> {
        rel(&self.path, "artifact path")?;
        rel(&self.executable, "executable")?;
        if self.path != self.executable {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "artifact path 與 executable 必須指向同一檔案。",
            ));
        }
        if self.version != version || semver(&self.version).is_err() {
            return Err(PublishError::stable(
                ErrorCode::VersionMismatch,
                "artifact 版本與 manifest 不一致，請重新打包同一版本。",
            ));
        }
        if self.os != self.platform.os() || self.arch != self.platform.arch() {
            return Err(PublishError::stable(
                ErrorCode::WrongPlatform,
                "artifact 宣告的 OS/架構與平台不一致。",
            ));
        }
        if !sha256(&self.sha256) {
            return Err(PublishError::stable(
                ErrorCode::CorruptChecksum,
                "artifact SHA-256 格式不正確，請重新計算。",
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorCode {
    InvalidManifest,
    MissingBinary,
    WrongPlatform,
    VersionMismatch,
    CorruptChecksum,
    NonExecutable,
    UnsafePath,
    PythonRuntime,
    TransactionConflict,
    TransactionReplay,
    TransactionCorrupt,
    Io,
    NotFound,
    VerificationFailed,
    Unsupported,
}
impl ErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::InvalidManifest => "invalid_manifest",
            Self::MissingBinary => "missing_binary",
            Self::WrongPlatform => "wrong_platform",
            Self::VersionMismatch => "version_mismatch",
            Self::CorruptChecksum => "corrupt_checksum",
            Self::NonExecutable => "non_executable",
            Self::UnsafePath => "unsafe_path",
            Self::PythonRuntime => "python_runtime",
            Self::TransactionConflict => "transaction_conflict",
            Self::TransactionReplay => "transaction_replay",
            Self::TransactionCorrupt => "transaction_corrupt",
            Self::Io => "io",
            Self::NotFound => "not_found",
            Self::VerificationFailed => "verification_failed",
            Self::Unsupported => "unsupported",
        }
    }
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PublishError {
    pub code: ErrorCode,
    pub message: String,
    pub remediation: String,
}
impl PublishError {
    fn stable(code: ErrorCode, remediation: &str) -> Self {
        Self {
            code,
            message: code.as_str().to_owned(),
            remediation: remediation.to_owned(),
        }
    }
    pub const fn code(&self) -> ErrorCode {
        self.code
    }
}
impl fmt::Display for PublishError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{}: {}; remediation: {}",
            self.code.as_str(),
            self.message,
            self.remediation
        )
    }
}
impl std::error::Error for PublishError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TransactionStatus {
    Started,
    Committed,
    Aborted,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TargetPhase {
    Prepared,
    BackedUp,
    Swapped,
    Restored,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct TargetReceipt {
    pub destination: String,
    pub temp: String,
    pub backup: String,
    pub phase: TargetPhase,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct TransactionReceipt {
    pub schema_version: String,
    pub operation_id: String,
    pub digest: String,
    pub status: TransactionStatus,
    pub staging: String,
    pub destinations: Vec<String>,
    pub backups: Vec<String>,
    pub transaction_root: String,
    pub destination_count: usize,
    pub targets: Vec<TargetReceipt>,
}

/// Receipt for the local Codex marketplace manifest.  Registration is kept
/// separate from package materialization because the host discovers a plugin
/// through `.agents/plugins/marketplace.json`, not through the plugin tree
/// itself.  The receipt makes that second atomic mutation replayable and
/// rollbackable without invoking a host CLI.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RegistrationReceipt {
    pub schema_version: String,
    pub operation_id: String,
    pub digest: String,
    pub version: String,
    pub status: RegistrationStatus,
    pub target: String,
    pub temp: String,
    pub backup: Option<String>,
    pub transaction_root: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RegistrationStatus {
    Started,
    Committed,
    Aborted,
    RolledBack,
}
#[derive(Debug, Clone)]
pub struct PublishRequest {
    pub source: PathBuf,
    pub staging: PathBuf,
    pub operation_id: String,
    pub expected_platform: Platform,
    pub expected_version: String,
}
impl PublishRequest {
    pub fn new(
        source: impl Into<PathBuf>,
        staging: impl Into<PathBuf>,
        operation_id: impl Into<String>,
        platform: Platform,
        version: impl Into<String>,
    ) -> Self {
        Self {
            source: source.into(),
            staging: staging.into(),
            operation_id: operation_id.into(),
            expected_platform: platform,
            expected_version: version.into(),
        }
    }
}
#[derive(Debug, Clone)]
pub struct InstallRequest {
    pub package: PathBuf,
    pub destinations: Vec<PathBuf>,
    pub operation_id: String,
    pub expected_platform: Platform,
    pub expected_version: String,
}
impl InstallRequest {
    pub fn new(
        package: impl Into<PathBuf>,
        destinations: Vec<PathBuf>,
        operation_id: impl Into<String>,
        platform: Platform,
        version: impl Into<String>,
    ) -> Self {
        Self {
            package: package.into(),
            destinations,
            operation_id: operation_id.into(),
            expected_platform: platform,
            expected_version: version.into(),
        }
    }
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PreflightReport {
    pub manifest: PlatformManifest,
    pub artifact: PlatformArtifact,
    pub digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FrozenFile {
    pub relative_path: String,
    pub bytes: Vec<u8>,
    pub executable: bool,
}
impl FrozenFile {
    pub fn new(path: impl Into<String>, bytes: impl Into<Vec<u8>>, executable: bool) -> Self {
        Self {
            relative_path: path.into(),
            bytes: bytes.into(),
            executable,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FrozenPackage {
    files: Vec<FrozenFile>,
}
impl FrozenPackage {
    pub fn new(mut files: Vec<FrozenFile>) -> Result<Self, PublishError> {
        if files.len() > MAX_FILES {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "frozen package 檔案數量超過上限。",
            ));
        }
        let mut seen = HashSet::new();
        let mut total = 0u64;
        for file in &files {
            validate_frozen_path(&file.relative_path)?;
            if !seen.insert(file.relative_path.clone()) {
                return Err(PublishError::stable(
                    ErrorCode::UnsafePath,
                    "frozen package 含重複 relative path。",
                ));
            }
            let metadata_bytes = file.relative_path.len() as u64;
            if file.relative_path.len() > MAX_PATH_BYTES
                || file.bytes.len() as u64 > MAX_FILE_BYTES
                || metadata_bytes
                    .saturating_add(file.bytes.len() as u64)
                    .saturating_add(total)
                    > MAX_TOTAL_BYTES
            {
                return Err(PublishError::stable(
                    ErrorCode::InvalidManifest,
                    "frozen package 檔案、path metadata 或總大小超過上限。",
                ));
            }
            total = total
                .saturating_add(metadata_bytes)
                .saturating_add(file.bytes.len() as u64);
        }
        files.sort_by(|a, b| a.relative_path.cmp(&b.relative_path));
        Ok(Self { files })
    }
    pub fn files(&self) -> &[FrozenFile] {
        &self.files
    }
    pub fn verify(
        &self,
        platform: Platform,
        version: &str,
    ) -> Result<PreflightReport, PublishError> {
        scan_frozen_python(&self.files)?;
        let manifest = self.file(PLATFORM_MANIFEST_FILE).ok_or_else(|| {
            PublishError::stable(
                ErrorCode::MissingBinary,
                "frozen package 缺少 platform manifest。",
            )
        })?;
        let manifest = PlatformManifest::from_json(&manifest.bytes)?;
        if manifest.version != version {
            return Err(PublishError::stable(
                ErrorCode::VersionMismatch,
                "要求版本與 frozen package 不同。",
            ));
        }
        for declared_platform in Platform::ALL {
            let artifact = manifest.for_platform(declared_platform)?.clone();
            let binary = self.file(&artifact.path).ok_or_else(|| {
                PublishError::stable(
                    ErrorCode::MissingBinary,
                    "frozen package 缺少宣告的平台執行檔。",
                )
            })?;
            if binary.bytes.is_empty() {
                return Err(PublishError::stable(
                    ErrorCode::MissingBinary,
                    "宣告的平台執行檔不可為空檔。",
                ));
            }
            if !binary.executable {
                return Err(PublishError::stable(
                    ErrorCode::NonExecutable,
                    "frozen 平台執行檔未標示 executable。",
                ));
            }
            if sha256_digest(&binary.bytes) != artifact.sha256 {
                return Err(PublishError::stable(
                    ErrorCode::CorruptChecksum,
                    "平台執行檔 SHA-256 不符。",
                ));
            }
            identity(&binary.bytes, declared_platform)?;
        }
        let artifact = manifest.for_platform(platform)?.clone();
        let plugin = self.file(PLUGIN_MANIFEST_FILE).ok_or_else(|| {
            PublishError::stable(
                ErrorCode::InvalidManifest,
                "frozen package 缺少 plugin.json。",
            )
        })?;
        plugin_manifest_bytes(&plugin.bytes, &manifest.version)?;
        Ok(PreflightReport {
            manifest,
            artifact,
            digest: digest_frozen(&self.files),
        })
    }

    /// Verify the frozen package and return exactly the artifact selected for
    /// the requested platform. Verification still covers every declared
    /// platform first, so an incomplete package cannot be used merely because
    /// the current host's artifact happens to be present.
    pub fn select_artifact(
        &self,
        platform: Platform,
        version: &str,
    ) -> Result<PlatformArtifact, PublishError> {
        self.verify(platform, version).map(|report| report.artifact)
    }
    fn file(&self, path: &str) -> Option<&FrozenFile> {
        self.files.iter().find(|file| file.relative_path == path)
    }
}

/// An immutable, offline staging result.  This is deliberately a receipt and
/// not an install handle: no filesystem path is opened or written here.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct StagingReceipt {
    pub schema_version: String,
    pub operation_id: String,
    pub action: StagingAction,
    pub platform: Platform,
    pub version: String,
    pub package_digest: String,
    pub status: StagingStatus,
    pub written: bool,
    pub rollback_supported: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum StagingAction {
    Publish,
    Install,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum StagingStatus {
    Prepared,
}

/// Mutation entry points intentionally remain disabled until a platform
/// native, handle-relative transaction adapter exists.  This receipt lets a
/// caller report that fact without implying that an install or rollback ran.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MutationAction {
    Publish,
    Install,
    Rollback,
    Reconcile,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum MutationStatus {
    Unsupported,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct UnsupportedMutationReceipt {
    pub schema_version: String,
    pub operation_id: String,
    pub action: MutationAction,
    pub status: MutationStatus,
    pub written: bool,
    pub rollback_supported: bool,
    pub remediation: String,
}

impl UnsupportedMutationReceipt {
    pub fn new(
        action: MutationAction,
        operation_id: impl Into<String>,
    ) -> Result<Self, PublishError> {
        let operation_id = operation_id.into();
        validate_staging_operation_id(&operation_id)?;
        Ok(Self {
            schema_version: SCHEMA_VERSION.to_owned(),
            operation_id,
            action,
            status: MutationStatus::Unsupported,
            written: false,
            rollback_supported: false,
            remediation: MUTATION_REMEDIATION.to_owned(),
        })
    }
}

/// Build an explicit fail-closed mutation receipt without reading or writing
/// any filesystem path. This is the native contract currently available to
/// wrappers while durable installer/rollback handles are not implemented.
pub fn unsupported_mutation_receipt(
    action: MutationAction,
    operation_id: impl Into<String>,
) -> Result<UnsupportedMutationReceipt, PublishError> {
    UnsupportedMutationReceipt::new(action, operation_id)
}

fn validate_staging_operation_id(operation_id: &str) -> Result<(), PublishError> {
    if operation_id.is_empty()
        || operation_id.len() > 128
        || operation_id
            .bytes()
            .any(|byte| !(byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-')))
    {
        return Err(PublishError::stable(
            ErrorCode::UnsafePath,
            "operationId 必須是 1 至 128 字元的安全識別字串。",
        ));
    }
    Ok(())
}

fn stage_frozen_package(
    package: &FrozenPackage,
    action: StagingAction,
    operation_id: &str,
    platform: Platform,
    version: &str,
) -> Result<StagingReceipt, PublishError> {
    validate_staging_operation_id(operation_id)?;
    if version.is_empty() || semver(version).is_err() {
        return Err(PublishError::stable(
            ErrorCode::VersionMismatch,
            "要求版本必須是合法 SemVer。",
        ));
    }
    let report = package.verify(platform, version)?;
    Ok(StagingReceipt {
        schema_version: SCHEMA_VERSION.to_owned(),
        operation_id: operation_id.to_owned(),
        action,
        platform,
        version: report.manifest.version,
        package_digest: report.digest,
        status: StagingStatus::Prepared,
        written: false,
        rollback_supported: false,
    })
}

/// Verify and prepare a publish transaction without touching the filesystem.
pub fn stage_publish(
    package: &FrozenPackage,
    operation_id: &str,
    platform: Platform,
    version: &str,
) -> Result<StagingReceipt, PublishError> {
    stage_frozen_package(
        package,
        StagingAction::Publish,
        operation_id,
        platform,
        version,
    )
}

/// Verify and prepare an install transaction without touching the filesystem.
pub fn stage_install(
    package: &FrozenPackage,
    operation_id: &str,
    platform: Platform,
    version: &str,
) -> Result<StagingReceipt, PublishError> {
    stage_frozen_package(
        package,
        StagingAction::Install,
        operation_id,
        platform,
        version,
    )
}

/// There is no safe cross-platform native handle adapter yet, so rollback is
/// explicit and fail-closed instead of pretending that a receipt can mutate.
pub fn rollback_staged(_receipt: &StagingReceipt) -> Result<(), PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        MUTATION_REMEDIATION,
    ))
}

pub fn preflight_publish(_request: &PublishRequest) -> Result<PreflightReport, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        FILESYSTEM_VERIFIER_REMEDIATION,
    ))
}
pub fn preflight_install(_request: &InstallRequest) -> Result<PreflightReport, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        FILESYSTEM_VERIFIER_REMEDIATION,
    ))
}

fn validate_frozen_path(path: &str) -> Result<(), PublishError> {
    if path.is_empty()
        || path.len() > MAX_PATH_BYTES
        || path.contains('\\')
        || path.starts_with('/')
        || path.contains(':')
        || path.bytes().any(|byte| byte == 0)
        || path
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
        || path.split('/').count() > MAX_DEPTH
    {
        return Err(PublishError::stable(
            ErrorCode::UnsafePath,
            "frozen relative path 必須是唯一且受控的相對路徑。",
        ));
    }
    Ok(())
}
fn rel(s: &str, label: &str) -> Result<(), PublishError> {
    if s.is_empty()
        || s.contains('\\')
        || s.starts_with('/')
        || s.contains(':')
        || s.split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
    {
        return Err(PublishError::stable(
            ErrorCode::UnsafePath,
            &format!("{label} 必須是安全相對路徑。"),
        ));
    }
    Ok(())
}
fn frozen_python_allowlist(path: &str) -> bool {
    path.split('/').next().is_some_and(|part| {
        matches!(
            part.to_ascii_lowercase().as_str(),
            "docs" | "compat" | "python-oracle"
        )
    })
}
fn formal_runtime_role(path: &str) -> bool {
    let lower = path.to_ascii_lowercase();
    lower.ends_with(".sh")
        || lower.ends_with(".bash")
        || lower.ends_with(".zsh")
        || lower.ends_with(".cmd")
        || lower.ends_with(".bat")
        || lower.ends_with(".ps1")
        || lower.split('/').any(|part| matches!(part, "hooks" | "bin"))
}
fn frozen_python_path(path: &str) -> bool {
    let base = path.rsplit('/').next().unwrap_or(path).to_ascii_lowercase();
    base.ends_with(".py") || base.ends_with(".pyc") || python_command_token(&base)
}
fn scan_frozen_python(files: &[FrozenFile]) -> Result<(), PublishError> {
    for file in files {
        let allowlisted = frozen_python_allowlist(&file.relative_path);
        let formal = formal_runtime_role(&file.relative_path);
        if frozen_python_path(&file.relative_path) && !(allowlisted && !file.executable && !formal)
        {
            return Err(PublishError::stable(
                ErrorCode::PythonRuntime,
                "正式 staged runtime 不得含 Python runtime 檔案。",
            ));
        }
        if file.executable || formal {
            let text = String::from_utf8_lossy(&file.bytes).to_ascii_lowercase();
            let has_shebang = text.lines().any(|line| line.trim_start().starts_with("#!"));
            if formal
                && (formal_script_path(&file.relative_path)
                    || has_shebang
                    || (!known_binary_header(&file.bytes) && ascii_text(&file.bytes)))
            {
                validate_formal_script(&text)?;
            }
            if python_invocation(&text) {
                return Err(PublishError::stable(
                    ErrorCode::PythonRuntime,
                    "staged package 不得含 Python invocation/fallback。",
                ));
            }
        }
    }
    Ok(())
}
fn formal_script_path(path: &str) -> bool {
    let lower = path.to_ascii_lowercase();
    [".sh", ".bash", ".zsh", ".cmd", ".bat", ".ps1"]
        .iter()
        .any(|suffix| lower.ends_with(suffix))
}
fn known_binary_header(bytes: &[u8]) -> bool {
    bytes.starts_with(b"MZ")
        || bytes.starts_with(b"\x7fELF")
        || bytes.starts_with(b"\xcf\xfa\xed\xfe")
        || bytes.starts_with(b"\xfe\xed\xfa\xcf")
}
fn ascii_text(bytes: &[u8]) -> bool {
    bytes
        .iter()
        .all(|byte| *byte == b'\n' || *byte == b'\r' || (0x20..=0x7e).contains(byte))
}
fn validate_formal_script(text: &str) -> Result<(), PublishError> {
    for line in text.lines() {
        let trimmed = line.trim_start();
        if trimmed.is_empty() || trimmed.starts_with('#') || trimmed.starts_with("rem ") {
            continue;
        }
        if trimmed.chars().any(|c| "'\"$%`".contains(c)) {
            return Err(PublishError::stable(
                ErrorCode::PythonRuntime,
                "正式 shell/batch role 含不安全引號、變數或 command substitution。",
            ));
        }
        let tokens = shell_tokens(trimmed);
        for token in &tokens {
            let lower = token.to_ascii_lowercase();
            if matches!(lower.as_str(), "-c" | "/c" | "-command" | "/command")
                || token.contains('=')
            {
                return Err(PublishError::stable(
                    ErrorCode::PythonRuntime,
                    "正式 shell/batch role 禁止 -c、變數與未驗證 command wrapper。",
                ));
            }
        }
        let mut start = 0;
        for (index, token) in tokens.iter().enumerate() {
            if matches!(token.as_str(), ";" | "|" | "&") {
                validate_formal_segment(&tokens[start..index])?;
                start = index + 1;
            }
        }
        validate_formal_segment(&tokens[start..])?;
    }
    Ok(())
}
fn validate_formal_segment(tokens: &[String]) -> Result<(), PublishError> {
    let Some(first) = tokens.first() else {
        return Ok(());
    };
    let first = first.trim_start_matches('@').to_ascii_lowercase();
    const SAFE_COMMANDS: &[&str] = &[
        "[", "]", "cd", "command", "do", "echo", "else", "esac", "exec", "exit", "export", "false",
        "fi", "for", "if", "nice", "printf", "pwd", "read", "rem", "return", "set", "shift",
        "sudo", "test", "then", "true", "type", "unset", "while", "env",
    ];
    if !SAFE_COMMANDS.contains(&first.as_str()) {
        return Err(PublishError::stable(
            ErrorCode::PythonRuntime,
            "正式 shell/batch role 含未知 command wrapper，已 fail-closed。",
        ));
    }
    Ok(())
}
fn plugin_manifest_bytes(bytes: &[u8], expected_version: &str) -> Result<(), PublishError> {
    let v: Value = serde_json::from_slice::<StrictJson>(bytes)
        .map(|value| value.0)
        .map_err(|_| {
            PublishError::stable(
                ErrorCode::InvalidManifest,
                "plugin.json JSON 損壞，請用 plugin-creator 驗證。",
            )
        })?;
    let o = v.as_object().ok_or_else(|| {
        PublishError::stable(
            ErrorCode::InvalidManifest,
            "plugin.json 必須是 JSON object。",
        )
    })?;
    const ROOT_FIELDS: &[&str] = &[
        "name",
        "version",
        "description",
        "author",
        "homepage",
        "repository",
        "license",
        "keywords",
        "skills",
        "interface",
    ];
    if o.keys().any(|key| !ROOT_FIELDS.contains(&key.as_str())) {
        return Err(PublishError::stable(
            ErrorCode::InvalidManifest,
            "plugin.json 含未知欄位，請依 manifest schema 重建。",
        ));
    }
    if let Some(author) = o.get("author").and_then(Value::as_object)
        && author
            .keys()
            .any(|key| !matches!(key.as_str(), "name" | "email" | "url"))
    {
        return Err(PublishError::stable(
            ErrorCode::InvalidManifest,
            "plugin.json author 含未知欄位，請依 manifest schema 重建。",
        ));
    }
    if let Some(interface) = o.get("interface").and_then(Value::as_object) {
        const INTERFACE_FIELDS: &[&str] = &[
            "displayName",
            "shortDescription",
            "longDescription",
            "developerName",
            "category",
            "capabilities",
            "websiteURL",
            "privacyPolicyURL",
            "defaultPrompt",
            "brandColor",
            "composerIcon",
            "logo",
            "screenshots",
        ];
        if interface
            .keys()
            .any(|key| !INTERFACE_FIELDS.contains(&key.as_str()))
        {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "plugin.json interface 含未知欄位，請依 manifest schema 重建。",
            ));
        }
    }
    if o.get("name").and_then(Value::as_str) != Some("mission-center") {
        return Err(PublishError::stable(
            ErrorCode::InvalidManifest,
            "plugin.json name 必須是 mission-center。",
        ));
    }
    let actual_version = o.get("version").and_then(Value::as_str).ok_or_else(|| {
        PublishError::stable(
            ErrorCode::InvalidManifest,
            "plugin.json version 不是合法 SemVer。",
        )
    })?;
    if semver(actual_version).is_err() {
        return Err(PublishError::stable(
            ErrorCode::InvalidManifest,
            "plugin.json version 不是合法 SemVer。",
        ));
    }
    if actual_version != expected_version {
        return Err(PublishError::stable(
            ErrorCode::VersionMismatch,
            "plugin.json 與 platform manifest 版本不一致。",
        ));
    }
    if o.contains_key("hooks") {
        return Err(PublishError::stable(
            ErrorCode::InvalidManifest,
            "plugin.json 不得內嵌 hooks。",
        ));
    }
    Ok(())
}
fn digest_frozen(files: &[FrozenFile]) -> String {
    let mut data = Vec::new();
    for file in files {
        data.extend_from_slice(&(file.relative_path.len() as u64).to_be_bytes());
        data.extend_from_slice(file.relative_path.as_bytes());
        data.push(u8::from(file.executable));
        data.extend_from_slice(&(file.bytes.len() as u64).to_be_bytes());
        data.extend_from_slice(&file.bytes);
    }
    sha256_digest(&data)
}

#[cfg_attr(windows, allow(unreachable_code))]
#[cfg(any())]
mod transaction_legacy {
    use super::*;

    pub fn publish_package(r: &PublishRequest) -> Result<TransactionReceipt, PublishError> {
        #[cfg(windows)]
        {
            let _ = r;
            return Err(PublishError::stable(
                ErrorCode::Unsupported,
                "Windows durable publish 暫不支援；請在 POSIX 交易模型驗證後再由受控 installer 執行。",
            ));
        }
        validate_operation_id(&r.operation_id)?;
        // Keep the public operation zero-write on invalid input. A second pass
        // below runs under the cross-process writer lock before any swap.
        let initial_report = preflight_publish(r)?;
        let parent = r.staging.parent().ok_or_else(|| {
            PublishError::stable(ErrorCode::UnsafePath, "staging 必須有同層父目錄。")
        })?;
        if !parent.is_absolute() || !r.staging.is_absolute() {
            return Err(PublishError::stable(
                ErrorCode::UnsafePath,
                "staging 必須使用受控絕對路徑。",
            ));
        }
        ensure_parent(parent)?;
        let lock = WriterLock::acquire(parent)?;
        let report = preflight_publish(r)?;
        if report.digest != initial_report.digest {
            return Err(PublishError::stable(
                ErrorCode::VerificationFailed,
                "來源在鎖定前後發生變更，請重新建立 immutable snapshot。",
            ));
        }
        let tx = tx_path(&r.staging, &r.operation_id);
        reject(&tx, "transaction receipt")?;
        if let Some(old) = load(&tx)? {
            if old.digest != report.digest {
                let _ = lock.release();
                return Err(PublishError::stable(
                    ErrorCode::TransactionConflict,
                    "operationId 已被不同內容使用，請改用新的 operationId。",
                ));
            }
            if old.status == TransactionStatus::Committed {
                lock.release()?;
                return Ok(old);
            }
        }
        let temp = temp_path(&r.staging, &r.operation_id);
        let backup = backup_path(&r.staging, &r.operation_id);
        reject(&temp, "staging temp")?;
        reject(&backup, "staging backup")?;
        if temp.exists() {
            return Err(PublishError::stable(
                ErrorCode::TransactionConflict,
                "既有 temp 未完成處理，請先 reconcile，不可刪除交易快照。",
            ));
        }
        copy_tree(&r.source, &temp)?;
        let snapshot = preflight_package(&temp, r.expected_platform, &r.expected_version)?;
        let mut started = TransactionReceipt {
            schema_version: SCHEMA_VERSION.into(),
            operation_id: r.operation_id.clone(),
            digest: snapshot.digest,
            status: TransactionStatus::Started,
            staging: r.staging.to_string_lossy().into(),
            destinations: vec![r.staging.to_string_lossy().into()],
            backups: vec![backup.to_string_lossy().into()],
            transaction_root: parent.to_string_lossy().into(),
            destination_count: 1,
            targets: vec![TargetReceipt {
                destination: r.staging.to_string_lossy().into(),
                temp: temp.to_string_lossy().into(),
                backup: backup.to_string_lossy().into(),
                phase: TargetPhase::Prepared,
            }],
        };
        write_receipt(&tx, &started)?;
        if r.staging.exists() {
            if backup.exists() {
                return Err(PublishError::stable(
                    ErrorCode::TransactionConflict,
                    "既有 backup 未完成處理，請先 reconcile 或 rollback，不可覆寫唯一備份。",
                ));
            }
            fs::rename(&r.staging, &backup).map_err(io_error)?;
            started.targets[0].phase = TargetPhase::BackedUp;
            write_receipt(&tx, &started)?;
        }
        fs::rename(&temp, &r.staging).map_err(|e| {
            let _ = restore(&r.staging, &backup);
            io_error(e)
        })?;
        started.targets[0].phase = TargetPhase::Swapped;
        write_receipt(&tx, &started)?;
        let done = TransactionReceipt {
            status: TransactionStatus::Committed,
            ..started
        };
        write_receipt(&tx, &done)?;
        lock.release()?;
        Ok(done)
    }
    #[cfg_attr(windows, allow(unreachable_code))]
    pub fn install_package(r: &InstallRequest) -> Result<TransactionReceipt, PublishError> {
        #[cfg(windows)]
        {
            let _ = r;
            return Err(PublishError::stable(
                ErrorCode::Unsupported,
                "Windows durable install 暫不支援；請使用受控 native installer。",
            ));
        }
        validate_operation_id(&r.operation_id)?;
        let initial_report = preflight_install(r)?;
        let root = r.package.parent().ok_or_else(|| {
            PublishError::stable(ErrorCode::UnsafePath, "package 必須有同層父目錄。")
        })?;
        ensure_parent(root)?;
        let lock = WriterLock::acquire(root)?;
        let report = preflight_install(r)?;
        if report.digest != initial_report.digest {
            return Err(PublishError::stable(
                ErrorCode::VerificationFailed,
                "staged package 在鎖定前後發生變更，請重新建立 immutable snapshot。",
            ));
        }
        if r.destinations.is_empty() {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "至少需要一個 canonical 或 derived 目的地。",
            ));
        }
        let tx = tx_path(&r.package, &r.operation_id);
        reject(&tx, "transaction receipt")?;
        if let Some(old) = load(&tx)? {
            if old.digest != report.digest {
                let _ = lock.release();
                return Err(PublishError::stable(
                    ErrorCode::TransactionConflict,
                    "operationId 已被不同內容使用，請改用新的 operationId。",
                ));
            }
            if old.status == TransactionStatus::Committed {
                lock.release()?;
                return Ok(old);
            }
        }
        let mut started = TransactionReceipt {
            schema_version: SCHEMA_VERSION.into(),
            operation_id: r.operation_id.clone(),
            digest: report.digest.clone(),
            status: TransactionStatus::Started,
            staging: r.package.to_string_lossy().into(),
            destinations: r
                .destinations
                .iter()
                .map(|p| p.to_string_lossy().into())
                .collect(),
            backups: Vec::new(),
            transaction_root: r
                .package
                .parent()
                .unwrap_or(&r.package)
                .to_string_lossy()
                .into(),
            destination_count: r.destinations.len(),
            targets: Vec::new(),
        };
        let mut entries = Vec::new();
        let mut backups = Vec::new();
        let result: Result<(), PublishError> = (|| {
            for (i, dest) in r.destinations.iter().enumerate() {
                ensure_parent(dest.parent().ok_or_else(|| {
                    PublishError::stable(ErrorCode::UnsafePath, "目的地必須有父目錄。")
                })?)?;
                let temp = temp_path(dest, &format!("{}-{i}", r.operation_id));
                let backup = backup_path(dest, &format!("{}-{i}", r.operation_id));
                reject(&temp, "install temp")?;
                reject(&backup, "install backup")?;
                if temp.exists() || backup.exists() {
                    return Err(PublishError::stable(
                        ErrorCode::TransactionConflict,
                        "既有 temp/backup 未完成處理，請先 reconcile，不可刪除唯一交易資料。",
                    ));
                }
                copy_tree(&r.package, &temp)?;
                let snapshot = preflight_package(&temp, r.expected_platform, &r.expected_version)?;
                if snapshot.digest != report.digest {
                    return Err(PublishError::stable(
                        ErrorCode::VerificationFailed,
                        "staged snapshot digest 在安裝前不一致，請重新建立 immutable stage。",
                    ));
                }
                entries.push((temp, dest.clone(), backup.clone()));
                backups.push(backup.to_string_lossy().into());
            }
            started.targets = entries
                .iter()
                .map(|(temp, dest, backup)| TargetReceipt {
                    destination: dest.to_string_lossy().into(),
                    temp: temp.to_string_lossy().into(),
                    backup: backup.to_string_lossy().into(),
                    phase: TargetPhase::Prepared,
                })
                .collect();
            started.backups = backups.clone();
            write_receipt(&tx, &started)?;
            for (temp, dest, backup) in &entries {
                if dest.exists() {
                    fs::rename(dest, backup).map_err(io_error)?;
                }
                if let Some(target) = started
                    .targets
                    .iter_mut()
                    .find(|target| target.destination == dest.to_string_lossy())
                {
                    target.phase = TargetPhase::BackedUp;
                }
                write_receipt(&tx, &started)?;
                fs::rename(temp, dest).map_err(io_error)?;
                if let Some(target) = started
                    .targets
                    .iter_mut()
                    .find(|target| target.destination == dest.to_string_lossy())
                {
                    target.phase = TargetPhase::Swapped;
                }
                write_receipt(&tx, &started)?;
            }
            Ok(())
        })();
        if let Err(e) = result {
            rollback_paths(&entries);
            let _ = write_receipt(
                &tx,
                &TransactionReceipt {
                    status: TransactionStatus::Aborted,
                    backups,
                    ..started
                },
            );
            return Err(e);
        }
        let done = TransactionReceipt {
            status: TransactionStatus::Committed,
            backups,
            ..started
        };
        write_receipt(&tx, &done)?;
        lock.release()?;
        Ok(done)
    }
    pub fn verify_package(
        path: &Path,
        platform: Platform,
        version: &str,
    ) -> Result<PreflightReport, PublishError> {
        preflight_package(path, platform, version)
    }
    pub fn install(r: &InstallRequest) -> Result<TransactionReceipt, PublishError> {
        install_package(r)
    }
    pub fn verify(
        path: &Path,
        platform: Platform,
        version: &str,
    ) -> Result<PreflightReport, PublishError> {
        verify_package(path, platform, version)
    }
    pub fn rollback(receipt_path: &Path) -> Result<TransactionReceipt, PublishError> {
        rollback_transaction(receipt_path)
    }
    pub fn reconcile(root: &Path) -> Result<Vec<TransactionReceipt>, PublishError> {
        reconcile_transactions(root)
    }
    #[cfg_attr(windows, allow(unreachable_code))]
    pub fn rollback_transaction(receipt_path: &Path) -> Result<TransactionReceipt, PublishError> {
        #[cfg(windows)]
        {
            let _ = receipt_path;
            return Err(PublishError::stable(
                ErrorCode::Unsupported,
                "Windows durable rollback 暫不支援；已 fail-closed 且未寫入交易資料。",
            ));
        }
        let receipt = load(receipt_path)?.ok_or_else(|| {
            PublishError::stable(
                ErrorCode::NotFound,
                "找不到交易 receipt，請指定有效 operationId。",
            )
        })?;
        let receipt_root = receipt_path
            .parent()
            .and_then(Path::parent)
            .ok_or_else(|| {
                PublishError::stable(
                    ErrorCode::UnsafePath,
                    "receipt 必須位於 transactionRoot/.mission-center-transactions。",
                )
            })?;
        if Path::new(&receipt.transaction_root) != receipt_root {
            return Err(PublishError::stable(
                ErrorCode::TransactionCorrupt,
                "receipt transactionRoot 與 receipt 路徑不一致。",
            ));
        }
        let lock_root = Path::new(&receipt.transaction_root);
        let lock = WriterLock::acquire(lock_root)?;
        if receipt.status == TransactionStatus::Aborted {
            lock.release()?;
            return Ok(receipt);
        };
        for target_info in &receipt.targets {
            let target = PathBuf::from(&target_info.destination);
            let temp = PathBuf::from(&target_info.temp);
            let backup = PathBuf::from(&target_info.backup);
            reject(&target, "交易目的地")?;
            reject(&temp, "交易 temp")?;
            reject(&backup, "交易 backup")?;
            match (receipt.status, target_info.phase) {
                (TransactionStatus::Started, TargetPhase::Prepared) => {
                    if temp.exists() {
                        remove(&temp)?;
                    }
                    if !target.exists() && backup.exists() {
                        fs::rename(&backup, &target).map_err(io_error)?;
                    }
                }
                (_, TargetPhase::Prepared) => {
                    if temp.exists() {
                        remove(&temp)?;
                    }
                    if !target.exists() && backup.exists() {
                        fs::rename(&backup, &target).map_err(io_error)?;
                    }
                }
                (_, TargetPhase::BackedUp) => {
                    if backup.exists() && !target.exists() {
                        fs::rename(&backup, &target).map_err(io_error)?;
                    } else if receipt.status == TransactionStatus::Started
                        && backup.exists()
                        && !temp.exists()
                    {
                        remove(&target)?;
                        fs::rename(&backup, &target).map_err(io_error)?;
                    }
                }
                (_, TargetPhase::Swapped) => {
                    if target.exists() {
                        remove(&target)?;
                    }
                    if backup.exists() {
                        fs::rename(&backup, &target).map_err(io_error)?;
                    }
                }
                (_, TargetPhase::Restored) => {}
            }
        }
        let restored_targets = receipt
            .targets
            .iter()
            .map(|target| TargetReceipt {
                phase: TargetPhase::Restored,
                ..target.clone()
            })
            .collect();
        let out = TransactionReceipt {
            status: TransactionStatus::Aborted,
            targets: restored_targets,
            ..receipt
        };
        write_receipt(receipt_path, &out)?;
        lock.release()?;
        Ok(out)
    }
    #[cfg_attr(windows, allow(unreachable_code))]
    pub fn reconcile_transactions(root: &Path) -> Result<Vec<TransactionReceipt>, PublishError> {
        #[cfg(windows)]
        {
            let _ = root;
            return Err(PublishError::stable(
                ErrorCode::Unsupported,
                "Windows durable reconcile 暫不支援；已 fail-closed 且未寫入交易資料。",
            ));
        }
        reject(root, "交易根目錄")?;
        let dir = root.join(".mission-center-transactions");
        if !dir.exists() {
            return Ok(Vec::new());
        }
        reject(&dir, "交易目錄")?;
        let mut out = Vec::new();
        for e in fs::read_dir(&dir).map_err(io_error)? {
            let p = e.map_err(io_error)?.path();
            if p.extension().and_then(|s| s.to_str()) != Some("json") {
                continue;
            }
            let r = load(&p)?.ok_or_else(|| {
                PublishError::stable(
                    ErrorCode::TransactionCorrupt,
                    "交易 receipt 損壞，請保留備份後重新 reconcile。",
                )
            })?;
            if r.schema_version != SCHEMA_VERSION || r.operation_id.is_empty() || !sha256(&r.digest)
            {
                return Err(PublishError::stable(
                    ErrorCode::TransactionCorrupt,
                    "交易 receipt 欄位不合法，請重新發布。",
                ));
            }
            validate_operation_id(&r.operation_id)?;
            if Path::new(&r.transaction_root) != root {
                return Err(PublishError::stable(
                    ErrorCode::TransactionCorrupt,
                    "receipt transactionRoot 與 reconcile root 不一致。",
                ));
            }
            for path in r.destinations.iter().chain(r.backups.iter()) {
                reject(Path::new(path), "transaction receipt path")?;
            }
            if r.status == TransactionStatus::Started {
                let restored = rollback_transaction(&p)?;
                let lock = dir.join(format!(".lock-{}", restored.operation_id));
                let _ = fs::remove_dir(lock);
                out.push(restored);
            } else {
                let lock = WriterLock::acquire(root)?;
                lock.release()?;
                out.push(r)
            }
        }
        Ok(out)
    }
}

pub fn publish_package(_request: &PublishRequest) -> Result<TransactionReceipt, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        MUTATION_REMEDIATION,
    ))
}
pub fn install_package(_request: &InstallRequest) -> Result<TransactionReceipt, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        MUTATION_REMEDIATION,
    ))
}
pub fn verify_package(
    _path: &Path,
    _platform: Platform,
    _version: &str,
) -> Result<PreflightReport, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        FILESYSTEM_VERIFIER_REMEDIATION,
    ))
}
pub fn verify(
    _path: &Path,
    _platform: Platform,
    _version: &str,
) -> Result<PreflightReport, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        FILESYSTEM_VERIFIER_REMEDIATION,
    ))
}
pub fn install(_request: &InstallRequest) -> Result<TransactionReceipt, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        MUTATION_REMEDIATION,
    ))
}
pub fn rollback(_receipt_path: &Path) -> Result<TransactionReceipt, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        MUTATION_REMEDIATION,
    ))
}
pub fn reconcile(_root: &Path) -> Result<Vec<TransactionReceipt>, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        MUTATION_REMEDIATION,
    ))
}
pub fn rollback_transaction(_receipt_path: &Path) -> Result<TransactionReceipt, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        MUTATION_REMEDIATION,
    ))
}
pub fn reconcile_transactions(_root: &Path) -> Result<Vec<TransactionReceipt>, PublishError> {
    Err(PublishError::stable(
        ErrorCode::Unsupported,
        MUTATION_REMEDIATION,
    ))
}

/// Apply an already verified frozen package to one or more destinations.
///
/// This is deliberately a separate opt-in API from the legacy `install`
/// entrypoint.  Callers must provide a package directory and explicit
/// destinations; the package is fully loaded and verified before the first
/// destination is touched.  Each destination is swapped through a sibling
/// temporary and backup directory, and a durable receipt is written after
/// every phase so a later rollback can restore the previous tree.
pub fn native_install_package(
    package: &Path,
    destinations: &[PathBuf],
    operation_id: &str,
    platform: Platform,
    version: &str,
) -> Result<TransactionReceipt, PublishError> {
    validate_staging_operation_id(operation_id)?;
    if destinations.is_empty() {
        return Err(PublishError::stable(
            ErrorCode::InvalidManifest,
            "至少需要一個明確的 install destination。",
        ));
    }
    let package = absolute_directory(package, "package")?;
    let frozen = load_frozen_directory(&package)?;
    let report = frozen.verify(platform, version)?;
    let transaction_root = package
        .parent()
        .ok_or_else(|| PublishError::stable(ErrorCode::UnsafePath, "package 缺少父目錄。"))?
        .join(".mission-center-transactions");
    ensure_native_directory(&transaction_root)?;
    let lock = NativeInstallLock::acquire(&transaction_root, operation_id)?;
    let receipt_path = transaction_root.join(format!("{operation_id}.json"));
    reject_native_path(&receipt_path, "transaction receipt")?;
    if let Some(previous) = read_transaction_receipt(&receipt_path)? {
        if previous.digest != report.digest {
            return Err(PublishError::stable(
                ErrorCode::TransactionConflict,
                "operationId 已被不同 package 使用，請改用新的 operationId。",
            ));
        }
        if previous.status == TransactionStatus::Committed {
            return Ok(previous);
        }
    }
    validate_destinations(&package, &transaction_root, destinations)?;
    let mut entries = Vec::with_capacity(destinations.len());
    let nonce = unique_native_nonce();
    for (index, destination) in destinations.iter().enumerate() {
        let destination = absolute_path(destination, "destination")?;
        let parent = destination.parent().ok_or_else(|| {
            PublishError::stable(ErrorCode::UnsafePath, "destination 缺少父目錄。")
        })?;
        ensure_native_directory(parent)?;
        let temp = parent.join(format!(
            ".mission-center-{operation_id}-{nonce}-{index}.tmp"
        ));
        let backup = parent.join(format!(
            ".mission-center-{operation_id}-{nonce}-{index}.bak"
        ));
        reject_native_path(&temp, "install temp")?;
        reject_native_path(&backup, "install backup")?;
        if temp.exists() || backup.exists() {
            return Err(PublishError::stable(
                ErrorCode::TransactionConflict,
                "既有 install temp/backup 未完成處理，請先 rollback 或 reconcile。",
            ));
        }
        if let Err(error) = copy_frozen_directory(&frozen, &temp) {
            remove_native_temps(&entries);
            let _ = remove_native_tree(&temp);
            return Err(error);
        }
        entries.push(TargetReceipt {
            destination: destination.to_string_lossy().into_owned(),
            temp: temp.to_string_lossy().into_owned(),
            backup: backup.to_string_lossy().into_owned(),
            phase: TargetPhase::Prepared,
        });
    }
    let mut receipt = TransactionReceipt {
        schema_version: SCHEMA_VERSION.to_owned(),
        operation_id: operation_id.to_owned(),
        digest: report.digest,
        status: TransactionStatus::Started,
        staging: package.to_string_lossy().into_owned(),
        destinations: entries.iter().map(|x| x.destination.clone()).collect(),
        backups: entries.iter().map(|x| x.backup.clone()).collect(),
        transaction_root: transaction_root.to_string_lossy().into_owned(),
        destination_count: entries.len(),
        targets: entries,
    };
    if let Err(error) = write_transaction_receipt(&receipt_path, &receipt) {
        remove_native_temps(&receipt.targets);
        return Err(error);
    }
    let swap_result = (|| {
        for index in 0..receipt.targets.len() {
            let destination = PathBuf::from(&receipt.targets[index].destination);
            let temp = PathBuf::from(&receipt.targets[index].temp);
            let backup = PathBuf::from(&receipt.targets[index].backup);
            reject_native_path(&destination, "destination")?;
            if destination.exists() {
                fs::rename(&destination, &backup).map_err(native_io)?;
            }
            receipt.targets[index].phase = TargetPhase::BackedUp;
            write_transaction_receipt(&receipt_path, &receipt)?;
            fs::rename(&temp, &destination).map_err(native_io)?;
            receipt.targets[index].phase = TargetPhase::Swapped;
            write_transaction_receipt(&receipt_path, &receipt)?;
        }
        Ok::<(), PublishError>(())
    })();
    if let Err(error) = swap_result {
        restore_native_targets(&receipt.targets);
        receipt.status = TransactionStatus::Aborted;
        for target in &mut receipt.targets {
            target.phase = TargetPhase::Restored;
        }
        let _ = write_transaction_receipt(&receipt_path, &receipt);
        return Err(error);
    }
    receipt.status = TransactionStatus::Committed;
    write_transaction_receipt(&receipt_path, &receipt)?;
    drop(lock);
    Ok(receipt)
}

const REGISTRATION_RECEIPT_MAX_BYTES: usize = 64 * 1024;
const REGISTRATION_MANIFEST_MAX_BYTES: usize = 64 * 1024;

fn registration_manifest(plugin_root: &Path, version: &str) -> Result<Vec<u8>, PublishError> {
    let path = plugin_root.join(".codex-plugin").join("plugin.json");
    reject_native_path(&path, "plugin manifest")?;
    let bytes = fs::read(&path).map_err(native_io)?;
    if bytes.len() > REGISTRATION_MANIFEST_MAX_BYTES {
        return Err(PublishError::stable(
            ErrorCode::InvalidManifest,
            "plugin.json 超過 registration 大小上限。",
        ));
    }
    let value = serde_json::from_slice::<StrictJson>(&bytes)
        .map(|strict| strict.0)
        .map_err(|_| PublishError::stable(ErrorCode::InvalidManifest, "plugin.json JSON 無效。"))?;
    let object = value.as_object().ok_or_else(|| {
        PublishError::stable(ErrorCode::InvalidManifest, "plugin.json 必須是 object。")
    })?;
    if object.get("name").and_then(Value::as_str) != Some("mission-center")
        || object.get("version").and_then(Value::as_str) != Some(version)
    {
        return Err(PublishError::stable(
            ErrorCode::VersionMismatch,
            "plugin.json name/version 與 registration 要求不一致。",
        ));
    }
    let interface = match object.get("interface") {
        None => None,
        Some(Value::Object(interface)) => Some(interface),
        Some(_) => {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "plugin interface 必須是 object。",
            ));
        }
    };
    let display_name = interface
        .and_then(|interface| interface.get("displayName"))
        .and_then(Value::as_str)
        .unwrap_or("Mission Center");
    if display_name.is_empty()
        || display_name.len() > 256
        || display_name.chars().any(|character| character.is_control())
    {
        return Err(PublishError::stable(
            ErrorCode::InvalidManifest,
            "plugin displayName 不符合 registration 限制。",
        ));
    }
    let category = match interface.and_then(|interface| interface.get("category")) {
        None => "Productivity",
        Some(Value::String(category)) if !category.is_empty() && category.len() <= 128 => category,
        Some(_) => {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "plugin category 不符合 registration 限制。",
            ));
        }
    };
    let display_json = serde_json::to_string(&format!("Local {display_name}"))
        .map_err(|_| PublishError::stable(ErrorCode::Io, "marketplace displayName 序列化失敗。"))?;
    let category_json = serde_json::to_string(category)
        .map_err(|_| PublishError::stable(ErrorCode::Io, "marketplace category 序列化失敗。"))?;
    // Keep the same field order/indentation as the Python oracle's
    // json.dumps(..., indent=2, ensure_ascii=False) output.
    Ok(format!(
        "{{\n  \"name\": \"mission-center-local\",\n  \"interface\": {{\n    \"displayName\": {display_json}\n  }},\n  \"plugins\": [\n    {{\n      \"name\": \"mission-center\",\n      \"source\": {{\n        \"source\": \"local\",\n        \"path\": \"./plugins/mission-center\"\n      }},\n      \"policy\": {{\n        \"installation\": \"AVAILABLE\",\n        \"authentication\": \"ON_INSTALL\"\n      }},\n      \"category\": {category_json}\n    }}\n  ]\n}}\n"
    )
    .into_bytes())
}

fn read_registration_receipt(path: &Path) -> Result<Option<RegistrationReceipt>, PublishError> {
    if !path.exists() {
        return Ok(None);
    }
    let bytes = fs::read(path).map_err(native_io)?;
    if bytes.len() > REGISTRATION_RECEIPT_MAX_BYTES {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "registration receipt 超過大小上限。",
        ));
    }
    serde_json::from_slice(&bytes).map(Some).map_err(|_| {
        PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "registration receipt JSON 損壞。",
        )
    })
}

fn write_registration_receipt(
    path: &Path,
    receipt: &RegistrationReceipt,
) -> Result<(), PublishError> {
    let bytes = serde_json::to_vec(receipt)
        .map_err(|_| PublishError::stable(ErrorCode::Io, "registration receipt 序列化失敗。"))?;
    if bytes.len() > REGISTRATION_RECEIPT_MAX_BYTES {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "registration receipt 超過大小上限。",
        ));
    }
    let temp = path.with_extension(format!("json.{}.tmp", unique_native_nonce()));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(native_io)?;
    file.write_all(&bytes).map_err(native_io)?;
    file.sync_all().map_err(native_io)?;
    fs::rename(&temp, path).map_err(native_io)
}

/// Atomically write the local marketplace discovery manifest after a verified
/// plugin tree has been installed. This is a filesystem registration artifact;
/// it never invokes the Codex executable or performs an external submission.
pub fn native_register_marketplace(
    plugin_root: &Path,
    marketplace_root: &Path,
    operation_id: &str,
    version: &str,
) -> Result<RegistrationReceipt, PublishError> {
    validate_staging_operation_id(operation_id)?;
    let plugin_root = absolute_directory(plugin_root, "plugin root")?;
    let marketplace_root = absolute_path(marketplace_root, "marketplace root")?;
    ensure_native_directory(&marketplace_root)?;
    let expected_plugin = marketplace_root.join("plugins").join("mission-center");
    if plugin_root != expected_plugin {
        return Err(PublishError::stable(
            ErrorCode::UnsafePath,
            "plugin root 必須是 marketplace/plugins/mission-center。",
        ));
    }
    let manifest_bytes = registration_manifest(&plugin_root, version)?;
    let digest = sha256_digest(&manifest_bytes);
    let target = marketplace_root
        .join(".agents")
        .join("plugins")
        .join("marketplace.json");
    // Keep registration receipts in their own namespace so the generic
    // package transaction reconciler cannot mistake them for install receipts.
    let transaction_root = marketplace_root.join(".mission-center-registration-transactions");
    ensure_native_directory(target.parent().expect("marketplace manifest parent"))?;
    ensure_native_directory(&transaction_root)?;
    let lock = NativeInstallLock::acquire(&transaction_root, operation_id)?;
    let receipt_path = transaction_root.join(format!("{operation_id}.json"));
    reject_native_path(&receipt_path, "registration receipt")?;
    if let Some(previous) = read_registration_receipt(&receipt_path)? {
        validate_registration_receipt(&previous, &receipt_path, &transaction_root)?;
        if previous.digest != digest || previous.version != version {
            return Err(PublishError::stable(
                ErrorCode::TransactionConflict,
                "operationId 已被不同 marketplace manifest 使用。",
            ));
        }
        if previous.status == RegistrationStatus::Committed {
            return Ok(previous);
        }
        return Err(PublishError::stable(
            ErrorCode::TransactionConflict,
            "registration operation 已有未完成 receipt，請先 rollback/reconcile。",
        ));
    }
    reject_native_path(&target, "marketplace manifest")?;
    if let Ok(metadata) = fs::symlink_metadata(&target)
        && (metadata.file_type().is_symlink() || !metadata.is_file())
    {
        return Err(PublishError::stable(
            ErrorCode::UnsafePath,
            "marketplace manifest 不得是 symlink 或非檔案。",
        ));
    }
    let nonce = unique_native_nonce();
    let temp = target.with_extension(format!("json.{nonce}.tmp"));
    let backup = target.with_extension(format!("json.{nonce}.bak"));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(native_io)?;
    file.write_all(&manifest_bytes).map_err(native_io)?;
    file.sync_all().map_err(native_io)?;
    let mut receipt = RegistrationReceipt {
        schema_version: SCHEMA_VERSION.to_owned(),
        operation_id: operation_id.to_owned(),
        digest,
        version: version.to_owned(),
        status: RegistrationStatus::Started,
        target: target.to_string_lossy().into_owned(),
        temp: temp.to_string_lossy().into_owned(),
        backup: target
            .exists()
            .then(|| backup.to_string_lossy().into_owned()),
        transaction_root: transaction_root.to_string_lossy().into_owned(),
    };
    if let Err(error) = write_registration_receipt(&receipt_path, &receipt) {
        let _ = fs::remove_file(&temp);
        return Err(error);
    }
    let swap = (|| {
        if target.exists() {
            fs::rename(&target, &backup).map_err(native_io)?;
        }
        fs::rename(&temp, &target).map_err(native_io)?;
        Ok::<(), PublishError>(())
    })();
    if let Err(error) = swap {
        let _ = fs::remove_file(&temp);
        if backup.exists() && !target.exists() {
            let _ = fs::rename(&backup, &target);
        }
        receipt.status = RegistrationStatus::Aborted;
        let _ = write_registration_receipt(&receipt_path, &receipt);
        return Err(error);
    }
    receipt.status = RegistrationStatus::Committed;
    // The manifest is committed but receipt persistence can still fail; leave
    // the target intact and surface the error for explicit reconciliation.
    write_registration_receipt(&receipt_path, &receipt)?;
    drop(lock);
    Ok(receipt)
}

/// Roll back a committed marketplace registration only when the target still
/// matches the recorded digest. External edits therefore fail closed.
pub fn native_rollback_registration(
    receipt_path: &Path,
) -> Result<RegistrationReceipt, PublishError> {
    let receipt_path = absolute_path(receipt_path, "registration receipt")?;
    let receipt = read_registration_receipt(&receipt_path)?.ok_or_else(|| {
        PublishError::stable(ErrorCode::NotFound, "找不到 registration receipt。")
    })?;
    if receipt.status != RegistrationStatus::Committed {
        return Err(PublishError::stable(
            ErrorCode::TransactionConflict,
            "registration receipt 不是 committed，拒絕 rollback。",
        ));
    }
    let root = receipt_path
        .parent()
        .ok_or_else(|| PublishError::stable(ErrorCode::UnsafePath, "receipt 缺少 parent。"))?;
    let lock = NativeInstallLock::acquire(root, &receipt.operation_id)?;
    validate_registration_receipt(&receipt, &receipt_path, root)?;
    let target = absolute_path(Path::new(&receipt.target), "registration target")?;
    reject_native_path(&target, "registration target")?;
    let current = fs::read(&target).map_err(native_io)?;
    if sha256_digest(&current) != receipt.digest {
        return Err(PublishError::stable(
            ErrorCode::TransactionConflict,
            "marketplace manifest 已被外部修改，拒絕 rollback。",
        ));
    }
    fs::remove_file(&target).map_err(native_io)?;
    if let Some(backup) = receipt.backup.as_deref() {
        let backup = absolute_path(Path::new(backup), "registration backup")?;
        if backup.exists() {
            fs::rename(backup, &target).map_err(native_io)?;
        }
    }
    let mut restored = receipt;
    restored.status = RegistrationStatus::RolledBack;
    write_registration_receipt(&receipt_path, &restored)?;
    drop(lock);
    Ok(restored)
}

/// Reconcile registration receipts after a crash.  A `started` receipt is
/// recoverable because it records both the staged temp file and optional
/// backup; any digest/path ambiguity fails closed instead of guessing.
pub fn native_reconcile_registrations(
    marketplace_root: &Path,
) -> Result<Vec<RegistrationReceipt>, PublishError> {
    let marketplace_root = absolute_directory(marketplace_root, "marketplace root")?;
    let transaction_root = marketplace_root.join(".mission-center-registration-transactions");
    if !transaction_root.exists() {
        return Ok(Vec::new());
    }
    let transaction_root =
        absolute_directory(&transaction_root, "registration transaction directory")?;
    let mut paths = Vec::new();
    for entry in fs::read_dir(&transaction_root).map_err(native_io)? {
        let path = entry.map_err(native_io)?.path();
        reject_native_path(&path, "registration transaction entry")?;
        if path.extension().and_then(|value| value.to_str()) == Some("json") {
            paths.push(path);
        } else if path.file_name().and_then(|value| value.to_str()) != Some(".lock") {
            return Err(PublishError::stable(
                ErrorCode::TransactionCorrupt,
                "registration transaction directory 含未識別殘留檔案。",
            ));
        }
    }
    if paths.len() > MAX_TRANSACTION_RECEIPTS {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "registration receipt 數量超過上限。",
        ));
    }
    paths.sort();
    let mut receipts = Vec::with_capacity(paths.len());
    for path in paths {
        let receipt = read_registration_receipt(&path)?.ok_or_else(|| {
            PublishError::stable(
                ErrorCode::TransactionCorrupt,
                "registration receipt 在掃描期間消失。",
            )
        })?;
        validate_registration_receipt(&receipt, &path, &transaction_root)?;
        if receipt.status != RegistrationStatus::Started {
            receipts.push(receipt);
            continue;
        }
        let _lock = NativeInstallLock::acquire(&transaction_root, &receipt.operation_id)?;
        let target = absolute_path(Path::new(&receipt.target), "registration target")?;
        let temp = absolute_path(Path::new(&receipt.temp), "registration temp")?;
        let backup = receipt
            .backup
            .as_deref()
            .map(|value| absolute_path(Path::new(value), "registration backup"))
            .transpose()?;
        reject_native_path(&target, "registration target")?;
        reject_native_path(&temp, "registration temp")?;
        if let Some(backup) = &backup {
            reject_native_path(backup, "registration backup")?;
        }
        if target.exists() {
            let current = fs::read(&target).map_err(native_io)?;
            if sha256_digest(&current) != receipt.digest {
                return Err(PublishError::stable(
                    ErrorCode::TransactionConflict,
                    "registration target 在 crash recovery 期間內容不一致。",
                ));
            }
            fs::remove_file(&target).map_err(native_io)?;
        }
        if temp.exists() {
            fs::remove_file(&temp).map_err(native_io)?;
        }
        if let Some(backup) = backup
            && backup.exists()
            && !target.exists()
        {
            fs::rename(backup, &target).map_err(native_io)?;
        }
        let mut aborted = receipt;
        aborted.status = RegistrationStatus::Aborted;
        write_registration_receipt(&path, &aborted)?;
        receipts.push(aborted);
    }
    Ok(receipts)
}

fn validate_registration_receipt(
    receipt: &RegistrationReceipt,
    receipt_path: &Path,
    transaction_root: &Path,
) -> Result<(), PublishError> {
    let expected_name = format!("{}.json", receipt.operation_id);
    if receipt.schema_version != SCHEMA_VERSION
        || receipt.operation_id.is_empty()
        || !sha256(&receipt.digest)
        || semver(&receipt.version).is_err()
        || receipt_path.file_name().and_then(|value| value.to_str()) != Some(expected_name.as_str())
        || Path::new(&receipt.transaction_root) != transaction_root
    {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "registration receipt 欄位、檔名或 transactionRoot 不一致。",
        ));
    }
    validate_staging_operation_id(&receipt.operation_id)?;
    for (label, value) in [
        ("target", receipt.target.as_str()),
        ("temp", receipt.temp.as_str()),
    ] {
        let path = Path::new(value);
        if !path.is_absolute() {
            return Err(PublishError::stable(
                ErrorCode::TransactionCorrupt,
                &format!("registration {label} 必須是絕對路徑。"),
            ));
        }
        reject_native_path(path, "registration receipt path")?;
    }
    if let Some(value) = receipt.backup.as_deref() {
        let path = Path::new(value);
        if !path.is_absolute() {
            return Err(PublishError::stable(
                ErrorCode::TransactionCorrupt,
                "registration backup 必須是絕對路徑。",
            ));
        }
        reject_native_path(path, "registration backup")?;
    }
    Ok(())
}

/// Publish a fully verified frozen package through the same atomic transaction
/// used by native install. Publishing is intentionally destination-explicit;
/// marketplace registration is a separate receipt-backed operation so package
/// bytes, checksums, replay and rollback each retain one audited mutation path.
pub fn native_publish_package(
    package: &Path,
    destinations: &[PathBuf],
    operation_id: &str,
    platform: Platform,
    version: &str,
) -> Result<TransactionReceipt, PublishError> {
    native_install_package(package, destinations, operation_id, platform, version)
}

/// Restore destinations from a receipt produced by [`native_install_package`].
pub fn native_rollback_transaction(
    receipt_path: &Path,
) -> Result<TransactionReceipt, PublishError> {
    let receipt = read_transaction_receipt(receipt_path)?.ok_or_else(|| {
        PublishError::stable(ErrorCode::NotFound, "找不到 install transaction receipt。")
    })?;
    if receipt.schema_version != SCHEMA_VERSION || receipt.operation_id.is_empty() {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "transaction receipt 欄位不合法。",
        ));
    }
    validate_staging_operation_id(&receipt.operation_id)?;
    let expected_name = format!("{}.json", receipt.operation_id);
    if receipt_path.file_name().and_then(|name| name.to_str()) != Some(expected_name.as_str()) {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "receipt 檔名與 operationId 不一致。",
        ));
    }
    reject_native_path(receipt_path, "transaction receipt")?;
    let root = receipt_path.parent().ok_or_else(|| {
        PublishError::stable(
            ErrorCode::UnsafePath,
            "receipt 不在 transaction directory。",
        )
    })?;
    if Path::new(&receipt.transaction_root) != root {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "receipt transactionRoot 與路徑不一致。",
        ));
    }
    let _lock = NativeInstallLock::acquire(root, &receipt.operation_id)?;
    if receipt.status == TransactionStatus::Aborted {
        return Ok(receipt);
    }
    for target in &receipt.targets {
        reject_native_path(Path::new(&target.destination), "destination")?;
        reject_native_path(Path::new(&target.temp), "install temp")?;
        reject_native_path(Path::new(&target.backup), "install backup")?;
    }
    restore_native_targets_checked(&receipt.targets, &receipt.digest)?;
    let mut restored = receipt;
    restored.status = TransactionStatus::Aborted;
    for target in &mut restored.targets {
        target.phase = TargetPhase::Restored;
    }
    write_transaction_receipt(receipt_path, &restored)?;
    Ok(restored)
}

/// Reconcile durable native install/publish receipts after a process crash.
///
/// The scan is deliberately read-only until each `started` receipt has passed
/// strict validation.  Committed and aborted receipts are returned as facts;
/// only started transactions are rolled back through the same checked path as
/// an explicit rollback.  No receipt is silently ignored or rewritten.
pub fn native_reconcile_transactions(root: &Path) -> Result<Vec<TransactionReceipt>, PublishError> {
    let root = absolute_directory(root, "transaction root")?;
    let transaction_root = root.join(".mission-center-transactions");
    if !transaction_root.exists() {
        return Ok(Vec::new());
    }
    let transaction_root = absolute_directory(&transaction_root, "transaction directory")?;
    let mut paths = Vec::new();
    for entry in fs::read_dir(&transaction_root).map_err(native_io)? {
        let path = entry.map_err(native_io)?.path();
        reject_native_path(&path, "transaction entry")?;
        let name = path.file_name().and_then(|value| value.to_str());
        if path.extension().and_then(|value| value.to_str()) == Some("json") {
            paths.push(path);
        } else if name != Some(".lock") {
            return Err(PublishError::stable(
                ErrorCode::TransactionCorrupt,
                "transaction directory 含未識別殘留檔案，請先隔離後重試。",
            ));
        }
    }
    if paths.len() > MAX_TRANSACTION_RECEIPTS {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "transaction receipt 數量超過上限，請先隔離舊交易後重試。",
        ));
    }
    paths.sort();
    let mut receipts = Vec::with_capacity(paths.len());
    for path in paths {
        let receipt = read_transaction_receipt(&path)?.ok_or_else(|| {
            PublishError::stable(
                ErrorCode::TransactionCorrupt,
                "transaction receipt 在掃描期間消失，請保留現場後重試。",
            )
        })?;
        validate_native_receipt(&receipt, &path, &transaction_root)?;
        if receipt.status == TransactionStatus::Started {
            receipts.push(native_rollback_transaction(&path)?);
        } else {
            receipts.push(receipt);
        }
    }
    Ok(receipts)
}

fn validate_native_receipt(
    receipt: &TransactionReceipt,
    receipt_path: &Path,
    transaction_root: &Path,
) -> Result<(), PublishError> {
    if receipt.schema_version != SCHEMA_VERSION
        || receipt.operation_id.is_empty()
        || !sha256(&receipt.digest)
        || receipt.destination_count == 0
        || receipt.destination_count > MAX_TRANSACTION_TARGETS
        || receipt.destination_count != receipt.destinations.len()
        || receipt.destination_count != receipt.backups.len()
        || receipt.destination_count != receipt.targets.len()
    {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "transaction receipt 欄位不合法，請保留現場後重新 reconcile。",
        ));
    }
    validate_staging_operation_id(&receipt.operation_id)?;
    let expected_name = format!("{}.json", receipt.operation_id);
    if receipt_path.file_name().and_then(|value| value.to_str()) != Some(expected_name.as_str())
        || Path::new(&receipt.transaction_root) != transaction_root
    {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "receipt 檔名或 transactionRoot 與 reconcile root 不一致。",
        ));
    }
    let staging = Path::new(&receipt.staging);
    if !staging.is_absolute() {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "receipt staging 必須是絕對路徑。",
        ));
    }
    reject_native_path(staging, "receipt staging")?;
    for (index, target) in receipt.targets.iter().enumerate() {
        if receipt.destinations[index] != target.destination
            || receipt.backups[index] != target.backup
        {
            return Err(PublishError::stable(
                ErrorCode::TransactionCorrupt,
                "receipt destinations/backups 與 targets 不一致。",
            ));
        }
        for path in [&target.destination, &target.temp, &target.backup] {
            let path = Path::new(path);
            if !path.is_absolute() {
                return Err(PublishError::stable(
                    ErrorCode::TransactionCorrupt,
                    "receipt path 必須是絕對路徑。",
                ));
            }
            reject_native_path(path, "receipt target path")?;
        }
        if receipt.status == TransactionStatus::Committed && target.phase != TargetPhase::Swapped
            || receipt.status == TransactionStatus::Aborted && target.phase != TargetPhase::Restored
        {
            return Err(PublishError::stable(
                ErrorCode::TransactionCorrupt,
                "receipt status 與 target phase 不一致。",
            ));
        }
    }
    Ok(())
}

struct NativeInstallLock {
    path: PathBuf,
}

impl NativeInstallLock {
    fn acquire(root: &Path, operation_id: &str) -> Result<Self, PublishError> {
        let path = root.join(".lock");
        fs::create_dir(&path).map_err(|error| {
            if error.kind() == std::io::ErrorKind::AlreadyExists {
                PublishError::stable(
                    ErrorCode::TransactionConflict,
                    "install transaction 正由另一個 writer 使用。",
                )
            } else {
                native_io(error)
            }
        })?;
        let owner = path.join("owner");
        fs::write(
            &owner,
            format!(
                "{}:{}:{operation_id}",
                std::process::id(),
                unique_native_nonce()
            ),
        )
        .map_err(native_io)?;
        Ok(Self { path })
    }
}

impl Drop for NativeInstallLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(self.path.join("owner"));
        let _ = fs::remove_dir(&self.path);
    }
}

fn unique_native_nonce() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos())
        .unwrap_or_default()
}

fn native_io(error: std::io::Error) -> PublishError {
    PublishError {
        code: ErrorCode::Io,
        message: "檔案操作失敗".to_owned(),
        remediation: format!("請確認檔案權限、磁碟狀態與受控路徑後重試（{error}）。"),
    }
}

fn absolute_path(path: &Path, label: &str) -> Result<PathBuf, PublishError> {
    if !path.is_absolute()
        || path.as_os_str().is_empty()
        || path
            .components()
            .any(|component| matches!(component, Component::CurDir | Component::ParentDir))
    {
        return Err(PublishError::stable(
            ErrorCode::UnsafePath,
            &format!("{label} 必須是沒有 traversal 的絕對路徑。"),
        ));
    }
    Ok(path.to_path_buf())
}

fn absolute_directory(path: &Path, label: &str) -> Result<PathBuf, PublishError> {
    let path = absolute_path(path, label)?;
    let metadata = fs::symlink_metadata(&path)
        .map_err(|_| PublishError::stable(ErrorCode::NotFound, &format!("找不到 {label}。")))?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err(PublishError::stable(
            ErrorCode::UnsafePath,
            &format!("{label} 必須是非 symlink 目錄。"),
        ));
    }
    reject_native_path(&path, label)?;
    Ok(path)
}

fn ensure_native_directory(path: &Path) -> Result<(), PublishError> {
    if path.exists() {
        let metadata = fs::symlink_metadata(path).map_err(native_io)?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err(PublishError::stable(
                ErrorCode::UnsafePath,
                "目錄不可是 symlink 或非目錄檔案。",
            ));
        }
        reject_native_path(path, "directory")?;
        return Ok(());
    }
    fs::create_dir_all(path).map_err(native_io)?;
    reject_native_path(path, "directory")
}

fn reject_native_path(path: &Path, label: &str) -> Result<(), PublishError> {
    if path
        .components()
        .any(|component| matches!(component, Component::CurDir | Component::ParentDir))
    {
        return Err(PublishError::stable(
            ErrorCode::UnsafePath,
            &format!("{label} 含 traversal。"),
        ));
    }
    let mut current = PathBuf::new();
    for component in path.components() {
        current.push(component.as_os_str());
        if let Ok(metadata) = fs::symlink_metadata(&current) {
            if metadata.file_type().is_symlink() {
                return Err(PublishError::stable(
                    ErrorCode::UnsafePath,
                    &format!("{label} 不得包含 symlink/reparse point。"),
                ));
            }
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if metadata.file_attributes() & 0x400 != 0 {
                    return Err(PublishError::stable(
                        ErrorCode::UnsafePath,
                        &format!("{label} 不得包含 Windows reparse point。"),
                    ));
                }
            }
        }
    }
    Ok(())
}

fn load_frozen_directory(root: &Path) -> Result<FrozenPackage, PublishError> {
    let mut files = Vec::new();
    let mut total = 0u64;
    collect_frozen_files(root, root, 0, &mut files, &mut total)?;
    FrozenPackage::new(files)
}

fn collect_frozen_files(
    root: &Path,
    current: &Path,
    depth: usize,
    files: &mut Vec<FrozenFile>,
    total: &mut u64,
) -> Result<(), PublishError> {
    if depth > MAX_DEPTH {
        return Err(PublishError::stable(
            ErrorCode::UnsafePath,
            "package 目錄深度超過上限。",
        ));
    }
    reject_native_path(current, "package path")?;
    for entry in fs::read_dir(current).map_err(native_io)? {
        let path = entry.map_err(native_io)?.path();
        let metadata = fs::symlink_metadata(&path).map_err(native_io)?;
        if metadata.file_type().is_symlink() {
            return Err(PublishError::stable(
                ErrorCode::UnsafePath,
                "package 不得包含 symlink/reparse point。",
            ));
        }
        if metadata.is_dir() {
            collect_frozen_files(root, &path, depth + 1, files, total)?;
            continue;
        }
        if !metadata.is_file() {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "package 僅允許一般檔案。",
            ));
        }
        if files.len() >= MAX_FILES || metadata.len() > MAX_FILE_BYTES {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "package 檔案數量或單檔大小超過上限。",
            ));
        }
        *total = (*total).checked_add(metadata.len()).ok_or_else(|| {
            PublishError::stable(ErrorCode::InvalidManifest, "package 大小溢位。")
        })?;
        if *total > MAX_TOTAL_BYTES {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "package 總大小超過上限。",
            ));
        }
        let relative = path
            .strip_prefix(root)
            .map_err(|_| PublishError::stable(ErrorCode::UnsafePath, "package path 逃逸根目錄。"))?
            .to_string_lossy()
            .replace('\\', "/");
        let bytes = fs::read(&path).map_err(native_io)?;
        files.push(FrozenFile::new(&relative, bytes, native_executable(&path)));
    }
    Ok(())
}

fn native_executable(path: &Path) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        return fs::metadata(path)
            .map(|metadata| metadata.permissions().mode() & 0o111 != 0)
            .unwrap_or(false);
    }
    #[cfg(windows)]
    {
        return path
            .file_name()
            .and_then(|value| value.to_str())
            .is_some_and(|value| {
                value.eq_ignore_ascii_case("mission-center")
                    || path
                        .extension()
                        .and_then(|extension| extension.to_str())
                        .is_some_and(|extension| {
                            ["exe", "com", "bat", "cmd"]
                                .iter()
                                .any(|allowed| extension.eq_ignore_ascii_case(allowed))
                        })
            });
    }
    #[allow(unreachable_code)]
    false
}

fn copy_frozen_directory(package: &FrozenPackage, destination: &Path) -> Result<(), PublishError> {
    fs::create_dir(destination).map_err(native_io)?;
    for file in package.files() {
        let path = destination.join(
            file.relative_path
                .replace('/', std::path::MAIN_SEPARATOR_STR),
        );
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(native_io)?;
        }
        let mut handle = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)
            .map_err(native_io)?;
        handle.write_all(&file.bytes).map_err(native_io)?;
        handle.sync_all().map_err(native_io)?;
        #[cfg(unix)]
        if file.executable {
            use std::os::unix::fs::PermissionsExt;
            let mut permissions = handle.metadata().map_err(native_io)?.permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(&path, permissions).map_err(native_io)?;
        }
    }
    Ok(())
}

fn remove_native_temps(targets: &[TargetReceipt]) {
    for target in targets {
        let _ = remove_native_tree(Path::new(&target.temp));
    }
}

fn restore_native_targets(targets: &[TargetReceipt]) {
    for target in targets.iter().rev() {
        let destination = Path::new(&target.destination);
        let temp = Path::new(&target.temp);
        let backup = Path::new(&target.backup);
        if destination.exists() {
            let _ = remove_native_tree(destination);
        }
        if backup.exists() {
            let _ = fs::rename(backup, destination);
        }
        if temp.exists() {
            let _ = remove_native_tree(temp);
        }
    }
}

fn restore_native_targets_checked(
    targets: &[TargetReceipt],
    expected_digest: &str,
) -> Result<(), PublishError> {
    for target in targets {
        let destination = Path::new(&target.destination);
        if !destination.exists() {
            continue;
        }
        let current = load_frozen_directory(destination).map_err(|_| {
            PublishError::stable(
                ErrorCode::TransactionConflict,
                "destination 已被修改，拒絕無法驗證的 rollback。",
            )
        })?;
        if digest_frozen(current.files()) != expected_digest {
            return Err(PublishError::stable(
                ErrorCode::TransactionConflict,
                "destination digest 與 install receipt 不一致，拒絕覆寫外部變更。",
            ));
        }
    }
    restore_native_targets(targets);
    Ok(())
}

fn remove_native_tree(path: &Path) -> Result<(), PublishError> {
    if !path.exists() {
        return Ok(());
    }
    let metadata = fs::symlink_metadata(path).map_err(native_io)?;
    if metadata.file_type().is_symlink() {
        return Err(PublishError::stable(
            ErrorCode::UnsafePath,
            "拒絕刪除 symlink/reparse point。",
        ));
    }
    if metadata.is_dir() {
        fs::remove_dir_all(path).map_err(native_io)
    } else {
        fs::remove_file(path).map_err(native_io)
    }
}

fn validate_destinations(
    package: &Path,
    transaction_root: &Path,
    destinations: &[PathBuf],
) -> Result<(), PublishError> {
    let mut seen = HashSet::new();
    for destination in destinations {
        let destination = absolute_path(destination, "destination")?;
        reject_native_path(&destination, "destination")?;
        let parent = destination.parent().ok_or_else(|| {
            PublishError::stable(ErrorCode::UnsafePath, "destination 缺少父目錄。")
        })?;
        if parent.exists() {
            ensure_native_directory(parent)?;
        } else {
            reject_native_path(parent, "destination parent")?;
        }
        if destination.starts_with(package)
            || package.starts_with(&destination)
            || destination.starts_with(transaction_root)
            || transaction_root.starts_with(&destination)
        {
            return Err(PublishError::stable(
                ErrorCode::UnsafePath,
                "destination 不可與 package 或 transaction root 重疊。",
            ));
        }
        if !seen.insert(destination) {
            return Err(PublishError::stable(
                ErrorCode::UnsafePath,
                "canonical 與 derived destination 不可重複。",
            ));
        }
    }
    Ok(())
}

fn read_transaction_receipt(path: &Path) -> Result<Option<TransactionReceipt>, PublishError> {
    if !path.exists() {
        return Ok(None);
    }
    let bytes = fs::read(path).map_err(native_io)?;
    if bytes.len() > MAX_FILE_BYTES as usize {
        return Err(PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "transaction receipt 超過大小上限。",
        ));
    }
    serde_json::from_slice(&bytes).map(Some).map_err(|_| {
        PublishError::stable(
            ErrorCode::TransactionCorrupt,
            "transaction receipt JSON 損壞。",
        )
    })
}

fn write_transaction_receipt(
    path: &Path,
    receipt: &TransactionReceipt,
) -> Result<(), PublishError> {
    let bytes = serde_json::to_vec(receipt)
        .map_err(|_| PublishError::stable(ErrorCode::Io, "transaction receipt 序列化失敗。"))?;
    let temp = path.with_extension(format!("json.{}.tmp", unique_native_nonce()));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(native_io)?;
    file.write_all(&bytes).map_err(native_io)?;
    file.sync_all().map_err(native_io)?;
    fs::rename(&temp, path).map_err(native_io)
}

#[cfg(any())]
mod filesystem_legacy {
    use super::*;

    fn plugin_manifest(root: &Path, expected_version: &str) -> Result<(), PublishError> {
        let v: Value = serde_json::from_slice(&read_bounded(&root.join(PLUGIN_MANIFEST_FILE))?)
            .map_err(|_| {
                PublishError::stable(
                    ErrorCode::InvalidManifest,
                    "plugin.json JSON 損壞，請用 plugin-creator 驗證。",
                )
            })?;
        let o = v.as_object().ok_or_else(|| {
            PublishError::stable(
                ErrorCode::InvalidManifest,
                "plugin.json 必須是 JSON object。",
            )
        })?;
        if o.get("name").and_then(Value::as_str) != Some("mission-center") {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "plugin.json name 必須是 mission-center。",
            ));
        }
        if o.get("version")
            .and_then(Value::as_str)
            .is_none_or(|s| semver(s).is_err())
        {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "plugin.json version 不是合法 SemVer。",
            ));
        }
        if o.get("version").and_then(Value::as_str) != Some(expected_version) {
            return Err(PublishError::stable(
                ErrorCode::VersionMismatch,
                "plugin.json 與平台 manifest 版本不一致，請重新打包同一版本。",
            ));
        }
        if o.contains_key("hooks") {
            return Err(PublishError::stable(
                ErrorCode::InvalidManifest,
                "plugin.json 不得內嵌 hooks，請保留 companion 結構。",
            ));
        }
        Ok(())
    }
    fn scan(root: &Path, cur: &Path) -> Result<(), PublishError> {
        let mut files = 0usize;
        let mut total = 0u64;
        scan_inner(root, cur, 0, &mut files, &mut total)
    }
    fn scan_inner(
        root: &Path,
        cur: &Path,
        depth: usize,
        files: &mut usize,
        total: &mut u64,
    ) -> Result<(), PublishError> {
        if depth > MAX_DEPTH {
            return Err(PublishError::stable(
                ErrorCode::UnsafePath,
                "套件目錄深度超過上限，請整理 staged package。",
            ));
        }
        for e in fs::read_dir(cur).map_err(io_error)? {
            let p = e.map_err(io_error)?.path();
            let rel = p
                .strip_prefix(root)
                .map_err(|_| PublishError::stable(ErrorCode::UnsafePath, "檔案逃逸來源根目錄。"))?;
            reject(&p, "套件檔案")?;
            let allowlisted = python_allowlist(rel);
            for c in rel.components() {
                if let Component::Normal(x) = c {
                    let s = x.to_string_lossy().to_ascii_lowercase();
                    if python_path_component(&s) && !allowlisted {
                        return Err(PublishError::stable(
                            ErrorCode::PythonRuntime,
                            "staged package 正式 runtime 路徑不得含 Python 檔案。",
                        ));
                    }
                }
            }
            if p.is_dir() {
                scan_inner(root, &p, depth + 1, files, total)?
            } else if p.is_file() {
                let m = fs::metadata(&p).map_err(io_error)?;
                *files += 1;
                *total = (*total).saturating_add(m.len());
                if *files > MAX_FILES || *total > MAX_TOTAL_BYTES {
                    return Err(PublishError::stable(
                        ErrorCode::InvalidManifest,
                        "套件檔案數量或總大小超過上限，請提供受控 release package。",
                    ));
                }
                if m.len() <= MAX_FILE_BYTES {
                    if allowlisted && executable(&p) {
                        return Err(PublishError::stable(
                            ErrorCode::PythonRuntime,
                            "docs/compat/python-oracle 檔案不可具備 executable 權限。",
                        ));
                    }
                    let t = String::from_utf8_lossy(&fs::read(&p).map_err(io_error)?)
                        .to_ascii_lowercase();
                    if !allowlisted && python_invocation(&t) {
                        return Err(PublishError::stable(
                            ErrorCode::PythonRuntime,
                            "staged package 不得含 Python invocation/fallback。",
                        ));
                    }
                }
            }
        }
        Ok(())
    }
    fn python_allowlist(path: &Path) -> bool {
        let parts = path
            .components()
            .filter_map(|component| match component {
                Component::Normal(value) => Some(value.to_string_lossy().to_ascii_lowercase()),
                _ => None,
            })
            .collect::<Vec<_>>();
        parts
            .first()
            .is_some_and(|part| part == "docs" || part == "compat" || part == "python-oracle")
    }
    fn python_invocation(text: &str) -> bool {
        text.lines().any(|line| {
            let line = line.trim_start();
            if line.starts_with("#!") && line.contains("python") {
                return true;
            }
            let normalized = line.split_whitespace().collect::<Vec<_>>().join(" ");
            let words = normalized.split(' ').collect::<Vec<_>>();
            words.iter().enumerate().any(|(index, word)| {
                let token = word.trim_matches(|c: char| "&;|$(){}<>\"'".contains(c));
                if python_command_token(token)
                    && (index == 0
                        || words[index - 1]
                            .trim_matches(|c: char| "&;|$(){}<>\"'".contains(c))
                            .is_empty())
                {
                    return true;
                }
                if index > 0
                    && (words[index - 1] == "env"
                        || words[index - 1].ends_with("&&")
                        || words[index - 1].ends_with(';')
                        || words[index - 1].ends_with('|')
                        || words[index - 1].ends_with("$(")
                        || words[index - 1] == "exec")
                    && python_command_token(token)
                {
                    return true;
                }
                index == 0
                    && token.eq_ignore_ascii_case("py")
                    && words
                        .get(index + 1)
                        .is_some_and(|flag| flag.starts_with("-3"))
            })
        })
    }
    fn python_path_component(path: &str) -> bool {
        let lower = path.to_ascii_lowercase();
        lower.ends_with(".py") || lower.ends_with(".pyc") || python_command_token(&lower)
    }
    fn python_command_token(token: &str) -> bool {
        let lower = token.to_ascii_lowercase();
        let base = lower.rsplit(['/', '\\']).next().unwrap_or(&lower);
        if matches!(base, "python" | "python.exe" | "python3" | "python3.exe") {
            return true;
        }
        base.strip_prefix("python3.")
            .map(|suffix| suffix.strip_suffix(".exe").unwrap_or(suffix))
            .is_some_and(|suffix| !suffix.is_empty() && suffix.bytes().all(|c| c.is_ascii_digit()))
    }
    fn destinations(ds: &[PathBuf]) -> Result<(), PublishError> {
        let mut s = HashSet::new();
        for d in ds {
            reject(d, "目的地")?;
            let c = d.canonicalize().unwrap_or_else(|_| d.clone());
            if !s.insert(c) {
                return Err(PublishError::stable(
                    ErrorCode::UnsafePath,
                    "canonical 與 derived 目的地不可重複。",
                ));
            }
        }
        Ok(())
    }
    fn reject(p: &Path, label: &str) -> Result<(), PublishError> {
        if p.as_os_str().is_empty()
            || p.components()
                .any(|c| matches!(c, Component::ParentDir | Component::CurDir))
        {
            return Err(PublishError::stable(
                ErrorCode::UnsafePath,
                "路徑含 traversal；請使用受控的絕對路徑。",
            ));
        }
        let mut c = if p.is_absolute() {
            PathBuf::from(p.components().next().unwrap().as_os_str())
        } else {
            std::env::current_dir().map_err(io_error)?
        };
        for x in p.components() {
            if matches!(x, Component::RootDir | Component::Prefix(_)) {
                continue;
            }
            c.push(x.as_os_str());
            if let Ok(m) = fs::symlink_metadata(&c)
                && m.file_type().is_symlink()
            {
                return Err(PublishError::stable(
                    ErrorCode::UnsafePath,
                    &format!("{label} 不得包含 symlink/reparse point。"),
                ));
            }
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if let Ok(m) = fs::symlink_metadata(&c)
                    && m.file_attributes() & 0x400 != 0
                {
                    return Err(PublishError::stable(
                        ErrorCode::UnsafePath,
                        "Windows reparse point 不受支援，已 fail-closed。",
                    ));
                }
            }
        }
        Ok(())
    }
    fn rel(s: &str, label: &str) -> Result<(), PublishError> {
        let p = Path::new(s);
        if s.is_empty()
            || p.is_absolute()
            || s.contains(':')
            || p.components()
                .any(|c| matches!(c, Component::ParentDir | Component::CurDir))
        {
            return Err(PublishError::stable(
                ErrorCode::UnsafePath,
                &format!("{label} 必須是安全相對路徑。"),
            ));
        }
        Ok(())
    }
}

fn python_invocation(text: &str) -> bool {
    text.lines().any(|line| {
        let trimmed = line.trim_start();
        if trimmed.starts_with("#!") && trimmed.to_ascii_lowercase().contains("python") {
            return true;
        }
        let tokens = shell_tokens(trimmed);
        let mut start = 0;
        for (index, token) in tokens.iter().enumerate() {
            if matches!(token.as_str(), ";" | "|" | "&") {
                if python_command_segment(&tokens[start..index]) {
                    return true;
                }
                start = index + 1;
            }
        }
        if python_command_segment(&tokens[start..]) {
            return true;
        }
        tokens.iter().enumerate().any(|(index, token)| {
            matches!(token.as_str(), "$" | "(")
                && python_command_segment(tokens.get(index + 1..).unwrap_or_default())
        })
    })
}
fn shell_tokens(line: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    for c in line.chars() {
        if c.is_whitespace() || ";|&()<>".contains(c) {
            if !current.is_empty() {
                tokens.push(std::mem::take(&mut current));
            }
            if ";|&()<>".contains(c) {
                tokens.push(c.to_string());
            }
        } else {
            current.push(c);
        }
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    tokens
}
fn python_command_segment(tokens: &[String]) -> bool {
    let mut i = 0;
    while i < tokens.len() {
        let token = tokens[i].to_ascii_lowercase();
        if matches!(
            token.as_str(),
            ";" | "|" | "&" | "$" | "(" | ")" | "then" | "do" | "else"
        ) {
            i += 1;
            continue;
        }
        if token == "if" {
            i += 1;
            continue;
        }
        if matches!(token.as_str(), "command" | "exec" | "nice") {
            i += 1;
            while i < tokens.len() && tokens[i].starts_with('-') {
                let option = tokens[i].to_ascii_lowercase();
                i += 1;
                if token == "nice" && option == "-n" && i < tokens.len() {
                    i += 1;
                }
            }
            continue;
        }
        if token == "sudo" {
            i += 1;
            while i < tokens.len() && tokens[i].starts_with('-') {
                let option = tokens[i].to_ascii_lowercase();
                i += 1;
                if matches!(
                    option.as_str(),
                    "-u" | "--user" | "-g" | "--group" | "-c" | "--chdir"
                ) && i < tokens.len()
                {
                    i += 1;
                }
            }
            continue;
        }
        if token == "env" {
            i += 1;
            while i < tokens.len() && (tokens[i].starts_with('-') || tokens[i].contains('=')) {
                let option = tokens[i].to_ascii_lowercase();
                i += 1;
                if matches!(option.as_str(), "-u" | "--unset" | "-c" | "--chdir")
                    && i < tokens.len()
                {
                    i += 1;
                }
            }
            continue;
        }
        if python_command_token(&token) {
            return true;
        }
        if token == "py" && tokens.get(i + 1).is_some_and(|flag| flag.starts_with("-3")) {
            return true;
        }
        return false;
    }
    false
}
fn python_command_token(token: &str) -> bool {
    let lower = token.trim_start_matches('@').to_ascii_lowercase();
    let base = lower.rsplit(['/', '\\']).next().unwrap_or(&lower);
    if matches!(base, "python" | "python.exe" | "python3" | "python3.exe") {
        return true;
    }
    base.strip_prefix("python3.")
        .map(|suffix| suffix.strip_suffix(".exe").unwrap_or(suffix))
        .is_some_and(|suffix| !suffix.is_empty() && suffix.bytes().all(|c| c.is_ascii_digit()))
}

fn identity(b: &[u8], p: Platform) -> Result<(), PublishError> {
    let ok = match p {
        Platform::WindowsX86_64 => pe(b) == Some(0x8664),
        Platform::LinuxX86_64 => elf(b) == Some(62) && b.get(4) == Some(&2) && b.get(5) == Some(&1),
        Platform::MacosX86_64 => macho(b) == Some(0x01000007),
        Platform::MacosAarch64 => macho(b) == Some(0x0100000c),
    };
    if !ok {
        Err(PublishError::stable(
            ErrorCode::WrongPlatform,
            "執行檔 magic/架構與宣告平台不符，請提供正確四平台 artifact。",
        ))
    } else {
        Ok(())
    }
}
fn elf(b: &[u8]) -> Option<u16> {
    if b.get(0..4) != Some(b"\x7fELF") {
        return None;
    }
    Some(u16::from_le_bytes([*b.get(18)?, *b.get(19)?]))
}
fn pe(b: &[u8]) -> Option<u16> {
    if b.get(0..2) != Some(b"MZ") {
        return None;
    }
    let o = u32::from_le_bytes([*b.get(60)?, *b.get(61)?, *b.get(62)?, *b.get(63)?]) as usize;
    if b.get(o..o + 4) != Some(b"PE\0\0") {
        return None;
    }
    Some(u16::from_le_bytes([*b.get(o + 4)?, *b.get(o + 5)?]))
}
fn macho(b: &[u8]) -> Option<u32> {
    let m = b.get(0..4)?;
    let le = m == b"\xcf\xfa\xed\xfe";
    let be = m == b"\xfe\xed\xfa\xcf";
    if !le && !be {
        return None;
    }
    let x = [*b.get(4)?, *b.get(5)?, *b.get(6)?, *b.get(7)?];
    Some(if le {
        u32::from_le_bytes(x)
    } else {
        u32::from_be_bytes(x)
    })
}
#[cfg(any())]
fn executable(p: &Path) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        return fs::metadata(p)
            .map(|m| m.permissions().mode() & 0o111 != 0)
            .unwrap_or(false);
    }
    #[cfg(windows)]
    {
        p.extension().and_then(|x| x.to_str()).is_some_and(|x| {
            ["exe", "com", "bat", "cmd", "ps1"]
                .iter()
                .any(|allowed| x.eq_ignore_ascii_case(allowed))
        })
    }
    #[cfg(not(any(unix, windows)))]
    {
        false
    }
}
#[cfg(any())]
fn read_bounded(p: &Path) -> Result<Vec<u8>, PublishError> {
    let m = fs::metadata(p).map_err(|_| {
        PublishError::stable(
            ErrorCode::NotFound,
            "找不到必要 manifest，請確認 staged package 完整。",
        )
    })?;
    if m.len() > MAX_FILE_BYTES {
        return Err(PublishError::stable(
            ErrorCode::InvalidManifest,
            "manifest 超過大小上限。",
        ));
    }
    let mut f = File::open(p).map_err(io_error)?;
    let mut b = Vec::new();
    f.read_to_end(&mut b).map_err(io_error)?;
    Ok(b)
}
#[cfg(any())]
fn digest_tree(r: &Path) -> Result<String, PublishError> {
    fn rec(
        r: &Path,
        c: &Path,
        depth: usize,
        o: &mut Vec<(String, PathBuf, u64)>,
        total: &mut u64,
    ) -> Result<(), PublishError> {
        if depth > MAX_DEPTH {
            return Err(PublishError::stable(
                ErrorCode::UnsafePath,
                "套件目錄深度超過上限，請整理 staged package。",
            ));
        }
        for e in fs::read_dir(c).map_err(io_error)? {
            let p = e.map_err(io_error)?.path();
            if p.is_dir() {
                rec(r, &p, depth + 1, o, total)?
            } else {
                let metadata = fs::metadata(&p).map_err(io_error)?;
                if o.len() >= MAX_FILES
                    || metadata.len() > MAX_FILE_BYTES
                    || total.saturating_add(metadata.len()) > MAX_TOTAL_BYTES
                {
                    return Err(PublishError::stable(
                        ErrorCode::InvalidManifest,
                        "套件檔案數量或總大小超過上限，請提供受控 release package。",
                    ));
                }
                *total += metadata.len();
                o.push((
                    p.strip_prefix(r)
                        .map_err(|_| {
                            PublishError::stable(ErrorCode::UnsafePath, "檔案逃逸來源根目錄。")
                        })?
                        .to_string_lossy()
                        .replace('\\', "/"),
                    p,
                    metadata.len(),
                ))
            }
        }
        Ok(())
    }
    let mut v = Vec::new();
    let mut total = 0;
    rec(r, r, 0, &mut v, &mut total)?;
    v.sort_by(|a, b| a.0.cmp(&b.0));
    let mut b = Vec::new();
    let mut chunk = [0u8; 64 * 1024];
    for (n, path, length) in v {
        b.extend_from_slice(&(n.len() as u64).to_be_bytes());
        b.extend_from_slice(n.as_bytes());
        b.extend_from_slice(&length.to_be_bytes());
        let mut file = File::open(path).map_err(io_error)?;
        loop {
            let read = file.read(&mut chunk).map_err(io_error)?;
            if read == 0 {
                break;
            }
            b.extend_from_slice(&chunk[..read]);
        }
    }
    Ok(sha256_digest(&b))
}
#[cfg(any())]
fn within_root(root: &Path, child: &Path) -> bool {
    child.is_absolute() && root.is_absolute() && child.strip_prefix(root).is_ok()
}
#[cfg(any())]
fn path_overlap(left: &Path, right: &Path) -> bool {
    let normalize = |path: &Path| {
        if path.is_absolute() {
            path.to_path_buf()
        } else {
            std::env::current_dir().unwrap_or_default().join(path)
        }
    };
    let left = normalize(left);
    let right = normalize(right);
    left.starts_with(&right) || right.starts_with(&left)
}
#[cfg(any())]
fn io_error(e: std::io::Error) -> PublishError {
    let _ = e;
    PublishError {
        code: ErrorCode::Io,
        message: "檔案操作失敗".into(),
        remediation: "請確認檔案權限、磁碟狀態與受控路徑後重試。".into(),
    }
}
fn sha256(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|c| c.is_ascii_hexdigit())
}
fn semver(s: &str) -> Result<(), ()> {
    if s.is_empty() || s.len() > 256 || !s.is_ascii() {
        return Err(());
    }
    let (without_build, build) = match s.split_once('+') {
        Some((core, build)) => (core, Some(build)),
        None => (s, None),
    };
    if let Some(build) = build
        && (build.is_empty()
            || build.split('.').any(|id| {
                id.is_empty() || !id.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-')
            }))
    {
        return Err(());
    }
    let (core, pre) = match without_build.split_once('-') {
        Some((core, pre)) => (core, Some(pre)),
        None => (without_build, None),
    };
    let numbers = core.split('.').collect::<Vec<_>>();
    if numbers.len() != 3
        || numbers.iter().any(|id| {
            id.is_empty()
                || (id.len() > 1 && id.starts_with('0'))
                || !id.bytes().all(|c| c.is_ascii_digit())
        })
    {
        return Err(());
    }
    if let Some(pre) = pre
        && (pre.is_empty()
            || pre.split('.').any(|id| {
                id.is_empty()
                    || !id.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-')
                    || (id.bytes().all(|c| c.is_ascii_digit())
                        && id.len() > 1
                        && id.starts_with('0'))
            }))
    {
        return Err(());
    }
    Ok(())
}

// Wave 3 evidence-envelope compatibility API.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ScopeError {
    Empty,
    TooMany,
    Duplicate(String),
    InvalidLocator(String),
}
impl fmt::Display for ScopeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Empty => f.write_str("scope must not be empty"),
            Self::TooMany => f.write_str("scope exceeds 64 locators"),
            Self::Duplicate(x) => write!(f, "scope contains duplicate locator: {x}"),
            Self::InvalidLocator(x) => write!(f, "scope locator is invalid: {x}"),
        }
    }
}
pub fn scope_digest(s: &[u8]) -> String {
    let mut b = b"mission-center-evidence-scope-v1\0".to_vec();
    b.extend(s);
    sha256_digest(&b)
}
pub fn scope_digest_files(f: &[(&str, &[u8])]) -> String {
    let mut v = f.to_vec();
    v.sort_by(|a, b| a.0.cmp(b.0));
    let mut d = b"mission-center-evidence-scope-v1\0".to_vec();
    for (n, x) in v {
        d.extend_from_slice(&(n.len() as u32).to_be_bytes());
        d.extend(n.as_bytes());
        d.extend_from_slice(&(x.len() as u64).to_be_bytes());
        d.extend(x)
    }
    sha256_digest(&d)
}
pub fn validate_scope(v: &[&str]) -> Result<(), ScopeError> {
    if v.is_empty() {
        return Err(ScopeError::Empty);
    }
    if v.len() > 64 {
        return Err(ScopeError::TooMany);
    }
    let mut s = HashSet::new();
    for x in v {
        let p = Path::new(x);
        if x.is_empty()
            || x.contains("://")
            || p.is_absolute()
            || x.len() >= 2 && x.as_bytes()[1] == b':'
            || x.split(&['/', '\\'][..]).any(|z| z == "..")
        {
            return Err(ScopeError::InvalidLocator((*x).into()));
        }
        if !s.insert(*x) {
            return Err(ScopeError::Duplicate((*x).into()));
        }
    }
    Ok(())
}
pub fn scope_digest_checked(f: &[(&str, &[u8])]) -> Result<String, ScopeError> {
    validate_scope(&f.iter().map(|x| x.0).collect::<Vec<_>>())?;
    Ok(scope_digest_files(f))
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvidenceEnvelope {
    pub envelope_id: String,
    pub task_id: String,
    pub check_id: String,
    pub scope: Vec<String>,
    pub scope_digest: String,
    pub result: String,
    pub status: String,
    pub artifact_locators: Vec<String>,
    pub recorded_at: String,
}
impl EvidenceEnvelope {
    pub fn new(t: impl Into<String>, c: impl Into<String>, s: &[u8]) -> Self {
        let t = t.into();
        Self {
            envelope_id: format!("env-{t}"),
            task_id: t,
            check_id: c.into(),
            scope: vec!["inline".into()],
            scope_digest: scope_digest(s),
            result: "unknown".into(),
            status: "current".into(),
            artifact_locators: vec!["inline".into()],
            recorded_at: "1970-01-01T00:00:00Z".into(),
        }
    }
    pub fn json(&self) -> String {
        format!(
            "{{\"schemaVersion\":\"{SCHEMA_VERSION}\",\"artifactType\":\"evidence-envelope\",\"envelopeId\":\"{}\",\"taskId\":\"{}\",\"checkId\":\"{}\",\"scope\":[{}],\"scopeDigest\":\"{}\",\"result\":\"{}\",\"status\":\"{}\",\"artifactLocators\":[{}],\"recordedAt\":\"{}\"}}",
            escape(&self.envelope_id),
            escape(&self.task_id),
            escape(&self.check_id),
            self.scope
                .iter()
                .map(|v| format!("\"{}\"", escape(v)))
                .collect::<Vec<_>>()
                .join(","),
            self.scope_digest,
            escape(&self.result),
            escape(&self.status),
            self.artifact_locators
                .iter()
                .map(|v| format!("\"{}\"", escape(v)))
                .collect::<Vec<_>>()
                .join(","),
            escape(&self.recorded_at)
        )
    }
}
fn escape(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    for character in value.chars() {
        match character {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            character if character <= '\u{1f}' => {
                let _ = write!(out, "\\u{:04x}", character as u32);
            }
            character => out.push(character),
        }
    }
    out
}
pub fn publish(write_requested: bool) -> Result<&'static str, &'static str> {
    if write_requested {
        Err("mutationSupported:false; native handle adapter required")
    } else {
        Ok("dry-run")
    }
}

#[cfg(test)]
mod tests {
    use super::{ErrorCode, PlatformManifest, plugin_manifest_bytes};

    #[test]
    fn nested_plugin_manifest_duplicate_and_unknown_fields_are_rejected() {
        let duplicate = br#"{"name":"mission-center","name":"mission-center","version":"0.5.1"}"#;
        let error = plugin_manifest_bytes(duplicate, "0.5.1").unwrap_err();
        assert_eq!(error.code(), ErrorCode::InvalidManifest);

        let unknown = br#"{"name":"mission-center","version":"0.5.1","interface":{"displayName":"x","unknown":true}}"#;
        let error = plugin_manifest_bytes(unknown, "0.5.1").unwrap_err();
        assert_eq!(error.code(), ErrorCode::InvalidManifest);

        let platform = br#"{"schemaVersion":"1.0","pluginName":"mission-center","version":"0.5.1","artifacts":[{"platform":"windows-x86_64","platform":"linux-x86_64","path":"bin/x","sha256":"0000000000000000000000000000000000000000000000000000000000000000","version":"0.5.1","os":"linux","arch":"x86_64","executable":"bin/x"}]}"#;
        let error = PlatformManifest::from_json(platform).unwrap_err();
        assert_eq!(error.code(), ErrorCode::InvalidManifest);
    }
}
