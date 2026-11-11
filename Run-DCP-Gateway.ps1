[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath($PSScriptRoot)
$python = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python Launcher (py.exe) was not found. Run Setup-DCP-Local.cmd first.' }

$dataDir = Join-Path $env:LOCALAPPDATA 'DCP'
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
$env:DCP_LOCAL_PORT = '8789'
$env:DCP_GATEWAY_PORT = '18790'
$env:DCP_GATEWAY_PROVISIONING_ENABLED = 'false'
$env:DCP_GATEWAY_OWNER_APPROVED = 'false'
if ([string]::IsNullOrWhiteSpace($env:DCP_RUNNER_WORKSPACE_ROOT)) {
    $env:DCP_RUNNER_WORKSPACE_ROOT = Join-Path $dataDir 'workspaces'
}
if (-not [System.IO.Path]::IsPathRooted($env:DCP_RUNNER_WORKSPACE_ROOT)) {
    throw 'DCP_RUNNER_WORKSPACE_ROOT must be an absolute path.'
}

Write-Host 'Starting DCP Dashboard + Local Auth Proxy + Gateway.'
Write-Host 'First launch asks you to choose an owner username and password (14+ characters).'
Write-Host 'Password is stored only as a salted PBKDF2 hash; session and Gateway secrets stay in memory.'
Write-Host 'Cloud provisioning: DISABLED. Keep this window open; Ctrl+C stops the local stack.'
Push-Location $project
try {
    & $python.Source -3 -m tools.local_auth_proxy
    if ($LASTEXITCODE -ne 0) { throw "DCP local stack exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
