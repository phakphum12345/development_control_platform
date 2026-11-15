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
$target = Join-Path $PSScriptRoot 'Start-DCP-Gateway-Runner.ps1'
if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    throw 'Start-DCP-Gateway-Runner.ps1 is missing; the legacy Local Runner entry point cannot continue.'
}

# Preserve the historical entry point while routing to the unified Runner Agent.
& $target @PSBoundParameters
if ($LASTEXITCODE -is [int] -and $LASTEXITCODE -ne 0) {
    throw "DCP Runner exited with code $LASTEXITCODE."
}
