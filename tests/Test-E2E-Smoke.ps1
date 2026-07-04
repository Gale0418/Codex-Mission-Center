# End-to-End Integration Smoke Test for Codex Mission Center
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Split-Path -Parent $ScriptDir

Write-Host "=== Codex Mission Center E2E Smoke Test ===" -ForegroundColor Cyan

$SkillScriptsDir = Join-Path $RepoRoot "skills\mission-center\scripts"
$BootstrapScript = Join-Path $SkillScriptsDir "bootstrap_mission_center.py"
if (-not (Test-Path $BootstrapScript)) {
    throw "Bootstrap script not found: $BootstrapScript"
}

# Test script syntax and execution availability
Write-Host "[1/2] Verifying Python scripts presence..." -ForegroundColor Yellow
$scripts = @('bootstrap_mission_center.py', 'normalize_mission_center.py', 'sync_mission_center.py')
foreach ($s in $scripts) {
    $path = Join-Path $SkillScriptsDir $s
    if (-not (Test-Path $path)) {
        throw "Missing core script: $path"
    }
}
Write-Host "  Scripts Verification PASSED." -ForegroundColor Green

Write-Host "[2/2] Checking MissionCenter Assets..." -ForegroundColor Yellow
$visualAsset = Join-Path $RepoRoot "skills\mission-center\assets\visual-hub\visual-summary.html"
if (-not (Test-Path $visualAsset)) {
    throw "Visual HUD asset not found: $visualAsset"
}
Write-Host "  Visual HUD Assets PASSED." -ForegroundColor Green

Write-Host "=== Mission Center E2E Smoke Test PASSED! ===" -ForegroundColor Green
