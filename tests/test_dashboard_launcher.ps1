[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $project 'Start-DCP-Dashboard.ps1'
$stopScript = Join-Path $project 'Stop-DCP-Dashboard.ps1'
$port = 8001
$stateDir = Join-Path $env:LOCALAPPDATA "DCP-Test-$port"
$recordPath = Join-Path $stateDir 'dashboard-server.json'
$testUrl = "http://127.0.0.1:$port/"
$mainUrl = 'http://127.0.0.1:8000/'
$powerShellExe = Join-Path $PSHOME 'powershell.exe'
$ownedPid = 0
$validRecordJson = $null
$testPassed = $false

function Assert-Check($condition, [string]$message) {
    if (-not $condition) { throw "FAIL: $message" }
    Write-Output "PASS: $message"
}
function Get-TestListeners {
    @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}
function Test-Http200([string]$url) {
    try { return (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 }
    catch { return $false }
}
function Invoke-ChildScript([string]$script, [string[]]$arguments) {
    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()

    try {
        $childArguments = @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $script
        ) + @($arguments)

        $argumentLine = (
            $childArguments | ForEach-Object {
                '"' + [string]$_ + '"'
            }
        ) -join ' '

        $child = Start-Process -FilePath $powerShellExe `
            -ArgumentList $argumentLine `
            -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath

        foreach ($line in @(Get-Content -LiteralPath $stdoutPath -ErrorAction SilentlyContinue)) {
            Write-Host ([string]$line)
        }
        foreach ($line in @(Get-Content -LiteralPath $stderrPath -ErrorAction SilentlyContinue)) {
            Write-Host "CHILD_STDERR: $line"
        }

        return [int]$child.ExitCode
    } finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath `
            -Force -ErrorAction SilentlyContinue
    }
}

try {
    Assert-Check (Test-Path -LiteralPath $startScript) 'Start script exists'
    Assert-Check (Test-Path -LiteralPath $stopScript) 'Stop script exists'
    Assert-Check (Test-Http200 $mainUrl) 'Main dashboard remains HTTP 200 before test'
    Assert-Check ((Get-TestListeners).Count -eq 0) 'Test port 8001 is free before test'
    Assert-Check (-not (Test-Path -LiteralPath $recordPath)) 'Test ownership record does not already exist'

    Write-Output "`n=== Start test server on isolated port $port ==="
    $startCode = 0
    try {
        & $startScript -Port $port
    } catch {
        Write-Output ("START_EXCEPTION: " + $_.Exception.Message)
        $startCode = 1
    }
    Assert-Check ($startCode -eq 0) 'Start returns exit code 0'
    Assert-Check (Test-Path -LiteralPath $recordPath) 'Start creates ownership record'
    $validRecordJson = Get-Content -LiteralPath $recordPath -Raw
    $record = $validRecordJson | ConvertFrom-Json
    $ownedPid = [int]$record.pid
    Assert-Check ($ownedPid -gt 0) 'Ownership record contains valid PID'
    Assert-Check ($record.dashboard -eq (Join-Path $project 'dashboard')) 'Ownership record points to current dashboard'
    $proc = $null
    $processDeadline = (Get-Date).AddSeconds(4)
    do {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ownedPid" -ErrorAction SilentlyContinue
        if ($proc -and $proc.Name -ieq 'python.exe') { break }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $processDeadline)

    $diagnosticListeners = @(Get-TestListeners)
    $diagnosticOwners = @($diagnosticListeners | Select-Object -ExpandProperty OwningProcess -Unique)
    Write-Output ("DIAGNOSTIC: recorded PID={0}; listener PIDs={1}" -f $ownedPid, ($diagnosticOwners -join ','))

    Assert-Check ($null -ne $proc -and $proc.Name -ieq 'python.exe') 'Recorded Python process exists'
    $listeners = Get-TestListeners
    $ownerPids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    Assert-Check ($ownerPids.Count -eq 1 -and [int]$ownerPids[0] -eq $ownedPid) 'Recorded PID exclusively owns port 8001'
    Assert-Check (Test-Http200 $testUrl) 'Test dashboard returns HTTP 200'

    Write-Output "`n=== Wrong PID refusal ==="
    $badRecord = [ordered]@{
        schema_version = 1
        port = $port
        pid = $PID
        dashboard = $record.dashboard
        startedAt = $record.startedAt
        processCreatedAtUtc = $record.processCreatedAtUtc
    } | ConvertTo-Json -Depth 4
    [System.IO.File]::WriteAllText($recordPath, $badRecord, [System.Text.Encoding]::UTF8)
    $badStopCode = Invoke-ChildScript $stopScript @('-Port', [string]$port)
    Assert-Check ($badStopCode -ne 0) 'Stop rejects mismatched PID'
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ownedPid" -ErrorAction SilentlyContinue
    Assert-Check ($null -ne $proc) 'Wrong-PID refusal leaves real server alive'
    Assert-Check (Test-Http200 $testUrl) 'Test server remains HTTP 200 after refusal'
    [System.IO.File]::WriteAllText($recordPath, $validRecordJson, [System.Text.Encoding]::UTF8)

    Write-Output "`n=== Repeated Start ==="
    $repeatCode = 0
    try {
        & $startScript -Port $port
    } catch {
        Write-Output ("REPEAT_START_EXCEPTION: " + $_.Exception.Message)
        $repeatCode = 1
    }
    Assert-Check ($repeatCode -eq 0) 'Repeated Start returns exit code 0'
    $after = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    Assert-Check ([int]$after.pid -eq $ownedPid) 'Repeated Start reuses same PID'
    $listeners = Get-TestListeners
    $ownerPids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    Assert-Check ($ownerPids.Count -eq 1 -and [int]$ownerPids[0] -eq $ownedPid) 'Repeated Start does not create duplicate listener'

    Write-Output "`n=== Verified Stop ==="
    $stopCode = Invoke-ChildScript $stopScript @('-Port', [string]$port)
    Assert-Check ($stopCode -eq 0) 'Stop returns exit code 0'
    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 250
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ownedPid" -ErrorAction SilentlyContinue
    } while ($proc -and (Get-Date) -lt $deadline)
    Assert-Check ($null -eq $proc) 'Verified server process exited'
    Assert-Check ((Get-TestListeners).Count -eq 0) 'Test port 8001 is released'
    Assert-Check (-not (Test-Path -LiteralPath $recordPath)) 'Successful Stop removes ownership record'
    Assert-Check (Test-Http200 $mainUrl) 'Main dashboard remains HTTP 200 after test'
    $testPassed = $true
    Write-Output "`nRESULT: ALL LAUNCHER INTEGRATION ASSERTIONS PASSED"
} catch {
    Write-Output "`nRESULT: TEST FAILED OR INCOMPLETE"
    Write-Output $_.Exception.Message
    Write-Output 'No unverified process will be terminated.'
} finally {
    # If the verified test server remains alive after a test failure, restore
    # its ownership record only after rechecking exact command line and path.
    if ($ownedPid -gt 0) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ownedPid" -ErrorAction SilentlyContinue
        if ($proc) {
            $cmd = [string]$proc.CommandLine
            $dashboard = Join-Path $project 'dashboard'
            $expectedCmd = (
                $proc.Name -ieq 'python.exe' -and
                $cmd -match '(?i)-m\s+http\.server\s+8001(?:\s|$)' -and
                $cmd -match '(?i)--bind\s+127\.0\.0\.1(?:\s|$)' -and
                $cmd.IndexOf($dashboard, [StringComparison]::OrdinalIgnoreCase) -ge 0
            )
            if ($expectedCmd -and $validRecordJson) {
                $current = $null
                if (Test-Path -LiteralPath $recordPath) {
                    try { $current = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json } catch { }
                }
                if ($null -eq $current -or [int]$current.pid -ne $ownedPid) {
                    [System.IO.File]::WriteAllText($recordPath, $validRecordJson, [System.Text.Encoding]::UTF8)
                    Write-Output 'SAFETY: Restored record for the still-running verified test server.'
                }
            } else {
                Write-Output 'SAFETY: Process did not match the exact expected test server; no cleanup was attempted.'
            }
        }
    }
    if (-not $testPassed) {
        Write-Output 'Inspect port 8001, its PID, and ownership record before retrying.'
    }
}
if (-not $testPassed) { exit 1 }
exit 0
