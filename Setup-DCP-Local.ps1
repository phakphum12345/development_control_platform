[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath($PSScriptRoot)

if ($env:OS -ne 'Windows_NT') { throw 'This setup script is for Windows 11/Windows only.' }
$python = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python Launcher (py.exe) was not found. Install Python 3.10+ and reopen PowerShell.' }
$git = Get-Command git.exe -ErrorAction SilentlyContinue

Write-Host 'DCP local setup preflight' -ForegroundColor Cyan
Write-Host 'No cloud account, paid service, package installation, or firewall change is required.'
Write-Host ''
& $python.Source -3 --version
if ($LASTEXITCODE -ne 0) { throw 'Python 3 could not be started.' }
if ($git) { & $git.Source --version } else { Write-Warning 'Git was not found. Git is optional for running the local dashboard and gateway.' }

$dataDir = Join-Path $env:LOCALAPPDATA 'DCP'
$logsDir = Join-Path $dataDir 'logs'
New-Item -ItemType Directory -Path $logsDir -Force | Out-Null

Push-Location $project
try {
    & $python.Source -3 -m tools.cloud_gateway.local_mode
    if ($LASTEXITCODE -ne 0) { throw 'Local environment checks reported a failure. Review the diagnostic output above.' }
} finally {
    Pop-Location
}

Write-Host ''
Write-Host "Local data directory: $dataDir"
Write-Host 'Preflight passed. No service was started and no cloud resources were contacted.' -ForegroundColor Green
