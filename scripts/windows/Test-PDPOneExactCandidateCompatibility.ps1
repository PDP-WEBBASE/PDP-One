#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$CommitSha,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$DeploymentId,
    [Parameter(Mandatory = $true)][string]$AgentRoot,
    [switch]$InspectionOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$SupportedProtocolVersion = 1
$StageAMigration = "stable-bootstrap-control-plane-stage-a"
$SteadyStateAgentFiles = @(
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
$StageAAgentFiles = @(
    "Deployment-Agent.Standard.ps1",
    "Invoke-PDPOneManagedFastDeployment.ps1",
    "PDPOne.Common.ps1",
    "PDPOne.OperationLock.ps1",
    "PDPOne.ReleaseManifest.ps1"
)
$downloadRoot = Join-Path $AgentRoot ("downloads\compatibility-" + $DeploymentId)
$reportRoot = Join-Path $AgentRoot "reports"
$reportPath = Join-Path $reportRoot ("compatibility-" + $DeploymentId + ".json")
$binRoot = Join-Path $AgentRoot "bin"
New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null

function Get-PDPOneRawCandidateFile {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryPath,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if ($RepositoryPath -notmatch '^scripts/windows/[A-Za-z0-9._-]+\.ps1$' -and $RepositoryPath -ne 'release/deployment-agent-compatibility.json') {
        throw "Compatibility contract contains an invalid repository path."
    }
    $uri = "https://raw.githubusercontent.com/PDP-WEBBASE/PDP-One/$CommitSha/$RepositoryPath"
    $lastError = $null
    for ($attempt = 1; $attempt -le 3; $attempt += 1) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $uri -OutFile $Destination -TimeoutSec 45
            if (-not (Test-Path -LiteralPath $Destination) -or (Get-Item -LiteralPath $Destination).Length -le 0) {
                throw "Downloaded candidate file is empty."
            }
            return
        } catch {
            $lastError = $_
            if ($attempt -lt 3) { Start-Sleep -Seconds ([Math]::Min(5, $attempt * 2)) }
        }
    }
    $message = if ($null -ne $lastError) { [string]$lastError.Exception.Message } else { "Unknown download error." }
    throw "Could not read exact candidate file '$RepositoryPath' from GitHub. $message"
}

function Assert-PDPOneManifestSet {
    param(
        [Parameter(Mandatory = $true)]$Contract,
        [Parameter(Mandatory = $true)][string[]]$ExpectedFiles
    )
    $entries = @($Contract.bootstrap_files)
    if ($entries.Count -ne $ExpectedFiles.Count) {
        throw "Exact candidate compatibility contract has an unexpected bootstrap file count."
    }
    $seenFiles = @{}
    $seenPaths = @{}
    foreach ($entry in $entries) {
        $repositoryPath = [string]$entry.path
        $agentFile = [string]$entry.agent_file
        if ($repositoryPath -notmatch '^scripts/windows/[A-Za-z0-9._-]+\.ps1$') {
            throw "Compatibility contract contains an invalid bootstrap repository path."
        }
        if ($agentFile -notmatch '^[A-Za-z0-9._-]+\.ps1$' -or $agentFile -ne (Split-Path $repositoryPath -Leaf)) {
            throw "Compatibility contract contains an invalid agent bootstrap filename."
        }
        if ($seenFiles.ContainsKey($agentFile) -or $seenPaths.ContainsKey($repositoryPath)) {
            throw "Compatibility contract contains duplicate bootstrap entries."
        }
        $seenFiles[$agentFile] = $true
        $seenPaths[$repositoryPath] = $true
    }
    $actual = @($seenFiles.Keys | Sort-Object)
    $expected = @($ExpectedFiles | Sort-Object)
    if (($actual -join "`n") -ne ($expected -join "`n")) {
        throw "Exact candidate compatibility contract does not match the fixed bootstrap file set for this stage."
    }
    return $entries
}

$report = [ordered]@{
    schema = "pdp-one.deployment-compatibility-preflight.v2"
    deployment_id = $DeploymentId
    commit_sha = $CommitSha
    repository = "PDP-WEBBASE/PDP-One"
    protocol_version = $null
    supported_protocol_version = $SupportedProtocolVersion
    migration_stage = $null
    candidate_manifest_sha256 = $null
    status = "starting"
    classification = "UNKNOWN"
    checked_at = [DateTime]::UtcNow.ToString("o")
    bootstrap_files = @()
    mismatches = @()
    production_changed = $false
    inspection_only = [bool]$InspectionOnly
    error = $null
}

try {
    $contractPath = Join-Path $downloadRoot "deployment-agent-compatibility.json"
    Get-PDPOneRawCandidateFile -RepositoryPath "release/deployment-agent-compatibility.json" -Destination $contractPath
    $report.candidate_manifest_sha256 = (Get-FileHash -LiteralPath $contractPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $contract = Get-Content -LiteralPath $contractPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$contract.schema -ne "pdp-one.deployment-agent-compatibility.v1") {
        throw "Exact candidate compatibility contract schema is unsupported."
    }

    $protocol = [int]$contract.protocol_version
    $report.protocol_version = $protocol
    if ($protocol -ne $SupportedProtocolVersion) {
        $report.classification = "PROTOCOL_MISMATCH"
        throw "Deployment-agent protocol mismatch. Installed preflight supports version $SupportedProtocolVersion but candidate requires version $protocol."
    }

    $migrationStage = ""
    $migrationProperty = $contract.PSObject.Properties["migration_stage"]
    if ($null -ne $migrationProperty) { $migrationStage = ([string]$migrationProperty.Value).Trim() }
    $report.migration_stage = if ($migrationStage) { $migrationStage } else { $null }
    $expectedFiles = if ([string]::IsNullOrWhiteSpace($migrationStage)) {
        $SteadyStateAgentFiles
    } elseif ($migrationStage -eq $StageAMigration) {
        $StageAAgentFiles
    } else {
        throw "Exact candidate compatibility contract has an unsupported migration stage."
    }
    $entries = @(Assert-PDPOneManifestSet -Contract $contract -ExpectedFiles $expectedFiles)

    $checks = @()
    $mismatches = @()
    foreach ($entry in $entries) {
        $repositoryPath = [string]$entry.path
        $agentFile = [string]$entry.agent_file
        $candidatePath = Join-Path $downloadRoot $agentFile
        Get-PDPOneRawCandidateFile -RepositoryPath $repositoryPath -Destination $candidatePath

        $parseTokens = $null
        $parseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($candidatePath, [ref]$parseTokens, [ref]$parseErrors) | Out-Null
        if (@($parseErrors).Count -gt 0) {
            throw "Candidate Agent bootstrap file failed Windows PowerShell 5.1 parsing: $agentFile"
        }

        $installedPath = Join-Path $binRoot $agentFile
        $candidateHash = (Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $installedExists = Test-Path -LiteralPath $installedPath
        $installedHash = if ($installedExists) { (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { "" }
        $matches = $installedExists -and [string]::Equals($candidateHash, $installedHash, [StringComparison]::OrdinalIgnoreCase)
        $check = [ordered]@{
            file = $agentFile
            repository_path = $repositoryPath
            candidate_sha256 = $candidateHash
            installed_sha256 = $installedHash
            installed = [bool]$installedExists
            matches = [bool]$matches
        }
        $checks += $check
        if (-not $matches) { $mismatches += $agentFile }
    }

    $report.bootstrap_files = $checks
    $report.mismatches = @($mismatches)
    if ($mismatches.Count -eq 0) {
        $report.status = "compatible"
        $report.classification = "MATCH"
        $report.error = $null
    } elseif (-not [string]::IsNullOrWhiteSpace($migrationStage)) {
        $report.status = "incompatible"
        $report.classification = "UNSAFE"
        $report.error = "Migration-stage compatibility manifests are never eligible for automatic Agent reconciliation."
    } else {
        $report.status = "safe_reconcilable"
        $report.classification = "SAFE_RECONCILABLE"
        $report.error = $null
    }

    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8

    if ($InspectionOnly) {
        Write-Output $reportPath
        return
    }
    if ($report.classification -ne "MATCH") {
        if ($report.classification -eq "SAFE_RECONCILABLE") {
            $joined = ($mismatches -join ", ")
            throw "Deployment-agent bootstrap prerequisite mismatch for: $joined. Exact Agent reconciliation is required before production deployment. No production changes were made."
        }
        throw $report.error
    }
    Write-Output $reportPath
} catch {
    if ($report.classification -eq "UNKNOWN") { $report.classification = "UNSAFE" }
    if ($report.classification -eq "PROTOCOL_MISMATCH") {
        $report.status = "protocol_mismatch"
    } elseif ($report.classification -ne "SAFE_RECONCILABLE") {
        $report.status = "incompatible"
    }
    $report.error = [string]$_.Exception.Message
    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    $report.production_changed = $false
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    if ($InspectionOnly) {
        Write-Output $reportPath
        return
    }
    throw $report.error
} finally {
    if (Test-Path -LiteralPath $downloadRoot) {
        Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}