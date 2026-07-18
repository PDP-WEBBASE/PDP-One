#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstalledRoot = "",
    [string]$CurrentSourceRoot = "",
    [switch]$CompactWsl
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($CurrentSourceRoot)) {
    $CurrentSourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Test-DockerReady {
    cmd /c "docker info >nul 2>&1"
    return $LASTEXITCODE -eq 0
}

function Find-Rdctl {
    $command = Get-Command rdctl.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $base = "C:\Program Files\Rancher Desktop"
    if (Test-Path -LiteralPath $base) {
        $match = Get-ChildItem -LiteralPath $base -Filter "rdctl.exe" -File -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($match) { return $match.FullName }
    }
    return $null
}

function Start-RancherDesktopAndWait([int]$TimeoutSeconds = 240) {
    if (Test-DockerReady) { return $true }

    Write-Host "Rancher Desktop is not ready. Starting it automatically ..." -ForegroundColor Yellow
    $rdctl = Find-Rdctl
    if ($rdctl) {
        $previousErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $rdctl start --application.start-in-background 2>&1 | Out-Host
        } finally {
            $ErrorActionPreference = $previousErrorAction
        }
    }

    if (-not (Get-Process -Name "Rancher Desktop" -ErrorAction SilentlyContinue)) {
        $desktopExe = "C:\Program Files\Rancher Desktop\Rancher Desktop.exe"
        if (Test-Path -LiteralPath $desktopExe) {
            Start-Process -FilePath $desktopExe -ArgumentList @(
                "--containerEngine.name", "moby",
                "--kubernetes.enabled=false"
            )
        }
    }

    $attempts = [Math]::Ceiling($TimeoutSeconds / 3)
    foreach ($attempt in 1..$attempts) {
        if (Test-DockerReady) {
            Write-Host "Rancher Desktop and Moby are ready." -ForegroundColor Green
            return $true
        }
        if (($attempt % 5) -eq 0) {
            Write-Host "Waiting for the Moby engine ... $($attempt * 3) seconds" -ForegroundColor DarkYellow
        }
        Start-Sleep -Seconds 3
    }
    return $false
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

function Get-WslVhdPath([string]$DistributionName) {
    $keys = Get-ChildItem -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss" -ErrorAction SilentlyContinue
    foreach ($key in $keys) {
        if ($key.GetValue("DistributionName") -eq $DistributionName) {
            $basePath = [Environment]::ExpandEnvironmentVariables([string]$key.GetValue("BasePath"))
            $candidate = Join-Path $basePath "ext4.vhdx"
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    return $null
}

function Get-FreeSystemDriveBytes {
    $driveName = $env:SystemDrive.TrimEnd(':')
    return (Get-PSDrive -Name $driveName).Free
}

function Format-Bytes([long]$Bytes) {
    return "{0:N2} GB" -f ($Bytes / 1GB)
}

function Compact-RancherWslDisks {
    Write-Host ""
    Write-Host "Preparing Rancher Desktop WSL disk compaction ..." -ForegroundColor Cyan
    Write-Host "PDP One will be temporarily unavailable during this step." -ForegroundColor Yellow

    if (-not [string]::IsNullOrWhiteSpace($InstalledRoot) -and
        (Test-Path -LiteralPath (Join-Path $InstalledRoot "docker-compose.yml"))) {
        Push-Location $InstalledRoot
        try {
            $previousErrorAction = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            & docker compose stop 2>&1 | Out-Host
            $ErrorActionPreference = $previousErrorAction
        } finally {
            Pop-Location
        }
    }

    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & wsl.exe -d rancher-desktop -u root -- sh -lc "fstrim -av || true" 2>&1 | Out-Host
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }

    $rdctl = Find-Rdctl
    if ($rdctl) {
        $previousErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & $rdctl shutdown 2>&1 | Out-Host
        } finally {
            $ErrorActionPreference = $previousErrorAction
        }
        Start-Sleep -Seconds 8
    } else {
        Get-Process -Name "Rancher Desktop" -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue
    }

    & wsl.exe --shutdown | Out-Host
    Start-Sleep -Seconds 5

    $distributionNames = @("rancher-desktop-data", "rancher-desktop")
    foreach ($distributionName in $distributionNames) {
        $vhdPath = Get-WslVhdPath -DistributionName $distributionName
        if ([string]::IsNullOrWhiteSpace($vhdPath)) {
            Write-Host "No VHDX file found for $distributionName; skipping." -ForegroundColor DarkYellow
            continue
        }

        $beforeSize = (Get-Item -LiteralPath $vhdPath).Length
        Write-Host "Compacting $distributionName ($((Format-Bytes $beforeSize))) ..." -ForegroundColor Cyan

        $previousErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & wsl.exe --manage $distributionName --set-sparse false 2>&1 | Out-Host
        } finally {
            $ErrorActionPreference = $previousErrorAction
        }

        $diskpartScript = Join-Path $env:TEMP ("pdp-one-compact-" + [Guid]::NewGuid().ToString("N") + ".txt")
        try {
            $quotedVhdPath = [char]34 + $vhdPath + [char]34
            [IO.File]::WriteAllLines(
                $diskpartScript,
                @(
                    ("select vdisk file=" + $quotedVhdPath),
                    "compact vdisk",
                    "exit"
                ),
                [Text.Encoding]::ASCII
            )
            & diskpart.exe /s $diskpartScript | Out-Host
        } finally {
            Remove-Item -LiteralPath $diskpartScript -Force -ErrorAction SilentlyContinue
        }

        $previousErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & wsl.exe --manage $distributionName --set-sparse true 2>&1 | Out-Host
        } finally {
            $ErrorActionPreference = $previousErrorAction
        }

        $afterSize = (Get-Item -LiteralPath $vhdPath).Length
        Write-Host "VHDX size: $(Format-Bytes $beforeSize) -> $(Format-Bytes $afterSize)" -ForegroundColor Green
    }

    Write-Host "Restarting Rancher Desktop and PDP One ..." -ForegroundColor Cyan
    if (-not (Start-RancherDesktopAndWait -TimeoutSeconds 300)) {
        Write-Host "Compaction completed, but Rancher Desktop did not restart automatically. Open it manually." -ForegroundColor Yellow
        return
    }

    if (-not [string]::IsNullOrWhiteSpace($InstalledRoot) -and
        (Test-Path -LiteralPath (Join-Path $InstalledRoot "docker-compose.yml"))) {
        Push-Location $InstalledRoot
        try {
            & docker compose up --detach | Out-Host
        } finally {
            Pop-Location
        }
    }
}

$freeBefore = Get-FreeSystemDriveBytes
Write-Host "PDP One safe disk cleanup 2026.07.18.2" -ForegroundColor Green
Write-Host "Database volumes and private-file volumes are protected and will not be removed." -ForegroundColor DarkGreen
Write-Host "Free space before cleanup: $(Format-Bytes $freeBefore)" -ForegroundColor Cyan

$dockerWasReady = Start-RancherDesktopAndWait
if ($dockerWasReady -and [string]::IsNullOrWhiteSpace($InstalledRoot)) {
    $containerId = docker ps -a --filter "label=com.docker.compose.project=pdp-one" --filter "label=com.docker.compose.service=nginx" --format "{{.ID}}" 2>$null |
        Select-Object -First 1
    if (-not [string]::IsNullOrWhiteSpace($containerId)) {
        try {
            $inspect = @((docker inspect $containerId | ConvertFrom-Json))[0]
            $detectedRoot = $inspect.Config.Labels.'com.docker.compose.project.working_dir'
            if (-not [string]::IsNullOrWhiteSpace($detectedRoot) -and (Test-Path -LiteralPath $detectedRoot)) {
                $InstalledRoot = (Resolve-Path -LiteralPath $detectedRoot).Path
                Write-Host "Detected PDP One installation: $InstalledRoot" -ForegroundColor DarkGreen
            }
        } catch {
            Write-Host "The installed project folder could not be detected; persistent Docker volumes remain protected." -ForegroundColor Yellow
        }
    }
}
if ($dockerWasReady) {
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
    Write-Host "Rancher Desktop could not be started; Docker cleanup was skipped." -ForegroundColor Yellow
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

if ($CompactWsl -and $dockerWasReady) {
    Compact-RancherWslDisks
}

$freeAfter = Get-FreeSystemDriveBytes
$reclaimed = $freeAfter - $freeBefore
Write-Host ""
Write-Host "Free space after cleanup: $(Format-Bytes $freeAfter)" -ForegroundColor Green
Write-Host "Space returned to Windows in this run: $(Format-Bytes $reclaimed)" -ForegroundColor Green
Write-Host "Cleanup completed. PDP One databases and persistent volumes were not touched." -ForegroundColor Green
