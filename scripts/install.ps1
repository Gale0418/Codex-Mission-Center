<#
.SYNOPSIS
    Compatibility installer that delegates to publish_local.py.
#>

[CmdletBinding()]
param(
    [string]$TargetSkillsDir = "",
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Split-Path -Parent $ScriptDir

$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$PersonalSkill = if ($TargetSkillsDir) { $TargetSkillsDir } elseif ($env:MISSION_CENTER_PERSONAL_SKILL) { $env:MISSION_CENTER_PERSONAL_SKILL } else { Join-Path $CodexHome 'skills\mission-center' }
$MarketplacePlugin = if ($env:MISSION_CENTER_MARKETPLACE_PLUGIN) { $env:MISSION_CENTER_MARKETPLACE_PLUGIN } else { Join-Path $CodexHome 'local-marketplaces\mission-center\plugins\mission-center' }
$Arguments = @((Join-Path $ScriptDir 'publish_local.py'), '--repo', $RepoRoot, '--personal-skill', $PersonalSkill, '--marketplace-plugin', $MarketplacePlugin, '--write')
if ($env:MISSION_CENTER_PUBLISH_REGISTER -ne '0') { $Arguments += '--register' }
& python @Arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'Codex Mission Center installed successfully!' -ForegroundColor Green
