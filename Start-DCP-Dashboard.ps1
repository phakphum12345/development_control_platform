[CmdletBinding()]
param(
    # Zero means choose a free loopback port automatically. Explicit ports are
    # retained for controlled tests and troubleshooting.
    [ValidateRange(0, 65535)]
    [int]$Port = 0,
    [switch]$OpenBrowser
)

$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath($PSScriptRoot)
$dashboard = [System.IO.Path]::GetFullPath((Join-Path $project 'dashboard'))
$indexFile = Join-Path $dashboard 'index.html'
$requestedPort = $Port
$autoPort = $requestedPort -eq 0
$stateName = if ($autoPort -or $Port -eq 8000) { 'DCP' } else { "DCP-Test-$Port" }
$stateDir = Join-Path $env:LOCALAPPDATA $stateName
$pidFile = Join-Path $stateDir 'dashboard-server.json'

# When this launcher already owns a server, reuse its recorded port. Otherwise
# ask Windows for an ephemeral loopback port rather than assuming 8000 is free.
if ($autoPort -and (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
    try {
        $priorRecord = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
        $priorPort = 0
        if ([int]::TryParse([string]$priorRecord.port, [ref]$priorPort) -and
            $priorPort -ge 1 -and $priorPort -le 65535) {
            $Port = $priorPort
        }
    } catch {
        # Preserve malformed ownership evidence; the validation below will fail closed.
    }
}
if ($autoPort -and $Port -eq 0) {
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $probe.Start()
        $Port = [int]$probe.LocalEndpoint.Port
    } finally {
        $probe.Stop()
    }
}
$url = "http://127.0.0.1:$Port/"

if (-not (Test-Path -LiteralPath $indexFile -PathType Leaf)) {
    throw "Dashboard entry point not found: $indexFile"
}

function Get-DcpListeners {
    @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    )
}

function Test-DcpServerCommand([object]$Process, [switch]$AllowRelativeDirectory) {
    if ($null -eq $Process -or $Process.Name -ine 'python.exe') { return $false }
    $cmd = [string]$Process.CommandLine
    $portPattern = '(?i)-m\s+http\.server\s+' + [regex]::Escape([string]$Port) + '(?:\s|$)'
    if ($cmd -notmatch $portPattern -or
        $cmd -notmatch '(?i)--bind\s+127\.0\.0\.1(?:\s|$)') {
        return $false
    }

    if ($cmd.IndexOf($dashboard, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
    }

    # A legacy relative path is eligible for REUSE only, and only after the
    # served HTML bytes match this project's current dashboard/index.html.
    return ($AllowRelativeDirectory -and
        $cmd -match '(?i)--directory\s+(?:"dashboard"|dashboard)(?:\s|$)')
}

function Test-DcpResponseMatchesDashboard {
    $response = $null
    $stream = $null
    $memory = $null
    $sha = $null
    try {
        $request = [System.Net.HttpWebRequest]::Create($url)
        $request.Method = 'GET'
        $request.Timeout = 3000
        $request.ReadWriteTimeout = 3000
        $request.AllowAutoRedirect = $false
        $request.Proxy = $null
        $response = $request.GetResponse()
        if ([int]$response.StatusCode -ne 200) { return $false }
        $stream = $response.GetResponseStream()
        $memory = New-Object System.IO.MemoryStream
        $stream.CopyTo($memory)
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $actualHash = ([System.BitConverter]::ToString($sha.ComputeHash($memory.ToArray()))).Replace('-', '')
        $expectedHash = (Get-FileHash -LiteralPath $indexFile -Algorithm SHA256).Hash
        return ($actualHash -eq $expectedHash)
    } catch {
        return $false
    } finally {
        if ($sha) { $sha.Dispose() }
        if ($memory) { $memory.Dispose() }
        if ($stream) { $stream.Dispose() }
        if ($response) { $response.Dispose() }
    }
}

function Read-DcpOwnershipRecord {
    if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) { return $null }
    try {
        $record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    } catch {
        throw "Ownership record is unreadable and was preserved: $pidFile"
    }
    if ($null -eq $record -or $null -eq $record.pid -or
        [string]::IsNullOrWhiteSpace([string]$record.dashboard)) {
        throw "Ownership record is incomplete and was preserved: $pidFile"
    }
    if ([string]$record.dashboard -ne $dashboard) {
        throw "Ownership record refers to a different dashboard and was preserved: $pidFile"
    }
    if (-not $autoPort -and $record.PSObject.Properties.Name -contains 'port' -and [int]$record.port -ne $Port) {
        throw "Ownership record refers to a different port and was preserved: $pidFile"
    }
    return $record
}

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null

# Retry transient empty listener snapshots before treating the port as free.
$listeners = @(Get-DcpListeners)
if ($listeners.Count -eq 0) {
    for ($retry = 0; $retry -lt 4 -and $listeners.Count -eq 0; $retry++) {
        Start-Sleep -Milliseconds 250
        $listeners = @(Get-DcpListeners)
    }
}

if ($listeners.Count -gt 0) {
    if (@($listeners | Where-Object { $_.LocalAddress -ne '127.0.0.1' }).Count -gt 0) {
        throw "Port $Port has a listener not bound exclusively to 127.0.0.1; refusing to reuse or stop it."
    }
    $ownerPids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($ownerPids.Count -ne 1) {
        throw "Port $Port has multiple listener owners; refusing to reuse or stop them."
    }
    $existingProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($ownerPids[0])" -ErrorAction SilentlyContinue
    if (-not (Test-DcpServerCommand -Process $existingProcess -AllowRelativeDirectory)) {
        throw "Port $Port is occupied by an unverified process (PID $($ownerPids[0])); refusing to use or stop it."
    }
    if (-not (Test-DcpResponseMatchesDashboard)) {
        throw "Port $Port does not serve the exact current dashboard index.html; refusing to reuse it."
    }
    $existingRecord = Read-DcpOwnershipRecord
    if ($existingRecord -and [int]$existingRecord.pid -ne [int]$ownerPids[0]) {
        throw "The ownership record PID does not own port $Port; record preserved and no process stopped."
    }
    Write-Output "REUSED_VERIFIED_SERVER: PID $($ownerPids[0]) serves the current dashboard on $url. No ownership was newly claimed."
    if ($OpenBrowser) { Start-Process -FilePath $url }
    return
}

# With no listener, only archive a stale record when its PID is genuinely absent.
$oldRecord = Read-DcpOwnershipRecord
if ($oldRecord) {
    $oldProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$oldRecord.pid)" -ErrorAction SilentlyContinue
    if ($oldProcess) {
        throw "Ownership record points to a live process while port $Port has no listener; record preserved for inspection."
    }
    $stalePath = "$pidFile.stale-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Move-Item -LiteralPath $pidFile -Destination $stalePath
    Write-Output "STALE_RECORD_BACKED_UP=$stalePath"
}

$python = 'C:\Program Files\Python314\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
}

$startedPid = 0
$tempRecord = $null
try {
    $arguments = @(
        '-m', 'http.server', [string]$Port,
        '--bind', '127.0.0.1',
        '--directory', ('"{0}"' -f $dashboard)
    )
    $newProcess = Start-Process -FilePath $python -ArgumentList $arguments -WindowStyle Hidden -PassThru
    $startedPid = [int]$newProcess.Id
    $ready = $false

    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        $currentProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $startedPid" -ErrorAction SilentlyContinue
        $currentListeners = Get-DcpListeners
        $ownsPort = @($currentListeners | Where-Object { [int]$_.OwningProcess -eq $startedPid }).Count -gt 0
        if ($currentProcess -and $ownsPort -and
            (Test-DcpServerCommand -Process $currentProcess) -and
            (Test-DcpResponseMatchesDashboard)) {
            $ready = $true
            break
        }
    }
    if (-not $ready) { throw "Dashboard did not become ready and verify on port $Port." }

    $currentProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $startedPid" -ErrorAction Stop
    $processCreatedAtUtc = ([datetime]$currentProcess.CreationDate).ToUniversalTime().ToString('o')
    $record = [ordered]@{
        schema_version = 1
        port = $Port
        pid = $startedPid
        dashboard = $dashboard
        startedAt = (Get-Date).ToString('o')
        processCreatedAtUtc = $processCreatedAtUtc
    }
    $tempRecord = "$pidFile.tmp-$PID"
    [System.IO.File]::WriteAllText($tempRecord, ($record | ConvertTo-Json -Depth 4), [System.Text.Encoding]::UTF8)
    Move-Item -LiteralPath $tempRecord -Destination $pidFile
    $tempRecord = $null
    Write-Output "STARTED_VERIFIED_SERVER: PID $startedPid; URL $url; state $pidFile"
    if ($OpenBrowser) { Start-Process -FilePath $url }
} catch {
    if ($tempRecord -and (Test-Path -LiteralPath $tempRecord)) {
        Remove-Item -LiteralPath $tempRecord -Force -ErrorAction SilentlyContinue
    }
    if ($startedPid -gt 0) {
        $cleanupProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $startedPid" -ErrorAction SilentlyContinue
        if ($cleanupProcess -and (Test-DcpServerCommand -Process $cleanupProcess)) {
            Stop-Process -Id $startedPid -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $pidFile) {
            try {
                $saved = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
                if ([int]$saved.pid -eq $startedPid -and [string]$saved.dashboard -eq $dashboard) {
                    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
                }
            } catch { }
        }
    }
    throw
}