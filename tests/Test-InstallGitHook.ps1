$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$tempRepo = Join-Path ([System.IO.Path]::GetTempPath()) ('mission-center-hook-' + [guid]::NewGuid().ToString('N'))
$preCommit = Join-Path $tempRepo '.git\hooks\pre-commit'
$postCommit = Join-Path $tempRepo '.git\hooks\post-commit'

try {
    New-Item -ItemType Directory -Path (Split-Path -Parent $preCommit) -Force | Out-Null
    $original = "#!/bin/sh`necho user-post-commit`n"
    [System.IO.File]::WriteAllText($postCommit, $original, [System.Text.UTF8Encoding]::new($false))

    & pwsh -NoLogo -NoProfile -File (Join-Path $repoRoot 'scripts\install_git_hook.ps1') -TargetRepoPath $tempRepo
    if ($LASTEXITCODE -ne 0) {
        throw 'PowerShell hook installer should install the check-only pre-commit hook.'
    }
    $preCommitText = [System.IO.File]::ReadAllText($preCommit)
    if ($preCommitText -notmatch 'check_mission_center.py') {
        throw 'PowerShell hook installer did not install the check-only pre-commit contract.'
    }
    if ([System.IO.File]::ReadAllText($postCommit) -ne $original) {
        throw 'PowerShell hook installer modified post-commit.'
    }
}
finally {
    if (Test-Path -LiteralPath $tempRepo) {
        Remove-Item -LiteralPath $tempRepo -Recurse -Force
    }
}

Write-Host 'PASS: PowerShell hook installer installs pre-commit and preserves post-commit'
