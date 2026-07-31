#requires -Version 5.1
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repositoryRoot = (Resolve-Path (Join-Path $root '..\..')).Path
. (Join-Path $root 'PDPOne.Common.ps1')

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

$temporary = Join-Path $env:TEMP ('pdp-one-ps51-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
try {
    $plain = Join-Path $temporary 'environment.env'
    $protected = Join-Path $temporary 'environment.dpapi'
    $restored = Join-Path $temporary 'environment.restored'
    [IO.File]::WriteAllText($plain, "PDP_ONE_TEST=value-$(New-PDPOneSecret 24)", [Text.UTF8Encoding]::new($false))

    Protect-PDPOneSecretFile -InputPath $plain -OutputPath $protected
    Assert-True ((Get-Item -LiteralPath $protected).Length -gt 0) 'DPAPI output is empty.'
    Unprotect-PDPOneSecretFile -InputPath $protected -OutputPath $restored
    Assert-True ((Get-FileHash -LiteralPath $plain -Algorithm SHA256).Hash -eq (Get-FileHash -LiteralPath $restored -Algorithm SHA256).Hash) 'Windows DPAPI round-trip failed.'

    Assert-True (Test-PDPOneExplicitDeploymentApproval 'APPROVE DEPLOY') 'Windows PowerShell approval compatibility failed.'
    $redacted = ConvertTo-PDPOneRedactedText 'POSTGRES_PASSWORD=not-a-real-password'
    Assert-True ($redacted -eq 'POSTGRES_PASSWORD=[REDACTED]') 'Windows PowerShell redaction compatibility failed.'

    $sampleCountOutput = @('9 objects imported automatically.', '9,2')
    $sampleCountText = ($sampleCountOutput | Out-String)
    $sampleCountMatch = [regex]::Match($sampleCountText, '(?m)^\s*(\d+),(\d+)\s*$')
    Assert-True $sampleCountMatch.Success 'Multiline Django count output was not parsed.'
    Assert-True ($sampleCountMatch.Value.Trim() -eq '9,2') 'Parsed Django counts are incorrect.'

    $updateScript = [IO.File]::ReadAllText((Join-Path $root 'Update-PDPOne.ps1'))
    $rollbackScript = [IO.File]::ReadAllText((Join-Path $root 'Rollback-PDPOne.ps1'))
    $connectivityScript = [IO.File]::ReadAllText((Join-Path $root 'Repair-PDPOneConnectivity.ps1'))
    $maintenanceScript = [IO.File]::ReadAllText((Join-Path $root 'Invoke-PDPOneDiskMaintenance.ps1'))
    $agentScript = [IO.File]::ReadAllText((Join-Path $root 'Deployment-Agent.ps1'))
    $deploymentScript = [IO.File]::ReadAllText((Join-Path $root 'Invoke-PDPOneDeployment.ps1'))
    $composeText = [IO.File]::ReadAllText((Join-Path $repositoryRoot 'docker-compose.yml'))

    Assert-True ($updateScript -notmatch '-RestoreDatabase:\$migrationAttempted') 'Unsafe Boolean switch forwarding returned.'
    Assert-True ($updateScript -match '\$rollbackArgs \+= "-RestoreDatabase"') 'Conditional rollback switch token is missing.'
    Assert-True ($updateScript -match 'manual-update') 'Manual diagnostic fallback identifier is missing.'

    foreach ($scriptText in @($updateScript, $rollbackScript)) {
        Assert-True ($scriptText -match 'function Invoke-PDPOneDockerCompose') 'Docker Compose native wrapper is missing.'
        Assert-True ($scriptText -match '\$ErrorActionPreference = "Continue"') 'Docker Compose stderr is not kept non-terminating.'
        Assert-True ($scriptText -match '\$exitCode = \$LASTEXITCODE') 'Docker Compose native exit code is not captured.'
        Assert-True ($scriptText -match 'docker compose @Arguments 2>&1') 'Docker Compose streams are not captured safely.'
    }
    Assert-True ($connectivityScript -match 'function Invoke-PDPOneConnectivityDockerCompose') 'Connectivity Docker Compose native wrapper is missing.'
    Assert-True ($connectivityScript -match '\$ErrorActionPreference = "Continue"') 'Connectivity stderr is not kept non-terminating.'
    Assert-True ($connectivityScript -match '\$exitCode = \$LASTEXITCODE') 'Connectivity native exit code is not captured.'
    Assert-True ($connectivityScript -match 'docker compose @Arguments 2>&1') 'Connectivity Docker Compose streams are not captured safely.'
    Assert-True ($updateScript -notmatch '(?m)^\s*& docker compose ') 'Raw Docker Compose calls returned to the updater.'
    Assert-True ($rollbackScript -notmatch '(?m)^\s*& docker compose ') 'Raw Docker Compose calls returned to rollback.'
    Assert-True ($connectivityScript -notmatch '(?m)^\s*& docker compose ') 'Raw Docker Compose calls returned to connectivity repair.'

    # Deployment builds must be isolated, sequential and completed before any
    # production service is stopped or source file is copied into place.
    Assert-True ($updateScript -match 'COMPOSE_PARALLEL_LIMIT = "1"') 'Sequential Compose build limit is missing.'
    Assert-True ($updateScript -match 'foreach \(\$service in @\("backend", "mcp", "web"\)\)') 'Expected sequential release build set is missing.'
    Assert-True ($updateScript -notmatch '@\("build", "backend", "worker", "beat", "mcp", "web"\)') 'Parallel duplicate backend build returned.'
    Assert-True ($updateScript -match 'candidate-\$releaseSuffix') 'Commit-scoped candidate image tags are missing.'
    Assert-True ($updateScript -match 'Candidate \$service image could not be activated') 'Candidate activation gate is missing.'
    Assert-True ($updateScript.IndexOf('Invoke-PDPOneSequentialBuild -Service $service') -lt $updateScript.IndexOf('"stop", "backend", "worker", "beat"')) 'Production is stopped before candidate builds finish.'
    Assert-True ($updateScript.IndexOf('"stop", "backend", "worker", "beat"') -lt $updateScript.IndexOf('Candidate $service image could not be activated')) 'Candidate image tags are activated before production is stopped.'
    Assert-True ($composeText -match 'image: \$\{PDP_BACKEND_IMAGE:-pdp-one-backend:local\}') 'Shared backend image variable is missing.'
    Assert-True (([regex]::Matches($composeText, 'image: \$\{PDP_BACKEND_IMAGE:-pdp-one-backend:local\}')).Count -eq 3) 'Backend, worker and beat do not share exactly one backend image.'
    Assert-True ($composeText -match 'image: \$\{PDP_MCP_IMAGE:-pdp-one-mcp:local\}') 'MCP candidate image variable is missing.'
    Assert-True ($composeText -match 'image: \$\{PDP_WEB_IMAGE:-pdp-one-web:local\}') 'Web candidate image variable is missing.'

    Assert-True ($maintenanceScript -match 'container", "prune", "--force"') 'Stopped-container cleanup is missing.'
    Assert-True ($maintenanceScript -match 'image", "prune", "--all", "--force"') 'Unused-image cleanup is missing.'
    Assert-True ($maintenanceScript -match 'builder", "prune", "--all", "--force"') 'Build-cache cleanup is missing.'
    Assert-True ($maintenanceScript -notmatch '(?i)docker\s+(volume\s+(rm|prune)|system\s+prune[^\r\n]*--volumes)') 'Disk maintenance contains a forbidden Docker volume operation.'
    Assert-True ($maintenanceScript -match '\[ValidateRange\(2, 10\)\]\[int\]\$KeepLocalFinalBackups = 2') 'Local verified-backup retention may fall below two.'
    Assert-True ($maintenanceScript -match 'database_volume_touched = \$false') 'Database-volume protection marker is missing.'
    Assert-True ($maintenanceScript -match 'private_files_volume_touched = \$false') 'Private-files volume protection marker is missing.'
    Assert-True ($maintenanceScript -match 'tailscale_volume_touched = \$false') 'Tailscale-volume protection marker is missing.'
    Assert-True ($updateScript -match 'Invoke-PDPOneDiskMaintenance\.ps1') 'Post-deployment disk maintenance is not wired into the updater.'
    Assert-True ($updateScript -match 'if \(-not \$DevelopmentFastMode\) \{ \$maintenanceArgs \+= @\("-ProtectedBackupPath", \$BackupPath\) \}') 'Standard mode does not protect the current rollback backup during cleanup.'

    # Standard mode must retain all approval, verified-backup and database-rollback gates.
    Assert-True ($agentScript -match 'state\\approved-backup\.json') 'Verified backup state is not recorded by the agent.'
    Assert-True ($agentScript -match '\$verifiedBackupPath = \[string\]\$backupState\.backup_path') 'Standard deployment does not bind the verified backup path.'
    Assert-True ($agentScript -match 'No explicit release approval is recorded') 'Standard explicit-approval gate is missing.'
    Assert-True ($agentScript -match 'No fresh verified final backup is recorded') 'Standard final-backup gate is missing.'
    Assert-True ($deploymentScript -match '\[string\]\$VerifiedBackupPath = ""') 'Deployment does not accept a verified backup path.'
    Assert-True ($deploymentScript -match 'Verified backup commit does not match') 'Verified backup commit binding is missing.'

    # Trial development-fast mode may skip per-commit approval and database backup,
    # but it must retain exact-commit validation, code snapshot, health and audit.
    Assert-True ($agentScript -match 'PDP_CHANGE_MANAGEMENT_MODE') 'Explicit change-management mode is not read.'
    Assert-True ($agentScript -match 'PDP_TRIAL_MODE') 'Trial-mode fallback is missing.'
    Assert-True ($agentScript -match 'development_fast') 'Development-fast mode marker is missing.'
    Assert-True ($agentScript -match 'if \(-not \$developmentFast\)') 'Standard gates are not isolated from development-fast mode.'
    Assert-True ($agentScript -match 'backup_skipped = \[bool\]\$developmentFast') 'Development-fast deployment does not report backup skipping.'
    Assert-True ($deploymentScript -match '\[switch\]\$DevelopmentFastMode') 'Deployment fast-mode switch is missing.'
    Assert-True ($deploymentScript -match 'preparing-code-only-rollback') 'Code-only rollback preparation is missing.'
    Assert-True ($deploymentScript -match 'snapshotting-current-code') 'Code snapshot is missing from fast mode.'
    Assert-True ($deploymentScript -match 'GitHub exact-commit verification') 'Exact-commit verification is missing.'
    Assert-True ($updateScript -match '\[switch\]\$DevelopmentFastMode') 'Updater fast-mode switch is missing.'
    Assert-True ($updateScript -match '\$migrationAttempted -and -not \$DevelopmentFastMode') 'Fast mode may still restore an unverified database backup.'
    Assert-True ($updateScript -match 'Layered post-update health failed') 'Post-update health gate is missing.'
    Assert-True ($deploymentScript -match 'Remove-Item -LiteralPath \$downloadDirectory -Recurse -Force') 'Deployment staging cleanup is missing.'

    Assert-True ($agentScript -match '"run_disk_maintenance"') 'Signed immediate disk-maintenance action is missing.'
    Assert-True ($agentScript -match '-Mode", "cleanup"') 'Immediate maintenance does not invoke cleanup mode.'
    Assert-True ($agentScript -match 'Backup retention must be between 2 and 10') 'Immediate maintenance retention validation is missing.'
    Assert-True ($agentScript -match 'volumes_pruned = \$false') 'Immediate maintenance does not enforce volume-protection results.'
    Assert-True ($agentScript -match 'state\\last-deployment\.json') 'Immediate maintenance does not protect the last rollback backup.'

    Write-Host 'Windows PowerShell 5.1 compatibility tests passed.' -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
