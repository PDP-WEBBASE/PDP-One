#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [ValidateSet("startup", "predeploy", "postdeploy", "scheduled", "emergency")][string]$Mode = "scheduled",
    [int]$CleanupThresholdGB = 10,
    [int]$TargetFreeGB = 15,
    [int]$CriticalFreeGB = 3,
    [int]$BuildCacheBudgetGB = 2,
    [int]$KeepLocalFinalBackups = 2,
    [string]$ProjectRoot = "",
    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent",
    [string]$BackupRoot = "C:\ProgramData\PDP-One\backups",
    [string]$ExternalBackupRoot = "D:\BackUp PDP-0NE-14050429-01"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

$mutex = New-Object Threading.Mutex($false, "Global\PDP-One-Disk-Guard")
if (-not $mutex.WaitOne(0)) { exit 0 }

function Get-PDPOneFreeBytes {
    return [int64](Get-PSDrive -Name C -ErrorAction Stop).Free
}

function Get-PDPOneDirectoryBytes([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return [int64]0 }
    $value = (Get-ChildItem -LiteralPath $Path -File -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    if ($null -eq $value) { return [int64]0 }
    return [int64]$value
}

function Invoke-PDPOneSafeNative([string]$Command, [string[]]$Arguments, [switch]$IgnoreFailure) {
    $previous = $ErrorActionPreference
    $output = @()
    $code = -1
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $Command @Arguments 2>&1)
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0 -and -not $IgnoreFailure) {
        $message = ConvertTo-PDPOneRedactedText (($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
        throw "$Command failed with exit code $code. $message"
    }
    return [pscustomobject]@{ ExitCode = $code; Output = @($output) }
}

function Remove-PDPOneOldDirectoryChildren([string]$Path, [datetime]$OlderThan, [ref]$Removed) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Get-ChildItem -LiteralPath $Path -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $OlderThan } |
        ForEach-Object {
            try {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
                $Removed.Value += $_.FullName
            } catch { }
        }
}

function Remove-PDPOneOldFiles([string]$Path, [datetime]$OlderThan, [ref]$Removed) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    Get-ChildItem -LiteralPath $Path -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $OlderThan } |
        ForEach-Object {
            try {
                Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop
                $Removed.Value += $_.FullName
            } catch { }
        }
}

function Get-PDPOneVerifiedBackupReport([string]$Path) {
    $reportPath = Join-Path $Path "backup-report.json"
    if (-not (Test-Path -LiteralPath $reportPath)) { return $null }
    try {
        $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not [bool]$report.restore_verified) { return $null }
        return $report
    } catch { return $null }
}

function Test-PDPOneArchivedBackup([string]$Source, [string]$Destination, $Report) {
    if ($null -ne $Report.file_sha256) {
        foreach ($property in $Report.file_sha256.PSObject.Properties) {
            $target = Join-Path $Destination $property.Name
            if (-not (Test-Path -LiteralPath $target)) { return $false }
            $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne ([string]$property.Value).ToLowerInvariant()) { return $false }
        }
        return $true
    }
    return (Get-PDPOneDirectoryBytes $Source) -eq (Get-PDPOneDirectoryBytes $Destination)
}

function Invoke-PDPOneBackupRetention([ref]$Archived, [ref]$Removed) {
    if (-not (Test-Path -LiteralPath $BackupRoot)) { return }
    if ($KeepLocalFinalBackups -lt 2) { throw "At least two verified final backups must remain local." }

    $protected = ""
    $lastDeployment = Join-Path $AgentRoot "state\last-deployment.json"
    if (Test-Path -LiteralPath $lastDeployment) {
        try {
            $state = Get-Content -LiteralPath $lastDeployment -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($state.backup_path -and (Test-Path -LiteralPath ([string]$state.backup_path))) {
                $protected = (Resolve-Path -LiteralPath ([string]$state.backup_path)).Path.TrimEnd('\')
            }
        } catch { }
    }

    $verified = @()
    Get-ChildItem -LiteralPath $BackupRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^PDP-One-final-Backup-\d{8}-\d{6}$' } |
        Sort-Object Name -Descending |
        ForEach-Object {
            $backupReport = Get-PDPOneVerifiedBackupReport $_.FullName
            if ($null -ne $backupReport) {
                $verified += [pscustomobject]@{ Directory = $_; Report = $backupReport }
            }
        }

    $keep = @{}
    foreach ($item in @($verified | Select-Object -First $KeepLocalFinalBackups)) {
        $keep[$item.Directory.FullName.TrimEnd('\').ToLowerInvariant()] = $true
    }
    if ($protected) { $keep[$protected.ToLowerInvariant()] = $true }

    $driveRoot = Split-Path -Qualifier $ExternalBackupRoot
    $externalAvailable = $driveRoot -and (Test-Path -LiteralPath $driveRoot)
    if ($externalAvailable) { New-Item -ItemType Directory -Force -Path $ExternalBackupRoot | Out-Null }

    foreach ($item in $verified) {
        $source = $item.Directory.FullName.TrimEnd('\')
        if ($keep.ContainsKey($source.ToLowerInvariant())) { continue }
        if (-not $externalAvailable) { break }

        $destination = Join-Path $ExternalBackupRoot $item.Directory.Name
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        & robocopy.exe $source $destination /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP | Out-Null
        if ($LASTEXITCODE -gt 7) { continue }
        if (-not (Test-PDPOneArchivedBackup -Source $source -Destination $destination -Report $item.Report)) { continue }
        Remove-Item -LiteralPath $source -Recurse -Force
        $Archived.Value += $destination
        $Removed.Value += $source
    }
}

function Get-PDPOneRetainedImageReferences {
    $keep = @{}
    $statePath = Join-Path $AgentRoot "state\last-deployment.json"
    if (-not (Test-Path -LiteralPath $statePath)) { return $keep }

    try {
        $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($commit in @([string]$state.approved_commit, [string]$state.previous_commit)) {
            if ($commit -notmatch '^[0-9a-f]{40}$') { continue }
            foreach ($service in @("backend", "mcp", "web")) {
                $keep[("ghcr.io/pdp-webbase/pdp-one-{0}:{1}" -f $service, $commit).ToLowerInvariant()] = $true
            }
        }
    } catch { }
    return $keep
}

function Invoke-PDPOneImageRetention([ref]$RemovedImages, [ref]$DockerActions) {
    $keep = Get-PDPOneRetainedImageReferences
    $references = @(& docker image ls --format "{{.Repository}}:{{.Tag}}" 2>$null)

    foreach ($raw in $references) {
        $reference = ([string]$raw).Trim()
        if (-not $reference -or $reference.EndsWith(":<none>")) { continue }
        $lower = $reference.ToLowerInvariant()
        $isRegistryImage = $lower -match '^ghcr\.io/pdp-webbase/pdp-one-(backend|mcp|web):[0-9a-f]{40}$'
        $isLegacyImage = $lower -match '^pdp-one-(backend|mcp|web):(candidate-[0-9a-f]+|local)$'
        if (-not $isRegistryImage -and -not $isLegacyImage) { continue }
        if ($keep.ContainsKey($lower)) { continue }

        $result = Invoke-PDPOneSafeNative -Command "docker" -Arguments @("image", "rm", $reference) -IgnoreFailure
        $DockerActions.Value += $result
        if ($result.ExitCode -eq 0) { $RemovedImages.Value += $reference }
    }

    $DockerActions.Value += (Invoke-PDPOneSafeNative -Command "docker" -Arguments @("image", "prune", "--force") -IgnoreFailure)
}

function Get-PDPOneRancherVhdFiles {
    $roots = @(
        (Join-Path $env:LOCALAPPDATA "rancher-desktop"),
        (Join-Path $env:LOCALAPPDATA "Rancher Desktop")
    ) | Select-Object -Unique
    $files = @()
    foreach ($root in $roots) {
        if (Test-Path -LiteralPath $root) {
            $files += @(Get-ChildItem -LiteralPath $root -Filter *.vhdx -File -Recurse -Force -ErrorAction SilentlyContinue)
        }
    }
    return @($files | Sort-Object FullName -Unique)
}

function Invoke-PDPOneVhdCompact([string]$Path) {
    if (Get-Command Optimize-VHD -ErrorAction SilentlyContinue) {
        Optimize-VHD -Path $Path -Mode Full -ErrorAction Stop
        return "Optimize-VHD"
    }
    $scriptPath = Join-Path $env:TEMP ("pdp-one-diskpart-" + [Guid]::NewGuid().ToString('N') + ".txt")
    try {
        @(
            "select vdisk file=`"$Path`"",
            "compact vdisk",
            "exit"
        ) | Set-Content -LiteralPath $scriptPath -Encoding ASCII
        Invoke-PDPOneSafeNative -Command "diskpart.exe" -Arguments @("/s", $scriptPath) | Out-Null
        return "diskpart"
    } finally {
        Remove-Item -LiteralPath $scriptPath -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-PDPOneRancherCompaction([ref]$Compacted) {
    $vhdFiles = @(Get-PDPOneRancherVhdFiles)
    if ($vhdFiles.Count -eq 0) { return }

    $servicesWereRunning = $false
    if (Test-PDPOneDockerEngine) {
        try {
            Set-Location $ProjectRoot
            $running = @(& docker compose --profile tunnel ps --status running -q 2>$null)
            $servicesWereRunning = $running.Count -gt 0
            foreach ($distro in @("rancher-desktop-data", "rancher-desktop")) {
                & wsl.exe -d $distro -u root -- sh -lc "fstrim -av >/dev/null 2>&1 || true" 2>$null | Out-Null
            }
        } catch { }
    }

    $rdctl = Get-Command rdctl.exe -ErrorAction SilentlyContinue
    if ($rdctl) { try { & $rdctl.Source shutdown *> $null } catch { } }
    try { & wsl.exe --shutdown *> $null } catch { }
    Start-Sleep -Seconds 5

    foreach ($file in $vhdFiles) {
        try {
            $beforeLength = [int64]$file.Length
            $method = Invoke-PDPOneVhdCompact -Path $file.FullName
            $file.Refresh()
            $Compacted.Value += [pscustomobject]@{
                path = $file.FullName
                method = $method
                bytes_before = $beforeLength
                bytes_after = [int64]$file.Length
            }
        } catch { }
    }

    if ($servicesWereRunning -or $Mode -eq "emergency") {
        Start-PDPOneRancherDesktop -TimeoutSeconds 300
        Set-Location $ProjectRoot
        & docker compose --profile tunnel up --detach --no-build --pull never
        if ($LASTEXITCODE -ne 0) { throw "PDP One services could not restart after VHD compaction." }
    }
}

if (-not $ProjectRoot) { $ProjectRoot = Get-PDPOneProjectRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$maintenanceRoot = "C:\ProgramData\PDP-One\maintenance"
New-Item -ItemType Directory -Force -Path $maintenanceRoot | Out-Null
$reportPath = Join-Path $maintenanceRoot ("disk-guard-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")

$removedHostPaths = @()
$removedImages = @()
$archivedBackups = @()
$removedBackups = @()
$compactedVhds = @()
$dockerActions = @()
$warnings = @()
$beforeFree = Get-PDPOneFreeBytes
$cleanupThreshold = [int64]$CleanupThresholdGB * 1GB
$targetFree = [int64]$TargetFreeGB * 1GB
$criticalFree = [int64]$CriticalFreeGB * 1GB
$cacheBudget = [Math]::Max(1, $BuildCacheBudgetGB).ToString() + "GB"
$mustClean = $Mode -in @("predeploy", "postdeploy", "scheduled", "emergency") -or $beforeFree -lt $cleanupThreshold

try {
    if ($mustClean) {
        $agentAge = if ($Mode -eq "postdeploy") { (Get-Date).AddMinutes(-1) } elseif ($Mode -in @("predeploy", "emergency")) { (Get-Date).AddMinutes(-20) } else { (Get-Date).AddHours(-6) }
        Remove-PDPOneOldDirectoryChildren -Path (Join-Path $AgentRoot "downloads") -OlderThan $agentAge -Removed ([ref]$removedHostPaths)
        Remove-PDPOneOldDirectoryChildren -Path (Join-Path $AgentRoot "staging") -OlderThan $agentAge -Removed ([ref]$removedHostPaths)
        Remove-PDPOneOldFiles -Path (Join-Path $AgentRoot "reports") -OlderThan (Get-Date).AddDays(-14) -Removed ([ref]$removedHostPaths)
        Remove-PDPOneOldDirectoryChildren -Path (Join-Path $ProjectRoot "work\reports") -OlderThan (Get-Date).AddDays(-14) -Removed ([ref]$removedHostPaths)
        Remove-PDPOneOldFiles -Path $maintenanceRoot -OlderThan (Get-Date).AddDays(-14) -Removed ([ref]$removedHostPaths)

        try {
            Start-PDPOneRancherDesktop -TimeoutSeconds 300
            $dockerActions += (Invoke-PDPOneSafeNative -Command "docker" -Arguments @("container", "prune", "--force") -IgnoreFailure)
            Invoke-PDPOneImageRetention -RemovedImages ([ref]$removedImages) -DockerActions ([ref]$dockerActions)
            $dockerActions += (Invoke-PDPOneSafeNative -Command "docker" -Arguments @("builder", "prune", "--all", "--force", "--keep-storage", $cacheBudget) -IgnoreFailure)
            $dockerActions += (Invoke-PDPOneSafeNative -Command "docker" -Arguments @("network", "prune", "--force") -IgnoreFailure)
        } catch {
            $warnings += ConvertTo-PDPOneRedactedText $_.Exception.Message
        }

        try {
            Invoke-PDPOneBackupRetention -Archived ([ref]$archivedBackups) -Removed ([ref]$removedBackups)
        } catch {
            $warnings += ConvertTo-PDPOneRedactedText $_.Exception.Message
        }

        $afterPrune = Get-PDPOneFreeBytes
        if ($Mode -in @("scheduled", "emergency") -and $afterPrune -lt $criticalFree) {
            try {
                Invoke-PDPOneRancherCompaction -Compacted ([ref]$compactedVhds)
            } catch {
                $warnings += ConvertTo-PDPOneRedactedText $_.Exception.Message
            }
        }
    }

    $afterFree = Get-PDPOneFreeBytes
    $status = if ($afterFree -ge $targetFree) { "healthy" } elseif ($afterFree -ge $criticalFree) { "degraded" } else { "critical" }

    $report = [ordered]@{
        schema = "pdp-one.disk-guard.v3"
        mode = $Mode
        completed_at = [DateTime]::UtcNow.ToString("o")
        c_free_bytes_before = $beforeFree
        c_free_bytes_after = $afterFree
        c_free_bytes_delta = $afterFree - $beforeFree
        cleanup_threshold_gb = $CleanupThresholdGB
        target_free_gb = $TargetFreeGB
        build_cache_budget_gb = $BuildCacheBudgetGB
        image_retention = "active_commit_and_previous_commit"
        status = $status
        capacity_gate_enforced = $false
        deployment_allowed = $true
        actual_write_failure_stops_deployment = $true
        removed_host_paths = $removedHostPaths
        removed_obsolete_images = $removedImages
        archived_verified_backups = $archivedBackups
        removed_local_verified_backups = $removedBackups
        compacted_rancher_vhds = $compactedVhds
        docker_action_count = $dockerActions.Count
        warnings = $warnings
        volumes_pruned = $false
        database_volume_touched = $false
        private_files_volume_touched = $false
        tailscale_volume_touched = $false
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output $reportPath

    if ($status -eq "critical") {
        Write-Warning "C: free space is critical, but the disk guard is advisory. PDP One will continue until Windows or Docker reports an actual write failure."
    }
} catch {
    $fallback = [ordered]@{
        schema = "pdp-one.disk-guard.v3"
        mode = $Mode
        completed_at = [DateTime]::UtcNow.ToString("o")
        status = "guard_error"
        build_cache_budget_gb = $BuildCacheBudgetGB
        capacity_gate_enforced = $false
        deployment_allowed = $true
        error = ConvertTo-PDPOneRedactedText $_.Exception.Message
        volumes_pruned = $false
        database_volume_touched = $false
        private_files_volume_touched = $false
        tailscale_volume_touched = $false
    }
    try { $fallback | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8 } catch { }
    Write-Warning "Disk guard could not complete, but it will not block startup or deployment."
    Write-Output $reportPath
    if ($Mode -eq "emergency") { exit 1 }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
