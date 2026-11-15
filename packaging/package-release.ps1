[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$outputDirectory = Join-Path $repositoryRoot 'dist'
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) "DCP-package-$([Guid]::NewGuid().ToString('N'))"
$portableRoot = Join-Path $stageRoot 'DCP'
$pwaArchive = Join-Path $outputDirectory "DCP-PWA-$Version.zip"
$portableArchive = Join-Path $outputDirectory "DCP-Portable-Windows-$Version.zip"
$installer = Join-Path $outputDirectory "Development-Control-Platform-Setup-$Version.exe"

try {
    New-Item -ItemType Directory -Path $portableRoot -Force | Out-Null

    $dashboardPath = Join-Path $repositoryRoot 'dashboard'
    Compress-Archive -Path (Join-Path $dashboardPath '*') -DestinationPath $pwaArchive -CompressionLevel Optimal -Force

    foreach ($directory in @('dashboard', 'tools', 'schemas')) {
        $source = Join-Path $repositoryRoot $directory
        if (-not (Test-Path -LiteralPath $source -PathType Container)) {
            throw "Required package directory is missing: $directory"
        }
        Copy-Item -LiteralPath $source -Destination $portableRoot -Recurse
    }

    $rootFiles = @(
        'Open-DCP-Dashboard.cmd',
        'Run-DCP-Gateway.ps1',
        'Setup-DCP-Local.cmd',
        'Setup-DCP-Local.ps1',
        'Start-DCP-Dashboard.ps1',
        'Start-DCP-Local.cmd',
        'Start-DCP-Local.ps1',
        'requirements-cloud-gateway.txt'
    )
    foreach ($file in $rootFiles) {
        $source = Join-Path $repositoryRoot $file
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Required package file is missing: $file"
        }
        Copy-Item -LiteralPath $source -Destination $portableRoot
    }

    Compress-Archive -Path (Join-Path $portableRoot '*') -DestinationPath $portableArchive -CompressionLevel Optimal -Force

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    foreach ($archivePath in @($pwaArchive, $portableArchive)) {
        $archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
        try {
            $entries = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
            $requiredEntries = if ($archivePath -eq $pwaArchive) {
                @('index.html', 'manifest.webmanifest', 'sw.js', 'icons/dcp.svg')
            } else {
                @('Start-DCP-Local.cmd', 'dashboard/index.html', 'tools/local_auth_proxy.py', 'schemas/project-state.schema.json')
            }
            foreach ($entry in $requiredEntries) {
                if ($entry -notin $entries) {
                    throw "Package archive is missing required entry '$entry': $archivePath"
                }
            }
        } finally {
            $archive.Dispose()
        }
    }

    $compiler = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    $compilerPath = if ($compiler) { $compiler.Source } else {
        $programFilesX86 = [System.Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
        if ($programFilesX86) {
            Join-Path $programFilesX86 'Inno Setup 6\ISCC.exe'
        }
    }
    if (-not $compilerPath -or -not (Test-Path -LiteralPath $compilerPath -PathType Leaf)) {
        throw 'Inno Setup 6 compiler (ISCC.exe) is required to build the Windows installer.'
    }

    $installerScript = Join-Path $repositoryRoot 'packaging\windows\DCP.iss'
    & $compilerPath "/DAppVersion=$Version" $installerScript
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
    }
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        throw "Inno Setup did not produce the expected installer: $installer"
    }
} finally {
    if (Test-Path -LiteralPath $stageRoot -PathType Container) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
}

Write-Output "PWA package: $pwaArchive"
Write-Output "Portable Windows package: $portableArchive"
Write-Output "Windows installer: $installer"
