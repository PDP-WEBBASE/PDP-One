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
    $agentWrapper = [IO.File]::ReadAllText((Join-Path $root 'Deployment-Agent.ps1'))
    $standardAgent = [IO.File]::ReadAllText((Join-Path $root 'Deployment-Agent.Standard.ps1'))
    $deploymentDispatcher = [IO.File]::ReadAllText((Join-Path $root 'Invoke-PDPOneDeployment.ps1'))
    $standardDeployment = [IO.File]::ReadAllText((Join-Path $root 'Invoke-PDPOneDeployment.Standard.ps1'))
    $fastDeployment = [IO.File]::ReadAllText((Join-Path $root 'Invoke-PDPOneFastDeployment.ps1'))
    $composeText = [IO.File]::ReadAllText((Join-Path $repositoryRoot 'docker-compose.yml'))
    $phasePath = Join-Path $repositoryRoot 'release\implementation-in-progress.json'

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

    Assert-True ($updateScript -match 'COMPOSE_PARALLEL_LIMIT = "1"') 'Sequential Compose build limit is missing.'
    Assert-True ($updateScript -match 'foreach \(\$service in @\("backend", "mcp", "web"\)\)') 'Expected sequential release build set is missing.'
    Assert-True ($updateScript -notmatch '@\("build", "backend", "worker", "beat", "mcp", "web"\)') 'Parallel duplicate backend build returned.'
    Assert-True ($updateScript -match 'candidate-\$releaseSuffix') 'Commit-scoped candidate image tags are missing.'
    Assert-True ($updateScript -match 'Candidate \$service image could not be activated') 'Candidate activation gate is missing.'
    Assert-True ($updateScript.IndexOf('Invoke-PDPOneSequentialBuild -Service $service') -lt $updateScript.IndexOf('"stop", "backend", "worker", "beat"')) 'Production is stopped before candidate builds finish.'
    Assert-True ($composeText -match 'image: \$\{PDP_BACKEND_IMAGE:-pdp-one-backend:local\}') 'Shared backend image variable is missing.'
    Assert-True (([regex]::Matches($composeText, 'image: \$\{PDP_BACKEND_IMAGE:-pdp-one-backend:local\}')).Count -eq 3) 'Backend, worker and beat do not share exactly one backend image.'
    Assert-True ($composeText -match 'image: \$\{PDP_MCP_IMAGE:-pdp-one-mcp:local\}') 'MCP candidate image variable is missing.'
    Assert-True ($composeText -match 'image: \$\{PDP_WEB_IMAGE:-pdp-one-web:local\}') 'Web candidate image variable is missing.'

    Assert-True ($maintenanceScript -notmatch '(?i)docker\s+(volume\s+(rm|prune)|system\s+prune[^\r\n]*--volumes)') 'Disk maintenance contains a forbidden Docker volume operation.'
    Assert-True ($maintenanceScript -match 'database_volume_touched = \$false') 'Database-volume protection marker is missing.'
    Assert-True ($maintenanceScript -match 'private_files_volume_touched = \$false') 'Private-files volume protection marker is missing.'
    Assert-True ($maintenanceScript -match 'tailscale_volume_touched = \$false') 'Tailscale-volume protection marker is missing.'

    # The preserved standard path remains available only for explicit completion
    # or a destructive/sensitive database change.
    Assert-True ($standardAgent -match 'state\\approved-backup\.json') 'Verified backup state is not retained in standard mode.'
    Assert-True ($standardAgent -match 'No explicit release approval is recorded') 'Standard explicit-approval gate is missing.'
    Assert-True ($standardAgent -match 'No fresh verified final backup is recorded') 'Standard final-backup gate is missing.'
    Assert-True ($standardDeployment -match '\[string\]\$VerifiedBackupPath = ""') 'Standard deployment does not accept a verified backup path.'
    Assert-True ($standardDeployment -match 'Verified backup commit does not match') 'Standard verified-backup binding is missing.'
    Assert-True ($standardDeployment -match 'snapshotting-current-code') 'Standard code snapshot was not preserved.'

    # While implementation is in progress the wrapper must restore fast mode on
    # every agent start. The exact completion phrase is recorded in the marker.
    Assert-True (Test-Path -LiteralPath $phasePath) 'Implementation-phase marker is missing.'
    $phaseText = [IO.File]::ReadAllText($phasePath, [Text.Encoding]::UTF8)
    $phase = $phaseText | ConvertFrom-Json
    Assert-True ([string]$phase.status -eq 'in_progress') 'Implementation phase is not active.'
    Assert-True ([string]$phase.change_management_mode -eq 'development_fast') 'Implementation marker does not select development_fast.'
    $expectedCompletion = New-PDPOneCodePointString @(0x067E,0x06CC,0x0627,0x062F,0x0647,0x0020,0x0633,0x0627,0x0632,0x06CC,0x0020,0x0633,0x0627,0x0645,0x0627,0x0646,0x0647,0x0020,0x062A,0x06A9,0x0645,0x06CC,0x0644,0x0020,0x0634,0x062F,0x0647,0x0020,0x0627,0x0633,0x062A)
    $actualCompletion = ([string]$phase.completion_trigger_exact_text).Normalize([Text.NormalizationForm]::FormKC).Trim()
    Assert-True ([string]::Equals($actualCompletion, $expectedCompletion, [StringComparison]::Ordinal)) 'Exact completion trigger changed.'
    Assert-True ($agentWrapper -match 'implementation-in-progress\.json') 'Agent wrapper does not read the implementation marker.'
    Assert-True ($agentWrapper -match 'PDP_CHANGE_MANAGEMENT_MODE') 'Agent wrapper does not set change-management mode.'
    Assert-True ($agentWrapper -match 'development_fast') 'Agent wrapper does not restore fast mode.'
    Assert-True ($agentWrapper -match 'PDP_TRIAL_MODE') 'Agent wrapper does not restore trial mode.'
    Assert-True ($agentWrapper -match 'Deployment-Agent\.Standard\.ps1') 'Preserved standard agent is not delegated safely.'

    # Fast mode is a separate implementation with no per-change backup, restore,
    # local code snapshot or automatic rollback.
    Assert-True ($deploymentDispatcher -match '\[switch\]\$DevelopmentFastMode') 'Deployment dispatcher has no fast-mode switch.'
    Assert-True ($deploymentDispatcher -match 'Invoke-PDPOneFastDeployment\.ps1') 'Fast deployment is not selected by the dispatcher.'
    Assert-True ($deploymentDispatcher -match 'Invoke-PDPOneDeployment\.Standard\.ps1') 'Standard deployment delegate is missing.'
    Assert-True ($fastDeployment -match 'GitHub exact-commit verification') 'Fast deployment does not verify the exact commit.'
    Assert-True ($fastDeployment -match 'candidate-\$releaseSuffix') 'Fast deployment does not use commit-scoped candidate images.'
    Assert-True ($fastDeployment.IndexOf('"compose", "build", $service') -lt $fastDeployment.IndexOf('"stop", "backend", "worker", "beat"')) 'Fast deployment stops production before candidate builds finish.'
    Assert-True ($fastDeployment -match 'manage\.py", "migrate", "--noinput"') 'Fast deployment does not control migrations.'
    Assert-True ($fastDeployment -match 'database-change-risk\.json') 'Sensitive database-change backup gate is missing.'
    Assert-True ($fastDeployment -match 'Wait-PDPOneUrl.+TimeoutSeconds 75') 'Short local health check is missing.'
    Assert-True ($fastDeployment -match 'Test-PDPOnePublicHealth.+TimeoutSeconds 25') 'Short public health check is missing.'
    Assert-True ($fastDeployment -match 'previous_commit') 'Previous GitHub commit is not recorded for emergency redeploy.'
    Assert-True ($fastDeployment -match 'redeploy_previous_commit_from_github') 'Emergency rollback method is not documented in state.'
    Assert-True ($fastDeployment -match 'database_backup_created = \$false') 'Fast deployment does not report backup omission.'
    Assert-True ($fastDeployment -match 'restore_verification_run = \$false') 'Fast deployment does not report restore omission.'
    Assert-True ($fastDeployment -match 'local_code_snapshot_created = \$false') 'Fast deployment does not report snapshot omission.'
    Assert-True ($fastDeployment -match 'automatic_rollback_enabled = \$false') 'Fast deployment does not report automatic rollback omission.'
    Assert-True ($fastDeployment -notmatch 'New-PDPOneBackup\.ps1') 'Fast deployment still creates a database backup.'
    Assert-True ($fastDeployment -notmatch 'Test-PDPOneBackupRestore\.ps1') 'Fast deployment still runs restore verification.'
    Assert-True ($fastDeployment -notmatch 'code-before-deployment\.zip') 'Fast deployment still creates a local code snapshot.'
    Assert-True ($fastDeployment -notmatch 'Rollback-PDPOne\.ps1') 'Fast deployment still performs automatic rollback.'
    Assert-True ($fastDeployment -notmatch '(?i)docker\s+(volume\s+(rm|prune)|system\s+prune[^\r\n]*--volumes)') 'Fast deployment contains a forbidden Docker volume operation.'

    Write-Host 'Windows PowerShell 5.1 compatibility and fast-development policy tests passed.' -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
