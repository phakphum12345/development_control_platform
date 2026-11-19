[CmdletBinding()]
param(
   [string]$AcceptanceParent = $env:DCP_PSEC_ACCEPTANCE_PARENT
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
   $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
   $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
   if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
       throw "Run this script from an elevated PowerShell session. No ACL changes are made automatically."
   }
}

function Assert-NoReparsePath {
   param([Parameter(Mandatory = $true)][string]$Path)

   $full = [System.IO.Path]::GetFullPath($Path)
   $root = [System.IO.Path]::GetPathRoot($full)
   $current = $root
   $relative = $full.Substring($root.Length)
   $parts = $relative.Split(
       [char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar),
       [System.StringSplitOptions]::RemoveEmptyEntries
   )
   foreach ($part in $parts) {
       $current = Join-Path $current $part
       if (Test-Path -LiteralPath $current) {
           $item = Get-Item -LiteralPath $current -Force
           if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
               throw "Refusing reparse-point path: $current"
           }
       }
   }
}

function Assert-TrustedAcl {
   param([Parameter(Mandatory = $true)][string]$Path)

   if (-not (Test-Path -LiteralPath $Path)) {
       throw "ACL verification target does not exist: $Path"
   }
   Assert-NoReparsePath -Path $Path

   $acl = Get-Acl -LiteralPath $Path
   $ownerSid = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
   $trustedOwners = @(
       "S-1-5-18",
       "S-1-5-32-544",
       "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
   )
   if ($ownerSid -notin $trustedOwners) {
       throw "Untrusted owner on '$Path': $ownerSid. Expected SYSTEM, Administrators, or TrustedInstaller."
   }

   $broadPrincipals = @(
       "S-1-1-0",       # Everyone
       "S-1-5-4",       # Interactive
       "S-1-5-11",      # Authenticated Users
       "S-1-5-32-545",  # BUILTIN\Users
       "S-1-15-2-1",    # ALL APPLICATION PACKAGES
       "S-1-15-2-2"     # ALL RESTRICTED APPLICATION PACKAGES
   )
   $currentUserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
   $broadPrincipals += $currentUserSid

   $writeMask = [int](
       0x00000002 -bor  # FILE_WRITE_DATA
       0x00000004 -bor  # FILE_APPEND_DATA
       0x00000010 -bor  # FILE_WRITE_EA
       0x00000040 -bor  # FILE_DELETE_CHILD
       0x00000100 -bor  # FILE_WRITE_ATTRIBUTES
       0x00010000 -bor  # DELETE
       0x00040000 -bor  # WRITE_DAC
       0x00080000 -bor  # WRITE_OWNER
       0x10000000 -bor  # GENERIC_ALL
       0x40000000       # GENERIC_WRITE
   )

   foreach ($rule in $acl.Access) {
       if ($rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) {
           continue
       }
       try {
           $sid = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
       }
       catch {
           throw "Could not resolve ACL principal on '$Path': $($rule.IdentityReference)"
       }
       if ($sid -notin $broadPrincipals) {
           continue
       }
       $rights = [int]$rule.FileSystemRights
       if (($rights -band $writeMask) -ne 0) {
           throw "Broad principal '$sid' has write-capable ACL rights on '$Path': $($rule.FileSystemRights)"
       }
   }
}

function Assert-PythonSignature {
   param([Parameter(Mandatory = $true)][string]$Path)

   $signature = Get-AuthenticodeSignature -FilePath $Path
   if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
       throw "Authenticode signature is not valid for '$Path': $($signature.Status)"
   }
   if (-not $signature.SignerCertificate.Subject.Contains("Python Software Foundation")) {
       throw "Unexpected signer for '$Path': $($signature.SignerCertificate.Subject)"
   }
}

Assert-Administrator
if (-not [Environment]::Is64BitOperatingSystem -or
   -not [Environment]::Is64BitProcess -or
   $env:PROCESSOR_ARCHITECTURE -ne "AMD64") {
   throw "This preparation script requires a 64-bit AMD64 Windows host and 64-bit PowerShell."
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$requirements = Join-Path $repoRoot "requirements-windows-psec.txt"
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
   throw "PSEC requirements file is missing: $requirements"
}

$programFilesRoot = [Environment]::GetEnvironmentVariable("ProgramW6432")
if ([string]::IsNullOrWhiteSpace($programFilesRoot)) {
   $programFilesRoot = [Environment]::GetFolderPath("ProgramFiles")
}
$programFilesRoot = [System.IO.Path]::GetFullPath($programFilesRoot)
$dcpRoot = Join-Path $programFilesRoot "DCP"
$baseRuntime = Join-Path $dcpRoot "Python312"
$basePython = Join-Path $baseRuntime "python.exe"
$venvRoot = Join-Path $baseRuntime "venvs\psec"
$venvPython = Join-Path $venvRoot "Scripts\python.exe"
$venvConfig = Join-Path $venvRoot "pyvenv.cfg"

Assert-TrustedAcl -Path $programFilesRoot
Assert-NoReparsePath -Path $dcpRoot
if (-not (Test-Path -LiteralPath $dcpRoot -PathType Container)) {
   New-Item -ItemType Directory -Path $dcpRoot | Out-Null
}
Assert-TrustedAcl -Path $dcpRoot

if (-not (Test-Path -LiteralPath $baseRuntime)) {
   $downloadRoot = Join-Path $env:TEMP "dcp-psec-python312"
   New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
   $installer = Join-Path $downloadRoot "python-3.12.10-amd64.exe"
   $installerUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"

   Invoke-WebRequest -Uri $installerUrl -OutFile $installer -UseBasicParsing
   Assert-PythonSignature -Path $installer

   $arguments = '/quiet InstallAllUsers=1 TargetDir="' + $baseRuntime +
       '" Include_launcher=0 Include_test=0 Include_pip=1 Include_doc=0 ' +
       'Include_tcltk=0 PrependPath=0 AppendPath=0 Shortcuts=0'
   $install = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
   if ($install.ExitCode -ne 0) {
       throw "Python 3.12.10 installer failed with exit code $($install.ExitCode)"
   }
}
elseif (-not (Test-Path -LiteralPath $basePython -PathType Leaf)) {
   throw "The trusted runtime directory already exists but has no python.exe. Refusing to overwrite it: $baseRuntime"
}

Assert-TrustedAcl -Path $baseRuntime
$pythonDll = Join-Path $baseRuntime "python312.dll"
$python3Dll = Join-Path $baseRuntime "python3.dll"
$stdlib = Join-Path $baseRuntime "Lib"
foreach ($requiredPath in @($basePython, $pythonDll, $python3Dll, (Join-Path $stdlib "os.py"), (Join-Path $stdlib "encodings\__init__.py"))) {
   if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
       throw "Trusted Python runtime is incomplete: $requiredPath"
   }
   Assert-TrustedAcl -Path $requiredPath
}
Assert-TrustedAcl -Path $stdlib
Assert-PythonSignature -Path $basePython

$versionOutput = & $basePython -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
if ($LASTEXITCODE -ne 0 -or $versionOutput.Trim() -ne "3.12.10") {
   throw "Expected trusted Base Python 3.12.10; got '$versionOutput'."
}

$venvParent = Split-Path -Parent $venvRoot
Assert-NoReparsePath -Path $venvParent
if (-not (Test-Path -LiteralPath $venvRoot)) {
   New-Item -ItemType Directory -Path $venvParent -Force | Out-Null
   & $basePython -m venv $venvRoot
   if ($LASTEXITCODE -ne 0) {
       throw "Creating the trusted PSEC virtual environment failed."
   }
}
elseif (-not (Test-Path -LiteralPath $venvPython -PathType Leaf) -or
       -not (Test-Path -LiteralPath $venvConfig -PathType Leaf)) {
   throw "The trusted PSEC virtual environment exists but is incomplete. Refusing to overwrite it."
}

Assert-TrustedAcl -Path $venvRoot
Assert-TrustedAcl -Path $venvPython
$homeEntries = @(
   Get-Content -LiteralPath $venvConfig |
       Where-Object { $_ -match '^\s*home\s*=' } |
       ForEach-Object { ($_ -split '=', 2)[1].Trim() }
)
if ($homeEntries.Count -ne 1 -or
   [System.IO.Path]::GetFullPath($homeEntries[0]) -ine [System.IO.Path]::GetFullPath($baseRuntime)) {
   throw "Trusted venv pyvenv.cfg does not point to the protected Base Python runtime."
}

$runtimeJson = & $venvPython -c "import json,sys,sysconfig; print(json.dumps({'executable':sys.executable,'base_executable':getattr(sys,'_base_executable',None),'prefix':sys.prefix,'base_prefix':sys.base_prefix,'stdlib':sysconfig.get_path('stdlib')}))"
if ($LASTEXITCODE -ne 0) {
   throw "Trusted venv interpreter self-check failed."
}
$runtime = $runtimeJson | ConvertFrom-Json
if ([System.IO.Path]::GetFullPath($runtime.base_prefix) -ine [System.IO.Path]::GetFullPath($baseRuntime) -or
   [System.IO.Path]::GetFullPath($runtime.stdlib) -ine [System.IO.Path]::GetFullPath($stdlib)) {
   throw "Trusted venv resolves an unexpected Base Python or standard-library location."
}

& $venvPython -m pip install --disable-pip-version-check -r $requirements
if ($LASTEXITCODE -ne 0) {
   throw "Installing Windows PSEC runtime dependencies failed."
}

& $venvPython -m unittest discover -s tests -p "test_windows_psec*.py" -v
if ($LASTEXITCODE -ne 0) {
   throw "Windows PSEC unit/regression suite failed."
}

$probeStdout = Join-Path $env:TEMP "dcp-psec-runtime-probe.stdout.json"
$probeStderr = Join-Path $env:TEMP "dcp-psec-runtime-probe.stderr.log"
Remove-Item -LiteralPath $probeStdout, $probeStderr -Force -ErrorAction SilentlyContinue
$probe = Start-Process -FilePath $venvPython -ArgumentList @("-m", "tools.local_runner_agent.windows_psec") -NoNewWindow -Wait -PassThru -RedirectStandardOutput $probeStdout -RedirectStandardError $probeStderr
if ($probe.ExitCode -ne 0) {
   throw "Trusted-runtime PSEC API probe failed with exit code $($probe.ExitCode). See $probeStderr"
}
$probeEvidence = Get-Content -LiteralPath $probeStdout -Raw | ConvertFrom-Json
if ($probeEvidence.state -ne "READY_FOR_ACCEPTANCE") {
   throw "PSEC API is not READY_FOR_ACCEPTANCE on this host: $($probeEvidence.reason)"
}

if ([string]::IsNullOrWhiteSpace($AcceptanceParent)) {
   $AcceptanceParent = Join-Path $dcpRoot "PSEC-Acceptance"
}
$AcceptanceParent = [System.IO.Path]::GetFullPath($AcceptanceParent)
Assert-NoReparsePath -Path $AcceptanceParent
if (-not (Test-Path -LiteralPath $AcceptanceParent -PathType Container)) {
   New-Item -ItemType Directory -Path $AcceptanceParent -Force | Out-Null
}
$env:DCP_PSEC_ACCEPTANCE_PARENT = $AcceptanceParent

$head = (& git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -notmatch "^[0-9a-f]{40}$") {
   throw "Cannot determine the exact repository HEAD; refusing to record acceptance evidence."
}

$acceptanceStdout = Join-Path $env:TEMP "dcp-psec-runtime-acceptance.stdout.json"
$acceptanceStderr = Join-Path $env:TEMP "dcp-psec-runtime-acceptance.stderr.log"
Remove-Item -LiteralPath $acceptanceStdout, $acceptanceStderr -Force -ErrorAction SilentlyContinue
$acceptance = Start-Process -FilePath $venvPython -ArgumentList @("-m", "tools.local_runner_agent.windows_psec_host_acceptance") -NoNewWindow -Wait -PassThru -RedirectStandardOutput $acceptanceStdout -RedirectStandardError $acceptanceStderr

try {
   $evidence = Get-Content -LiteralPath $acceptanceStdout -Raw | ConvertFrom-Json
}
catch {
   throw "PSEC host acceptance did not produce valid JSON. stdout=$acceptanceStdout stderr=$acceptanceStderr"
}

$evidence | Add-Member -Force -NotePropertyName repository_head -NotePropertyValue $head
$evidence | Add-Member -Force -NotePropertyName runner_exit_code -NotePropertyValue $acceptance.ExitCode
$artifactDirectory = Join-Path $repoRoot "artifacts"
if (-not (Test-Path -LiteralPath $artifactDirectory -PathType Container)) {
   New-Item -ItemType Directory -Path $artifactDirectory | Out-Null
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$artifactPath = Join-Path $artifactDirectory "windows-psec-trusted-runtime-acceptance-$stamp-$($head.Substring(0,12)).json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($artifactPath, ($evidence | ConvertTo-Json -Depth 30), $utf8NoBom)

Write-Output "Trusted Base Python: $basePython"
Write-Output "Trusted venv Python: $venvPython"
Write-Output "Acceptance parent: $AcceptanceParent"
Write-Output "Repository HEAD: $head"
Write-Output "Acceptance state: $($evidence.state)"
Write-Output "Evidence file: $artifactPath"

if ($acceptance.ExitCode -ne 0 -or $evidence.state -ne "PASS") {
   throw "Target-host PSEC acceptance did not PASS. See $artifactPath and $acceptanceStderr. Production VERIFIED remains closed."
}

Write-Output "PASS: Trusted Python runtime, venv, regression suite, PSEC API probe, and target-host acceptance."
