$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$tempRepo = Join-Path ([System.IO.Path]::GetTempPath()) ('mission-center-hook-' + [guid]::NewGuid().ToString('N'))
$hook = Join-Path $tempRepo '.git\hooks\post-commit'

try {
    New-Item -ItemType Directory -Path (Split-Path -Parent $hook) -Force | Out-Null
    $original = "#!/bin/sh`necho user-hook`n"
    [System.IO.File]::WriteAllText($hook, $original, [System.Text.UTF8Encoding]::new($false))

    & pwsh -NoLogo -NoProfile -File (Join-Path $repoRoot 'scripts\install_git_hook.ps1') -TargetRepoPath $tempRepo
    if ($LASTEXITCODE -eq 0) {
        throw 'PowerShell hook installer should fail for an existing non-tool hook.'
    }
    if ([System.IO.File]::ReadAllText($hook) -ne $original) {
        throw 'PowerShell hook installer overwrote an existing non-tool hook.'
    }
}
finally {
    if (Test-Path -LiteralPath $tempRepo) {
        Remove-Item -LiteralPath $tempRepo -Recurse -Force
    }
}

Write-Host 'PASS: PowerShell hook installer preserves non-tool hooks'
