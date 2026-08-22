#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$CommitSha,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$DeploymentId,
    [Parameter(Mandatory = $true)][string]$AgentRoot
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$SupportedProtocolVersion = 1
$ExpectedAgentFiles = @(
    "Deployment-Agent.Standard.ps1",
    "Invoke-PDPOneDeployment.ps1",
    "Invoke-PDPOneManagedFastDeployment.ps1",
    "Invoke-PDPOneScopedRegistryDeployment.ps1",
    "Invoke-PDPOneExactAgentReconciliation.ps1",
    "PDPOne.Common.ps1",
    "PDPOne.OperationLock.ps1",
    "PDPOne.ReleaseManifest.ps1",
    "Test-PDPOneExactCandidateCompatibility.ps1"
)
$secretPath = Join-Path $AgentRoot "secrets\github-token.dpapi"
$stageRoot = Join-Path $AgentRoot ("downloads\exact-agent-reconcile-" + $DeploymentId)
$backupRoot = Join-Path $AgentRoot ("state\agent-reconcile-backups\" + $DeploymentId)
$reportRoot = Join-Path $AgentRoot "reports"
$reportPath = Join-Path $reportRoot ("agent-reconciliation-" + $DeploymentId + ".json")
$binRoot = Join-Path $AgentRoot "bin"
New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null

$report = [ordered]@{
    schema = "pdp-one.exact-agent-reconciliation.v1"
    deployment_id = $DeploymentId
    commit_sha = $CommitSha
    repository = "PDP-WEBBASE/PDP-One"
    protocol_version = $null
    status = "starting"
    started_at = [DateTime]::UtcNow.ToString("o")
    completed_at = $null
    bootstrap_files = @()
    rollback_on_failure = $true
    rollback_attempted = $false
    rollback_succeeded = $null
    agent_changed = $false
    production_changed = $false
    restart_deferred_to_deployment_response = $true
    error = $null
}
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8

function Assert-ExactSteadyStateManifest($Contract) {
    if ([string]$Contract.schema -ne "pdp-one.deployment-agent-compatibility.v1") {
        throw "Candidate Agent compatibility contract schema is unsupported."
    }
    $protocol = [int]$Contract.protocol_version
    if ($protocol -ne $SupportedProtocolVersion) {
        throw "Candidate Agent protocol is unsupported."
    }
    $migrationProperty = $Contract.PSObject.Properties["migration_stage"]
    if ($null -ne $migrationProperty -and -not [string]::IsNullOrWhiteSpace([string]$migrationProperty.Value)) {
        throw "Automatic Agent reconciliation is disabled for migration-stage compatibility manifests."
    }

    $entries = @($Contract.bootstrap_files)
    if ($entries.Count -ne $ExpectedAgentFiles.Count) {
        throw "Steady-state Agent compatibility manifest has an unexpected bootstrap file count."
    }
    $seenFiles = @{}
    $seenPaths = @{}
    foreach ($entry in $entries) {
        $repositoryPath = [string]$entry.path
        $agentFile = [string]$entry.agent_file
        if ($repositoryPath -notmatch '^scripts/windows/[A-Za-z0-9._-]+\.ps1$') {
            throw "Candidate Agent manifest contains an invalid repository path."
        }
        if ($agentFile -notmatch '^[A-Za-z0-9._-]+\.ps1$' -or $agentFile -ne (Split-Path $repositoryPath -Leaf)) {
            throw "Candidate Agent manifest contains an invalid target filename."
        }
        if ($seenFiles.ContainsKey($agentFile) -or $seenPaths.ContainsKey($repositoryPath)) {
            throw "Candidate Agent manifest contains duplicate bootstrap entries."
        }
        $seenFiles[$agentFile] = $true
        $seenPaths[$repositoryPath] = $true
    }
    $actual = @($seenFiles.Keys | Sort-Object)
    $expected = @($ExpectedAgentFiles | Sort-Object)
    if (($actual -join "`n") -ne ($expected -join "`n")) {
        throw "Candidate Agent manifest does not match the fixed steady-state bootstrap file set."
    }
    return $entries
}

$credentialPointer = [IntPtr]::Zero
$plainCredential = $null
$records = @()
try {
    if (-not (Test-Path -LiteralPath $secretPath)) {
        throw "The protected GitHub package credential is missing."
    }
    $secureCredential = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
    $credentialPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureCredential)
    $plainCredential = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($credentialPointer)
    if ([string]::IsNullOrWhiteSpace($plainCredential)) {
        throw "The protected GitHub credential could not be opened."
    }
    $headers = @{
        Authorization = "Bearer $plainCredential"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = "PDP-One-Exact-Agent-Reconciliation"
    }

    $commitResponse = Invoke-RestMethod -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/commits/$CommitSha" -Headers $headers -TimeoutSec 45
    if ([string]$commitResponse.sha -ne $CommitSha) {
        throw "GitHub did not return the exact requested Agent reconciliation commit."
    }

    $contractResponse = Invoke-RestMethod -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/contents/release/deployment-agent-compatibility.json?ref=$CommitSha" -Headers $headers -TimeoutSec 45
    $contractBytes = [Convert]::FromBase64String(([string]$contractResponse.content -replace '\s', ''))
    $contractText = [Text.Encoding]::UTF8.GetString($contractBytes)
    $contract = $contractText | ConvertFrom-Json
    $entries = @(Assert-ExactSteadyStateManifest -Contract $contract)
    $report.protocol_version = [int]$contract.protocol_version

    foreach ($entry in $entries) {
        $repositoryPath = [string]$entry.path
        $agentFile = [string]$entry.agent_file
        $fileResponse = Invoke-RestMethod -Uri ("https://api.github.com/repos/PDP-WEBBASE/PDP-One/contents/" + $repositoryPath + "?ref=" + $CommitSha) -Headers $headers -TimeoutSec 45
        $fileBytes = [Convert]::FromBase64String(([string]$fileResponse.content -replace '\s', ''))
        if ($fileBytes.Length -le 0) {
            throw "Candidate Agent bootstrap file is empty: $agentFile"
        }
        $stagePath = Join-Path $stageRoot $agentFile
        [IO.File]::WriteAllBytes($stagePath, $fileBytes)

        $parseTokens = $null
        $parseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($stagePath, [ref]$parseTokens, [ref]$parseErrors) | Out-Null
        if (@($parseErrors).Count -gt 0) {
            throw "Candidate Agent bootstrap file failed Windows PowerShell 5.1 parsing: $agentFile"
        }

        $candidateHash = (Get-FileHash -LiteralPath $stagePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $installedPath = Join-Path $binRoot $agentFile
        $installedExists = Test-Path -LiteralPath $installedPath
        $installedHash = if ($installedExists) { (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { "" }
        $backupPath = Join-Path $backupRoot $agentFile
        if ($installedExists) {
            Copy-Item -LiteralPath $installedPath -Destination $backupPath -Force
        }
        $records += [pscustomobject]@{
            file = $agentFile
            stage_path = $stagePath
            installed_path = $installedPath
            backup_path = $backupPath
            installed_before = [bool]$installedExists
            installed_sha256_before = $installedHash
            candidate_sha256 = $candidateHash
            replaced = $false
        }
    }

    foreach ($record in $records) {
        $stageHashNow = (Get-FileHash -LiteralPath $record.stage_path -Algorithm SHA256).Hash.ToLowerInvariant()
        if (-not [string]::Equals($stageHashNow, [string]$record.candidate_sha256, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Candidate Agent bootstrap hash changed after download: $($record.file)"
        }
        $temporaryTarget = ([string]$record.installed_path) + ".pdp-reconcile.tmp"
        Copy-Item -LiteralPath $record.stage_path -Destination $temporaryTarget -Force
        Move-Item -LiteralPath $temporaryTarget -Destination $record.installed_path -Force
        $record.replaced = $true
        $installedHashAfter = (Get-FileHash -LiteralPath $record.installed_path -Algorithm SHA256).Hash.ToLowerInvariant()
        if (-not [string]::Equals($installedHashAfter, [string]$record.candidate_sha256, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Installed Agent bootstrap hash mismatch: $($record.file)"
        }
    }

    $report.bootstrap_files = @($records | ForEach-Object {
        [ordered]@{
            file = $_.file
            installed_before = $_.installed_before
            installed_sha256_before = $_.installed_sha256_before
            candidate_sha256 = $_.candidate_sha256
            installed_sha256_after = (Get-FileHash -LiteralPath $_.installed_path -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
    $report.status = "succeeded"
    $report.agent_changed = $true
    $report.rollback_succeeded = $null
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output $reportPath
} catch {
    $rollbackRecords = @($records | Where-Object { $_.replaced })
    $report.rollback_attempted = $rollbackRecords.Count -gt 0
    [array]::Reverse($rollbackRecords)
    $rollbackSucceeded = $true
    foreach ($record in $rollbackRecords) {
        try {
            if ([bool]$record.installed_before) {
                Copy-Item -LiteralPath $record.backup_path -Destination $record.installed_path -Force
                $restoredHash = (Get-FileHash -LiteralPath $record.installed_path -Algorithm SHA256).Hash.ToLowerInvariant()
                if (-not [string]::Equals($restoredHash, [string]$record.installed_sha256_before, [StringComparison]::OrdinalIgnoreCase)) {
                    $rollbackSucceeded = $false
                }
            } else {
                Remove-Item -LiteralPath $record.installed_path -Force -ErrorAction SilentlyContinue
                if (Test-Path -LiteralPath $record.installed_path) { $rollbackSucceeded = $false }
            }
        } catch {
            $rollbackSucceeded = $false
        }
    }
    $report.status = "failed"
    $report.rollback_succeeded = [bool]$rollbackSucceeded
    $report.agent_changed = $false
    $report.production_changed = $false
    $report.error = [string]$_.Exception.Message
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    throw $report.error
} finally {
    if ($credentialPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($credentialPointer)
    }
    Remove-Variable plainCredential -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $stageRoot) {
        Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}