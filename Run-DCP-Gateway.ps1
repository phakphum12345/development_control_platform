[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath($PSScriptRoot)
$python = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python Launcher (py.exe) was not found. Run Setup-DCP-Local.cmd first.' }

$dataDir = Join-Path $env:LOCALAPPDATA 'DCP'
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

# Generate a process-local token. Never write it to disk or print it.
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$tokenBytes = New-Object byte[] 32
try {
    $rng.GetBytes($tokenBytes)
    $env:DCP_GATEWAY_API_TOKEN = [Convert]::ToBase64String($tokenBytes)
} finally {
    [Array]::Clear($tokenBytes, 0, $tokenBytes.Length)
    $rng.Dispose()
}

$env:DCP_GATEWAY_HOST = '127.0.0.1'
$env:DCP_GATEWAY_PORT = '8789'
$env:DCP_GATEWAY_PROVISIONING_ENABLED = 'false'
$env:DCP_GATEWAY_OWNER_APPROVED = 'false'
$env:DCP_GATEWAY_DATABASE = Join-Path $dataDir 'gateway.sqlite3'
$env:DCP_GATEWAY_RECONCILE_SECONDS = '30'

Write-Host 'DCP local Gateway starting on http://127.0.0.1:8789'
Write-Host 'Cloud provisioning: DISABLED'
Write-Host "Local database: $env:DCP_GATEWAY_DATABASE"
Write-Host 'Keep this window open. Press Ctrl+C to stop the Gateway.'
Push-Location $project
try {
    & $python.Source -3 -m tools.cloud_gateway.server
    if ($LASTEXITCODE -ne 0) { throw "Gateway exited with code $LASTEXITCODE." }
} finally {
    Remove-Item Env:DCP_GATEWAY_API_TOKEN -ErrorAction SilentlyContinue
    Pop-Location
}
