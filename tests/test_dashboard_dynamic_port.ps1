$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $project 'Start-DCP-Dashboard.ps1'
$stopScript = Join-Path $project 'Stop-DCP-Dashboard.ps1'
$stateDir = Join-Path $env:LOCALAPPDATA 'DCP'
$recordPath = Join-Path $stateDir 'dashboard-server.json'
$testPassed = $false

function Assert-Check([bool]$condition, [string]$message) {
    if (-not $condition) { throw "FAIL: $message" }
    Write-Output "PASS: $message"
}
function Get-Listeners([int]$Port) {
    @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}
function Test-Http200([string]$Url) {
    try { return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 }
    catch { return $false }
}

try {
    Assert-Check (Test-Path -LiteralPath $startScript -PathType Leaf) 'Start script exists'
    Assert-Check (Test-Path -LiteralPath $stopScript -PathType Leaf) 'Stop script exists'
    Assert-Check (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) 'No pre-existing DCP ownership record'

    & $startScript | Out-Host
    Assert-Check (Test-Path -LiteralPath $recordPath -PathType Leaf) 'Dynamic start writes ownership record'
    $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $ownedPid = [int]$record.pid
    $port = [int]$record.port
    Assert-Check ($ownedPid -gt 0) 'Ownership record contains valid PID'
    Assert-Check ($port -ge 1 -and $port -le 65535) 'Ownership record contains a valid selected port'
    Assert-Check ($record.dashboard -eq (Join-Path $project 'dashboard')) 'Ownership record is scoped to this project'
    $url = "http://127.0.0.1:$port/"
    Assert-Check (Test-Http200 $url) 'Dynamic URL serves dashboard HTTP 200'

    $listeners = Get-Listeners $port
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    Assert-Check ($owners.Count -eq 1 -and [int]$owners[0] -eq $ownedPid) 'Launcher-owned process exclusively owns selected port'
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ownedPid" -ErrorAction SilentlyContinue
    Assert-Check ($null -ne $process -and $process.Name -ieq 'python.exe') 'Recorded Python server process exists'

    & $startScript | Out-Host
    $reused = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    Assert-Check ([int]$reused.pid -eq $ownedPid -and [int]$reused.port -eq $port) 'Repeated start reuses the recorded server and port'
    Assert-Check ((Get-Listeners $port).Count -eq 1) 'Repeated start does not create a duplicate listener'

    & $stopScript | Out-Host
    Assert-Check (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) 'Default stop discovers and removes ownership record'
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ownedPid" -ErrorAction SilentlyContinue
    Assert-Check ($null -eq $process) 'Verified server process exits'
    Assert-Check ((Get-Listeners $port).Count -eq 0) 'Dynamically selected port is released'
    $testPassed = $true
    Write-Output 'RESULT: WINDOWS DYNAMIC-PORT INTEGRATION PASSED'
} finally {
    if (-not $testPassed -and (Test-Path -LiteralPath $recordPath -PathType Leaf)) {
        try {
            $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
            $pidToCheck = [int]$record.pid
            $process = Get-CimInstance Win32_Process -Filter "ProcessId = $pidToCheck" -ErrorAction SilentlyContinue
            $expectedDashboard = Join-Path $project 'dashboard'
            if ($process -and $process.Name -ieq 'python.exe' -and
                ([string]$process.CommandLine).IndexOf($expectedDashboard, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
                [int]$record.port -ge 1 -and [int]$record.port -le 65535) {
                & $stopScript | Out-Host
                Write-Output 'SAFETY: Cleaned up only the launcher-owned dashboard process.'
            } else {
                Write-Output 'SAFETY: Ownership could not be verified; no process was stopped.'
            }
        } catch {
            Write-Output "SAFETY: Cleanup refused or failed: $($_.Exception.Message)"
        }
    }
}
if (-not $testPassed) { throw 'Windows dynamic-port integration test failed.' }
