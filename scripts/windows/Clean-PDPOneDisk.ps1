#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstalledRoot = "",
    [string]$CurrentSourceRoot = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Test-DockerReady {
    cmd /c "docker info >nul 2>&1"
    return $LASTEXITCODE -eq 0
}

function Invoke-DockerCleanup([string[]]$Arguments) {
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker @Arguments | Out-Host
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
}

function Test-ProtectedPath([string]$Candidate, [string[]]$ProtectedRoots) {
    $candidateFull = [IO.Path]::GetFullPath($Candidate).TrimEnd('\')
    foreach ($root in $ProtectedRoots) {
        if ([string]::IsNullOrWhiteSpace($root)) { continue }
        $rootFull = [IO.Path]::GetFullPath($root).TrimEnd('\')
        if ($candidateFull.Equals($rootFull, [StringComparison]::OrdinalIgnoreCase)) { return $true }
        if ($candidateFull.StartsWith($rootFull + '\', [StringComparison]::OrdinalIgnoreCase)) { return $true }
        if ($rootFull.StartsWith($candidateFull + '\', [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

function Send-FileToRecycleBin([string]$Path) {
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
        $Path,
        [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
        [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
    )
}

function Send-DirectoryToRecycleBin([string]$Path) {
    [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
        $Path,
        [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
        [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
    )
}

Write-Host "PDP One safe disk cleanup" -ForegroundColor Green
Write-Host "Database volumes and private-file volumes are protected and will not be removed." -ForegroundColor DarkGreen

if ((Get-Command docker -ErrorAction SilentlyContinue) -and (Test-DockerReady)) {
    Write-Host ""
    Write-Host "Docker usage before cleanup:" -ForegroundColor Cyan
    & docker system df | Out-Host

    Write-Host "Removing stopped PDP One containers ..." -ForegroundColor Cyan
    Invoke-DockerCleanup @("container", "prune", "--force", "--filter", "label=com.docker.compose.project=pdp-one") | Out-Null

    Write-Host "Removing dangling image layers ..." -ForegroundColor Cyan
    Invoke-DockerCleanup @("image", "prune", "--force") | Out-Null

    Write-Host "Removing unused Docker build cache ..." -ForegroundColor Cyan
    Invoke-DockerCleanup @("builder", "prune", "--all", "--force") | Out-Null

    Write-Host ""
    Write-Host "Docker usage after cleanup:" -ForegroundColor Cyan
    & docker system df | Out-Host
} else {
    Write-Host "Docker is not ready; package cleanup will continue." -ForegroundColor Yellow
}

$downloads = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads"
if (Test-Path -LiteralPath $downloads) {
    Add-Type -AssemblyName Microsoft.VisualBasic
    $protected = @($InstalledRoot, $CurrentSourceRoot)
    $recycledCount = 0

    Write-Host ""
    Write-Host "Moving obsolete PDP One download packages to Recycle Bin ..." -ForegroundColor Cyan

    $archives = Get-ChildItem -LiteralPath $downloads -File -Recurse -Filter "PDP-One-main*.zip" -ErrorAction SilentlyContinue
    foreach ($archive in $archives) {
        try {
            Send-FileToRecycleBin $archive.FullName
            $recycledCount++
            Write-Host "Recycled archive: $($archive.FullName)" -ForegroundColor DarkGray
        } catch {
            Write-Host "Could not recycle: $($archive.FullName)" -ForegroundColor Yellow
        }
    }

    $candidateDirectories = Get-ChildItem -LiteralPath $downloads -Directory -Recurse -Filter "PDP-One-main*" -ErrorAction SilentlyContinue |
        Sort-Object { $_.FullName.Length } -Descending

    foreach ($directory in $candidateDirectories) {
        if (-not (Test-Path -LiteralPath $directory.FullName)) { continue }
        if (Test-ProtectedPath -Candidate $directory.FullName -ProtectedRoots $protected) { continue }

        $isPdpPackage =
            (Test-Path -LiteralPath (Join-Path $directory.FullName "docker-compose.yml")) -and
            (Test-Path -LiteralPath (Join-Path $directory.FullName "UPDATE-PDP-ONE.bat")) -and
            (Test-Path -LiteralPath (Join-Path $directory.FullName "scripts\windows\Update-PDPOne.ps1"))

        if (-not $isPdpPackage) { continue }

        try {
            Send-DirectoryToRecycleBin $directory.FullName
            $recycledCount++
            Write-Host "Recycled old source package: $($directory.FullName)" -ForegroundColor DarkGray
        } catch {
            Write-Host "Could not recycle: $($directory.FullName)" -ForegroundColor Yellow
        }
    }

    Write-Host "Download-package cleanup completed. Items recycled: $recycledCount" -ForegroundColor Green
}

Write-Host ""
Write-Host "Cleanup completed. PDP One databases and persistent volumes were not touched." -ForegroundColor Green
