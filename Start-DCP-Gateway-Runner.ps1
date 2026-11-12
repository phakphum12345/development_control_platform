[CmdletBinding()]
param(
    [ValidatePattern('^[a-z0-9_.:-]{1,100}$')]
    [string]$WorkerId = 'windows-local-01',
    [switch]$EnableExecution,
    [switch]$Once,
    [string[]]$TrustedRepository = @(),
    [string[]]$TrustedLocalProject = @()
)

$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath($PSScriptRoot)
$credentialFile = Join-Path $env:LOCALAPPDATA 'DCP\runner-tokens.json'
$python = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python Launcher (py.exe) was not found. Run Setup-DCP-Local.cmd first.' }
if (-not (Test-Path -LiteralPath $credentialFile -PathType Leaf)) {
    throw 'Local Runner credentials are missing. Run Setup-DCP-Local-Runner.ps1 first.'
}
$item = Get-Item -LiteralPath $credentialFile -Force
if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $item.Length -gt 65536) {
    throw 'Local Runner credential file is unsafe or exceeds 64 KiB.'
}
try { $credentialMap = Get-Content -LiteralPath $credentialFile -Raw | ConvertFrom-Json }
catch { throw 'Local Runner credential file is invalid JSON.' }
if ($null -eq $credentialMap -or $credentialMap -isnot [pscustomobject]) {
    throw 'Local Runner credential file must be a JSON object.'
}
$property = $credentialMap.PSObject.Properties[$WorkerId]
if ($null -eq $property -or $property.Value -isnot [string] -or $property.Value.Length -lt 32) {
    throw "Worker '$WorkerId' is not configured. Run Setup-DCP-Local-Runner.ps1."
}
if ($Once -and -not $EnableExecution) {
    throw '-Once requires -EnableExecution.'
}
if ($EnableExecution) {
    if (($TrustedRepository.Count + $TrustedLocalProject.Count) -lt 1) {
        throw 'Execution requires at least one explicit -TrustedRepository or -TrustedLocalProject.'
    }
    foreach ($repository in $TrustedRepository) {
        if ($repository -notmatch '^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$') {
            throw "Invalid trusted repository name: $repository"
        }
    }
    if (@($TrustedRepository | Select-Object -Unique).Count -ne $TrustedRepository.Count) {
        throw 'Trusted repositories must be unique.'
    }
    foreach ($projectId in $TrustedLocalProject) {
        if ($projectId -notmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') {
            throw "Invalid trusted Local Project ID: $projectId"
        }
    }
    if (@($TrustedLocalProject | Select-Object -Unique).Count -ne $TrustedLocalProject.Count) {
        throw 'Trusted Local Project IDs must be unique.'
    }
} elseif (($TrustedRepository.Count + $TrustedLocalProject.Count) -gt 0) {
    throw 'Trusted sources are only accepted together with -EnableExecution.'
}

try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:18790/healthz' -TimeoutSec 3
} catch {
    throw 'DCP Gateway is not reachable. Start the DCP local stack and retry.'
}
if ($health.status -ne 'ok' -or $health.provisioning_enabled -ne $false) {
    throw 'DCP Gateway health/safe-default check failed.'
}

$names = @('DCP_GATEWAY_URL','DCP_RUNNER_WORKER_ID','DCP_RUNNER_TOKEN',
           'DCP_RUNNER_EXECUTION_ENABLED','DCP_RUNNER_TRUSTED_REPOSITORIES',
           'DCP_RUNNER_TRUSTED_LOCAL_PROJECTS','DCP_RUNNER_WORKSPACE_ROOT',
           'DCP_RUNNER_PLAYWRIGHT_ENABLED','DCP_RUNNER_CAPABILITIES')
$previous = @{}
foreach ($name in $names) { $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

try {
    $env:DCP_GATEWAY_URL = 'http://127.0.0.1:18790'
    $env:DCP_RUNNER_WORKER_ID = $WorkerId
    $env:DCP_RUNNER_TOKEN = $property.Value
    $env:DCP_RUNNER_WORKSPACE_ROOT = Join-Path $env:LOCALAPPDATA 'DCP\workspaces'
    Remove-Item Env:DCP_RUNNER_PLAYWRIGHT_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:DCP_RUNNER_CAPABILITIES -ErrorAction SilentlyContinue

    if ($EnableExecution) {
        $env:DCP_RUNNER_EXECUTION_ENABLED = '1'
        $env:DCP_RUNNER_TRUSTED_REPOSITORIES = ConvertTo-Json -InputObject ([string[]]$TrustedRepository) -Compress
        $env:DCP_RUNNER_TRUSTED_LOCAL_PROJECTS = ConvertTo-Json -InputObject ([string[]]$TrustedLocalProject) -Compress
        Write-Host "Starting the unified local Runner '$WorkerId' for explicitly trusted source IDs."
    } else {
        Remove-Item Env:DCP_RUNNER_EXECUTION_ENABLED -ErrorAction SilentlyContinue
        Remove-Item Env:DCP_RUNNER_TRUSTED_REPOSITORIES -ErrorAction SilentlyContinue
        Remove-Item Env:DCP_RUNNER_TRUSTED_LOCAL_PROJECTS -ErrorAction SilentlyContinue
        Write-Host "Enrolling Runner '$WorkerId' offline. No jobs will be claimed or executed."
    }

    $runnerArgs = @('--enroll-only')
    if ($EnableExecution -and $Once) { $runnerArgs = @('--once') }
    elseif ($EnableExecution) { $runnerArgs = @('--serve') }

    Push-Location $project
    try {
        & $python.Source -3 -m tools.local_runner_agent @runnerArgs
        if ($LASTEXITCODE -ne 0) { throw "DCP Runner exited with code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
} finally {
    foreach ($name in $names) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
