#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent",
    [switch]$Once,
    [int]$PollSeconds = 5
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

$projectRoot = Get-PDPOneProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $projectRoot
$phasePath = Join-Path $projectRoot "release\implementation-in-progress.json"

if (Test-Path -LiteralPath $phasePath) {
    $phaseText = [IO.File]::ReadAllText($phasePath, [Text.Encoding]::UTF8)
    $phase = $phaseText | ConvertFrom-Json
    if ([string]$phase.status -eq "in_progress") {
        $previousMode = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_CHANGE_MANAGEMENT_MODE")
        $previousTrial = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_TRIAL_MODE")
        Set-PDPOneEnvValue -Path $envPath -Name "PDP_CHANGE_MANAGEMENT_MODE" -Value "development_fast"
        Set-PDPOneEnvValue -Path $envPath -Name "PDP_TRIAL_MODE" -Value "true"

        foreach ($staleState in @("approved-release.json", "approved-backup.json")) {
            Remove-Item -LiteralPath (Join-Path $AgentRoot "state\$staleState") -Force -ErrorAction SilentlyContinue
        }

        if ($previousMode -ne "development_fast" -or $previousTrial.ToLowerInvariant() -notin @("1", "true", "yes")) {
            $auditRoot = Join-Path $AgentRoot "audit"
            New-Item -ItemType Directory -Force -Path $auditRoot | Out-Null
            [ordered]@{
                at = [DateTime]::UtcNow.ToString("o")
                action = "implementation_mode_transition"
                status = "succeeded"
                previous_mode = $previousMode
                change_management_mode = "development_fast"
                trial_mode = $true
                completion_trigger_exact_text = [string]$phase.completion_trigger_exact_text
            } | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $auditRoot "deployment-agent.jsonl") -Encoding UTF8
        }
    }
}

$delegate = Join-Path $PSScriptRoot "Deployment-Agent.Standard.ps1"
if (-not (Test-Path -LiteralPath $delegate)) {
    throw "The preserved standard deployment agent is missing."
}

$arguments = @(
    "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $delegate,
    "-AgentRoot", $AgentRoot,
    "-PollSeconds", ([string]$PollSeconds)
)
if ($Once) { $arguments += "-Once" }

& powershell.exe @arguments
exit $LASTEXITCODE
