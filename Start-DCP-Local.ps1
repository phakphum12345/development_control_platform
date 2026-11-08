[CmdletBinding()]
param(
    [switch]$SkipPreflight
)

$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath($PSScriptRoot)
$setup = Join-Path $project 'Setup-DCP-Local.ps1'
$gateway = Join-Path $project 'Run-DCP-Gateway.ps1'

if (-not $SkipPreflight) {
    & $setup
    if ($LASTEXITCODE -ne 0) { throw 'DCP local preflight did not complete successfully.' }
}

# Fail closed if the Gateway port is already occupied; never stop an unknown process.
$existing = @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8789 -State Listen -ErrorAction SilentlyContinue)
if ($existing.Count -gt 0) {
    throw '127.0.0.1:8789 is already in use. No existing process was stopped. Inspect the listener before retrying.'
}

Write-Host 'Starting the local Gateway in a separate PowerShell window...' -ForegroundColor Cyan
Start-Process -FilePath 'powershell.exe' -ArgumentList @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', ('"{0}"' -f $gateway)
) | Out-Null

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8789/healthz' -TimeoutSec 2
        if ($health.status -eq 'ok' -and $health.provisioning_enabled -eq $false) {
            $ready = $true
            break
        }
    } catch {
        # Gateway may still be starting. Continue the bounded readiness check.
    }
}
if (-not $ready) {
    throw 'Gateway did not pass the local health check. Inspect its PowerShell window. No unrelated process was stopped.'
}

Write-Host 'Gateway health check: PASS; cloud provisioning: DISABLED' -ForegroundColor Green
& (Join-Path $project 'Start-DCP-Dashboard.ps1') -OpenBrowser
if ($LASTEXITCODE -ne 0) { throw 'Dashboard startup failed. The local Gateway remains running in its own window.' }
Write-Host ''
Write-Host 'DCP local services started. Close the Gateway PowerShell window or press Ctrl+C there to stop the Gateway.'
