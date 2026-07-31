#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$CommitSha,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$DeploymentId,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$PreviewId,
    [Parameter(Mandatory = $true)][string]$AgentRoot
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

function Invoke-PDPOneNative {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage,
        [switch]$IgnoreFailure,
        [switch]$Quiet
    )
    $previousPreference = $ErrorActionPreference
    $output = @()
    $exitCode = -1
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& $Command @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if (-not $Quiet -and $output.Count -gt 0) {
        $safe = ConvertTo-PDPOneRedactedText (($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
        if (-not [string]::IsNullOrWhiteSpace($safe)) { Write-Host $safe }
    }
    if ($exitCode -ne 0 -and -not $IgnoreFailure) {
        throw "$FailureMessage (exit code $exitCode)."
    }
    return $exitCode
}

function Invoke-PDPOneAcquisitionRetry {
    param([string]$Stage, [scriptblock]$Action, [int]$Attempts = 3)
    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt += 1) {
        try { return & $Action } catch {
            $lastError = $_
            if ($attempt -ge $Attempts) { break }
            Start-Sleep -Seconds ([Math]::Min(5, [int][Math]::Pow(2, $attempt)))
        }
    }
    $message = if ($null -ne $lastError) { ConvertTo-PDPOneRedactedText $lastError.Exception.Message } else { "Unknown acquisition error." }
    throw "$Stage failed after $Attempts attempts. $message"
}

function Set-PDPOneProcessEnvironment([string]$Name, $Value) {
    if ($null -eq $Value) { Remove-Item ("Env:" + $Name) -ErrorAction SilentlyContinue }
    else { Set-Item ("Env:" + $Name) ([string]$Value) }
}

$projectRoot = Get-PDPOneProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $projectRoot
$reportsRoot = Join-Path $AgentRoot "reports"
$downloadRoot = Join-Path $AgentRoot "downloads\$DeploymentId"
$extractRoot = Join-Path $downloadRoot "source"
New-Item -ItemType Directory -Force -Path $reportsRoot | Out-Null
$reportPath = Join-Path $reportsRoot "$DeploymentId.json"
$previousCommit = ""
$lastStatePath = Join-Path $AgentRoot "state\last-deployment.json"
if (Test-Path -LiteralPath $lastStatePath) {
    try { $previousCommit = [string]((Get-Content -LiteralPath $lastStatePath -Raw -Encoding UTF8 | ConvertFrom-Json).approved_commit) } catch { }
}

$report = [ordered]@{
    deployment_id = $DeploymentId
    preview_id = $PreviewId
    approved_commit = $CommitSha
    previous_commit = $previousCommit
    started_at = [DateTime]::UtcNow.ToString("o")
    completed_at = $null
    status = "starting"
    stage = "initializing"
    change_management_mode = "development_fast"
    database_backup_created = $false
    restore_verification_run = $false
    local_code_snapshot_created = $false
    automatic_rollback_enabled = $false
    production_changed = $false
    health_profile = "short"
    error = $null
    recovery_instruction = "Redeploy previous_commit from GitHub if the active commit is unhealthy."
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8

$secretPath = Join-Path $AgentRoot "secrets\github-token.dpapi"
$pointer = [IntPtr]::Zero
$plainToken = $null
$sourceEnvPath = $null
$previousEnvironment = @{
    COMPOSE_PARALLEL_LIMIT = $env:COMPOSE_PARALLEL_LIMIT
    PDP_BACKEND_IMAGE = $env:PDP_BACKEND_IMAGE
    PDP_MCP_IMAGE = $env:PDP_MCP_IMAGE
    PDP_WEB_IMAGE = $env:PDP_WEB_IMAGE
}
$tokenBefore = Get-PDPOneTokenFingerprint (Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN")
$releaseSuffix = $CommitSha.Substring(0, 12)
$candidateImages = [ordered]@{
    backend = "pdp-one-backend:candidate-$releaseSuffix"
    mcp = "pdp-one-mcp:candidate-$releaseSuffix"
    web = "pdp-one-web:candidate-$releaseSuffix"
}
$productionImages = [ordered]@{
    backend = "pdp-one-backend:local"
    mcp = "pdp-one-mcp:local"
    web = "pdp-one-web:local"
}

try {
    Start-PDPOneRancherDesktop -TimeoutSeconds 300
    if (-not (Test-PDPOneDockerEngine)) { throw "Docker Engine is not ready." }
    if (-not (Test-Path -LiteralPath $secretPath)) { throw "The protected GitHub credential is missing." }

    $report.stage = "acquiring-exact-commit"
    $report.status = "running"
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8

    $secureToken = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($plainToken)) { throw "The protected GitHub credential could not be opened." }

    if (Test-Path -LiteralPath $downloadRoot) { Remove-Item -LiteralPath $downloadRoot -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
    $archive = Join-Path $downloadRoot "approved-source.zip"
    $headers = @{ Authorization = "Bearer $plainToken"; Accept = "application/vnd.github+json"; "X-GitHub-Api-Version" = "2022-11-28"; "User-Agent" = "PDP-One-Fast-Deployment" }
    $commit = Invoke-PDPOneAcquisitionRetry -Stage "GitHub exact-commit verification" -Action {
        Invoke-RestMethod -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/commits/$CommitSha" -Headers $headers -TimeoutSec 45
    }
    if ([string]$commit.sha -ne $CommitSha) { throw "GitHub did not return the requested exact commit." }
    Invoke-PDPOneAcquisitionRetry -Stage "GitHub source download" -Action {
        Invoke-WebRequest -UseBasicParsing -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/zipball/$CommitSha" -Headers $headers -OutFile $archive -TimeoutSec 120
    } | Out-Null
    if (-not (Test-Path -LiteralPath $archive) -or (Get-Item -LiteralPath $archive).Length -le 0) { throw "The exact-commit source archive is empty." }
    Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot -Force
    $sourceRoot = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
    if ($null -eq $sourceRoot -or -not (Test-Path -LiteralPath (Join-Path $sourceRoot.FullName "docker-compose.yml"))) {
        throw "The exact-commit source archive is invalid."
    }

    $riskPath = Join-Path $sourceRoot.FullName "release\database-change-risk.json"
    if (Test-Path -LiteralPath $riskPath) {
        $risk = Get-Content -LiteralPath $riskPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([bool]$risk.requires_backup) {
            throw "This commit declares a destructive or sensitive database change and must use the standard backup workflow."
        }
    }

    $report.stage = "building-candidate-images"
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $sourceEnvPath = Join-Path $sourceRoot.FullName ".env"
    Copy-Item -LiteralPath $envPath -Destination $sourceEnvPath -Force
    $env:COMPOSE_PARALLEL_LIMIT = "1"
    $env:PDP_BACKEND_IMAGE = $candidateImages.backend
    $env:PDP_MCP_IMAGE = $candidateImages.mcp
    $env:PDP_WEB_IMAGE = $candidateImages.web
    Set-Location $sourceRoot.FullName
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "config", "--quiet") -FailureMessage "Candidate Docker Compose configuration is invalid." | Out-Null
    foreach ($service in @("backend", "mcp", "web")) {
        Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "build", $service) -FailureMessage "Candidate image build failed for $service." | Out-Null
    }
    Remove-Item -LiteralPath $sourceEnvPath -Force -ErrorAction SilentlyContinue
    $sourceEnvPath = $null
    foreach ($name in @("COMPOSE_PARALLEL_LIMIT", "PDP_BACKEND_IMAGE", "PDP_MCP_IMAGE", "PDP_WEB_IMAGE")) {
        Set-PDPOneProcessEnvironment -Name $name -Value $previousEnvironment[$name]
    }

    $report.stage = "activating-exact-commit"
    $report.production_changed = $true
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Set-Location $projectRoot
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "--profile", "tunnel", "stop", "backend", "worker", "beat", "mcp", "web", "nginx", "tailscale") -FailureMessage "Application services could not be stopped cleanly." | Out-Null
    & robocopy.exe $sourceRoot.FullName $projectRoot /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NP /XF .env /XD .git work node_modules .next
    if ($LASTEXITCODE -gt 7) { throw "Exact-commit application files could not be copied." }
    foreach ($service in @("backend", "mcp", "web")) {
        Invoke-PDPOneNative -Command "docker" -Arguments @("image", "tag", $candidateImages[$service], $productionImages[$service]) -FailureMessage "Candidate image activation failed for $service." | Out-Null
    }
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "config", "--quiet") -FailureMessage "Installed Docker Compose configuration is invalid." | Out-Null
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "up", "--detach", "db", "redis") -FailureMessage "Database dependencies could not be started." | Out-Null
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "run", "--rm", "backend", "python", "manage.py", "migrate", "--noinput") -FailureMessage "Controlled migration failed." | Out-Null
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "--profile", "tunnel", "up", "--detach", "--no-build") -FailureMessage "Updated services failed to start." | Out-Null

    $report.stage = "short-health-check"
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    if (-not (Wait-PDPOneUrl -Url "http://127.0.0.1:8080/healthz" -TimeoutSeconds 75)) {
        throw "Short local health check timed out."
    }
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "exec", "-T", "db", "pg_isready") -FailureMessage "PostgreSQL health check failed." -Quiet | Out-Null
    $publicBase = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_PUBLIC_BASE_URL")
    if (-not [string]::IsNullOrWhiteSpace($publicBase)) {
        $publicHealth = Test-PDPOnePublicHealth -Url ($publicBase.TrimEnd('/') + "/healthz") -TimeoutSeconds 25
        if (-not [bool]$publicHealth.Success) { throw "Short public health check failed: $($publicHealth.Detail)" }
    }
    $tokenAfter = Get-PDPOneTokenFingerprint (Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN")
    if ($tokenBefore -ne $tokenAfter) { throw "Fast deployment changed the MCP path token without authorization." }

    $stateRoot = Join-Path $AgentRoot "state"
    New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
    [ordered]@{
        deployment_id = $DeploymentId
        preview_id = $PreviewId
        approved_commit = $CommitSha
        previous_commit = $previousCommit
        started_at = $report.started_at
        completed_at = [DateTime]::UtcNow.ToString("o")
        status = "healthy"
        change_management_mode = "development_fast"
        rollback_method = "redeploy_previous_commit_from_github"
        backup_path = $null
        code_archive = $null
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $lastStatePath -Encoding UTF8

    $binRoot = Join-Path $AgentRoot "bin"
    New-Item -ItemType Directory -Force -Path $binRoot | Out-Null
    Copy-Item -Path (Join-Path $projectRoot "scripts\windows\*.ps1") -Destination $binRoot -Force
    Set-Content -LiteralPath (Join-Path $stateRoot "restart-agent-after-response") -Value ([DateTime]::UtcNow.ToString("o")) -Encoding ASCII

    foreach ($service in @("backend", "mcp", "web")) {
        Invoke-PDPOneNative -Command "docker" -Arguments @("image", "rm", $candidateImages[$service]) -FailureMessage "Candidate tag cleanup failed." -IgnoreFailure -Quiet | Out-Null
    }

    $report.status = "healthy"
    $report.stage = "completed"
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report.error = $null
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output $reportPath
} catch {
    $report.status = "failed"
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report.error = ConvertTo-PDPOneRedactedText $_.Exception.Message
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    if ($report.production_changed) {
        try {
            Set-Location $projectRoot
            Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "--profile", "tunnel", "up", "--detach", "--no-build") -FailureMessage "Services could not be restarted after the failed deployment." -IgnoreFailure -Quiet | Out-Null
        } catch { }
    }
    throw "Fast deployment failed without automatic rollback. Redeploy previous commit '$previousCommit' from GitHub. $($report.error)"
} finally {
    if ($sourceEnvPath -and (Test-Path -LiteralPath $sourceEnvPath)) { Remove-Item -LiteralPath $sourceEnvPath -Force -ErrorAction SilentlyContinue }
    foreach ($name in @("COMPOSE_PARALLEL_LIMIT", "PDP_BACKEND_IMAGE", "PDP_MCP_IMAGE", "PDP_WEB_IMAGE")) {
        Set-PDPOneProcessEnvironment -Name $name -Value $previousEnvironment[$name]
    }
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $plainToken = $null
    if (Test-Path -LiteralPath $downloadRoot) { Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
