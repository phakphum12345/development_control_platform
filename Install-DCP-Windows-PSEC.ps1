$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Requirements = Join-Path $RepoRoot "requirements-windows-psec.txt"

Write-Host "Installing the optional, pure-Python Windows PSEC serializer dependency."
py -3 -m pip install --disable-pip-version-check -r $Requirements
if ($LASTEXITCODE -ne 0) {
    throw "PSEC serializer dependency installation failed. No Terminal execution was enabled."
}

Write-Host "Probing the Windows Process Security Environment API."
Push-Location $RepoRoot
try {
    py -3 -m tools.local_runner_agent.windows_psec
    $ProbeExit = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($ProbeExit -ne 0) {
    Write-Warning "PSEC probe is BLOCKED on this host. Terminal templates remain disabled."
    exit 2
}

Write-Host "PSEC v1.1 API surface is READY_FOR_ACCEPTANCE only. This does not enable Terminal execution."
exit 0
