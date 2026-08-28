#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$ProjectRoot = "",
    [int]$IncidentFailureThreshold = 3,
    [int]$RecoverySuccessThreshold = 3,
    [int]$HealthyRetentionDays = 7,
    [int]$IncidentRetentionDays = 60,
    [int]$ExternalEvidenceFreshSeconds = 300
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

if (-not $ProjectRoot) { $ProjectRoot = Get-PDPOneProjectRoot }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location $ProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
$agentRoot = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_DEPLOYMENT_AGENT_ROOT")
if ([string]::IsNullOrWhiteSpace($agentRoot)) { $agentRoot = "C:\ProgramData\PDP-One\deployment-agent" }
$agentRoot = ($agentRoot -replace '/', '\')
$reportRoot = Join-Path $agentRoot "reports\mcp-route-observability"
$incidentRoot = Join-Path $reportRoot "incidents"
$sampleRoot = Join-Path $reportRoot "samples"
$statePath = Join-Path $reportRoot "state.json"
$latestPath = Join-Path $reportRoot "latest.json"
$externalEvidencePath = Join-Path $agentRoot "queue\coordinator\mcp-external-observer.json"
New-Item -ItemType Directory -Force -Path $reportRoot, $incidentRoot, $sampleRoot | Out-Null

function New-Checkpoint {
    param([string]$Id, [string]$Name, [string]$Status, [int]$LatencyMs = 0, [string]$ErrorClass = "", [string]$Detail = "")
    [ordered]@{ id=$Id; name=$Name; status=$Status; latency_ms=$LatencyMs; error_class=$ErrorClass; detail=$Detail }
}

function Measure-Check {
    param([scriptblock]$Action)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try { $value = & $Action; $sw.Stop(); return [pscustomobject]@{ Ok=$true; Ms=[int]$sw.ElapsedMilliseconds; Value=$value; Error="" } }
    catch { $sw.Stop(); return [pscustomobject]@{ Ok=$false; Ms=[int]$sw.ElapsedMilliseconds; Value=$null; Error=(ConvertTo-PDPOneRedactedText $_.Exception.Message) } }
}

function Invoke-DockerText {
    param([string[]]$Arguments)
    $output = @(& docker @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) { throw (($output | ForEach-Object { [string]$_ }) -join " ") }
    return (($output | ForEach-Object { [string]$_ }) -join "`n")
}

function Test-UrlPassive {
    param([string]$Url, [string]$Expected = "")
    $result = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Get -TimeoutSec 8
    if ($result.StatusCode -lt 200 -or $result.StatusCode -ge 500) { throw "HTTP $($result.StatusCode)" }
    if ($Expected -and ([string]$result.Content -notmatch $Expected)) { throw "Unexpected response fingerprint" }
    return [int]$result.StatusCode
}

function Read-State {
    $default = [ordered]@{
        consecutive_failures=0
        consecutive_successes=0
        active_incident=$null
        active_incident_started_at=$null
        last_incident=$null
        incident_sequence=0
        first_failed_checkpoint=$null
        incident_origin_checkpoint=$null
        current_failed_checkpoint=$null
        host_recovery_candidate_at=$null
    }
    if (-not (Test-Path -LiteralPath $statePath)) { return $default }
    try {
        $raw = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($key in @('consecutive_failures','consecutive_successes','active_incident','active_incident_started_at','last_incident','incident_sequence','first_failed_checkpoint','incident_origin_checkpoint','current_failed_checkpoint','host_recovery_candidate_at')) {
            if ($null -ne $raw.PSObject.Properties[$key]) { $default[$key] = $raw.$key }
        }
    } catch { }
    if (-not $default.incident_origin_checkpoint -and $default.first_failed_checkpoint) {
        $default.incident_origin_checkpoint = $default.first_failed_checkpoint
    }
    return $default
}

function Read-ExternalEvidence {
    $result = [ordered]@{
        status='external_evidence_required'
        observed_at=$null
        source='none'
        age_seconds=$null
        fresh=$false
    }
    if (-not (Test-Path -LiteralPath $externalEvidencePath)) { return [pscustomobject]$result }
    try {
        $raw = Get-Content -LiteralPath $externalEvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$raw.status -ne 'pass') { return [pscustomobject]$result }
        [DateTimeOffset]$observed = [DateTimeOffset]::MinValue
        if (-not [DateTimeOffset]::TryParse([string]$raw.observed_at, [ref]$observed)) { return [pscustomobject]$result }
        $age = [Math]::Max(0,[int]([DateTimeOffset]::UtcNow - $observed.ToUniversalTime()).TotalSeconds)
        $result.status = $(if ($age -le [Math]::Max(30,$ExternalEvidenceFreshSeconds)) { 'pass' } else { 'external_evidence_stale' })
        $result.observed_at = $observed.ToUniversalTime().ToString('o')
        $result.source = $(if ($null -ne $raw.PSObject.Properties['source']) { [string]$raw.source } else { 'connected_mcp_diagnostic_call' })
        $result.age_seconds = $age
        $result.fresh = [bool]($age -le [Math]::Max(30,$ExternalEvidenceFreshSeconds))
    } catch { }
    return [pscustomobject]$result
}

function Write-JsonSafe {
    param([string]$Path, $Value)
    $tmp = "$Path.tmp"
    [IO.File]::WriteAllText($tmp, ($Value | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

function Get-RootCauseClassification {
    param([string]$CheckpointId)
    switch ($CheckpointId) {
        'CP-01' { return [pscustomobject]@{ Class='HOST_NETWORK'; Confidence='high'; ExternalCorrelation=$false } }
        'CP-02' { return [pscustomobject]@{ Class='DOCKER_RUNTIME'; Confidence='high'; ExternalCorrelation=$false } }
        'CP-03' { return [pscustomobject]@{ Class='MCP_PROCESS'; Confidence='high'; ExternalCorrelation=$false } }
        'CP-04' { return [pscustomobject]@{ Class='NGINX_LOCAL_ROUTE'; Confidence='high'; ExternalCorrelation=$false } }
        'CP-05' { return [pscustomobject]@{ Class='LOCAL_MCP_ROUTE'; Confidence='high'; ExternalCorrelation=$false } }
        'CP-06' { return [pscustomobject]@{ Class='TAILSCALE_DAEMON'; Confidence='high'; ExternalCorrelation=$false } }
        'CP-07' { return [pscustomobject]@{ Class='TAILSCALE_FUNNEL'; Confidence='high'; ExternalCorrelation=$false } }
        'CP-08' { return [pscustomobject]@{ Class='DNS_PUBLIC_EDGE'; Confidence='medium'; ExternalCorrelation=$true } }
        'CP-09' { return [pscustomobject]@{ Class='EXTERNAL_PUBLIC_PATH'; Confidence='medium'; ExternalCorrelation=$true } }
        'CP-10' { return [pscustomobject]@{ Class='TOKEN_BOUND_ROUTE'; Confidence='medium'; ExternalCorrelation=$true } }
        'CP-12' { return [pscustomobject]@{ Class='PDP_BACKEND'; Confidence='high'; ExternalCorrelation=$false } }
        'CP-13' { return [pscustomobject]@{ Class='POSTGRESQL'; Confidence='high'; ExternalCorrelation=$false } }
        default { return [pscustomobject]@{ Class='UNKNOWN_WITH_EVIDENCE'; Confidence='pending_correlation'; ExternalCorrelation=$true } }
    }
}

$token = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN")
$publicBase = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_PUBLIC_BASE_URL")
$publicHost = ""
if (-not [string]::IsNullOrWhiteSpace($publicBase)) {
    try { $publicHost = ([Uri]$publicBase).DnsSafeHost } catch { $publicHost = "" }
}
$tokenFingerprint = ""
if (-not [string]::IsNullOrWhiteSpace($token)) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $tokenFingerprint = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($token))).Replace('-','').ToLowerInvariant()).Substring(0,12) } finally { $sha.Dispose() }
}

$checks = New-Object System.Collections.Generic.List[object]

$c = Measure-Check { Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop | Select-Object -First 1 | Out-Null; "default_route_present" }
$checks.Add((New-Checkpoint "CP-01" "host_network" $(if($c.Ok){"pass"}else{"fail"}) $c.Ms $(if($c.Ok){""}else{"host_route"}) $(if($c.Ok){$c.Value}else{$c.Error})))

$c = Measure-Check { Invoke-DockerText @('info','--format','{{.ServerVersion}}') }
$checks.Add((New-Checkpoint "CP-02" "docker_engine" $(if($c.Ok){"pass"}else{"fail"}) $c.Ms $(if($c.Ok){""}else{"docker_engine"}) $(if($c.Ok){"reachable"}else{$c.Error})))

$c = Measure-Check { Invoke-DockerText @('compose','ps','--status','running','--services') }
$mcpRunning = $c.Ok -and ([string]$c.Value -split "`n" -contains 'mcp')
$checks.Add((New-Checkpoint "CP-03" "mcp_container" $(if($mcpRunning){"pass"}else{"fail"}) $c.Ms $(if($mcpRunning){""}else{"mcp_container"}) $(if($mcpRunning){"running"}else{$c.Error})))

$c = Measure-Check { Test-UrlPassive "http://127.0.0.1:8080/healthz" }
$checks.Add((New-Checkpoint "CP-04" "nginx_local" $(if($c.Ok){"pass"}else{"fail"}) $c.Ms $(if($c.Ok){""}else{"nginx_local"}) $(if($c.Ok){"http_$($c.Value)"}else{$c.Error})))

$c = Measure-Check { if ([string]::IsNullOrWhiteSpace($token)) { throw "token unavailable" }; Test-UrlPassive "http://127.0.0.1:8080/mcp/$token/healthz" "pdp-one-mcp" }
$checks.Add((New-Checkpoint "CP-05" "mcp_local_token_route" $(if($c.Ok){"pass"}else{"fail"}) $c.Ms $(if($c.Ok){""}else{"local_mcp_route"}) $(if($c.Ok){"healthy"}else{$c.Error})))

$c = Measure-Check { Invoke-DockerText @('compose','--profile','tunnel','exec','-T','tailscale','tailscale','--socket=/tmp/tailscaled.sock','status','--json') | ConvertFrom-Json }
$tailscaleRunning = $c.Ok -and ([string]$c.Value.BackendState -eq 'Running')
$checks.Add((New-Checkpoint "CP-06" "tailscale_daemon" $(if($tailscaleRunning){"pass"}else{"fail"}) $c.Ms $(if($tailscaleRunning){""}else{"tailscale_daemon"}) $(if($tailscaleRunning){"running"}else{$c.Error})))

$c = Measure-Check { Invoke-DockerText @('compose','--profile','tunnel','exec','-T','tailscale','tailscale','--socket=/tmp/tailscaled.sock','funnel','status') }
$funnelOk = $c.Ok -and -not [string]::IsNullOrWhiteSpace([string]$c.Value)
$checks.Add((New-Checkpoint "CP-07" "tailscale_funnel" $(if($funnelOk){"pass"}else{"fail"}) $c.Ms $(if($funnelOk){""}else{"tailscale_funnel"}) $(if($funnelOk){"mapping_present"}else{$c.Error})))

$c = Measure-Check { if (-not $publicHost) { throw "public host unavailable" }; [Net.Dns]::GetHostAddresses($publicHost) | Select-Object -First 1 | ForEach-Object { $_.IPAddressToString } }
$checks.Add((New-Checkpoint "CP-08" "public_dns" $(if($c.Ok){"pass"}else{"fail"}) $c.Ms $(if($c.Ok){""}else{"public_dns"}) $(if($c.Ok){"resolved"}else{$c.Error})))

$c = Measure-Check { if (-not $publicBase) { throw "public base unavailable" }; Test-UrlPassive "$publicBase/healthz" }
$checks.Add((New-Checkpoint "CP-09" "public_https" $(if($c.Ok){"pass"}else{"fail"}) $c.Ms $(if($c.Ok){""}else{"public_https"}) $(if($c.Ok){"reachable"}else{$c.Error})))

$c = Measure-Check { if (-not $publicBase -or [string]::IsNullOrWhiteSpace($token)) { throw "public MCP route unavailable" }; Test-UrlPassive "$publicBase/mcp/$token/healthz" "pdp-one-mcp" }
$checks.Add((New-Checkpoint "CP-10" "public_token_route" $(if($c.Ok){"pass"}else{"fail"}) $c.Ms $(if($c.Ok){""}else{"public_token_route"}) $(if($c.Ok){"healthy"}else{$c.Error})))

$checks.Add((New-Checkpoint "CP-11" "mcp_protocol_handshake" "not_attempted" 0 "" "passive policy forbids creating diagnostic MCP sessions"))

$c = Measure-Check { Test-UrlPassive "http://127.0.0.1:8080/api/v1/auth/session/" "authenticated" }
$checks.Add((New-Checkpoint "CP-12" "pdp_backend" $(if($c.Ok){"pass"}else{"fail"}) $c.Ms $(if($c.Ok){""}else{"pdp_backend"}) $(if($c.Ok){"reachable"}else{$c.Error})))

$c = Measure-Check { Invoke-DockerText @('compose','exec','-T','db','pg_isready') }
$checks.Add((New-Checkpoint "CP-13" "postgresql" $(if($c.Ok){"pass"}else{"fail"}) $c.Ms $(if($c.Ok){""}else{"postgresql"}) $(if($c.Ok){"accepting_connections"}else{$c.Error})))

$externalEvidence = Read-ExternalEvidence
$cp14Status = $(if ($externalEvidence.fresh -and [string]$externalEvidence.status -eq 'pass') { 'pass' } else { 'external_evidence_required' })
$cp14Detail = $(if ($cp14Status -eq 'pass') { "connected_mcp_reached age_seconds=$($externalEvidence.age_seconds)" } elseif ($externalEvidence.observed_at) { "external evidence stale; latest=$($externalEvidence.observed_at)" } else { 'correlate with ChatGPT-side MCP reachability when an incident is reviewed' })
$checks.Add((New-Checkpoint "CP-14" "external_observer" $cp14Status 0 "" $cp14Detail))

$criticalIds = @('CP-01','CP-02','CP-03','CP-04','CP-05','CP-06','CP-07','CP-08','CP-09','CP-10','CP-12','CP-13')
$failed = @($checks | Where-Object { $criticalIds -contains $_.id -and $_.status -eq 'fail' })
$hostOverall = $(if ($failed.Count -eq 0) { 'healthy' } else { 'degraded' })
$currentFailed = $(if ($failed.Count -gt 0) { [string]$failed[0].id } else { $null })
$now = (Get-Date).ToUniversalTime()
$state = Read-State
$recoveredIncident = $null

if ($failed.Count -gt 0) {
    $state.consecutive_failures = [int]$state.consecutive_failures + 1
    $state.consecutive_successes = 0
    $state.current_failed_checkpoint = $currentFailed
    $state.host_recovery_candidate_at = $null
    if (-not $state.first_failed_checkpoint) { $state.first_failed_checkpoint = $currentFailed }
    if (-not $state.incident_origin_checkpoint) { $state.incident_origin_checkpoint = $state.first_failed_checkpoint }
    if (-not $state.active_incident -and [int]$state.consecutive_failures -ge [Math]::Max(1,$IncidentFailureThreshold)) {
        $state.incident_sequence = [int]$state.incident_sequence + 1
        $state.active_incident = "MCP-INC-$($now.ToString('yyyyMMdd'))-$(([int]$state.incident_sequence).ToString('0000'))"
        $state.active_incident_started_at = $now.ToString('o')
    }
} else {
    $state.current_failed_checkpoint = $null
    $state.consecutive_successes = [int]$state.consecutive_successes + 1
    $state.consecutive_failures = 0
    if ($state.active_incident) {
        if (-not $state.host_recovery_candidate_at) { $state.host_recovery_candidate_at = $now.ToString('o') }
        $externalConfirmsRecovery = $false
        if ($externalEvidence.fresh -and [string]$externalEvidence.status -eq 'pass' -and $externalEvidence.observed_at) {
            [DateTimeOffset]$externalObserved = [DateTimeOffset]::MinValue
            [DateTimeOffset]$hostRecoveryCandidate = [DateTimeOffset]::MinValue
            if ([DateTimeOffset]::TryParse([string]$externalEvidence.observed_at,[ref]$externalObserved) -and [DateTimeOffset]::TryParse([string]$state.host_recovery_candidate_at,[ref]$hostRecoveryCandidate)) {
                $externalConfirmsRecovery = [bool]($externalObserved.ToUniversalTime() -ge $hostRecoveryCandidate.ToUniversalTime())
            }
        }
        if ([int]$state.consecutive_successes -ge [Math]::Max(1,$RecoverySuccessThreshold) -and $externalConfirmsRecovery) {
            $recoveredIncident = [pscustomobject]@{ Id=[string]$state.active_incident; StartedAt=[string]$state.active_incident_started_at }
            $state.last_incident = $state.active_incident
            $state.active_incident = $null
            $state.active_incident_started_at = $null
            $state.first_failed_checkpoint = $null
            $state.incident_origin_checkpoint = $null
            $state.current_failed_checkpoint = $null
            $state.host_recovery_candidate_at = $null
        }
    } else {
        $state.first_failed_checkpoint = $null
        $state.incident_origin_checkpoint = $null
        $state.host_recovery_candidate_at = $null
    }
}

$currentClassification = $(if ($currentFailed) { Get-RootCauseClassification -CheckpointId $currentFailed } elseif ($state.active_incident) { [pscustomobject]@{ Class='EXTERNAL_CONFIRMATION_PENDING'; Confidence='pending_correlation'; ExternalCorrelation=$true } } else { [pscustomobject]@{ Class='HEALTHY'; Confidence='high'; ExternalCorrelation=$false } })
$originClassification = Get-RootCauseClassification -CheckpointId ([string]$state.incident_origin_checkpoint)
$endToEndStatus = $(if ($failed.Count -gt 0) { 'degraded' } elseif ($state.active_incident) { 'host_recovered_pending_external_confirmation' } else { 'healthy' })
$checksArray = $checks.ToArray()
$sample = [ordered]@{
    schema = 'pdp-one.mcp-route-observability.v2'
    state_revision = 'v4-external-correlation'
    observed_at = $now.ToString('o')
    overall = $hostOverall
    end_to_end_status = $endToEndStatus
    token_fingerprint = $tokenFingerprint
    public_host = $publicHost
    active_incident = $state.active_incident
    last_incident = $state.last_incident
    consecutive_failures = [int]$state.consecutive_failures
    consecutive_successes = [int]$state.consecutive_successes
    first_failed_checkpoint = $state.first_failed_checkpoint
    incident_origin_checkpoint = $state.incident_origin_checkpoint
    current_failed_checkpoint = $state.current_failed_checkpoint
    host_recovery_candidate_at = $state.host_recovery_candidate_at
    root_cause_classification = $currentClassification.Class
    root_cause_confidence = $currentClassification.Confidence
    current_root_cause_classification = $currentClassification.Class
    current_root_cause_confidence = $currentClassification.Confidence
    incident_origin_root_cause_classification = $originClassification.Class
    incident_origin_root_cause_confidence = $originClassification.Confidence
    external_correlation_required = [bool]$currentClassification.ExternalCorrelation
    external_correlation_status = $externalEvidence.status
    external_last_observed_at = $externalEvidence.observed_at
    external_evidence_age_seconds = $externalEvidence.age_seconds
    checkpoints = $checksArray
    passive_only = $true
    repair_actions = 0
    secrets_included = $false
}

$dailyPath = Join-Path $sampleRoot ($now.ToString('yyyy-MM-dd') + '.jsonl')
Add-Content -LiteralPath $dailyPath -Value ($sample | ConvertTo-Json -Depth 8 -Compress) -Encoding UTF8
Write-JsonSafe -Path $latestPath -Value $sample
Write-JsonSafe -Path $statePath -Value $state

if ($state.active_incident) {
    $incidentPath = Join-Path $incidentRoot ($state.active_incident + '.json')
    $existing = $null
    if (Test-Path -LiteralPath $incidentPath) {
        try { $existing = Get-Content -LiteralPath $incidentPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $existing = $null }
    }
    $startedAt = $(if ($existing -and $existing.started_at) { [string]$existing.started_at } else { [string]$state.active_incident_started_at })
    $incident = [ordered]@{
        schema='pdp-one.mcp-route-incident.v2'
        state_revision='v4-external-correlation'
        incident_id=$state.active_incident
        started_at=$startedAt
        last_observed_at=$now.ToString('o')
        recovered_at=$null
        status=$(if ($failed.Count -gt 0) { 'active' } else { 'host_recovered_pending_external_confirmation' })
        first_failed_checkpoint=$state.first_failed_checkpoint
        incident_origin_checkpoint=$state.incident_origin_checkpoint
        current_failed_checkpoint=$state.current_failed_checkpoint
        host_recovery_candidate_at=$state.host_recovery_candidate_at
        latest_checkpoints=$checksArray
        evidence_source='local_passive_observer_plus_external_mcp_reachability'
        root_cause_classification=$currentClassification.Class
        current_root_cause_classification=$currentClassification.Class
        incident_origin_root_cause_classification=$originClassification.Class
        confidence=$currentClassification.Confidence
        external_correlation_required=[bool]$currentClassification.ExternalCorrelation
        external_correlation_status=$externalEvidence.status
        external_last_observed_at=$externalEvidence.observed_at
        end_to_end_status=$endToEndStatus
        evidence_window=[ordered]@{ pre_incident_minutes=15; post_recovery_minutes=10; sample_store='samples/YYYY-MM-DD.jsonl' }
        passive_only=$true
        repair_actions=0
        secrets_included=$false
    }
    Write-JsonSafe -Path $incidentPath -Value $incident
}

if ($recoveredIncident) {
    $incidentPath = Join-Path $incidentRoot ($recoveredIncident.Id + '.json')
    if (Test-Path -LiteralPath $incidentPath) {
        try {
            $incident = Get-Content -LiteralPath $incidentPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([string]$incident.status -ne 'recovered') {
                $incident.status = 'recovered'
                $incident.recovered_at = $now.ToString('o')
                $incident.last_observed_at = $now.ToString('o')
                if ($null -ne $incident.PSObject.Properties['end_to_end_status']) { $incident.end_to_end_status = 'healthy' }
                if ($null -ne $incident.PSObject.Properties['external_correlation_status']) { $incident.external_correlation_status = 'pass' }
                if ($null -ne $incident.PSObject.Properties['external_last_observed_at']) { $incident.external_last_observed_at = $externalEvidence.observed_at }
                Write-JsonSafe -Path $incidentPath -Value $incident
            }
        } catch { }
    }
}

Get-ChildItem -LiteralPath $sampleRoot -File -Filter '*.jsonl' -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTimeUtc -lt $now.AddDays(-[Math]::Max(1,$HealthyRetentionDays)) } | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath $incidentRoot -File -Filter 'MCP-INC-*.json' -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTimeUtc -lt $now.AddDays(-[Math]::Max(1,$IncidentRetentionDays)) } | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Output $latestPath
