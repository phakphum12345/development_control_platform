$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$setup = Join-Path $project 'Setup-DCP-Local-Runner.ps1'
$runnerScript = Join-Path $project 'Start-DCP-Gateway-Runner.ps1'
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    $runnerScript, [ref]$tokens, [ref]$parseErrors
) | Out-Null
if ($parseErrors.Count -gt 0) {
    throw 'Unified Local Runner PowerShell launcher has syntax errors.'
}
$runnerSource = Get-Content -LiteralPath $runnerScript -Raw
if ($runnerSource -notmatch '-m tools\.local_runner_agent' -or
    $runnerSource -match '-m tools\.runner_agent\.agent') {
    throw 'Windows launcher must invoke the unified Local Runner Agent.'
}
$testRoot = Join-Path $env:RUNNER_TEMP 'dcp-local-runner-credential-test'
$previousLocalAppData = $env:LOCALAPPDATA

if (Test-Path -LiteralPath $testRoot) {
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$env:LOCALAPPDATA = $testRoot

try {
    & $setup -WorkerId 'ci-runner-01' -TrustedRepository 'owner/mobile-app'
    if (-not $?) { throw 'Local Runner credential setup failed on first run.' }
    $credentialFile = Join-Path $testRoot 'DCP\runner-tokens.json'
    if (-not (Test-Path -LiteralPath $credentialFile -PathType Leaf)) {
        throw 'Local Runner credential file was not created.'
    }
    $firstMap = Get-Content -LiteralPath $credentialFile -Raw | ConvertFrom-Json
    $firstToken = $firstMap.'ci-runner-01'
    if ($firstToken -isnot [string] -or $firstToken.Length -lt 32) {
        throw 'Generated Runner token is missing or too short.'
    }

    & $setup -WorkerId 'ci-runner-01'
    if (-not $?) { throw 'Local Runner credential setup failed on idempotent run.' }
    $secondMap = Get-Content -LiteralPath $credentialFile -Raw | ConvertFrom-Json
    if ($secondMap.'ci-runner-01' -cne $firstToken) {
        throw 'Setup rotated an existing Runner token unexpectedly.'
    }

    & $setup -WorkerId 'ci-runner-02' -TrustedRepository 'org/another-app'
    if (-not $?) { throw 'Local Runner second-worker setup failed.' }
    $thirdMap = Get-Content -LiteralPath $credentialFile -Raw | ConvertFrom-Json
    if (@($thirdMap.PSObject.Properties).Count -ne 2) {
        throw 'Expected exactly two configured Runner workers.'
    }
    if ($thirdMap.'ci-runner-02' -ceq $firstToken) {
        throw 'Runner workers must receive unique tokens.'
    }

    $settingsFile = Join-Path $testRoot 'DCP\gateway-local-settings.json'
    $gatewaySettings = Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json
    $allowedRepositories = @($gatewaySettings.allowed_repositories)
    if ($allowedRepositories.Count -ne 2 -or
        $allowedRepositories -notcontains 'owner/mobile-app' -or
        $allowedRepositories -notcontains 'org/another-app') {
        throw 'Gateway local repository allowlist was not persisted correctly.'
    }

    $settingsAcl = (& icacls.exe $settingsFile) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0 -or $settingsAcl -match 'Everyone|Authenticated Users|BUILTIN\\Users') {
        throw 'Gateway settings ACL grants access to a broad user group or could not be verified.'
    }

    $acl = (& icacls.exe $credentialFile) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect Runner credential ACL.' }
    if ($acl -match 'Everyone|Authenticated Users|BUILTIN\\Users') {
        throw 'Runner credential ACL grants access to a broad user group.'
    }



    # Invalid and duplicate trust entries must be rejected before replacing
    # either the credential map or the existing Gateway allowlist.
    $settingsBeforeInvalid = (Get-FileHash -LiteralPath $settingsFile -Algorithm SHA256).Hash
    $tokensBeforeInvalid = Get-Content -LiteralPath $credentialFile -Raw
    $invalidRejected = $false
    try {
        & $setup -WorkerId 'ci-runner-03' -TrustedRepository 'owner/../escape'
    } catch {
        $invalidRejected = $true
    }
    if (-not $invalidRejected) {
        throw 'Setup accepted a repository path containing traversal segments.'
    }
    if ((Get-FileHash -LiteralPath $settingsFile -Algorithm SHA256).Hash -ne $settingsBeforeInvalid -or
        (Get-Content -LiteralPath $credentialFile -Raw) -cne $tokensBeforeInvalid) {
        throw 'Rejected repository input changed existing protected settings or credentials.'
    }

    $duplicateRejected = $false
    try {
        & $setup -WorkerId 'ci-runner-03' -TrustedRepository @('owner/mobile-app', 'OWNER/MOBILE-APP')
    } catch {
        $duplicateRejected = $true
    }
    if (-not $duplicateRejected) {
        throw 'Setup accepted duplicate trusted repositories with different casing.'
    }

    # Existing settings must not be read through a reparse point. Some
    # Windows hosts do not grant symlink creation to the current token; in that
    # case record an explicit skip and restore the original file.
    $settingsTarget = $settingsFile + '.target'
    Move-Item -LiteralPath $settingsFile -Destination $settingsTarget
    $symlinkCreated = $false
    try {
        try {
            New-Item -ItemType SymbolicLink -Path $settingsFile -Target $settingsTarget -ErrorAction Stop | Out-Null
            $symlinkCreated = $true
        } catch {
            Write-Warning 'SKIPPED: host did not permit creating a symbolic link for the Gateway settings test.'
        }
        if ($symlinkCreated) {
            $tokensBeforeReparse = (Get-FileHash -LiteralPath $credentialFile -Algorithm SHA256).Hash
            $reparseRejected = $false
            try {
                & $setup -WorkerId 'ci-runner-03'
            } catch {
                $reparseRejected = $true
            }
            if (-not $reparseRejected) {
                throw 'Setup followed a reparse-point Gateway settings file.'
            }
            if ((Get-FileHash -LiteralPath $credentialFile -Algorithm SHA256).Hash -ne $tokensBeforeReparse) {
                throw 'Rejected reparse-point settings changed the Runner credential file.'
            }
        }
    } finally {
        if (Test-Path -LiteralPath $settingsFile) {
            Remove-Item -LiteralPath $settingsFile -Force
        }
        if (Test-Path -LiteralPath $settingsTarget) {
            Move-Item -LiteralPath $settingsTarget -Destination $settingsFile -Force
        }
    }

    # The settings file is bounded independently from Runner credentials.
    [IO.File]::WriteAllText(
        $settingsFile,
        (' ' * 16385),
        [Text.UTF8Encoding]::new($false)
    )
    $oversizedSettingsHash = (Get-FileHash -LiteralPath $settingsFile -Algorithm SHA256).Hash
    $oversizedSettingsRejected = $false
    try {
        & $setup -WorkerId 'ci-runner-03'
    } catch {
        $oversizedSettingsRejected = $true
    }
    if (-not $oversizedSettingsRejected) {
        throw 'Setup accepted an oversized Gateway settings file.'
    }
    if ((Get-FileHash -LiteralPath $settingsFile -Algorithm SHA256).Hash -ne $oversizedSettingsHash) {
        throw 'Rejected oversized Gateway settings changed the original file.'
    }

    # The allowlist has a hard maximum. A failed extension must preserve the
    # existing file rather than silently truncating or partially writing it.
    $twentyRepositories = @(1..20 | ForEach-Object { "owner/repo$_" })
    $twentySettings = [ordered]@{ allowed_repositories = $twentyRepositories }
    [IO.File]::WriteAllText(
        $settingsFile,
        (ConvertTo-Json -InputObject $twentySettings -Compress -Depth 4),
        [Text.UTF8Encoding]::new($false)
    )
    $settingsBeforeLimit = (Get-FileHash -LiteralPath $settingsFile -Algorithm SHA256).Hash
    $limitRejected = $false
    try {
        & $setup -WorkerId 'ci-runner-03' -TrustedRepository 'owner/new-app'
    } catch {
        $limitRejected = $true
    }
    if (-not $limitRejected) {
        throw 'Setup accepted more than 20 trusted repositories.'
    }
    if ((Get-FileHash -LiteralPath $settingsFile -Algorithm SHA256).Hash -ne $settingsBeforeLimit) {
        throw 'Rejected allowlist overflow changed the existing Gateway settings file.'
    }

    # Reject a pre-existing token map that the Gateway itself would refuse.
    $seventeenWorkers = [ordered]@{}
    1..17 | ForEach-Object { $seventeenWorkers["worker-$_"] = [Guid]::NewGuid().ToString('N') }
    [IO.File]::WriteAllText(
        $credentialFile,
        (ConvertTo-Json -InputObject $seventeenWorkers -Compress -Depth 4),
        [Text.UTF8Encoding]::new($false)
    )
    $tokensBeforeWorkerLimit = (Get-FileHash -LiteralPath $credentialFile -Algorithm SHA256).Hash
    $workerLimitRejected = $false
    try {
        & $setup -WorkerId 'ci-runner-03'
    } catch {
        $workerLimitRejected = $true
    }
    if (-not $workerLimitRejected) {
        throw 'Setup accepted a Runner token map with more than 16 workers.'
    }
    if ((Get-FileHash -LiteralPath $credentialFile -Algorithm SHA256).Hash -ne $tokensBeforeWorkerLimit) {
        throw 'Rejected oversized Runner token map changed the existing credential file.'
    }

    Write-Host 'Local Runner credential bootstrap tests passed.'
} finally {
    $env:LOCALAPPDATA = $previousLocalAppData
    if (Test-Path -LiteralPath $testRoot) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
