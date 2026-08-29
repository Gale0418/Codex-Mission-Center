#!/usr/bin/env pwsh
# Mission Center Windows platform selector.
#
# This is a selector, not an installer. It only reads the frozen package
# manifests and replaces itself with an already-present, verified Rust binary.
# Any missing or inconsistent input fails closed; no alternate runtime exists.

$ErrorActionPreference = 'Stop'

function Fail-Selector([string]$Message) {
    [Console]::Error.WriteLine("mission-center selector: $Message")
    exit 1
}

$selectorRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$manifestPath = Join-Path $selectorRoot 'platform-manifest.json'
$pluginManifestPath = Join-Path $selectorRoot '.codex-plugin\plugin.json'

if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    Fail-Selector 'platform manifest is missing'
}
if (-not (Test-Path -LiteralPath $pluginManifestPath -PathType Leaf)) {
    Fail-Selector 'plugin manifest is missing'
}

try {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $pluginManifest = Get-Content -LiteralPath $pluginManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Fail-Selector 'manifest JSON is invalid'
}

if ($null -eq $manifest -or $manifest -is [array] -or $manifest.schemaVersion -ne '1.0' -or
    $manifest.pluginName -ne 'mission-center' -or $manifest.version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$') {
    Fail-Selector 'invalid platform manifest'
}
if ($null -eq $pluginManifest -or $pluginManifest -is [array] -or
    $pluginManifest.name -ne 'mission-center' -or $pluginManifest.version -ne $manifest.version) {
    Fail-Selector 'plugin/manifest version mismatch'
}
if ($env:MISSION_CENTER_VERSION -and $env:MISSION_CENTER_VERSION -ne $manifest.version) {
    Fail-Selector 'requested version mismatch'
}

$expectedPlatforms = @('linux-x86_64', 'macos-aarch64', 'macos-x86_64', 'windows-x86_64')
if ($null -eq $manifest.artifacts -or $manifest.artifacts.Count -ne 4) {
    Fail-Selector 'platform manifest must contain four artifacts'
}
$actualPlatforms = @($manifest.artifacts | ForEach-Object { [string]$_.platform } | Sort-Object)
if (($actualPlatforms -join '|') -ne ($expectedPlatforms -join '|')) {
    Fail-Selector 'platform manifest has an invalid platform set'
}

# The Windows hook is intentionally restricted to the release pair that this
# command can execute. Other host pairs remain in the manifest for package
# completeness but must never be selected by this process.
if ($env:PROCESSOR_ARCHITECTURE -notin @('AMD64', 'x86_64')) {
    Fail-Selector 'unsupported Windows host architecture'
}
$selectorPlatform = 'windows-x86_64'
$artifact = @($manifest.artifacts | Where-Object { $_.platform -eq $selectorPlatform })
if ($artifact.Count -ne 1) {
    Fail-Selector 'selected platform artifact is missing'
}
$artifact = $artifact[0]
$expectedPath = 'bin/windows-x86_64/mission-center.exe'
if ($artifact.version -ne $manifest.version -or $artifact.os -ne 'windows' -or
    $artifact.arch -ne 'x86_64' -or $artifact.path -ne $expectedPath -or
    $artifact.executable -ne $expectedPath -or
    [string]$artifact.sha256 -notmatch '^[0-9a-fA-F]{64}$') {
    Fail-Selector 'selected platform artifact is invalid'
}

$binary = Join-Path $selectorRoot ($artifact.path -replace '/', '\')
if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) {
    Fail-Selector 'selected binary is missing'
}
try {
    $actualSha256 = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()
} catch {
    Fail-Selector 'selected binary cannot be hashed'
}
if ($actualSha256 -ne ([string]$artifact.sha256).ToLowerInvariant()) {
    Fail-Selector 'selected binary checksum mismatch'
}

& $binary @args
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
exit 0
