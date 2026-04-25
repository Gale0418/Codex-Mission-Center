$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$target = Join-Path $codexHome "skills\mission-center"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
if (Test-Path -LiteralPath $target) {
  Remove-Item -LiteralPath $target -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $root "skills\mission-center") -Destination $target -Recurse -Force

Write-Output "Installed mission-center skill to $target"
Write-Output "Restart Codex to refresh the skill list."
