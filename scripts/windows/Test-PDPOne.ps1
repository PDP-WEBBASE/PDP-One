#requires -Version 5.1
[CmdletBinding()]
param([switch]$SkipPublicCheck, [switch]$SkipChatGPTToolCheck)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

function Invoke-PDPOneHealthRequest {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [hashtable]$Headers = @{},
        [string]$ExpectedPattern = '',
        [int]$Attempts = 24
    )
    $lastError = ''
    foreach ($attempt in 1..$Attempts) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Headers $Headers -TimeoutSec 15
            $content = ConvertTo-PDPOneResponseText $response.Content
            if ($response.StatusCode -eq 200 -and (-not $ExpectedPattern -or $content -match $ExpectedPattern)) { return $response }
            $lastError = "HTTP $($response.StatusCode) returned unexpected health content."
        } catch { $lastError = $_.Exception.Message }
        if ($attempt -lt $Attempts) { Start-Sleep -Seconds 5 }
    }
    throw "Health endpoint $Url did not become ready: $(ConvertTo-PDPOneRedactedText $lastError)"
}

$ProjectRoot = Get-PDPOneProjectRoot
Set-Location $ProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
if (-not (Test-PDPOneDockerEngine)) { throw "Docker Engine is unavailable." }
if (-not (Test-PDPOneTokenContinuity -ProjectRoot $ProjectRoot)) { throw "MCP path-token continuity check failed." }
& docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

$required = @("db", "redis", "backend", "worker", "beat", "mcp", "web", "nginx", "tailscale")
$running = @(& docker compose --profile tunnel ps --status running --services)
$missing = @($required | Where-Object { $_ -notin $running })
if ($missing.Count -gt 0) { throw "Inactive services: $($missing -join ', ')" }

& docker compose exec -T db pg_isready -U (Get-PDPOneEnvValue $envPath "POSTGRES_USER") -d (Get-PDPOneEnvValue $envPath "POSTGRES_DB") *> $null
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL is not ready." }
$redisPing = (& docker compose exec -T redis redis-cli ping 2>$null | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $redisPing -ne "PONG") { throw "Redis is not ready." }

& docker compose exec -T backend python manage.py check --database default *> $null
if ($LASTEXITCODE -ne 0) { throw "Django database/system check failed." }
$workerPing = (& docker compose exec -T worker celery -A config inspect ping --timeout 10 2>$null | Out-String)
if ($LASTEXITCODE -ne 0 -or $workerPing -notmatch '(?i)pong') { throw "Celery worker did not answer an application-level ping." }

foreach ($service in @("worker", "beat", "mcp")) {
    $id = (& docker compose ps -q $service).Trim()
    if (-not $id) { throw "$service container is missing." }
    $state = (& docker inspect --format '{{.State.Status}}' $id).Trim()
    if ($state -ne "running") { throw "$service is not running." }
}

$local = Invoke-PDPOneHealthRequest -Url "http://127.0.0.1:8080/healthz" -ExpectedPattern '(?i)(PDP One ready|healthy|ready|ok)'
$apiToken = Get-PDPOneEnvValue $envPath "PDP_MCP_TOKEN"
$api = Invoke-PDPOneHealthRequest -Url "http://127.0.0.1:8080/api/v1/system-status/" -Headers @{ Authorization = "Bearer $apiToken" } -ExpectedPattern '(?i)database'

& docker compose exec -T mcp python -c "import socket; s=socket.create_connection(('127.0.0.1',8010),5); s.close()" *> $null
if ($LASTEXITCODE -ne 0) { throw "MCP service did not accept a local connection." }

$counts = & docker compose exec -T backend python manage.py shell -c "from core.models import Contract,Receivable; print(str(Contract.objects.count())+','+str(Receivable.objects.count()))"
if ($LASTEXITCODE -ne 0 -or $counts -notmatch '\d+,\d+') { throw "Persisted sample-data check failed." }

$tailscaleStatus = (& docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock status --json 2>$null | Out-String)
if ($tailscaleStatus -notmatch '"BackendState"\s*:\s*"Running"') { throw "Tailscale health failed." }
$funnelStatus = (& docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock funnel status 2>$null | Out-String)
if ($funnelStatus -notmatch '(?i)Funnel on|Available on the internet|proxy http://127\.0\.0\.1:80') { throw "Tailscale Funnel health failed." }

if (-not $SkipPublicCheck) {
    $publicBase = Get-PDPOneEnvValue $envPath "PDP_PUBLIC_BASE_URL"
    if (-not $publicBase) { throw "PDP_PUBLIC_BASE_URL is missing; run CONNECT-CHATGPT.bat once." }
    $public = Invoke-PDPOneHealthRequest -Url "$($publicBase.TrimEnd('/'))/healthz" -ExpectedPattern '(?i)(PDP One ready|healthy|ready|ok)' -Attempts 12
}

$report = [ordered]@{
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    status = "healthy"
    services = $required
    persisted_counts = $counts.Trim()
    token_continuity = $true
    public_check = (-not $SkipPublicCheck)
    chatgpt_tool_check = $(if ($SkipChatGPTToolCheck) { "deferred-to-connected-app" } else { "requires-connected-app-observation" })
}
$reportDir = Join-Path $ProjectRoot "work\reports"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $reportDir "health-latest.json") -Encoding UTF8
Write-Host "All locally verifiable PDP One health layers are healthy. ChatGPT tool health is reported separately through the connected app." -ForegroundColor Green
