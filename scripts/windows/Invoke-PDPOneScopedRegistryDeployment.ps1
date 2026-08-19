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
. (Join-Path $PSScriptRoot "PDPOne.ReleaseManifest.ps1")

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
    if ($exitCode -ne 0 -and -not $IgnoreFailure) { throw "$FailureMessage (exit code $exitCode)." }
    return $exitCode
}

function Invoke-PDPOneRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][scriptblock]$Action,
        [int]$Attempts = 4
    )
    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt += 1) {
        try { return & $Action } catch {
            $lastError = $_
            if ($attempt -ge $Attempts) { break }
            Start-Sleep -Seconds ([Math]::Min(10, [int][Math]::Pow(2, $attempt)))
        }
    }
    $message = if ($null -ne $lastError) { ConvertTo-PDPOneRedactedText $lastError.Exception.Message } else { "Unknown error." }
    throw "$Stage failed after $Attempts attempts. $message"
}

function Set-PDPOneProcessEnvironment([string]$Name, $Value) {
    if ($null -eq $Value) { Remove-Item ("Env:" + $Name) -ErrorAction SilentlyContinue }
    else { Set-Item ("Env:" + $Name) ([string]$Value) }
}

function Get-PDPOnePreviousImageMap($State) {
    $images = [ordered]@{ backend = ""; mcp = ""; web = "" }
    if ($null -eq $State -or $null -eq $State.active_images) { return $images }
    foreach ($service in @("backend", "mcp", "web")) {
        $property = $State.active_images.PSObject.Properties[$service]
        if ($null -ne $property) { $images[$service] = [string]$property.Value }
    }
    return $images
}

function Test-PDPOneImageExistsLocally([string]$Image) {
    if (-not $Image) { return $false }
    & docker image inspect $Image *> $null
    return ($LASTEXITCODE -eq 0)
}

function Assert-PDPOneResolvedImage {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][string]$Image,
        [Parameter(Mandatory = $true)][string]$TargetImageMode,
        [string]$TargetFingerprint = "",
        [string]$ReleaseCommit = ""
    )
    if ($Image -match ':content-([0-9a-f]{64})$') {
        Assert-PDPOneReleaseImageIdentity -Component $Service -Image $Image -ImageMode "content-addressed-v1" -ExpectedFingerprint $matches[1]
        return
    }
    $revision = Get-PDPOneReferenceEmbeddedRevision -Image $Image
    if ($TargetImageMode -eq "legacy-exact-sha" -and $revision -eq $ReleaseCommit) {
        Assert-PDPOneReleaseImageIdentity -Component $Service -Image $Image -ImageMode "legacy-exact-sha" -ExpectedRevision $ReleaseCommit
        return
    }
    if ($revision -match '^[0-9a-f]{40}$') {
        Assert-PDPOneReleaseImageIdentity -Component $Service -Image $Image -ImageMode "legacy-exact-sha" -ExpectedRevision $revision
        return
    }
    if ($TargetImageMode -eq "content-addressed-v1" -and $TargetFingerprint -match '^[0-9a-f]{64}$') {
        Assert-PDPOneReleaseImageIdentity -Component $Service -Image $Image -ImageMode "content-addressed-v1" -ExpectedFingerprint $TargetFingerprint
        return
    }
    throw "Could not validate immutable image identity for $Service."
}

function Get-PDPOneActivationTargets([string[]]$ChangedServices) {
    $targets = @()
    if ("backend" -in $ChangedServices) { $targets += @("backend", "worker", "beat") }
    if ("mcp" -in $ChangedServices) { $targets += "mcp" }
    if ("web" -in $ChangedServices) { $targets += "web" }
    return @($targets | Select-Object -Unique)
}

$projectRoot = Get-PDPOneProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $projectRoot
$reportsRoot = Join-Path $AgentRoot "reports"
$downloadRoot = Join-Path $AgentRoot ("downloads\" + $DeploymentId)
$extractRoot = Join-Path $downloadRoot "source"
$stateRoot = Join-Path $AgentRoot "state"
$lastStatePath = Join-Path $stateRoot "last-deployment.json"
New-Item -ItemType Directory -Force -Path $reportsRoot | Out-Null
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null
$reportPath = Join-Path $reportsRoot ($DeploymentId + ".json")

$previousState = $null
$previousCommit = ""
if (Test-Path -LiteralPath $lastStatePath) {
    try {
        $previousState = Get-Content -LiteralPath $lastStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $previousCommit = [string]$previousState.approved_commit
    } catch { $previousState = $null; $previousCommit = "" }
}
$previousImages = Get-PDPOnePreviousImageMap -State $previousState
$currentImages = [ordered]@{ backend = ""; mcp = ""; web = "" }
$fingerprints = [ordered]@{ backend = ""; mcp = ""; web = "" }
$changedServices = @()
$changedPaths = @()
$imageMode = "legacy-exact-sha"
$healthProfile = "full"
$releaseManifestPath = ""
$previousManifestPath = if ($null -ne $previousState -and $previousState.active_release_manifest) { [string]$previousState.active_release_manifest } else { "" }

$report = [ordered]@{
    schema = "pdp-one.deployment-report.v3"
    deployment_id = $DeploymentId
    preview_id = $PreviewId
    approved_commit = $CommitSha
    previous_commit = $previousCommit
    started_at = [DateTime]::UtcNow.ToString("o")
    completed_at = $null
    status = "starting"
    stage = "initializing"
    change_management_mode = "development_fast"
    image_source = "github_container_registry"
    image_mode = $imageMode
    local_image_build_performed = $false
    database_backup_created = $false
    restore_verification_run = $false
    local_code_snapshot_created = $false
    automatic_rollback_enabled = $false
    production_changed = $false
    health_profile = $healthProfile
    changed_services = @()
    changed_paths = @()
    active_images = $currentImages
    retained_previous_images = $previousImages
    release_manifest = $null
    connectivity_repair_attempted = $false
    connectivity_repair_succeeded = $false
    error = $null
    recovery_instruction = "Redeploy the previous release commit through the governed deployment queue if the active release is unhealthy."
}
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8

$secretPath = Join-Path $AgentRoot "secrets\github-token.dpapi"
$pointer = [IntPtr]::Zero
$plainToken = $null
$sourceEnvPath = $null
$loggedIntoRegistry = $false
$previousEnvironment = @{
    PDP_BACKEND_IMAGE = $env:PDP_BACKEND_IMAGE
    PDP_MCP_IMAGE = $env:PDP_MCP_IMAGE
    PDP_WEB_IMAGE = $env:PDP_WEB_IMAGE
}
$tokenBefore = Get-PDPOneTokenFingerprint (Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN")

try {
    Start-PDPOneRancherDesktop -TimeoutSeconds 300
    if (-not (Test-PDPOneDockerEngine)) { throw "Docker Engine is not ready." }
    if (-not (Test-Path -LiteralPath $secretPath)) { throw "The protected GitHub credential is missing." }

    $secureToken = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($plainToken)) { throw "The protected GitHub credential could not be opened." }

    $headers = @{
        Authorization = "Bearer $plainToken"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = "PDP-One-Registry-Deployment"
    }

    $report.stage = "verifying-exact-commit"
    $report.status = "running"
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $commit = Invoke-PDPOneRetry -Stage "GitHub exact-commit verification" -Action {
        Invoke-RestMethod -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/commits/$CommitSha" -Headers $headers -TimeoutSec 45
    }
    if ([string]$commit.sha -ne $CommitSha) { throw "GitHub did not return the requested exact commit." }

    $report.stage = "acquiring-exact-source"
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    if (Test-Path -LiteralPath $downloadRoot) { Remove-Item -LiteralPath $downloadRoot -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
    $archive = Join-Path $downloadRoot "approved-source.zip"
    Invoke-PDPOneRetry -Stage "GitHub source download" -Action {
        Invoke-WebRequest -UseBasicParsing -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/zipball/$CommitSha" -Headers $headers -OutFile $archive -TimeoutSec 120
    } | Out-Null
    if (-not (Test-Path -LiteralPath $archive) -or (Get-Item -LiteralPath $archive).Length -le 0) { throw "The exact-commit source archive is empty." }
    Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot -Force
    $sourceRoot = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
    if ($null -eq $sourceRoot -or -not (Test-Path -LiteralPath (Join-Path $sourceRoot.FullName "docker-compose.yml"))) { throw "The exact-commit source archive is invalid." }

    $riskPath = Join-Path $sourceRoot.FullName "release\database-change-risk.json"
    if (Test-Path -LiteralPath $riskPath) {
        $risk = Get-Content -LiteralPath $riskPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([bool]$risk.requires_backup) { throw "This commit declares a destructive or sensitive database change and must use the standard backup workflow." }
    }

    $conservative = $true
    if ($previousCommit -match '^[0-9a-f]{40}$' -and $previousCommit -ne $CommitSha) {
        try {
            $changedPaths = @(Get-PDPOneChangedFilePaths -Headers $headers -PreviousCommit $previousCommit -CommitSha $CommitSha)
            $conservative = $false
        } catch {
            $changedPaths = @()
            $conservative = $true
        }
    }
    $scope = Get-PDPOneChangeScope -Paths $changedPaths -ConservativeFullStack:$conservative
    $imageMode = Get-PDPOneImageMode -SourceRoot $sourceRoot.FullName

    foreach ($service in @("backend", "mcp", "web")) {
        if ($imageMode -eq "content-addressed-v1") {
            $fingerprint = Get-PDPOneComponentFingerprint -SourceRoot $sourceRoot.FullName -Component $service
            $fingerprints[$service] = $fingerprint
            $currentImages[$service] = Get-PDPOneComponentImageReference -Component $service -Fingerprint $fingerprint
        } else {
            $previousReference = [string]$previousImages[$service]
            $serviceChanged = $scope.topology_sensitive -or ($service -in @($scope.changed_services)) -or [string]::IsNullOrWhiteSpace($previousReference)
            $currentImages[$service] = if ($serviceChanged) { "ghcr.io/pdp-webbase/pdp-one-$service`:$CommitSha" } else { $previousReference }
        }
    }

    foreach ($service in @("backend", "mcp", "web")) {
        if ([string]$previousImages[$service] -ne [string]$currentImages[$service]) { $changedServices += $service }
    }
    if ($scope.topology_sensitive) { $changedServices = @("backend", "mcp", "web") }
    $changedServices = @($changedServices | Select-Object -Unique)
    $healthProfile = if ($scope.topology_sensitive -or $changedServices.Count -gt 1) { "full" } elseif ($changedServices.Count -eq 1) { [string]$changedServices[0] } elseif ($scope.host) { "host" } else { "none" }

    $report.image_mode = $imageMode
    $report.changed_services = @($changedServices)
    $report.changed_paths = @($changedPaths)
    $report.health_profile = $healthProfile
    $report.active_images = $currentImages
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8

    $report.stage = "pulling-immutable-images"
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $plainToken | & docker login ghcr.io --username "PDP-WEBBASE" --password-stdin | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "GitHub Container Registry login failed. The protected token needs read access to private packages." }
    $loggedIntoRegistry = $true

    foreach ($service in @("backend", "mcp", "web")) {
        $image = [string]$currentImages[$service]
        $needsPull = ($service -in $changedServices) -or -not (Test-PDPOneImageExistsLocally -Image $image)
        if ($needsPull) {
            Invoke-PDPOneRetry -Stage "Pulling immutable $service image" -Action {
                Invoke-PDPOneNative -Command "docker" -Arguments @("pull", $image) -FailureMessage "Image pull failed for $service." | Out-Null
            } | Out-Null
        }
        Assert-PDPOneResolvedImage -Service $service -Image $image -TargetImageMode $imageMode -TargetFingerprint ([string]$fingerprints[$service]) -ReleaseCommit $CommitSha
    }

    $sourceEnvPath = Join-Path $sourceRoot.FullName ".env"
    Copy-Item -LiteralPath $envPath -Destination $sourceEnvPath -Force
    $env:PDP_BACKEND_IMAGE = $currentImages.backend
    $env:PDP_MCP_IMAGE = $currentImages.mcp
    $env:PDP_WEB_IMAGE = $currentImages.web
    Set-Location $sourceRoot.FullName
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "config", "--quiet") -FailureMessage "Registry-backed Docker Compose configuration is invalid." | Out-Null

    $report.stage = "activating-exact-release"
    $report.production_changed = $true
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8

    $activationTargets = @(Get-PDPOneActivationTargets -ChangedServices $changedServices)
    Set-Location $projectRoot
    if ($scope.topology_sensitive) {
        Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "--profile", "tunnel", "stop", "backend", "worker", "beat", "mcp", "web", "nginx", "tailscale") -FailureMessage "Application services could not be stopped cleanly." | Out-Null
    } elseif ($activationTargets.Count -gt 0) {
        Invoke-PDPOneNative -Command "docker" -Arguments (@("compose", "stop") + $activationTargets) -FailureMessage "Changed application services could not be stopped cleanly." | Out-Null
    }

    & robocopy.exe $sourceRoot.FullName $projectRoot /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NP /XF .env /XD .git work node_modules .next
    if ($LASTEXITCODE -gt 7) { throw "Exact-commit application files could not be copied." }

    Set-PDPOneEnvValue -Path $envPath -Name "PDP_BACKEND_IMAGE" -Value $currentImages.backend
    Set-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_IMAGE" -Value $currentImages.mcp
    Set-PDPOneEnvValue -Path $envPath -Name "PDP_WEB_IMAGE" -Value $currentImages.web

    Set-Location $projectRoot
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "config", "--quiet") -FailureMessage "Installed Docker Compose configuration is invalid." | Out-Null
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "up", "--detach", "db", "redis") -FailureMessage "Database dependencies could not be started." | Out-Null

    if ($scope.topology_sensitive -or ("backend" -in $changedServices)) {
        Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "run", "--rm", "backend", "python", "manage.py", "migrate", "--noinput") -FailureMessage "Controlled migration failed." | Out-Null
    }

    if ($scope.topology_sensitive) {
        Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "--profile", "tunnel", "up", "--detach", "--no-build", "--pull", "never") -FailureMessage "Updated services failed to start." | Out-Null
    } elseif ($activationTargets.Count -gt 0) {
        Invoke-PDPOneNative -Command "docker" -Arguments (@("compose", "up", "--detach", "--no-build", "--pull", "never", "--no-deps") + $activationTargets) -FailureMessage "Changed services failed to start." | Out-Null
    }

    $report.stage = "scope-aware-health-check"
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    $scopedHealthScript = Join-Path $projectRoot "scripts\windows\Test-PDPOneScopedHealth.ps1"
    if (-not (Test-Path -LiteralPath $scopedHealthScript)) { throw "Scope-aware health script is missing from the exact release." }
    try {
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $scopedHealthScript -Profile $healthProfile -TimeoutSeconds 75
        if ($LASTEXITCODE -ne 0) { throw "Scope-aware health returned a non-zero code." }
    } catch {
        $repairScript = Join-Path $projectRoot "scripts\windows\Repair-PDPOneConnectivity.ps1"
        if (Test-Path -LiteralPath $repairScript) {
            $report.connectivity_repair_attempted = $true
            $report.stage = "repairing-public-connectivity"
            $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
            try {
                & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $repairScript -ProjectRoot $projectRoot -RepairAttempts 1 -PublicCheckTimeoutSeconds 25 -TransientConfirmDelaySeconds 5 -DnsPublicationTimeoutSeconds 90 -DnsPollIntervalSeconds 10 | Out-Null
            } catch { }
            $report.stage = "scope-aware-health-check"
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $scopedHealthScript -Profile $healthProfile -TimeoutSeconds 75
            if ($LASTEXITCODE -ne 0) { throw "Scope-aware health failed after bounded connectivity recovery." }
            $report.connectivity_repair_succeeded = $true
        } else { throw }
    }

    $tokenAfter = Get-PDPOneTokenFingerprint (Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN")
    if ($tokenBefore -ne $tokenAfter) { throw "Fast deployment changed the MCP path token without authorization." }

    $releaseManifestPath = Write-PDPOneReleaseManifest -AgentRoot $AgentRoot -ReleaseCommit $CommitSha -DeploymentId $DeploymentId -ImageMode $imageMode -Images $currentImages -Fingerprints $fingerprints -ChangedServices $changedServices -HealthProfile $healthProfile
    $report.release_manifest = $releaseManifestPath

    [ordered]@{
        schema = "pdp-one.last-deployment.v3"
        deployment_id = $DeploymentId
        preview_id = $PreviewId
        approved_commit = $CommitSha
        previous_commit = $previousCommit
        active_images = $currentImages
        previous_images = $previousImages
        active_release_manifest = $releaseManifestPath
        previous_release_manifest = $previousManifestPath
        image_mode = $imageMode
        changed_services = @($changedServices)
        health_profile = $healthProfile
        started_at = $report.started_at
        completed_at = [DateTime]::UtcNow.ToString("o")
        status = "healthy"
        image_source = "github_container_registry"
        local_image_build_performed = $false
        change_management_mode = "development_fast"
        rollback_method = "redeploy_previous_release_commit_from_github_registry"
        backup_path = $null
        code_archive = $null
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $lastStatePath -Encoding UTF8

    $binRoot = Join-Path $AgentRoot "bin"
    New-Item -ItemType Directory -Force -Path $binRoot | Out-Null
    Copy-Item -Path (Join-Path $projectRoot "scripts\windows\*.ps1") -Destination $binRoot -Force
    Set-Content -LiteralPath (Join-Path $stateRoot "restart-agent-after-response") -Value ([DateTime]::UtcNow.ToString("o")) -Encoding ASCII

    $report.status = "healthy"
    $report.stage = "completed"
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report.error = $null
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output $reportPath
} catch {
    $report.status = "failed"
    $report.completed_at = [DateTime]::UtcNow.ToString("o")
    $report.error = ConvertTo-PDPOneRedactedText $_.Exception.Message
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    if ($report.production_changed) {
        try {
            Set-Location $projectRoot
            Invoke-PDPOneNative -Command "docker" -Arguments @("compose", "--profile", "tunnel", "up", "--detach", "--no-build", "--pull", "never") -FailureMessage "Services could not be restarted after the failed deployment." -IgnoreFailure -Quiet | Out-Null
        } catch { }
    }
    throw "Scoped registry deployment failed without automatic rollback. Redeploy previous release '$previousCommit'. $($report.error)"
} finally {
    if ($sourceEnvPath -and (Test-Path -LiteralPath $sourceEnvPath)) { Remove-Item -LiteralPath $sourceEnvPath -Force -ErrorAction SilentlyContinue }
    foreach ($name in @("PDP_BACKEND_IMAGE", "PDP_MCP_IMAGE", "PDP_WEB_IMAGE")) { Set-PDPOneProcessEnvironment -Name $name -Value $previousEnvironment[$name] }
    if ($loggedIntoRegistry) { & docker logout ghcr.io *> $null }
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $plainToken = $null
    if (Test-Path -LiteralPath $downloadRoot) { Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
