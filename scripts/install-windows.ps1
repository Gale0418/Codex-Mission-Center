$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$personalSkill = if ($env:MISSION_CENTER_PERSONAL_SKILL) {
  $env:MISSION_CENTER_PERSONAL_SKILL
} else {
  Join-Path $codexHome "skills\mission-center"
}
$marketplacePlugin = if ($env:MISSION_CENTER_MARKETPLACE_PLUGIN) {
  $env:MISSION_CENTER_MARKETPLACE_PLUGIN
} else {
  Join-Path $codexHome "local-marketplaces\mission-center\plugins\mission-center"
}
$mode = if ($env:MISSION_CENTER_PUBLISH_MODE) { $env:MISSION_CENTER_PUBLISH_MODE } else { "--write" }
if ($mode -notin @("--dry-run", "--write", "--verify")) {
  throw "MISSION_CENTER_PUBLISH_MODE must be --dry-run, --write, or --verify"
}

& python (Join-Path $PSScriptRoot "publish_local.py") `
  --repo $root `
  --personal-skill $personalSkill `
  --marketplace-plugin $marketplacePlugin `
  $mode `
  $(if ($mode -eq "--write") { "--register" })
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

switch ($mode) {
  "--dry-run" { Write-Output "Dry-run completed. No files were modified." }
  "--write" { Write-Output "Published Mission Center to personal Skill and local marketplace plugin, then refreshed Codex plugin registration." }
  "--verify" { Write-Output "Verification completed successfully." }
}
