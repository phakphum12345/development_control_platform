[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath($PSScriptRoot)
$dashboard = [System.IO.Path]::GetFullPath((Join-Path $project 'dashboard'))
$stateName = if ($Port -eq 8000) { 'DCP' } else { "DCP-Test-$Port" }
$pidFile = Join-Path (Join-Path $env:LOCALAPPDATA $stateName) 'dashboard-server.json'

function Get-DcpListeners {
    @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    )
}

function Test-DcpServerCommand([object]$Process) {
    if ($null -eq $Process -or $Process.Name -ine 'python.exe') { return $false }
    $cmd = [string]$Process.CommandLine
    $portPattern = '(?i)-m\s+http\.server\s+' + [regex]::Escape([string]$Port) + '(?:\s|$)'
    return (
        $cmd -match $portPattern -and
        $cmd -match '(?i)--bind\s+127\.0\.0\.1(?:\s|$)' -and
        $cmd.IndexOf($dashboard, [StringComparison]::OrdinalIgnoreCase) -ge 0
    )
}

if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
    Write-Output 'NO_OWNED_SERVER: no launcher-owned PID record; nothing was stopped.'
    exit 4
}

try {
    $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
} catch {
    throw "REFUSED: unreadable ownership record; it was preserved: $pidFile"
}
if ($null -eq $record -or $null -eq $record.pid -or
    [string]::IsNullOrWhiteSpace([string]$record.dashboard)) {
    throw "REFUSED: incomplete ownership record; it was preserved: $pidFile"
}
if ([string]$record.dashboard -ne $dashboard) {
    throw 'REFUSED: ownership record dashboard path does not match. Nothing was stopped.'
}
if ($record.PSObject.Properties.Name -contains 'port' -and [int]$record.port -ne $Port) {
    throw 'REFUSED: ownership record port does not match. Nothing was stopped.'
}
$recordPid = 0
if (-not [int]::TryParse([string]$record.pid, [ref]$recordPid) -or $recordPid -le 0) {
    throw 'REFUSED: ownership record PID is invalid. Nothing was stopped.'
}

$process = Get-CimInstance Win32_Process -Filter "ProcessId = $recordPid" -ErrorAction SilentlyContinue
$listeners = Get-DcpListeners
if (-not $process) {
    if ($listeners.Count -gt 0) {
        throw "REFUSED: recorded PID is absent but port $Port is occupied. Ownership record was preserved."
    }
    $stalePath = "$pidFile.stale-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Move-Item -LiteralPath $pidFile -Destination $stalePath
    Write-Output "ALREADY_STOPPED: stale record preserved as $stalePath"
    return
}

if (-not (Test-DcpServerCommand -Process $process)) {
    throw 'REFUSED: PID no longer matches the launcher-owned dashboard server. Nothing was stopped.'
}

$actualCreated = ([datetime]$process.CreationDate).ToUniversalTime()
if ($record.PSObject.Properties.Name -contains 'processCreatedAtUtc') {
    try {
        $recordCreated = [DateTimeOffset]::Parse([string]$record.processCreatedAtUtc).UtcDateTime
    } catch {
        throw 'REFUSED: process creation timestamp in ownership record is invalid. Nothing was stopped.'
    }
} elseif ($record.PSObject.Properties.Name -contains 'startedAt') {
    # Compatibility with older launcher records; still guard against PID reuse.
    try {
        $recordCreated = [DateTimeOffset]::Parse([string]$record.startedAt).UtcDateTime
    } catch {
        throw 'REFUSED: legacy ownership timestamp is invalid. Nothing was stopped.'
    }
} else {
    throw 'REFUSED: ownership record has no process creation evidence. Nothing was stopped.'
}
if ([Math]::Abs(($actualCreated - $recordCreated).TotalSeconds) -gt 15) {
    throw 'REFUSED: PID creation time differs from the ownership record. Nothing was stopped.'
}

if (@($listeners | Where-Object { $_.LocalAddress -ne '127.0.0.1' }).Count -gt 0) {
    throw "REFUSED: port $Port has a listener not bound exclusively to 127.0.0.1. Nothing was stopped."
}
$ownerPids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
if ($ownerPids.Count -ne 1 -or [int]$ownerPids[0] -ne $recordPid) {
    throw "REFUSED: recorded PID does not exclusively own port $Port. Nothing was stopped."
}

Stop-Process -Id $recordPid -ErrorAction Stop
$deadline = (Get-Date).AddSeconds(10)
do {
    Start-Sleep -Milliseconds 250
    $remaining = Get-CimInstance Win32_Process -Filter "ProcessId = $recordPid" -ErrorAction SilentlyContinue
} while ($remaining -and (Get-Date) -lt $deadline)
if ($remaining) { throw "Dashboard process PID $recordPid did not exit within 10 seconds; ownership record was preserved." }

if ((Get-DcpListeners).Count -gt 0) {
    throw "PID $recordPid exited, but port $Port is now occupied by another listener; ownership record was preserved for inspection."
}
Remove-Item -LiteralPath $pidFile -Force
Write-Output "STOPPED: verified launcher-owned dashboard PID $recordPid stopped; port $Port is free."