[CmdletBinding()]
param(
    [switch]$SkipPreflight
)

$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath($PSScriptRoot)
$setup = Join-Path $project 'Setup-DCP-Local.ps1'
$stack = Join-Path $project 'Run-DCP-Gateway.ps1'

if (-not $SkipPreflight) {
    & $setup
    if ($LASTEXITCODE -ne 0) { throw 'DCP local preflight did not complete successfully.' }
}

foreach ($port in @(8789, 8790)) {
    $existing = @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
        throw "127.0.0.1:$port is already in use. No existing process was stopped. Inspect the listener before retrying."
    }
}

Write-Host 'Starting the integrated local stack in a separate PowerShell window...' -ForegroundColor Cyan
Write-Host 'On first launch, choose your owner username and password in that window.'
Start-Process -FilePath 'powershell.exe' -ArgumentList @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', ('"{0}"' -f $stack)
) | Out-Null

$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8789/healthz' -TimeoutSec 2
        if ($health.status -eq 'ok' -and $health.auth_proxy -eq 'ready' -and
            $health.provisioning_enabled -eq $false) {
            $ready = $true
            break
        }
    } catch {
        # The owner may still be completing first-time password setup.
    }
}
if (-not $ready) {
    throw 'Local Auth Proxy + Gateway did not pass readiness checks. Inspect the stack PowerShell window.'
}

Write-Host 'Local Auth Proxy: PASS; Gateway: PASS; cloud provisioning: DISABLED' -ForegroundColor Green
try { Start-Process 'http://127.0.0.1:8789/' } catch {
    Write-Warning "Stack is ready at http://127.0.0.1:8789/; browser could not be opened automatically."
}
Write-Host 'Dashboard URL: http://127.0.0.1:8789/'
Write-Host 'Keep the stack PowerShell window open. Close it or press Ctrl+C there to stop all local services.'
