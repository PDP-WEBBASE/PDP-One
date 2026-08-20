#requires -Version 5.1
[CmdletBinding()]
param([string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent", [switch]$Once, [int]$PollSeconds = 5)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

$mutex = New-Object Threading.Mutex($false, "Global\PDP-One-Deployment-Agent")
if (-not $mutex.WaitOne(0)) { exit 0 }
$restartAfterResponse = $false
$script:PDPOneChangeManagementMode = "standard"

function Test-PDPOneDevelopmentFastMode {
    return $script:PDPOneChangeManagementMode -eq "development_fast"
}

function Write-AgentAudit([string]$RequestId, [string]$Action, [string]$Status, [string]$Message) {
    $entry = [ordered]@{
        at = (Get-Date).ToUniversalTime().ToString("o")
        request_id = $RequestId
        action = $Action
        status = $Status
        message = (ConvertTo-PDPOneRedactedText $Message)
    } | ConvertTo-Json -Compress
    Add-Content -LiteralPath (Join-Path $AgentRoot "audit\deployment-agent.jsonl") -Value $entry -Encoding UTF8
}

function Write-AgentResponse([string]$RequestId, [string]$Action, [string]$Status, $Result) {
    $response = [ordered]@{
        request_id = $RequestId
        action = $Action
        status = $Status
        completed_at = (Get-Date).ToUniversalTime().ToString("o")
        result = $Result
    }
    $target = Join-Path $AgentRoot "queue\responses\$RequestId.json"
    $temporary = "$target.tmp"
    $response | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $target -Force
}

function Test-AgentSignature([byte[]]$PayloadBytes, [string]$Signature, [string]$SigningKey) {
    $hmac = [Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($SigningKey))
    try { $actual = ([BitConverter]::ToString($hmac.ComputeHash($PayloadBytes))).Replace('-', '').ToLowerInvariant() } finally { $hmac.Dispose() }
    return [string]::Equals($actual, $Signature, [StringComparison]::OrdinalIgnoreCase)
}

function Get-SafeBackupPath([string]$BackupId) {
    if ($BackupId -notmatch '^PDP-One-(initial|final|manual)-Backup-\d{8}-\d{6}$') { throw "Invalid backup identifier." }
    $root = "C:\ProgramData\PDP-One\backups"
    $path = Join-Path $root $BackupId
    if (-not (Test-Path -LiteralPath $path)) { throw "Backup was not found." }
    return $path
}

function Assert-SafeIdentifier([string]$Value, [string]$Name) {
    if ($Value -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') { throw "$Name is invalid." }
    return $Value
}

function Invoke-AgentAction($Payload) {
    $action = [string]$Payload.action
    $params = $Payload.params
    $scripts = $PSScriptRoot
    switch ($action) {
        "approve_release" {
            $commit = [string]$params.commit_sha
            $previewId = Assert-SafeIdentifier ([string]$params.preview_id) "preview_id"
            if ($commit -notmatch '^[0-9a-f]{40}$') { throw "Approval commit is invalid." }
            if (-not (Test-PDPOneExplicitDeploymentApproval ([string]$params.approval_text))) { throw "Explicit approval phrase is invalid." }
            $approval = [ordered]@{ commit_sha = $commit; preview_id = $previewId; approved_at = (Get-Date).ToUniversalTime().ToString("o"); expires_at = (Get-Date).ToUniversalTime().AddHours(24).ToString("o") }
            $approval | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $AgentRoot "state\approved-release.json") -Encoding UTF8
            return @{ approved_commit = $commit; preview_id = [string]$params.preview_id; expires_in_hours = 24; deployed = $false }
        }
        "create_final_backup" {
            $commit = [string]$params.commit_sha
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            if ($commit -notmatch '^[0-9a-f]{40}$') { throw "Backup commit is invalid." }
            $output = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "New-PDPOneBackup.ps1") -Kind final -DeploymentId $deploymentId -ApprovedCommit $commit)
            if ($LASTEXITCODE -ne 0) { throw "Final backup creation failed." }
            $path = [string]$output[-1]
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-PDPOneBackupRestore.ps1") -BackupPath $path | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Final backup restore verification failed." }
            $backupState = [ordered]@{
                commit_sha = $commit
                deployment_id = $deploymentId
                backup_path = $path
                backup_id = (Split-Path $path -Leaf)
                restore_verified = $true
                verified_at = (Get-Date).ToUniversalTime().ToString("o")
                expires_at = (Get-Date).ToUniversalTime().AddHours(24).ToString("o")
            }
            $backupState | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $AgentRoot "state\approved-backup.json") -Encoding UTF8
            return @{ backup_id = (Split-Path $path -Leaf); restore_verified = $true; production_changed = $false; reusable_for_deploy = $true }
        }
        "verify_backup_restore" {
            $path = Get-SafeBackupPath ([string]$params.backup_id)
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-PDPOneBackupRestore.ps1") -BackupPath $path | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Backup restore verification failed." }
            return @{ backup_id = ([string]$params.backup_id); restore_verified = $true }
        }
        "deploy_approved_release" {
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            $previewId = Assert-SafeIdentifier ([string]$params.preview_id) "preview_id"
            $commit = [string]$params.commit_sha
            if ($commit -notmatch '^[0-9a-f]{40}$') { throw "Deployment commit is invalid." }
            $developmentFast = Test-PDPOneDevelopmentFastMode
            $approvalPath = Join-Path $AgentRoot "state\approved-release.json"
            $backupStatePath = Join-Path $AgentRoot "state\approved-backup.json"
            $verifiedBackupPath = ""
            $verifiedBackupId = ""

            if (-not $developmentFast) {
                if (-not (Test-Path -LiteralPath $approvalPath)) { throw "No explicit release approval is recorded." }
                $approval = Get-Content -LiteralPath $approvalPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([DateTimeOffset]::Parse($approval.expires_at) -le [DateTimeOffset]::UtcNow) { throw "Release approval expired." }
                if ($approval.commit_sha -ne $commit -or $approval.preview_id -ne $previewId) { throw "Requested deployment does not match the approved preview." }

                if (-not (Test-Path -LiteralPath $backupStatePath)) { throw "No fresh verified final backup is recorded for this deployment." }
                $backupState = Get-Content -LiteralPath $backupStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([DateTimeOffset]::Parse($backupState.expires_at) -le [DateTimeOffset]::UtcNow) { throw "Verified final backup authorization expired." }
                if ([string]$backupState.commit_sha -ne $commit) { throw "Verified final backup commit does not match the approved deployment." }
                if ([string]$backupState.deployment_id -ne $deploymentId) { throw "Verified final backup deployment identifier does not match." }
                if (-not [bool]$backupState.restore_verified -or -not (Test-Path -LiteralPath ([string]$backupState.backup_path))) { throw "Verified final backup is not available." }
                $verifiedBackupPath = [string]$backupState.backup_path
                $verifiedBackupId = [string]$backupState.backup_id
            }

            $deploymentArgs = @(
                "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                (Join-Path $scripts "Invoke-PDPOneDeployment.ps1"),
                "-CommitSha", $commit,
                "-DeploymentId", $deploymentId,
                "-PreviewId", $previewId,
                "-AgentRoot", $AgentRoot
            )
            if ($developmentFast) {
                $deploymentArgs += "-DevelopmentFastMode"
            } else {
                $deploymentArgs += @("-VerifiedBackupPath", $verifiedBackupPath)
            }
            $report = @(& powershell.exe @deploymentArgs)
            if ($LASTEXITCODE -ne 0) { throw "Deployment failed; see the rollback result in the deployment report." }
            Remove-Item -LiteralPath $approvalPath -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $backupStatePath -Force -ErrorAction SilentlyContinue
            return @{
                deployment_id = $deploymentId
                commit_sha = $commit
                status = "healthy"
                report = ([string]$report[-1])
                change_management_mode = $(if ($developmentFast) { "development_fast" } else { "standard" })
                backup_skipped = [bool]$developmentFast
                reused_verified_backup = $verifiedBackupId
            }
        }
        "promote_exact_candidate" {
            if (-not (Test-PDPOneDevelopmentFastMode)) {
                throw "Exact candidate one-command promotion is available only in development-fast mode."
            }
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            $previewId = Assert-SafeIdentifier ([string]$params.preview_id) "preview_id"
            $commit = [string]$params.commit_sha
            if ($commit -notmatch '^[0-9a-f]{40}$') { throw "Promotion commit is invalid." }

            $deploymentArgs = @(
                "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                (Join-Path $scripts "Invoke-PDPOneDeployment.ps1"),
                "-CommitSha", $commit,
                "-DeploymentId", $deploymentId,
                "-PreviewId", $previewId,
                "-AgentRoot", $AgentRoot,
                "-DevelopmentFastMode"
            )
            $report = @(& powershell.exe @deploymentArgs)
            if ($LASTEXITCODE -ne 0) { throw "Exact candidate promotion deployment failed; see the deployment report." }
            $deploymentReport = if ($report.Count -gt 0) { [string]$report[-1] } else { "" }

            # This is deliberately a separate child process after exact deployment.
            # The deployment may recreate MCP; orchestration remains in the Windows Agent.
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-PDPOne.ps1") -SkipChatGPTToolCheck | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Exact candidate deployed, but independent layered health failed. Do not merge." }

            return @{
                deployment_id = $deploymentId
                commit_sha = $commit
                deployment_status = "healthy"
                deployment_report = $deploymentReport
                independent_health = "healthy"
                runtime_accepted = $true
                change_management_mode = "development_fast"
                compatibility_preflight_enforced = $true
                automatic_merge = $false
                premerge_required = $true
            }
        }
        "sync_agent_from_exact_commit" {
            $commit = [string]$params.commit_sha
            if ($commit -notmatch '^[0-9a-f]{40}$') { throw "Agent synchronization commit is invalid." }

            $requestId = [Guid]::Parse([string]$Payload.request_id).ToString()
            $secretPath = Join-Path $AgentRoot "secrets\github-token.dpapi"
            if (-not (Test-Path -LiteralPath $secretPath)) { throw "The protected GitHub package credential is missing." }
            $stageRoot = Join-Path $AgentRoot ("downloads\agent-sync-" + $requestId)
            $backupRoot = Join-Path $AgentRoot ("state\agent-sync-backups\" + $requestId)
            New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null
            New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

            $credentialPointer = [IntPtr]::Zero
            $plainCredential = $null
            $records = @()
            try {
                $secureCredential = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
                $credentialPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureCredential)
                $plainCredential = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($credentialPointer)
                if ([string]::IsNullOrWhiteSpace($plainCredential)) { throw "The protected GitHub credential could not be opened." }
                $headers = @{
                    Authorization = "Bearer $plainCredential"
                    Accept = "application/vnd.github+json"
                    "X-GitHub-Api-Version" = "2022-11-28"
                    "User-Agent" = "PDP-One-Agent-Sync"
                }

                $commitResponse = Invoke-RestMethod -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/commits/$commit" -Headers $headers -TimeoutSec 45
                if ([string]$commitResponse.sha -ne $commit) { throw "GitHub did not return the exact requested Agent synchronization commit." }

                $contractResponse = Invoke-RestMethod -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/contents/release/deployment-agent-compatibility.json?ref=$commit" -Headers $headers -TimeoutSec 45
                $contractBytes = [Convert]::FromBase64String(([string]$contractResponse.content -replace '\s', ''))
                $contractText = [Text.Encoding]::UTF8.GetString($contractBytes)
                $contract = $contractText | ConvertFrom-Json
                if ([string]$contract.schema -ne "pdp-one.deployment-agent-compatibility.v1" -or [int]$contract.protocol_version -ne 1) {
                    throw "Candidate Agent compatibility contract is unsupported."
                }
                $entries = @($contract.bootstrap_files)
                if ($entries.Count -eq 0 -or $entries.Count -gt 32) { throw "Candidate Agent compatibility contract has an invalid bootstrap file count." }
                if (-not (@($entries | ForEach-Object { [string]$_.agent_file }) -contains "Deployment-Agent.Standard.ps1")) {
                    throw "Candidate Agent synchronization is allowed only when Deployment-Agent.Standard.ps1 is protected by the compatibility manifest."
                }

                foreach ($entry in $entries) {
                    $repositoryPath = [string]$entry.path
                    $agentFile = [string]$entry.agent_file
                    if ($repositoryPath -notmatch '^scripts/windows/[A-Za-z0-9._-]+\.ps1$') { throw "Candidate Agent manifest contains an invalid repository path." }
                    if ($agentFile -notmatch '^[A-Za-z0-9._-]+\.ps1$' -or $agentFile -ne (Split-Path $repositoryPath -Leaf)) { throw "Candidate Agent manifest contains an invalid target filename." }

                    $fileResponse = Invoke-RestMethod -Uri ("https://api.github.com/repos/PDP-WEBBASE/PDP-One/contents/" + $repositoryPath + "?ref=" + $commit) -Headers $headers -TimeoutSec 45
                    $fileBytes = [Convert]::FromBase64String(([string]$fileResponse.content -replace '\s', ''))
                    if ($fileBytes.Length -le 0) { throw "Candidate Agent bootstrap file is empty: $agentFile" }
                    $stagePath = Join-Path $stageRoot $agentFile
                    [IO.File]::WriteAllBytes($stagePath, $fileBytes)
                    $parseTokens = $null
                    $parseErrors = $null
                    [System.Management.Automation.Language.Parser]::ParseFile($stagePath, [ref]$parseTokens, [ref]$parseErrors) | Out-Null
                    if (@($parseErrors).Count -gt 0) { throw "Candidate Agent bootstrap file does not parse in Windows PowerShell: $agentFile" }
                    $candidateHash = (Get-FileHash -LiteralPath $stagePath -Algorithm SHA256).Hash.ToLowerInvariant()
                    $destination = Join-Path $scripts $agentFile
                    $existed = Test-Path -LiteralPath $destination
                    $backupPath = Join-Path $backupRoot $agentFile
                    if ($existed) { Copy-Item -LiteralPath $destination -Destination $backupPath -Force }
                    $records += [pscustomobject]@{
                        agent_file = $agentFile
                        stage_path = $stagePath
                        destination = $destination
                        backup_path = $backupPath
                        existed = [bool]$existed
                        candidate_sha256 = $candidateHash
                    }
                }

                try {
                    foreach ($record in $records) {
                        $temporary = ([string]$record.destination) + ".pdp-sync-new"
                        Copy-Item -LiteralPath ([string]$record.stage_path) -Destination $temporary -Force
                        Move-Item -LiteralPath $temporary -Destination ([string]$record.destination) -Force
                        $installedHash = (Get-FileHash -LiteralPath ([string]$record.destination) -Algorithm SHA256).Hash.ToLowerInvariant()
                        if (-not [string]::Equals($installedHash, [string]$record.candidate_sha256, [StringComparison]::OrdinalIgnoreCase)) {
                            throw "Installed Agent bootstrap hash mismatch: $($record.agent_file)"
                        }
                    }
                } catch {
                    for ($index = $records.Count - 1; $index -ge 0; $index -= 1) {
                        $record = $records[$index]
                        if ([bool]$record.existed -and (Test-Path -LiteralPath ([string]$record.backup_path))) {
                            Copy-Item -LiteralPath ([string]$record.backup_path) -Destination ([string]$record.destination) -Force -ErrorAction SilentlyContinue
                        } elseif (-not [bool]$record.existed) {
                            Remove-Item -LiteralPath ([string]$record.destination) -Force -ErrorAction SilentlyContinue
                        }
                    }
                    throw
                }

                Set-Content -LiteralPath (Join-Path $AgentRoot "state\restart-agent-after-response") -Value ([DateTime]::UtcNow.ToString("o")) -Encoding ASCII
                return @{
                    exact_commit = $commit
                    fixed_repository = "PDP-WEBBASE/PDP-One"
                    synchronized_files = @($records | ForEach-Object { [string]$_.agent_file })
                    synchronized_file_count = $records.Count
                    hashes_verified = $true
                    powershell_parse_verified = $true
                    backup_created = $true
                    rollback_on_sync_failure = $true
                    arbitrary_shell_allowed = $false
                    agent_restart_scheduled = $true
                }
            } finally {
                if ($credentialPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($credentialPointer) }
                $plainCredential = $null
                if (Test-Path -LiteralPath $stageRoot) { Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue }
            }
        }
        "ensure_pdp_one_started" {
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Start-PDPOne.ps1") | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Stable PDP One startup failed." }
            return @{ started = $true; operation = "fixed_stable_start"; arbitrary_shell_allowed = $false }
        }
        "repair_pdp_one_connectivity" {
            $projectRoot = Get-PDPOneProjectRoot
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Repair-PDPOneConnectivity.ps1") -ProjectRoot $projectRoot -RepairAttempts 1 -PublicCheckTimeoutSeconds 35 -TransientConfirmDelaySeconds 10 -DnsPublicationTimeoutSeconds 60 -DnsPollIntervalSeconds 10 | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Bounded PDP One connectivity repair failed." }
            return @{ repaired = $true; repair_attempts = 1; identity_reset = $false; credential_rotation = $false; arbitrary_shell_allowed = $false }
        }
        "collect_pdp_one_diagnostics" {
            $output = @(& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "New-PDPOneDiagnostics.ps1") -FailureMessage "Owner-requested signed diagnostics" -Stage "signed-diagnostics")
            if ($LASTEXITCODE -ne 0) { throw "Safe PDP One diagnostics failed." }
            $reportPath = if ($output.Count -gt 0) { [string]$output[-1] } else { "" }
            return @{ diagnostics_created = $true; report_file = $(if ($reportPath) { Split-Path $reportPath -Leaf } else { "" }); secret_values_returned = $false; arbitrary_shell_allowed = $false }
        }
        "check_deployment_health" {
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-PDPOne.ps1") -SkipChatGPTToolCheck | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Layered deployment health failed." }
            return @{ deployment_id = $deploymentId; health = "healthy"; chatgpt_tool_check = "reported-through-connected-app" }
        }
        "run_disk_maintenance" {
            $keep = [int]$params.keep_local_final_backups
            if ($keep -lt 2 -or $keep -gt 10) { throw "Backup retention must be between 2 and 10." }
            $protectedBackup = ""
            $statePath = Join-Path $AgentRoot "state\last-deployment.json"
            if (Test-Path -LiteralPath $statePath) {
                $deploymentState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
                $backupPathProperty = $deploymentState.PSObject.Properties["backup_path"]
                if ($null -ne $backupPathProperty -and -not [string]::IsNullOrWhiteSpace([string]$backupPathProperty.Value) -and (Test-Path -LiteralPath ([string]$backupPathProperty.Value))) {
                    $protectedBackup = [string]$backupPathProperty.Value
                }
            }
            $maintenanceArgs = @(
                "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                (Join-Path $scripts "Invoke-PDPOneDiskMaintenance.ps1"),
                "-Mode", "cleanup",
                "-KeepLocalFinalBackups", ([string]$keep)
            )
            if ($protectedBackup) { $maintenanceArgs += @("-ProtectedBackupPath", $protectedBackup) }
            $output = @(& powershell.exe @maintenanceArgs)
            if ($LASTEXITCODE -ne 0) { throw "Signed disk maintenance failed." }
            $maintenanceReport = [string]$output[-1]
            if (-not (Test-Path -LiteralPath $maintenanceReport)) { throw "Disk maintenance report was not created." }
            $result = Get-Content -LiteralPath $maintenanceReport -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([bool]$result.volumes_pruned -or [bool]$result.database_volume_touched -or [bool]$result.private_files_volume_touched -or [bool]$result.tailscale_volume_touched) {
                throw "Disk maintenance protection markers are invalid."
            }
            return @{
                report = $maintenanceReport
                c_free_bytes_before = [int64]$result.c_free_bytes_before
                c_free_bytes_after = [int64]$result.c_free_bytes_after
                c_free_bytes_delta = [int64]$result.c_free_bytes_delta
                removed_verified_final_backups = @($result.removed_verified_final_backups)
                externally_archived_backups = @($result.externally_archived_backups)
                removed_agent_download_directories = @($result.removed_agent_download_directories)
                volumes_pruned = $false
            }
        }
        "rollback_deployment" {
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            $statePath = Join-Path $AgentRoot "state\last-deployment.json"
            if (-not (Test-Path -LiteralPath $statePath)) { throw "No deployment state is available for rollback." }
            $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($state.deployment_id -ne $deploymentId) { throw "Rollback deployment identifier does not match." }
            $rollbackArgs = @(
                "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                (Join-Path $scripts "Rollback-PDPOne.ps1"),
                "-BackupPath", ([string]$state.backup_path),
                "-CodeArchive", ([string]$state.code_archive),
                "-Automatic"
            )
            $mode = if ($null -ne $state.PSObject.Properties["change_management_mode"]) { [string]$state.change_management_mode } else { "standard" }
            if ($mode -ne "development_fast") { $rollbackArgs += "-RestoreDatabase" }
            & powershell.exe @rollbackArgs
            if ($LASTEXITCODE -ne 0) { throw "Rollback failed." }
            return @{ deployment_id = $state.deployment_id; rollback = "healthy"; change_management_mode = $mode; reason = (ConvertTo-PDPOneRedactedText ([string]$params.reason)) }
        }
        "rotate_mcp_token" {
            if (([string]$params.confirmation) -cne "ROTATE MCP TOKEN") { throw "Rotation confirmation is invalid." }
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Rotate-PDPOneMcpToken.ps1") -Confirmed -NonInteractive
            if ($LASTEXITCODE -ne 0) { throw "MCP token rotation failed and was rolled back." }
            return @{ rotated = $true; app_url_update_required = $true; secret_returned = $false }
        }
        default { throw "Unsupported agent action." }
    }
}

try {
    foreach ($directory in @("queue\incoming", "queue\processing", "queue\responses", "queue\rejected", "state\processed", "audit")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $AgentRoot $directory) | Out-Null
    }
    $lastStartupAttempt = [DateTime]::MinValue
    :AgentLoop do {
        $ProjectRoot = Get-PDPOneProjectRoot
        $envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
        $configuredChangeMode = [string](Get-PDPOneEnvValue $envPath "PDP_CHANGE_MANAGEMENT_MODE")
        $trialModeValue = [string](Get-PDPOneEnvValue $envPath "PDP_TRIAL_MODE")
        if ([string]::IsNullOrWhiteSpace($configuredChangeMode)) {
            $script:PDPOneChangeManagementMode = $(if ($trialModeValue.ToLowerInvariant() -in @("1", "true", "yes")) { "development_fast" } else { "standard" })
        } elseif ($configuredChangeMode -in @("development_fast", "standard")) {
            $script:PDPOneChangeManagementMode = $configuredChangeMode
        } else {
            throw "PDP_CHANGE_MANAGEMENT_MODE must be development_fast or standard."
        }
        $signingKey = Get-PDPOneEnvValue $envPath "PDP_DEPLOYMENT_AGENT_SIGNING_KEY"
        if ([string]::IsNullOrWhiteSpace($signingKey) -or $signingKey.Length -lt 32) { throw "Deployment-agent signing key is missing." }
        Set-Location $ProjectRoot
        $nginxRunning = $false
        if (Test-PDPOneDockerEngine) {
            $nginxRunning = ((& docker compose ps --status running --services nginx 2>$null) -contains "nginx")
        }
        if (-not $nginxRunning -and ((Get-Date) - $lastStartupAttempt).TotalSeconds -ge 60) {
            $lastStartupAttempt = Get-Date
            try {
                & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "Start-PDPOne.ps1") | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "Automatic startup returned a failure." }
                Write-AgentAudit "startup" "stable_startup" "succeeded" "PDP One started after Windows logon."
            } catch {
                Write-AgentAudit "startup" "stable_startup" "failed" $_.Exception.Message
            }
        }
        $requests = Get-ChildItem -LiteralPath (Join-Path $AgentRoot "queue\incoming") -Filter "*.json" | Sort-Object CreationTimeUtc
        foreach ($request in $requests) {
            $processing = Join-Path $AgentRoot "queue\processing\$($request.Name)"
            $payload = $null
            try {
                Move-Item -LiteralPath $request.FullName -Destination $processing -ErrorAction Stop
                $envelope = Get-Content -LiteralPath $processing -Raw -Encoding UTF8 | ConvertFrom-Json
                $payloadBytes = [Convert]::FromBase64String([string]$envelope.payload_b64)
                if (-not (Test-AgentSignature $payloadBytes ([string]$envelope.signature) $signingKey)) { throw "Request signature is invalid." }
                $payload = [Text.Encoding]::UTF8.GetString($payloadBytes) | ConvertFrom-Json
                $requestId = [Guid]::Parse([string]$payload.request_id).ToString()
                if ([DateTimeOffset]::Parse($payload.expires_at) -le [DateTimeOffset]::UtcNow) { throw "Request expired." }
                $processedMarker = Join-Path $AgentRoot "state\processed\$requestId.done"
                if (Test-Path -LiteralPath $processedMarker) { throw "Replay request rejected." }
                $result = Invoke-AgentAction $payload
                Write-AgentResponse $requestId ([string]$payload.action) "succeeded" $result
                Set-Content -LiteralPath $processedMarker -Value ((Get-Date).ToUniversalTime().ToString("o")) -Encoding ASCII
                Write-AgentAudit $requestId ([string]$payload.action) "succeeded" "Allowlisted request completed."
                Remove-Item -LiteralPath $processing -Force
                $restartMarker = Join-Path $AgentRoot 'state\restart-agent-after-response'
                if (Test-Path -LiteralPath $restartMarker) {
                    Remove-Item -LiteralPath $restartMarker -Force
                    $restartAfterResponse = $true
                    break
                }
            } catch {
                $requestId = [IO.Path]::GetFileNameWithoutExtension($request.Name)
                $action = "unknown"
                if ($null -ne $payload) {
                    try { $requestId = [Guid]::Parse([string]$payload.request_id).ToString() } catch { }
                    $action = [string]$payload.action
                }
                Write-AgentResponse $requestId $action "failed" @{ error = (ConvertTo-PDPOneRedactedText $_.Exception.Message) }
                Write-AgentAudit $requestId $action "failed" $_.Exception.Message
                if (Test-Path -LiteralPath $processing) { Move-Item -LiteralPath $processing -Destination (Join-Path $AgentRoot "queue\rejected\$($request.Name)") -Force }
            }
        }
        if ($restartAfterResponse) { break AgentLoop }
        if (-not $Once) { Start-Sleep -Seconds $PollSeconds }
    } while (-not $Once)
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
if ($restartAfterResponse -and -not $Once) {
    $arguments = "-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`" -AgentRoot `"$AgentRoot`" -PollSeconds $PollSeconds"
    Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WindowStyle Hidden | Out-Null
}
