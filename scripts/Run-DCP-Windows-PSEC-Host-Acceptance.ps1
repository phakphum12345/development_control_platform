$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$exitCode = 0
Push-Location $repoRoot
try {
    $head = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch "^[0-9a-f]{40}$") {
        throw "Cannot determine the exact repository HEAD; refusing to record acceptance evidence."
    }

    $outputLines = & py -3 -m tools.local_runner_agent.windows_psec_host_acceptance
    $pythonExitCode = $LASTEXITCODE
    $rawJson = ($outputLines | ForEach-Object { [string]$_ }) -join "`n"
    if ([string]::IsNullOrWhiteSpace($rawJson)) {
        throw "Windows PSEC host acceptance returned no JSON evidence."
    }

    try {
        $evidence = $rawJson | ConvertFrom-Json
    }
    catch {
        throw "Windows PSEC host acceptance output was not valid JSON; evidence was not recorded."
    }

    $evidence | Add-Member -Force -NotePropertyName repository_head -NotePropertyValue $head
    $evidence | Add-Member -Force -NotePropertyName runner_exit_code -NotePropertyValue $pythonExitCode

    $artifactDirectory = Join-Path $repoRoot "artifacts"
    if (-not (Test-Path -LiteralPath $artifactDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $artifactDirectory | Out-Null
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $artifactPath = Join-Path $artifactDirectory "windows-psec-host-acceptance-$stamp-$($head.Substring(0,12)).json"
    $json = $evidence | ConvertTo-Json -Depth 20
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($artifactPath, $json, $utf8NoBom)

    Write-Output "Evidence file: $artifactPath"
    Write-Output "Repository HEAD: $head"
    Write-Output "Acceptance state: $($evidence.state)"
    $exitCode = $pythonExitCode
}
catch {
    Write-Error $_
    $exitCode = 1
}
finally {
    Pop-Location
}

if ($exitCode -ne 0) {
    exit $exitCode
}
