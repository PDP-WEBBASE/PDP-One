#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$CommitSha,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$DeploymentId,
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')][string]$PreviewId,
    [Parameter(Mandatory = $true)][string]$AgentRoot,
    [int]$StabilizationSeconds = 30
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
. (Join-Path $PSScriptRoot "PDPOne.ReleaseManifest.ps1")

function Invoke-PDPOneNative {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage,
        [switch]$Quiet
    )
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $out = @(& $Command @Arguments 2>&1)
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $old }
    if (-not $Quiet -and $out.Count -gt 0) {
        $safe = ConvertTo-PDPOneRedactedText (($out | ForEach-Object { [string]$_ }) -join [Environment]::NewLine)
        if ($safe) { Write-Host $safe }
    }
    if ($code -ne 0) { throw "$FailureMessage (exit code $code)." }
    return $out
}

function Set-PDPOneProcessEnvironment([string]$Name, $Value) {
    if ($null -eq $Value) { Remove-Item ("Env:" + $Name) -ErrorAction SilentlyContinue }
    else { Set-Item ("Env:" + $Name) ([string]$Value) }
}

function Get-PDPOnePreviousImageMap($State) {
    $images = [ordered]@{ backend = ""; mcp = ""; web = "" }
    if ($null -eq $State -or $null -eq $State.active_images) { return $images }
    foreach ($service in @("backend", "mcp", "web")) {
        $p = $State.active_images.PSObject.Properties[$service]
        if ($null -ne $p) { $images[$service] = [string]$p.Value }
    }
    return $images
}

function Test-PDPOneImageExistsLocally([string]$Image) {
    if (-not $Image) { return $false }
    & docker image inspect $Image *> $null
    return ($LASTEXITCODE -eq 0)
}

function Assert-PDPOneResolvedImage {
    param([string]$Service,[string]$Image,[string]$TargetImageMode,[string]$TargetFingerprint,[string]$ReleaseCommit)
    if ($Image -match ':content-([0-9a-f]{64})$') {
        Assert-PDPOneReleaseImageIdentity -Component $Service -Image $Image -ImageMode "content-addressed-v1" -ExpectedFingerprint $matches[1]
        return
    }
    $revision = Get-PDPOneReferenceEmbeddedRevision -Image $Image
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

function Wait-PDPOneCandidateHttp {
    param([Parameter(Mandatory=$true)][string]$Container,[Parameter(Mandatory=$true)][int]$Port,[Parameter(Mandatory=$true)][string]$Path,[string]$Expected="",[int]$Timeout=75)
    $deadline = (Get-Date).AddSeconds([Math]::Max(10,$Timeout))
    while ((Get-Date) -lt $deadline) {
        $python = "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:$Port$Path',timeout=3); b=r.read(1024); sys.exit(0 if r.status==200" + $(if ($Expected) { " and b'" + $Expected.Replace("'","") + "' in b" } else { "" }) + " else 1)"
        $probeCode = 1
        $old = $ErrorActionPreference
        try {
            $ErrorActionPreference = "Continue"
            & docker exec $Container python -c $python *> $null
            $probeCode = $LASTEXITCODE
        } finally { $ErrorActionPreference = $old }
        if ($probeCode -eq 0) { return }
        Start-Sleep -Seconds 2
    }
    throw "Candidate $Container did not become ready."
}

function Test-PDPOneHttpOnce {
    param([Parameter(Mandatory=$true)][string]$Url,[string]$Expected="")
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 8
        $text = ConvertTo-PDPOneResponseText $r.Content
        return ($r.StatusCode -eq 200 -and (-not $Expected -or $text -match $Expected))
    } catch { return $false }
}

function Set-PDPOneNginxRuntimeUpstreams {
    param([Parameter(Mandatory=$true)][string]$BackendTarget,[Parameter(Mandatory=$true)][string]$McpTarget)
    $temp = Join-Path $env:TEMP ("pdp-upstreams-" + [Guid]::NewGuid().ToString("N") + ".conf")
    try {
        @(
            "set `$pdp_backend_upstream $BackendTarget`:8000;",
            "set `$pdp_mcp_upstream $McpTarget`:8010;",
            "set `$pdp_web_upstream web:3000;"
        ) | Set-Content -LiteralPath $temp -Encoding ASCII
        Invoke-PDPOneNative -Command "docker" -Arguments @("exec","pdp-one-nginx-1","mkdir","-p","/etc/nginx/pdp-runtime-upstreams") -FailureMessage "Nginx runtime-upstream directory could not be prepared." -Quiet | Out-Null
        Invoke-PDPOneNative -Command "docker" -Arguments @("cp",$temp,"pdp-one-nginx-1:/etc/nginx/pdp-runtime-upstreams/active.conf") -FailureMessage "Nginx runtime-upstream override could not be installed." -Quiet | Out-Null
        Invoke-PDPOneNative -Command "docker" -Arguments @("exec","pdp-one-nginx-1","/docker-entrypoint.d/20-envsubst-on-templates.sh") -FailureMessage "Nginx template could not be regenerated." -Quiet | Out-Null
        Invoke-PDPOneNative -Command "docker" -Arguments @("exec","pdp-one-nginx-1","nginx","-t") -FailureMessage "Nginx candidate routing configuration is invalid." -Quiet | Out-Null
        Invoke-PDPOneNative -Command "docker" -Arguments @("exec","pdp-one-nginx-1","nginx","-s","reload") -FailureMessage "Nginx graceful candidate traffic switch failed." -Quiet | Out-Null
    } finally { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
}

function Clear-PDPOneNginxRuntimeUpstreams {
    Invoke-PDPOneNative -Command "docker" -Arguments @("exec","pdp-one-nginx-1","sh","-c","rm -f /etc/nginx/pdp-runtime-upstreams/active.conf") -FailureMessage "Nginx runtime-upstream override could not be cleared." -Quiet | Out-Null
    Invoke-PDPOneNative -Command "docker" -Arguments @("exec","pdp-one-nginx-1","/docker-entrypoint.d/20-envsubst-on-templates.sh") -FailureMessage "Nginx canonical template could not be regenerated." -Quiet | Out-Null
    Invoke-PDPOneNative -Command "docker" -Arguments @("exec","pdp-one-nginx-1","nginx","-t") -FailureMessage "Nginx canonical routing configuration is invalid." -Quiet | Out-Null
    Invoke-PDPOneNative -Command "docker" -Arguments @("exec","pdp-one-nginx-1","nginx","-s","reload") -FailureMessage "Nginx graceful return to canonical routing failed." -Quiet | Out-Null
}

function Remove-PDPOneCandidate([string]$Name) {
    if (-not $Name) { return }
    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & docker container inspect $Name *> $null
        $inspectCode = $LASTEXITCODE
        if ($inspectCode -ne 0) { return }
        & docker rm -f $Name *> $null
        $removeCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $old }
    if ($removeCode -ne 0) { throw "Candidate container cleanup failed for $Name (exit code $removeCode)." }
}

function Get-PDPOneCanonicalRuntimeNetwork {
    $raw = @(& docker inspect "pdp-one-nginx-1" 2>&1)
    if ($LASTEXITCODE -ne 0 -or $raw.Count -eq 0) { throw "Canonical Nginx runtime network could not be inspected." }
    $inspect = (($raw | ForEach-Object { [string]$_ }) -join [Environment]::NewLine) | ConvertFrom-Json
    $names = @($inspect[0].NetworkSettings.Networks.PSObject.Properties | ForEach-Object { [string]$_.Name })
    if ($names.Count -ne 1) { throw "Canonical runtime network could not be resolved unambiguously." }
    $name = $names[0]
    if ($name -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$') { throw "Canonical runtime network name is invalid." }
    return $name
}

function Get-PDPOneCanonicalPrivateFilesVolume {
    $raw = @(& docker inspect "pdp-one-backend-1" 2>&1)
    if ($LASTEXITCODE -ne 0 -or $raw.Count -eq 0) { throw "Canonical backend volume could not be inspected." }
    $inspect = (($raw | ForEach-Object { [string]$_ }) -join [Environment]::NewLine) | ConvertFrom-Json
    $mount = @($inspect[0].Mounts | Where-Object { $_.Type -eq "volume" -and $_.Destination -eq "/data/private" }) | Select-Object -First 1
    if ($null -eq $mount) { throw "Canonical private-files volume could not be resolved." }
    $name = [string]$mount.Name
    if ($name -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$') { throw "Canonical private-files volume name is invalid." }
    return $name
}

function Write-PDPOneCandidateComposeOverride {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$NetworkName,
        [Parameter(Mandatory=$true)][string]$PrivateFilesVolume
    )
    @(
        "networks:",
        "  default:",
        "    external: true",
        "    name: `"$NetworkName`"",
        "volumes:",
        "  private_files:",
        "    external: true",
        "    name: `"$PrivateFilesVolume`""
    ) | Set-Content -LiteralPath $Path -Encoding ASCII
}

$projectRoot = Get-PDPOneProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $projectRoot
$reportsRoot = Join-Path $AgentRoot "reports"
$downloadRoot = Join-Path $AgentRoot ("downloads\" + $DeploymentId)
$extractRoot = Join-Path $downloadRoot "source"
$stateRoot = Join-Path $AgentRoot "state"
$lastStatePath = Join-Path $stateRoot "last-deployment.json"
New-Item -ItemType Directory -Force -Path $reportsRoot,$stateRoot | Out-Null
$reportPath = Join-Path $reportsRoot ($DeploymentId + ".json")
$previousState = $null
$previousCommit = ""
if (Test-Path -LiteralPath $lastStatePath) {
    try { $previousState = Get-Content -LiteralPath $lastStatePath -Raw -Encoding UTF8 | ConvertFrom-Json; $previousCommit = [string]$previousState.approved_commit } catch { }
}
$previousImages = Get-PDPOnePreviousImageMap -State $previousState
$currentImages = [ordered]@{ backend=""; mcp=""; web="" }
$fingerprints = [ordered]@{ backend=""; mcp=""; web="" }
$changedServices = @()
$changedPaths = @()
$imageMode = "legacy-exact-sha"
$healthProfile = "full"
$backendCandidate = ""
$mcpCandidate = ""
$candidateProject = ""
$candidateOverridePath = $null
$candidateRuntimeNetwork = ""
$overrideActive = $false
$sourceEnvPath = $null
$loggedIntoRegistry = $false
$pointer = [IntPtr]::Zero
$plainToken = $null
$previousEnvironment = @{ PDP_BACKEND_IMAGE=$env:PDP_BACKEND_IMAGE; PDP_MCP_IMAGE=$env:PDP_MCP_IMAGE; PDP_WEB_IMAGE=$env:PDP_WEB_IMAGE }
$tokenBefore = Get-PDPOneTokenFingerprint (Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN")
$continuityFailures = 0
$report = [ordered]@{
    schema="pdp-one.deployment-report.v4-zero-downtime"
    deployment_id=$DeploymentId; preview_id=$PreviewId; approved_commit=$CommitSha; previous_commit=$previousCommit
    started_at=[DateTime]::UtcNow.ToString("o"); completed_at=$null; status="starting"; stage="initializing"
    change_management_mode="development_fast"; image_source="github_container_registry"; production_changed=$false
    changed_services=@(); changed_paths=@($changedPaths); active_images=$currentImages; retained_previous_images=$previousImages
    health_profile=$healthProfile; release_manifest=$null
    zero_downtime_strategy="temporary_candidate_nginx_graceful_switch_v1"; stabilization_seconds=$StabilizationSeconds
    candidate_compose_isolated=$false; candidate_compose_project=$null; candidate_runtime_network=$null
    readiness_before_switch=$false; nginx_restarted=$false; tailscale_restarted=$false; graceful_reload_used=$false
    mcp_continuity_probe_failures=0; api_continuity_probe_failures=0; traffic_switched_to_candidate=$false; traffic_returned_to_canonical=$false
    automatic_recovery_enabled=$true; automatic_recovery_attempted=$false; automatic_recovery_succeeded=$false
    connectivity_edge_preserved=$true; secrets_included=$false; error=$null
}
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8

try {
    Start-PDPOneRancherDesktop -TimeoutSeconds 300
    if (-not (Test-PDPOneDockerEngine)) { throw "Docker Engine is not ready." }
    $secretPath = Join-Path $AgentRoot "secrets\github-token.dpapi"
    if (-not (Test-Path -LiteralPath $secretPath)) { throw "The protected GitHub credential is missing." }
    $secureToken = (Get-Content -LiteralPath $secretPath -Raw).Trim() | ConvertTo-SecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if (-not $plainToken) { throw "The protected GitHub credential could not be opened." }
    $headers = @{ Authorization="Bearer $plainToken"; Accept="application/vnd.github+json"; "X-GitHub-Api-Version"="2022-11-28"; "User-Agent"="PDP-One-Zero-Downtime-Deployment" }

    $report.stage="verifying-exact-commit"; $report.status="running"; $report | ConvertTo-Json -Depth 10 | Set-Content $reportPath -Encoding UTF8
    $commit = Invoke-RestMethod -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/commits/$CommitSha" -Headers $headers -TimeoutSec 45
    if ([string]$commit.sha -ne $CommitSha) { throw "GitHub did not return the requested exact commit." }

    if (Test-Path -LiteralPath $downloadRoot) { Remove-Item $downloadRoot -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null
    $archive=Join-Path $downloadRoot "approved-source.zip"
    Invoke-WebRequest -UseBasicParsing -Uri "https://api.github.com/repos/PDP-WEBBASE/PDP-One/zipball/$CommitSha" -Headers $headers -OutFile $archive -TimeoutSec 120
    Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot -Force
    $sourceRoot = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
    if ($null -eq $sourceRoot -or -not (Test-Path (Join-Path $sourceRoot.FullName "docker-compose.yml"))) { throw "The exact-commit source archive is invalid." }
    $riskPath=Join-Path $sourceRoot.FullName "release\database-change-risk.json"
    if (Test-Path $riskPath) { $risk=Get-Content $riskPath -Raw -Encoding UTF8 | ConvertFrom-Json; if ([bool]$risk.requires_backup) { throw "This commit requires the guarded standard database workflow." } }

    $conservative=$true
    if ($previousCommit -match '^[0-9a-f]{40}$' -and $previousCommit -ne $CommitSha) {
        try { $changedPaths=@(Get-PDPOneChangedFilePaths -Headers $headers -PreviousCommit $previousCommit -CommitSha $CommitSha); $conservative=$false } catch { $changedPaths=@(); $conservative=$true }
    }
    $scope=Get-PDPOneChangeScope -Paths $changedPaths -ConservativeFullStack:$conservative
    $imageMode=Get-PDPOneImageMode -SourceRoot $sourceRoot.FullName
    foreach ($service in @("backend","mcp","web")) {
        if ($imageMode -eq "content-addressed-v1") {
            $fingerprints[$service]=Get-PDPOneComponentFingerprint -SourceRoot $sourceRoot.FullName -Component $service
            $currentImages[$service]=Get-PDPOneComponentImageReference -Component $service -Fingerprint $fingerprints[$service]
        } else {
            $old=[string]$previousImages[$service]
            $serviceChanged=$scope.topology_sensitive -or ($service -in @($scope.changed_services)) -or -not $old
            $currentImages[$service]=$(if ($serviceChanged) { "ghcr.io/pdp-webbase/pdp-one-$service`:$CommitSha" } else { $old })
        }
    }
    foreach ($service in @("backend","mcp","web")) { if ([string]$previousImages[$service] -ne [string]$currentImages[$service]) { $changedServices += $service } }
    if ($scope.topology_sensitive) { $changedServices=@("backend","mcp","web") }
    $changedServices=@($changedServices | Select-Object -Unique)
    $healthProfile=$(if ($scope.topology_sensitive -or $changedServices.Count -gt 1) { "full" } elseif ($changedServices.Count -eq 1) { [string]$changedServices[0] } elseif ($scope.host) { "host" } else { "none" })
    $report.changed_services=@($changedServices); $report.changed_paths=@($changedPaths); $report.health_profile=$healthProfile; $report.active_images=$currentImages

    $plainToken | & docker login ghcr.io --username "PDP-WEBBASE" --password-stdin | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "GitHub Container Registry login failed." }
    $loggedIntoRegistry=$true
    foreach ($service in @("backend","mcp","web")) {
        $image=[string]$currentImages[$service]
        if (($service -in $changedServices) -or -not (Test-PDPOneImageExistsLocally $image)) { Invoke-PDPOneNative -Command "docker" -Arguments @("pull",$image) -FailureMessage "Image pull failed for $service." -Quiet | Out-Null }
        Assert-PDPOneResolvedImage -Service $service -Image $image -TargetImageMode $imageMode -TargetFingerprint ([string]$fingerprints[$service]) -ReleaseCommit $CommitSha
    }

    $sourceEnvPath=Join-Path $sourceRoot.FullName ".env"
    Copy-Item $envPath $sourceEnvPath -Force
    $env:PDP_BACKEND_IMAGE=$currentImages.backend; $env:PDP_MCP_IMAGE=$currentImages.mcp; $env:PDP_WEB_IMAGE=$currentImages.web
    Set-Location $sourceRoot.FullName
    Invoke-PDPOneNative -Command "docker" -Arguments @("compose","config","--quiet") -FailureMessage "Candidate Docker Compose configuration is invalid." -Quiet | Out-Null

    Set-Location $projectRoot
    & robocopy.exe $sourceRoot.FullName $projectRoot /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NP /XF .env /XD .git work node_modules .next | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "Exact-commit application files could not be copied." }
    $report.production_changed=$true

    if ($scope.topology_sensitive -or ("backend" -in $changedServices)) {
        Invoke-PDPOneNative -Command "docker" -Arguments @("compose","run","--rm","--no-deps","backend","python","manage.py","migrate","--noinput") -FailureMessage "Controlled migration failed." -Quiet | Out-Null
    }

    $short=$CommitSha.Substring(0,8)
    $candidateProject="pdp-zd-$short"
    $candidateRuntimeNetwork=Get-PDPOneCanonicalRuntimeNetwork
    $candidatePrivateFilesVolume=Get-PDPOneCanonicalPrivateFilesVolume
    $candidateOverridePath=Join-Path $downloadRoot "candidate-runtime.override.yml"
    Write-PDPOneCandidateComposeOverride -Path $candidateOverridePath -NetworkName $candidateRuntimeNetwork -PrivateFilesVolume $candidatePrivateFilesVolume
    $candidateCompose=@("compose","--project-name",$candidateProject,"-f",(Join-Path $projectRoot "docker-compose.yml"),"-f",$candidateOverridePath)
    Invoke-PDPOneNative -Command "docker" -Arguments @($candidateCompose + @("config","--quiet")) -FailureMessage "Isolated candidate Docker Compose configuration is invalid." -Quiet | Out-Null
    $report.candidate_compose_isolated=$true; $report.candidate_compose_project=$candidateProject; $report.candidate_runtime_network=$candidateRuntimeNetwork

    $backendTarget="backend"
    $needsMcpContinuity=("backend" -in $changedServices) -or ("mcp" -in $changedServices) -or $scope.topology_sensitive
    if (("backend" -in $changedServices) -or $scope.topology_sensitive) {
        $backendCandidate="pdp-zd-backend-$short"
        Remove-PDPOneCandidate $backendCandidate
        Invoke-PDPOneNative -Command "docker" -Arguments @($candidateCompose + @("run","--detach","--no-deps","--name",$backendCandidate,"backend")) -FailureMessage "Candidate backend could not start." -Quiet | Out-Null
        Wait-PDPOneCandidateHttp -Container $backendCandidate -Port 8000 -Path "/api/v1/auth/session/" -Timeout 90
        $backendTarget=$backendCandidate
    }
    if ($needsMcpContinuity) {
        $mcpCandidate="pdp-zd-mcp-$short"
        Remove-PDPOneCandidate $mcpCandidate
        Invoke-PDPOneNative -Command "docker" -Arguments @($candidateCompose + @("run","--detach","--no-deps","--name",$mcpCandidate,"-e",("PDP_API_URL=http://"+$backendTarget+":8000/api/v1"),"mcp")) -FailureMessage "Candidate MCP could not start." -Quiet | Out-Null
        Wait-PDPOneCandidateHttp -Container $mcpCandidate -Port 8010 -Path "/healthz" -Expected "pdp-one-mcp" -Timeout 90
    }
    $report.readiness_before_switch=$true

    if ($needsMcpContinuity) {
        Set-PDPOneNginxRuntimeUpstreams -BackendTarget $backendTarget -McpTarget $mcpCandidate
        $overrideActive=$true; $report.graceful_reload_used=$true; $report.traffic_switched_to_candidate=$true
        $pathToken=Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN"
        $publicBase=[string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_PUBLIC_BASE_URL")
        $deadline=(Get-Date).AddSeconds([Math]::Max(1,$StabilizationSeconds))
        while ((Get-Date) -lt $deadline) {
            if (-not (Test-PDPOneHttpOnce -Url "http://127.0.0.1:8080/api/v1/auth/session/" -Expected 'authenticated')) { $report.api_continuity_probe_failures=[int]$report.api_continuity_probe_failures+1 }
            if (-not (Test-PDPOneHttpOnce -Url ("http://127.0.0.1:8080/mcp/"+$pathToken+"/healthz") -Expected 'pdp-one-mcp')) { $continuityFailures += 1 }
            if ($publicBase) {
                $base=$publicBase.TrimEnd('/')
                if (-not (Test-PDPOneHttpOnce -Url ($base+"/mcp/"+$pathToken+"/healthz") -Expected 'pdp-one-mcp')) { $continuityFailures += 1 }
            }
            if ($continuityFailures -gt 0 -or [int]$report.api_continuity_probe_failures -gt 0) { throw "Continuity probe failed during the stabilization window." }
            Start-Sleep -Seconds 2
        }
    }
    $report.mcp_continuity_probe_failures=$continuityFailures

    Set-Location $projectRoot
    if (("backend" -in $changedServices) -or $scope.topology_sensitive) {
        Invoke-PDPOneNative -Command "docker" -Arguments @("compose","up","--detach","--no-build","--pull","never","--no-deps","--force-recreate","backend","worker","beat") -FailureMessage "Canonical backend services failed to start." -Quiet | Out-Null
        $id=[string](& docker compose ps -q backend | Select-Object -First 1)
        if (-not $id) { throw "Canonical backend container is missing." }
        Wait-PDPOneCandidateHttp -Container $id.Trim() -Port 8000 -Path "/api/v1/auth/session/" -Timeout 90
    }
    if (("mcp" -in $changedServices) -or $scope.topology_sensitive -or ("backend" -in $changedServices)) {
        Invoke-PDPOneNative -Command "docker" -Arguments @("compose","up","--detach","--no-build","--pull","never","--no-deps","--force-recreate","mcp") -FailureMessage "Canonical MCP failed to start." -Quiet | Out-Null
        $id=[string](& docker compose ps -q mcp | Select-Object -First 1)
        if (-not $id) { throw "Canonical MCP container is missing." }
        Wait-PDPOneCandidateHttp -Container $id.Trim() -Port 8010 -Path "/healthz" -Expected "pdp-one-mcp" -Timeout 90
    }
    if ("web" -in $changedServices) {
        Invoke-PDPOneNative -Command "docker" -Arguments @("compose","up","--detach","--no-build","--pull","never","--no-deps","--force-recreate","web") -FailureMessage "Canonical web failed to start." -Quiet | Out-Null
    }

    if ($overrideActive) { Clear-PDPOneNginxRuntimeUpstreams; $overrideActive=$false; $report.graceful_reload_used=$true; $report.traffic_returned_to_canonical=$true }

    $scopedHealth=Join-Path $projectRoot "scripts\windows\Test-PDPOneScopedHealth.ps1"
    if (-not (Test-Path $scopedHealth)) { throw "Scope-aware health script is missing." }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $scopedHealth -Profile $healthProfile -TimeoutSeconds 90
    if ($LASTEXITCODE -ne 0) { throw "Final exact-candidate scoped health failed." }

    $tokenAfter=Get-PDPOneTokenFingerprint (Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN")
    if ($tokenBefore -ne $tokenAfter) { throw "Deployment changed the MCP path token without authorization." }
    $releaseManifestPath=Write-PDPOneReleaseManifest -AgentRoot $AgentRoot -ReleaseCommit $CommitSha -DeploymentId $DeploymentId -ImageMode $imageMode -Images $currentImages -Fingerprints $fingerprints -ChangedServices $changedServices -HealthProfile $healthProfile
    $report.release_manifest=$releaseManifestPath
    [ordered]@{
        schema="pdp-one.last-deployment.v3"; deployment_id=$DeploymentId; preview_id=$PreviewId; approved_commit=$CommitSha; previous_commit=$previousCommit
        active_images=$currentImages; retained_previous_images=$previousImages; active_release_manifest=$releaseManifestPath
        changed_services=@($changedServices); changed_paths=@($changedPaths); health_profile=$healthProfile
        connectivity_edge_impacted=$false; connectivity_edge_refresh_performed=$false; connectivity_edge_preserved=$true
        started_at=$report.started_at; completed_at=[DateTime]::UtcNow.ToString("o"); status="healthy"
        image_source="github_container_registry"; local_image_build_performed=$false; change_management_mode="development_fast"
        rollback_method="zero_downtime_candidate_route_and_previous_release_recovery"
        zero_downtime_strategy="temporary_candidate_nginx_graceful_switch_v1"; mcp_continuity_probe_failures=0
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $lastStatePath -Encoding UTF8

    $binRoot=Join-Path $AgentRoot "bin"
    New-Item -ItemType Directory -Force -Path $binRoot | Out-Null
    Copy-Item -Path (Join-Path $projectRoot "scripts\windows\*.ps1") -Destination $binRoot -Force
    Set-Content -LiteralPath (Join-Path $stateRoot "restart-agent-after-response") -Value ([DateTime]::UtcNow.ToString("o")) -Encoding ASCII

    Remove-PDPOneCandidate $mcpCandidate; $mcpCandidate=""
    Remove-PDPOneCandidate $backendCandidate; $backendCandidate=""
    $report.status="healthy"; $report.stage="completed"; $report.completed_at=[DateTime]::UtcNow.ToString("o"); $report.mcp_continuity_probe_failures=0; $report.error=$null
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output $reportPath
} catch {
    $message=ConvertTo-PDPOneRedactedText $_.Exception.Message
    $report.error=$message; $report.status="failed"; $report.automatic_recovery_attempted=$report.production_changed
    try {
        if ($overrideActive) { Clear-PDPOneNginxRuntimeUpstreams; $overrideActive=$false }
        Remove-PDPOneCandidate $mcpCandidate; $mcpCandidate=""
        Remove-PDPOneCandidate $backendCandidate; $backendCandidate=""
        if ($report.production_changed -and $previousCommit -match '^[0-9a-f]{40}$') {
            $recovery=Join-Path $projectRoot "scripts\windows\Restore-PDPOneAcceptedRelease.ps1"
            if (Test-Path $recovery) {
                & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $recovery -FailedCommit $CommitSha -FailedDeploymentId $DeploymentId -PreviousAcceptedCommit $previousCommit -ProjectRoot $projectRoot -AgentRoot $AgentRoot
                if ($LASTEXITCODE -eq 0) { $report.automatic_recovery_succeeded=$true }
            }
        }
    } catch { }
    $report.completed_at=[DateTime]::UtcNow.ToString("o"); $report.stage=$(if ($report.automatic_recovery_succeeded) { "failed-recovered-previous-release" } else { "failed" })
    $report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    throw "Zero-downtime exact-candidate deployment failed. $message"
} finally {
    if ($overrideActive) { try { Clear-PDPOneNginxRuntimeUpstreams } catch { } }
    Remove-PDPOneCandidate $mcpCandidate
    Remove-PDPOneCandidate $backendCandidate
    if ($sourceEnvPath -and (Test-Path $sourceEnvPath)) { Remove-Item $sourceEnvPath -Force -ErrorAction SilentlyContinue }
    foreach ($name in @("PDP_BACKEND_IMAGE","PDP_MCP_IMAGE","PDP_WEB_IMAGE")) { Set-PDPOneProcessEnvironment -Name $name -Value $previousEnvironment[$name] }
    if ($loggedIntoRegistry) { & docker logout ghcr.io *> $null }
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $plainToken=$null
    if (Test-Path $downloadRoot) { Remove-Item $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue }
    Set-Location $projectRoot
}