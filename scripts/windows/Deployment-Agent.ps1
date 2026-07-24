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
            # Keep the script source ASCII-safe for Windows PowerShell 5.1.
            # The helper constructs the approved Persian phrases from Unicode code points.
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
            $approvalPath = Join-Path $AgentRoot "state\approved-release.json"
            if (-not (Test-Path -LiteralPath $approvalPath)) { throw "No explicit release approval is recorded." }
            $approval = Get-Content -LiteralPath $approvalPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([DateTimeOffset]::Parse($approval.expires_at) -le [DateTimeOffset]::UtcNow) { throw "Release approval expired." }
            if ($approval.commit_sha -ne ([string]$params.commit_sha) -or $approval.preview_id -ne $previewId) { throw "Requested deployment does not match the approved preview." }

            $backupStatePath = Join-Path $AgentRoot "state\approved-backup.json"
            if (-not (Test-Path -LiteralPath $backupStatePath)) { throw "No fresh verified final backup is recorded for this deployment." }
            $backupState = Get-Content -LiteralPath $backupStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([DateTimeOffset]::Parse($backupState.expires_at) -le [DateTimeOffset]::UtcNow) { throw "Verified final backup authorization expired." }
            if ([string]$backupState.commit_sha -ne ([string]$params.commit_sha)) { throw "Verified final backup commit does not match the approved deployment." }
            if ([string]$backupState.deployment_id -ne $deploymentId) { throw "Verified final backup deployment identifier does not match." }
            if (-not [bool]$backupState.restore_verified -or -not (Test-Path -LiteralPath ([string]$backupState.backup_path))) { throw "Verified final backup is not available." }

            $report = & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Invoke-PDPOneDeployment.ps1") -CommitSha ([string]$params.commit_sha) -DeploymentId $deploymentId -PreviewId $previewId -AgentRoot $AgentRoot -VerifiedBackupPath ([string]$backupState.backup_path)
            if ($LASTEXITCODE -ne 0) { throw "Deployment failed; see the rollback result in the deployment report." }
            Remove-Item -LiteralPath $approvalPath -Force
            Remove-Item -LiteralPath $backupStatePath -Force
            return @{ deployment_id = ([string]$params.deployment_id); commit_sha = ([string]$params.commit_sha); status = "healthy"; report = ($report | Select-Object -Last 1); reused_verified_backup = [string]$backupState.backup_id }
        }
        "check_deployment_health" {
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Test-PDPOne.ps1") -SkipChatGPTToolCheck | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Layered deployment health failed." }
            return @{ deployment_id = $deploymentId; health = "healthy"; chatgpt_tool_check = "reported-through-connected-app" }
        }
        "rollback_deployment" {
            $deploymentId = Assert-SafeIdentifier ([string]$params.deployment_id) "deployment_id"
            $statePath = Join-Path $AgentRoot "state\last-deployment.json"
            if (-not (Test-Path -LiteralPath $statePath)) { throw "No deployment state is available for rollback." }
            $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($state.deployment_id -ne $deploymentId) { throw "Rollback deployment identifier does not match." }
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scripts "Rollback-PDPOne.ps1") -BackupPath $state.backup_path -CodeArchive $state.code_archive -Automatic -RestoreDatabase
            if ($LASTEXITCODE -ne 0) { throw "Rollback failed." }
            return @{ deployment_id = $state.deployment_id; rollback = "healthy"; reason = (ConvertTo-PDPOneRedactedText ([string]$params.reason)) }
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
