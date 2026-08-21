#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$FailedDeploymentId,
    [Parameter(Mandatory = $true)][string]$AgentRoot,
    [switch]$RefreshConnectivityEdge
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
. (Join-Path $PSScriptRoot "PDPOne.ReleaseManifest.ps1")

function Invoke-PDPOneRecoveryNative {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage,
        [switch]$IgnoreFailure
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
    if ($exitCode -ne 0 -and -not $IgnoreFailure) { throw "$FailureMessage (exit code $exitCode)." }
    return $exitCode
}

function Invoke-PDPOneRecoveryRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)][scriptblock]$Action,
        [int]$Attempts = 3
    )
    $lastError = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt += 1) {
        try { return & $Action } catch {
            $lastError = $_
            if ($attempt -ge $Attempts) { break }
            Start-Sleep -Seconds ([Math]::Min(8, [int][Math]::Pow(2, $attempt)))
        }
    }
    $message = if ($null -ne $lastError) { ConvertTo-PDPOneRedactedText $lastError.Exception.Message } else { "Unknown error." }
    throw "$Stage failed after $Attempts attempts. $message"
}

function Set-PDPOneRecoveryProcessEnvironment([string]$Name, $Value) {
    if ($null -eq $Value) { Remove-Item ("Env:" + $Name) -ErrorAction SilentlyContinue }
    else { Set-Item ("Env:" + $Name) ([string]$Value) }
}

function Test-PDPOneRecoveryImageExists([string]$Image) {
    if ([string]::IsNullOrWhiteSpace($Image)) { return $false }
    & docker image inspect $Image *> $null
    return ($LASTEXITCODE -eq 0)
}

function Assert-PDPOneRecoveryImage([string]$Service, [string]$Image) {
    if ($Image -match '^ghcr\.io/pdp-webbase/pdp-one-(backend|mcp|web):content-([0-9a-f]{64})$') {
        if ($matches[1] -ne $Service) { throw "Accepted image component mismatch for $Service." }
        Assert-PDPOneReleaseImageIdentity -Component $Service -Image $Image -ImageMode "content-addressed-v1" -ExpectedFingerprint $matches[2]
        return
    }
    if ($Image -match '^ghcr\.io/pdp-webbase/pdp-one-(backend|mcp|web):([0-9a-f]{40})$') {
        if ($matches[1] -ne $Service) { throw "Accepted image component mismatch for $Service." }
        Assert-PDPOneReleaseImageIdentity -Component $Service -Image $Image -ImageMode "legacy-exact-sha" -ExpectedRevision $matches[2]
        return
    }
    throw "Accepted recovery image is not an immutable governed PDP One image for $Service."
}

$projectRoot = Get-PDPOneProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $projectRoot
$stateRoot = Join-Path $AgentRoot "state"
$lastStatePath = Join-Path $stateRoot "last-deployment.json"
$recoveryRoot = Join-Path $AgentRoot ("downloads\recovery-" + $FailedDeploymentId)
$sourceRoot = $null
$sourceEnvPath = $null
$pointer = [IntPtr]::Zero
$plainToken = $null
$loggedIntoRegistry = $false
$previousEnvironment = @{
    PDP_BACKEND_IMAGE = $env:PDP_BACKEND_IMAGE
    PDP_MCP_IMAGE = $env:PDP_MCP_IMAGE
    PDP_WEB_IMAGE = $env:PDP_WEB_IMAGE
}
$tokenBefore = Get-PDPOneTokenFingerprint (Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN")

try {
    if (-not (Test-Path -LiteralPath $lastStatePath)) { throw "No accepted deployment state exists for recovery." }
    $state = Get-Content -LiteralPath $lastStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$state.status -ne "healthy") { throw "Last deployment state is not accepted healthy state." }
    $previousCommit = [string]$state.approved_commit
    if ($previousCommit -notmatch '^[0-9a-f]{40}$') { throw "Accepted previous commit identity is invalid." }
    if ($previousCommit -eq ('0' * 40)) { throw "Accepted previous commit identity is invalid." }

    $images = [ordered]@{ backend = ""; mcp = ""; web = "" }
    if ($null -eq $state.active_images) { throw "Accepted deployment state does not contain immutable images." }
    foreach ($service in @("backend", "mcp", "web")) {
        $property = $state.active_images.PSObject.Properties[$service]
        if ($null -eq $property -or [string]::IsNullOrWhiteSpace([string]$property.Value)) {
            throw "Accepted deployment state is missing the $service image."
        }
        $images[$service] = [string]$property.Value
    }

    Start-PDPOneRancherDesktop -TimeoutSeconds 300
    if (-not (Test-PDPOneDockerEngine)) { throw "Docker Engine is not ready for accepted-release recovery." }

    $secretPath = Join-Path $AgentRoot "secrets\github-token.dpapi"
    if (-not (Test-Path -LiteralPath $secretPath)) { throw "The protected GitHub credential is missing." }
    $secureToken = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($plainToken)) { throw "The protected GitHub credential could not be opened." }
    $headers = @{
        Authorization = "Bearer $plainToken"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = "PDP-One-Accepted-Release-Recovery"
    }

    $commit = Invoke-PDPOneRecoveryRetry -Stage "Previous accepted GitHub commit verification" -Action {
        Invoke-RestMethod -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/commits/$previousCommit" -Headers $headers -TimeoutSec 45
    }
    if ([string]$commit.sha -ne $previousCommit) { throw "GitHub did not return the exact previous accepted commit." }

    $plainToken | & docker login ghcr.io --username "PDP-WEBBASE" --password-stdin | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "GitHub Container Registry login failed during accepted-release recovery." }
    $loggedIntoRegistry = $true
    foreach ($service in @("backend", "mcp", "web")) {
        $image = [string]$images[$service]
        if (-not (Test-PDPOneRecoveryImageExists -Image $image)) {
            Invoke-PDPOneRecoveryRetry -Stage "Pulling accepted $service image" -Action {
                Invoke-PDPOneRecoveryNative -Command "docker" -Arguments @("pull", $image) -FailureMessage "Accepted image pull failed for $service." | Out-Null
            } | Out-Null
        }
        Assert-PDPOneRecoveryImage -Service $service -Image $image
    }

    if (Test-Path -LiteralPath $recoveryRoot) { Remove-Item -LiteralPath $recoveryRoot -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $recoveryRoot | Out-Null
    $archive = Join-Path $recoveryRoot "accepted-source.zip"
    $extractRoot = Join-Path $recoveryRoot "source"
    Invoke-PDPOneRecoveryRetry -Stage "Previous accepted source download" -Action {
        Invoke-WebRequest -UseBasicParsing -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/zipball/$previousCommit" -Headers $headers -OutFile $archive -TimeoutSec 120
    } | Out-Null
    if (-not (Test-Path -LiteralPath $archive) -or (Get-Item -LiteralPath $archive).Length -le 0) { throw "Previous accepted source archive is empty." }
    Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot -Force
    $sourceRoot = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
    if ($null -eq $sourceRoot -or -not (Test-Path -LiteralPath (Join-Path $sourceRoot.FullName "docker-compose.yml"))) {
        throw "Previous accepted source archive is invalid."
    }

    $sourceEnvPath = Join-Path $sourceRoot.FullName ".env"
    Copy-Item -LiteralPath $envPath -Destination $sourceEnvPath -Force
    $env:PDP_BACKEND_IMAGE = $images.backend
    $env:PDP_MCP_IMAGE = $images.mcp
    $env:PDP_WEB_IMAGE = $images.web
    Set-Location $sourceRoot.FullName
    Invoke-PDPOneRecoveryNative -Command "docker" -Arguments @("compose", "config", "--quiet") -FailureMessage "Accepted recovery Compose configuration is invalid." | Out-Null

    Set-Location $projectRoot
    Invoke-PDPOneRecoveryNative -Command "docker" -Arguments @("compose", "stop", "backend", "worker", "beat", "mcp", "web") -FailureMessage "Failed candidate application services could not be stopped for recovery." -IgnoreFailure | Out-Null
    if ($RefreshConnectivityEdge) {
        Invoke-PDPOneRecoveryNative -Command "docker" -Arguments @("compose", "--profile", "tunnel", "stop", "tailscale", "nginx") -FailureMessage "Failed candidate Connectivity Edge could not be stopped for recovery." -IgnoreFailure | Out-Null
    }

    & robocopy.exe $sourceRoot.FullName $projectRoot /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NP /XF .env /XD .git work node_modules .next
    if ($LASTEXITCODE -gt 7) { throw "Previous accepted application files could not be restored." }

    Set-PDPOneEnvValue -Path $envPath -Name "PDP_BACKEND_IMAGE" -Value $images.backend
    Set-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_IMAGE" -Value $images.mcp
    Set-PDPOneEnvValue -Path $envPath -Name "PDP_WEB_IMAGE" -Value $images.web

    Set-Location $projectRoot
    Invoke-PDPOneRecoveryNative -Command "docker" -Arguments @("compose", "config", "--quiet") -FailureMessage "Restored accepted Docker Compose configuration is invalid." | Out-Null
    Invoke-PDPOneRecoveryNative -Command "docker" -Arguments @("compose", "up", "--detach", "db", "redis") -FailureMessage "Database dependencies could not be preserved during recovery." | Out-Null
    Invoke-PDPOneRecoveryNative -Command "docker" -Arguments @("compose", "up", "--detach", "--no-build", "--pull", "never", "--no-deps", "--force-recreate", "backend", "worker", "beat", "mcp", "web") -FailureMessage "Accepted application services could not be restored." | Out-Null

    if ($RefreshConnectivityEdge) {
        Invoke-PDPOneRecoveryNative -Command "docker" -Arguments @("compose", "up", "--detach", "--no-build", "--pull", "never", "--no-deps", "nginx") -FailureMessage "Accepted Nginx Connectivity Edge could not be restored." | Out-Null
        Invoke-PDPOneRecoveryNative -Command "docker" -Arguments @("compose", "--profile", "tunnel", "up", "--detach", "--no-build", "--pull", "never", "--no-deps", "tailscale") -FailureMessage "Accepted Tailscale Connectivity Edge could not be restored." | Out-Null
    }

    $healthScript = Join-Path $projectRoot "scripts\windows\Test-PDPOneScopedHealth.ps1"
    if (-not (Test-Path -LiteralPath $healthScript)) { throw "Accepted recovery health script is missing." }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $healthScript -Profile "full" -TimeoutSeconds 90
    if ($LASTEXITCODE -ne 0) { throw "Accepted previous release did not pass full recovery health." }

    $tokenAfter = Get-PDPOneTokenFingerprint (Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN")
    if ($tokenBefore -ne $tokenAfter) { throw "Accepted-release recovery changed the MCP path token without authorization." }

    [ordered]@{
        schema = "pdp-one.accepted-release-recovery.v1"
        status = "succeeded"
        failed_deployment_id = $FailedDeploymentId
        recovered_commit = $previousCommit
        connectivity_edge_refreshed = [bool]$RefreshConnectivityEdge
        health = "healthy"
    } | ConvertTo-Json -Compress
} finally {
    if ($sourceEnvPath -and (Test-Path -LiteralPath $sourceEnvPath)) { Remove-Item -LiteralPath $sourceEnvPath -Force -ErrorAction SilentlyContinue }
    foreach ($name in @("PDP_BACKEND_IMAGE", "PDP_MCP_IMAGE", "PDP_WEB_IMAGE")) { Set-PDPOneRecoveryProcessEnvironment -Name $name -Value $previousEnvironment[$name] }
    if ($loggedIntoRegistry) { & docker logout ghcr.io *> $null }
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $plainToken = $null
    if (Test-Path -LiteralPath $recoveryRoot) { Remove-Item -LiteralPath $recoveryRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
