#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$FailureMessage = "Unspecified failure",
    [string]$DeploymentId = "",
    [string]$BackupId = "",
    [string]$RollbackResult = "not-run",
    [string]$Stage = "unspecified",
    [switch]$OpenReport
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
$ProjectRoot = Get-PDPOneProjectRoot
Set-Location $ProjectRoot
$reportDir = Join-Path $ProjectRoot "work\diagnostics"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$path = Join-Path $reportDir ("PDP-ONE-DIAGNOSTICS-{0}.txt" -f $stamp)
$jsonPath = Join-Path $reportDir ("PDP-ONE-DIAGNOSTICS-{0}.json" -f $stamp)
$stablePath = Join-Path $ProjectRoot "PDP-ONE-LAST-DIAGNOSTICS.txt"
$stableJsonPath = Join-Path $ProjectRoot "PDP-ONE-LAST-DIAGNOSTICS.json"

function Invoke-SafeCapture([scriptblock]$Action) {
    try { return (& $Action 2>&1 | Out-String).TrimEnd() } catch { return "ERROR: $($_.Exception.Message)" }
}

$localHealth = "unavailable"
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8080/healthz" -TimeoutSec 8
    $localHealth = "HTTP $($response.StatusCode): $(ConvertTo-PDPOneResponseText $response.Content)"
} catch { $localHealth = "ERROR: $($_.Exception.Message)" }

$tailscaleState = "unavailable"
$tailscaleDnsName = ""
try {
    $statusText = (& docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock status --json 2>$null | Out-String)
    if ($LASTEXITCODE -eq 0 -and $statusText) {
        $status = $statusText | ConvertFrom-Json
        $tailscaleState = [string]$status.BackendState
        $tailscaleDnsName = [string]$status.Self.DNSName
    }
} catch { $tailscaleState = "ERROR: $($_.Exception.Message)" }

$publicBase = ""
try {
    $envPath = Join-Path $ProjectRoot ".env"
    $publicBase = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_PUBLIC_BASE_URL")
} catch { }

$publicHealth = $null
if ($publicBase) {
    $publicHealth = Test-PDPOnePublicHealth -Url "$($publicBase.TrimEnd('/'))/healthz" -TimeoutSeconds 25
}

$composeStatus = Invoke-SafeCapture { docker compose --profile tunnel ps }
$funnelStatus = Invoke-SafeCapture { docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock funnel status }
$netcheck = Invoke-SafeCapture { docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock netcheck }
$systemDns = $(if ($tailscaleDnsName) { Invoke-SafeCapture { nslookup.exe $tailscaleDnsName.TrimEnd('.') } } else { "DNS name unavailable" })
$publicDns = $(if ($tailscaleDnsName) { Invoke-SafeCapture { nslookup.exe $tailscaleDnsName.TrimEnd('.') 1.1.1.1 } } else { "DNS name unavailable" })
$tasks = Invoke-SafeCapture {
    Get-ScheduledTask -TaskName "PDP One*" -ErrorAction SilentlyContinue |
        Select-Object TaskName, State |
        Format-Table -AutoSize
}
$taskInfo = Invoke-SafeCapture {
    $items = @()
    foreach ($taskName in @("PDP One Local Deployment Agent", "PDP One Stable Startup", "PDP One Open Local Web")) {
        $info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
        if ($info) {
            $items += [pscustomobject]@{ TaskName = $taskName; LastRunTime = $info.LastRunTime; LastTaskResult = $info.LastTaskResult; NextRunTime = $info.NextRunTime }
        }
    }
    $items | Format-Table -AutoSize
}
$agentAudit = Invoke-SafeCapture {
    $agentRoot = "C:\ProgramData\PDP-One\deployment-agent"
    $auditPath = Join-Path $agentRoot "audit\deployment-agent.jsonl"
    if (Test-Path -LiteralPath $auditPath) { Get-Content -LiteralPath $auditPath -Tail 30 }
}
$logs = Invoke-SafeCapture { docker compose --profile tunnel logs --tail 100 nginx backend mcp worker beat tailscale }

$summary = [ordered]@{
    schema_version = 2
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    stage = $Stage
    failure = $FailureMessage
    deployment_id = $DeploymentId
    backup_id = $BackupId
    rollback = $RollbackResult
    windows = [Environment]::OSVersion.VersionString
    docker_ready = [bool](Test-PDPOneDockerEngine)
    local_health = $localHealth
    tailscale_state = $tailscaleState
    tailscale_dns_name = $tailscaleDnsName
    public_base_url = $publicBase
    public_health_success = $(if ($null -ne $publicHealth) { [bool]$publicHealth.Success } else { $false })
    public_health_method = $(if ($null -ne $publicHealth) { [string]$publicHealth.Method } else { "not-tested" })
    local_dns_degraded = $(if ($null -ne $publicHealth) { [bool]$publicHealth.LocalDnsDegraded } else { $false })
    safe_to_share = $true
}

$lines = @(
    "PDP One safe diagnostics",
    "Generated: $($summary.generated_at)",
    "Stage: $Stage",
    "Failure: $FailureMessage",
    "Deployment ID: $DeploymentId",
    "Backup ID: $BackupId",
    "Rollback: $RollbackResult",
    "Windows: $($summary.windows)",
    "Docker ready: $($summary.docker_ready)",
    "Local health: $localHealth",
    "Tailscale state: $tailscaleState",
    "Tailscale DNS name: $tailscaleDnsName",
    "Public base URL: $publicBase",
    "Public health success: $($summary.public_health_success)",
    "Public health method: $($summary.public_health_method)",
    "Local DNS degraded: $($summary.local_dns_degraded)",
    "",
    "===== Scheduled Tasks =====",
    $tasks,
    $taskInfo,
    "",
    "===== Compose status =====",
    $composeStatus,
    "",
    "===== Tailscale Funnel status =====",
    $funnelStatus,
    "",
    "===== Tailscale netcheck =====",
    $netcheck,
    "",
    "===== Active Windows resolver =====",
    $systemDns,
    "",
    "===== Public resolver 1.1.1.1 =====",
    $publicDns,
    "",
    "===== Deployment Agent audit tail =====",
    $agentAudit,
    "",
    "===== Redacted service logs =====",
    $logs
) -join [Environment]::NewLine

$safeText = ConvertTo-PDPOneRedactedText -Text $lines
[IO.File]::WriteAllText($path, $safeText, [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($stablePath, $safeText, [Text.UTF8Encoding]::new($false))
Write-PDPOneJsonFile -Path $jsonPath -Value $summary
Write-PDPOneJsonFile -Path $stableJsonPath -Value $summary

try {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if ($desktop -and (Test-Path -LiteralPath $desktop)) {
        Copy-Item -LiteralPath $stablePath -Destination (Join-Path $desktop "PDP-ONE-LAST-DIAGNOSTICS.txt") -Force
        Copy-Item -LiteralPath $stableJsonPath -Destination (Join-Path $desktop "PDP-ONE-LAST-DIAGNOSTICS.json") -Force
    }
} catch { }

Write-Host "Safe diagnostics written to $stablePath" -ForegroundColor Yellow
if ($OpenReport) { Start-Process notepad.exe -ArgumentList $stablePath | Out-Null }
Write-Output $stablePath
