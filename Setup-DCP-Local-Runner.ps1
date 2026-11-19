# Prepares local Runner credentials and the Gateway's explicit repository allowlist.
# Persisting an allowlist does not enroll a live Runner or enable command execution.
[CmdletBinding()]
param(
    [ValidatePattern('^[a-z0-9_.:-]{1,100}$')]
    [string]$WorkerId = 'windows-local-01',
    [string[]]$TrustedRepository = @()
)

$ErrorActionPreference = 'Stop'
if (-not $env:LOCALAPPDATA) {
    throw 'LOCALAPPDATA is not available for this Windows account.'
}

$repositoryPattern = '^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$'
$workerPattern = '^[a-z0-9_.:-]{1,100}$'
$maxCredentialBytes = 65536
$maxSettingsBytes = 16384

function Get-ExistingRegularFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][long]$MaximumBytes,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item) {
        return $null
    }
    $isReparsePoint = (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
    if ($isReparsePoint -or $item.PSIsContainer) {
        throw "$Label path is not a regular non-reparse file."
    }
    if ($item.Length -gt $MaximumBytes) {
        throw "$Label file exceeds its size limit."
    }
    return $item
}

function Write-ProtectedJsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Value,
        [Parameter(Mandatory = $true)][string]$Identity,
        [Parameter(Mandatory = $true)][long]$MaximumBytes
    )

    $temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    $encoding = [Text.UTF8Encoding]::new($false)
    $json = ConvertTo-Json -InputObject $Value -Compress -Depth 5
    $aclArguments = @(
        $temporary,
        '/inheritance:r',
        '/grant:r',
        "$($Identity):(R,W)",
        '*S-1-5-18:(F)',
        '*S-1-5-32-544:(F)'
    )

    try {
        # Create a new empty file first. Restrict its ACL before writing credential
        # or allowlist content, and never follow a pre-existing temporary path.
        $created = [IO.File]::Open(
            $temporary,
            [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,
            [IO.FileShare]::None
        )
        $created.Dispose()

        & icacls.exe @aclArguments | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not protect the temporary file ACL for '$Path'."
        }

        $bytes = $encoding.GetBytes($json)
        $stream = [IO.File]::Open(
            $temporary,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Write,
            [IO.FileShare]::None
        )
        try {
            $stream.SetLength(0)
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush($true)
        } finally {
            $stream.Dispose()
        }

        Move-Item -LiteralPath $temporary -Destination $Path -Force

        $destination = Get-ExistingRegularFile -Path $Path -MaximumBytes $MaximumBytes -Label 'Protected local DCP'
        if ($null -eq $destination) {
            throw "Protected file '$Path' was not created."
        }
        $destinationAclArguments = @(
            $Path,
            '/inheritance:r',
            '/grant:r',
            "$($Identity):(R,W)",
            '*S-1-5-18:(F)',
            '*S-1-5-32-544:(F)'
        )
        & icacls.exe @destinationAclArguments | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not verify the protected file ACL for '$Path'."
        }

        $aclOutput = (& icacls.exe $Path) -join [Environment]::NewLine
        if ($LASTEXITCODE -ne 0 -or $aclOutput -match 'Everyone|Authenticated Users|BUILTIN\\Users') {
            throw "Protected file '$Path' has a broad or unverifiable ACL."
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

$dataDir = Join-Path $env:LOCALAPPDATA 'DCP'
$existingDataDir = Get-Item -LiteralPath $dataDir -Force -ErrorAction SilentlyContinue
if ($null -ne $existingDataDir -and
    ((($existingDataDir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) -or
     -not $existingDataDir.PSIsContainer)) {
    throw 'Local DCP data directory is not a regular directory.'
}
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
$verifiedDataDir = Get-Item -LiteralPath $dataDir -Force
if ((($verifiedDataDir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) -or
    -not $verifiedDataDir.PSIsContainer) {
    throw 'Local DCP data directory resolved to a reparse point or non-directory.'
}

$credentialFile = Join-Path $dataDir 'runner-tokens.json'
$settingsFile = Join-Path $dataDir 'gateway-local-settings.json'
$tokenMap = @{}
$allowedRepositoryMap = @{}
$settingsFileExists = $false

$existingCredentialItem = Get-ExistingRegularFile -Path $credentialFile -MaximumBytes $maxCredentialBytes -Label 'Existing Runner credential'
if ($null -ne $existingCredentialItem) {
    try {
        $existingTokens = Get-Content -LiteralPath $credentialFile -Raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw 'Existing Runner credential file is invalid JSON; it was not changed.'
    }
    if ($null -eq $existingTokens -or $existingTokens -isnot [pscustomobject]) {
        throw 'Existing Runner credential file must be a JSON object.'
    }

    $seenTokens = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($property in $existingTokens.PSObject.Properties) {
        if ($property.Name -notmatch $workerPattern -or
            $property.Value -isnot [string] -or
            $property.Value.Length -lt 32 -or
            $property.Value.Length -gt 256) {
            throw 'Existing Runner credential file contains an invalid entry; it was not changed.'
        }
        if ($tokenMap.ContainsKey($property.Name)) {
            throw 'Existing Runner credential file contains a duplicate worker ID.'
        }
        if (-not $seenTokens.Add($property.Value)) {
            throw 'Existing Runner credentials must be unique per worker.'
        }
        $tokenMap[$property.Name] = $property.Value
    }
    if ($tokenMap.Count -gt 16) {
        throw 'Existing Runner credential file exceeds the 16-worker limit.'
    }
}

$existingSettingsItem = Get-ExistingRegularFile -Path $settingsFile -MaximumBytes $maxSettingsBytes -Label 'Existing local Gateway settings'
if ($null -ne $existingSettingsItem) {
    try {
        $existingSettings = Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw 'Existing local Gateway settings file is invalid JSON; it was not changed.'
    }
    if ($null -eq $existingSettings -or
        $existingSettings -isnot [pscustomobject] -or
        @($existingSettings.PSObject.Properties).Count -ne 1 -or
        $null -eq $existingSettings.PSObject.Properties['allowed_repositories'] -or
        $existingSettings.allowed_repositories -isnot [System.Array]) {
        throw 'Existing local Gateway settings file has an invalid schema.'
    }
    if ($existingSettings.allowed_repositories.Count -gt 20) {
        throw 'Existing local Gateway repository allowlist exceeds 20 entries.'
    }

    $settingsFileExists = $true
    foreach ($repository in @($existingSettings.allowed_repositories)) {
        if ($repository -isnot [string] -or
            $repository -notmatch $repositoryPattern -or
            @($repository.Split('/')) -contains '.' -or
            @($repository.Split('/')) -contains '..') {
            throw 'Existing local Gateway allowlist contains an invalid repository.'
        }
        if ($allowedRepositoryMap.ContainsKey($repository)) {
            throw 'Existing local Gateway allowlist contains duplicate repository names.'
        }
        $allowedRepositoryMap[$repository] = $repository
    }
}

$requestedRepositories = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($repository in $TrustedRepository) {
    if ($repository -notmatch $repositoryPattern -or
        @($repository.Split('/')) -contains '.' -or
        @($repository.Split('/')) -contains '..') {
        throw "Invalid trusted repository name: $repository"
    }
    if (-not $requestedRepositories.Add($repository)) {
        throw 'Trusted repository entries must be unique (case-insensitive).'
    }

    $matchingKeys = @($allowedRepositoryMap.Keys | Where-Object {
        [string]::Equals($_, $repository, [StringComparison]::OrdinalIgnoreCase)
    })
    if ($matchingKeys.Count -gt 0 -and
        -not [string]::Equals($matchingKeys[0], $repository, [StringComparison]::Ordinal)) {
        throw 'Trusted repository name casing must match the existing Gateway allowlist exactly.'
    }
    $allowedRepositoryMap[$repository] = $repository
}
if ($allowedRepositoryMap.Count -gt 20) {
    throw 'The local Gateway repository allowlist is limited to 20 repositories.'
}

if (-not $tokenMap.ContainsKey($WorkerId)) {
    if ($tokenMap.Count -ge 16) {
        throw 'The local Runner credential file already contains 16 workers.'
    }
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    $tokenMap[$WorkerId] = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$orderedTokens = [ordered]@{}
foreach ($key in ($tokenMap.Keys | Sort-Object)) {
    $orderedTokens[$key] = $tokenMap[$key]
}
Write-ProtectedJsonFile -Path $credentialFile -Value $orderedTokens -Identity $identity -MaximumBytes $maxCredentialBytes

# Do not create an empty allowlist for offline enrollment. Preserve and protect an
# existing settings file, or persist the explicit repositories supplied by Owner.
if ($settingsFileExists -or $allowedRepositoryMap.Count -gt 0) {
    $orderedRepositories = @($allowedRepositoryMap.Keys | Sort-Object)
    $settings = [ordered]@{
        allowed_repositories = $orderedRepositories
    }
    Write-ProtectedJsonFile -Path $settingsFile -Value $settings -Identity $identity -MaximumBytes $maxSettingsBytes
}

Write-Host "Local Runner credential prepared for worker '$WorkerId'."
Write-Host "Credential file: $credentialFile"
Write-Host 'The token is stored with a restricted Windows ACL and was not displayed.'
if ($allowedRepositoryMap.Count -gt 0) {
    Write-Host ('Approved repositories: ' + (($allowedRepositoryMap.Keys | Sort-Object) -join ', '))
}
Write-Host 'Restart the DCP local stack so the Gateway loads the Runner credentials and repository allowlist.'
