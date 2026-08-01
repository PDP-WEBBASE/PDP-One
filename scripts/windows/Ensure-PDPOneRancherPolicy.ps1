#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [int]$DockerTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

$maintenanceRoot = "C:\ProgramData\PDP-One\maintenance"
New-Item -ItemType Directory -Force -Path $maintenanceRoot | Out-Null
$reportPath = Join-Path $maintenanceRoot "rancher-policy-latest.json"

$report = [ordered]@{
    schema = "pdp-one.rancher-policy.v1"
    checked_at = [DateTime]::UtcNow.ToString("o")
    kubernetes_required = $false
    kubernetes_enabled_before = $null
    kubernetes_enabled_after = $null
    changed = $false
    docker_ready = $false
    status = "failed"
    error = $null
}

try {
    Start-PDPOneRancherDesktop -TimeoutSeconds $DockerTimeoutSeconds

    $rdctl = Get-Command rdctl.exe -ErrorAction SilentlyContinue
    if ($null -eq $rdctl) { throw "rdctl.exe was not found." }

    $settingsText = (& $rdctl.Source list-settings 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($settingsText)) {
        throw "Rancher Desktop settings could not be read."
    }
    $settings = $settingsText | ConvertFrom-Json
    $report.kubernetes_enabled_before = [bool]$settings.kubernetes.enabled

    if ([bool]$settings.kubernetes.enabled) {
        & $rdctl.Source set --kubernetes-enabled=false *> $null
        if ($LASTEXITCODE -ne 0) { throw "Rancher Desktop Kubernetes could not be disabled." }
        $report.changed = $true
        Start-PDPOneRancherDesktop -TimeoutSeconds $DockerTimeoutSeconds
    }

    $verifiedText = (& $rdctl.Source list-settings 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($verifiedText)) {
        throw "Rancher Desktop settings could not be verified."
    }
    $verified = $verifiedText | ConvertFrom-Json
    $report.kubernetes_enabled_after = [bool]$verified.kubernetes.enabled
    if ($report.kubernetes_enabled_after) {
        throw "Kubernetes is still enabled after applying the PDP One Rancher policy."
    }

    if (-not (Test-PDPOneDockerEngine)) {
        Start-PDPOneRancherDesktop -TimeoutSeconds $DockerTimeoutSeconds
    }
    $report.docker_ready = [bool](Test-PDPOneDockerEngine)
    if (-not $report.docker_ready) { throw "Docker did not become ready after applying the Rancher policy." }

    $report.status = "succeeded"
    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-Output $reportPath
} catch {
    $report.error = ConvertTo-PDPOneRedactedText $_.Exception.Message
    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    try { $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8 } catch { }
    throw $report.error
}
