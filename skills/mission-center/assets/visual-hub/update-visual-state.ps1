param(
  [string]$Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [Parameter(Mandatory = $true)]
  [string]$SkillRoot,
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$syncScript = Join-Path $SkillRoot "scripts\sync_mission_center.py"
if (-not (Test-Path -LiteralPath $syncScript -PathType Leaf)) {
  throw "MissionCenter sync script not found: $syncScript"
}

& $Python $syncScript $Workspace
if ($LASTEXITCODE -ne 0) {
  throw "MissionCenter task sync failed with exit code $LASTEXITCODE"
}
