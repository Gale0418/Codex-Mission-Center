$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$pluginName = "mission-center"
$pluginRoot = Join-Path $env:USERPROFILE "plugins\$pluginName"
$marketplaceDir = Join-Path $env:USERPROFILE ".agents\plugins"
$marketplacePath = Join-Path $marketplaceDir "marketplace.json"

New-Item -ItemType Directory -Force -Path $pluginRoot | Out-Null
foreach ($item in @(".codex-plugin", "assets", "skills", "scripts")) {
  $source = Join-Path $root $item
  $target = Join-Path $pluginRoot $item
  if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
  }
  Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
}

foreach ($file in @("README.md", "LICENSE", "NOTICE.md")) {
  Copy-Item -LiteralPath (Join-Path $root $file) -Destination (Join-Path $pluginRoot $file) -Force
}

New-Item -ItemType Directory -Force -Path $marketplaceDir | Out-Null
$marketplace = [ordered]@{
  name = "local"
  interface = [ordered]@{
    displayName = "Local Plugins"
  }
  plugins = @(
    [ordered]@{
      name = $pluginName
      source = [ordered]@{
        source = "local"
        path = "./plugins/$pluginName"
      }
      policy = [ordered]@{
        installation = "AVAILABLE"
        authentication = "ON_INSTALL"
      }
      category = "Productivity"
    }
  )
}

if (Test-Path -LiteralPath $marketplacePath) {
  $existing = Get-Content -Raw -LiteralPath $marketplacePath | ConvertFrom-Json
  if (-not $existing.name) { $existing | Add-Member -NotePropertyName name -NotePropertyValue "local" }
  if (-not $existing.interface) {
    $existing | Add-Member -NotePropertyName interface -NotePropertyValue ([pscustomobject]@{ displayName = "Local Plugins" })
  }
  $plugins = @($existing.plugins | Where-Object { $_.name -ne $pluginName })
  $plugins += $marketplace.plugins[0]
  $existing.plugins = $plugins
  $marketplace = $existing
}

$marketplace | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $marketplacePath -Encoding UTF8

Write-Output "Installed Mission Center plugin to $pluginRoot"
Write-Output "Updated marketplace at $marketplacePath"
Write-Output "Restart Codex to refresh the plugin list."
