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

$report = [ordered]@{
    schema = "pdp-one.deployment-compatibility-preflight.v1"
    deployment_id = $DeploymentId
    commit_sha = $CommitSha
    protocol_version = $null
    supported_protocol_version = $SupportedProtocolVersion
    status = "starting"
    checked_at = [DateTime]::UtcNow.ToString("o")
    bootstrap_files = @()
    mismatches = @()
    production_changed = $false
    error = $null
}

try {
    $contractPath = Join-Path $downloadRoot "deployment-agent-compatibility.json"
    Get-PDPOneRawCandidateFile -RepositoryPath "release/deployment-agent-compatibility.json" -Destination $contractPath
    $contract = Get-Content -LiteralPath $contractPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$contract.schema -ne "pdp-one.deployment-agent-compatibility.v1") {
        throw "Exact candidate compatibility contract schema is unsupported."
    }
    $protocol = [int]$contract.protocol_version
    $report.protocol_version = $protocol
    if ($protocol -ne $SupportedProtocolVersion) {
        throw "Deployment-agent protocol mismatch. Installed preflight supports version $SupportedProtocolVersion but candidate requires version $protocol."
    }

    $entries = @($contract.bootstrap_files)
    if ($entries.Count -eq 0 -or $entries.Count -gt 32) {
        throw "Exact candidate compatibility contract must declare between 1 and 32 bootstrap files."
    }

    $checks = @()
    $mismatches = @()
    foreach ($entry in $entries) {
        $repositoryPath = [string]$entry.path
        $agentFile = [string]$entry.agent_file
        if ($repositoryPath -notmatch '^scripts/windows/[A-Za-z0-9._-]+\.ps1$') {
            throw "Compatibility contract contains an invalid bootstrap repository path."
        }
        if ($agentFile -notmatch '^[A-Za-z0-9._-]+\.ps1$' -or $agentFile -ne (Split-Path $repositoryPath -Leaf)) {
            throw "Compatibility contract contains an invalid agent bootstrap filename."
        }

        $candidatePath = Join-Path $downloadRoot $agentFile
        Get-PDPOneRawCandidateFile -RepositoryPath $repositoryPath -Destination $candidatePath
        $installedPath = Join-Path $binRoot $agentFile
        $candidateHash = (Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $installedExists = Test-Path -LiteralPath $installedPath
        $installedHash = if ($installedExists) { (Get-FileHash -LiteralPath $installedPath -Algorithm SHA256).Hash.ToLowerInvariant() } else { "" }
        $matches = $installedExists -and [string]::Equals($candidateHash, $installedHash, [StringComparison]::OrdinalIgnoreCase)
        $check = [ordered]@{
            file = $agentFile
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
    if ($mismatches.Count -gt 0) {
        $joined = ($mismatches -join ", ")
        throw "Deployment-agent bootstrap prerequisite mismatch for: $joined. Synchronize these exact candidate bootstrap files into the protected Agent bin before retrying. No production changes were made."
    }

    $report.status = "compatible"
    $report.error = $null
    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output $reportPath
} catch {
    $report.status = "incompatible"
    $report.error = [string]$_.Exception.Message
    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    throw $report.error
} finally {
    if (Test-Path -LiteralPath $downloadRoot) {
        Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
