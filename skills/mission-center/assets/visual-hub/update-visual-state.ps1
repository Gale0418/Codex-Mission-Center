param(
  [ValidateSet("Intake", "In Progress", "Blocked", "Review", "Done")]
  [string]$Status = "Intake",
  [string]$Goal = "Build task dashboard",
  [int]$Progress = 40,
  [string[]]$Active = @(),
  [string[]]$Blocked = @(),
  [string[]]$Agents = @()
)

$agentRows = @()
for ($i = 0; $i -lt $Agents.Count; $i++) {
  $parts = $Agents[$i] -split "\|", 4
  $agentStatus = if ($parts.Count -ge 2 -and $parts[1]) { $parts[1] } else { $Status }
  $agentTask = if ($parts.Count -ge 3 -and $parts[2]) { $parts[2] } else { $agentStatus }

  $agentRow = [ordered]@{
    id = "agent-$($i + 1)"
    name = if ($parts.Count -ge 1 -and $parts[0]) { $parts[0] } else { "Agent $($i + 1)" }
    status = $agentStatus
    task = $agentTask
  }

    if ($parts.Count -ge 4 -and $parts[3]) {
    $agentRow.avatar = [Math]::Max(1, [Math]::Min(16, [int]$parts[3]))
    }

  $agentRows += $agentRow
}

$state = [ordered]@{
  status = $Status
  goal = $Goal
  progress = [Math]::Max(0, [Math]::Min(100, $Progress))
  active = $Active
  blocked = $Blocked
  agents = $agentRows
}

$out = Join-Path $PSScriptRoot "visual-state.json"
$state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $out -Encoding UTF8
Write-Output "MissionCenter visual state updated: $Status"
