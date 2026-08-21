#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param([string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent")

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")
. (Join-Path $PSScriptRoot "PDPOne.HiddenTask.ps1")
$ProjectRoot = Get-PDPOneProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $ProjectRoot
$BootstrapSourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$hiddenRunner = Get-PDPOneHiddenRunnerPath -BaseDirectory $PSScriptRoot

Write-Host "One-time setup: PDP One Local Deployment Agent" -ForegroundColor Cyan
Write-Host "A GitHub Personal Access Token (classic) with minimum read:packages is required once for Private GHCR image pulls." -ForegroundColor Yellow
Write-Host "The application repository is Public; repo scope is not required for source access. The GitHub account must have read access to the PDP One container packages." -ForegroundColor Yellow
Write-Host "The token is protected with Windows DPAPI for this Windows account and is never printed or committed." -ForegroundColor DarkGreen
$secureToken = Read-Host "Paste the GitHub PAT classic with read:packages" -AsSecureString
if ($secureToken.Length -lt 20) { throw "A GitHub token was not supplied." }

if (-not (Test-PDPOneDockerEngine)) { throw "Docker Engine must be ready before the GHCR credential can be validated." }

$credentialPointer = [IntPtr]::Zero
$plainCredential = $null
try {
    $credentialPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainCredential = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($credentialPointer)
    if ([string]::IsNullOrWhiteSpace($plainCredential)) { throw "The GitHub token could not be opened for validation." }
    $plainCredential | & docker login ghcr.io --username "PDP-WEBBASE" --password-stdin | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "GitHub Container Registry login failed. Use a PAT classic with read:packages and an account that can read the PDP One container packages." }
} finally {
    if ($credentialPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($credentialPointer) }
    Remove-Variable plainCredential -ErrorAction SilentlyContinue
    & docker logout ghcr.io *> $null
}

foreach ($directory in @("queue\incoming", "queue\processing", "queue\responses", "queue\rejected", "state\processed", "audit", "secrets", "reports", "downloads")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $AgentRoot $directory) | Out-Null
}
& icacls.exe $AgentRoot /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" "SYSTEM:(OI)(CI)F" "Administrators:(OI)(CI)F" *> $null
$bootstrapBackup = Join-Path $AgentRoot "bootstrap-backup"
New-Item -ItemType Directory -Force -Path $bootstrapBackup | Out-Null
Protect-PDPOneSecretFile -InputPath $envPath -OutputPath (Join-Path $bootstrapBackup "environment-before-agent.dpapi")
Copy-Item -LiteralPath (Join-Path $ProjectRoot "docker-compose.yml") -Destination (Join-Path $bootstrapBackup "docker-compose.yml") -Force
& robocopy.exe (Join-Path $ProjectRoot "services\pdp_mcp") (Join-Path $bootstrapBackup "pdp_mcp") /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP
if ($LASTEXITCODE -gt 7) { throw "The existing MCP control plane could not be backed up." }
$secureToken | ConvertFrom-SecureString | Set-Content -LiteralPath (Join-Path $AgentRoot "secrets\github-token.dpapi") -Encoding ASCII

$signingKey = Get-PDPOneEnvValue $envPath "PDP_DEPLOYMENT_AGENT_SIGNING_KEY"
if ([string]::IsNullOrWhiteSpace($signingKey) -or $signingKey -match '^replace-with-') {
    $signingKey = New-PDPOneSecret 48
    Set-PDPOneEnvValue $envPath "PDP_DEPLOYMENT_AGENT_SIGNING_KEY" $signingKey
}
Set-PDPOneEnvValue $envPath "PDP_DEPLOYMENT_AGENT_ROOT" ($AgentRoot -replace '\\', '/')

$binRoot = Join-Path $AgentRoot "bin"
New-Item -ItemType Directory -Force -Path $binRoot | Out-Null
$bootstrapScripts = @(
    "PDPOne.Common.ps1", "Deployment-Agent.ps1", "Invoke-PDPOneDeployment.ps1",
    "New-PDPOneBackup.ps1", "Test-PDPOneBackupRestore.ps1", "Restore-PDPOneBackup.ps1",
    "Rollback-PDPOne.ps1", "Update-PDPOne.ps1", "Test-PDPOne.ps1",
    "Start-PDPOne.ps1", "Repair-PDPOneConnectivity.ps1", "Open-PDPOneLocal.ps1",
    "Register-PDPOneStartupTask.ps1", "New-PDPOneDiagnostics.ps1", "Rotate-PDPOneMcpToken.ps1",
    "Invoke-PDPOneDiskMaintenance.ps1"
)
foreach ($name in $bootstrapScripts) {
    $source = Join-Path $PSScriptRoot $name
    if (-not (Test-Path -LiteralPath $source)) { throw "Agent bootstrap file is missing: $name" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $binRoot $name) -Force
}
$publicBase = Get-PDPOneEnvValue $envPath "PDP_PUBLIC_BASE_URL"
if ([string]::IsNullOrWhiteSpace($publicBase) -and (Test-PDPOneDockerEngine)) {
    Set-Location $ProjectRoot
    $tailscaleJson = (& docker compose --profile tunnel exec -T tailscale tailscale --socket=/tmp/tailscaled.sock status --json 2>$null | Out-String)
    try {
        $tailscale = $tailscaleJson | ConvertFrom-Json
        $dnsName = [string]$tailscale.Self.DNSName
        if ($dnsName) { Set-PDPOneEnvValue $envPath "PDP_PUBLIC_BASE_URL" ("https://" + $dnsName.TrimEnd('.')) }
    } catch { }
}
$agentScript = Join-Path $binRoot "Deployment-Agent.ps1"

try {
    Copy-Item -LiteralPath (Join-Path $BootstrapSourceRoot "docker-compose.yml") -Destination (Join-Path $ProjectRoot "docker-compose.yml") -Force
    & robocopy.exe (Join-Path $BootstrapSourceRoot "services\pdp_mcp") (Join-Path $ProjectRoot "services\pdp_mcp") /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP
    if ($LASTEXITCODE -gt 7) { throw "The signed MCP deployment tools could not be staged." }
    Set-Location $ProjectRoot
    & docker compose build mcp
    if ($LASTEXITCODE -ne 0) { throw "The signed MCP control-plane image could not be built." }
    & docker compose up --detach --no-deps --force-recreate mcp
    if ($LASTEXITCODE -ne 0) { throw "The signed MCP control plane could not be started." }
} catch {
    Copy-Item -LiteralPath (Join-Path $bootstrapBackup "docker-compose.yml") -Destination (Join-Path $ProjectRoot "docker-compose.yml") -Force
    & robocopy.exe (Join-Path $bootstrapBackup "pdp_mcp") (Join-Path $ProjectRoot "services\pdp_mcp") /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP *> $null
    Set-Location $ProjectRoot
    & docker compose up --build --detach --no-deps mcp *> $null
    throw "Agent control-plane bootstrap failed and the previous MCP files were restored: $($_.Exception.Message)"
}

$action = New-PDPOneHiddenPowerShellAction -ScriptPath $agentScript -ScriptArguments @("-AgentRoot", $AgentRoot) -HiddenRunnerPath $hiddenRunner
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 20 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "PDP One Local Deployment Agent" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Processes only signed, allowlisted PDP One deployment requests." -Force | Out-Null
Assert-PDPOneScheduledTaskWindowless -TaskName "PDP One Local Deployment Agent" -HiddenRunnerPath $hiddenRunner | Out-Null
Start-ScheduledTask -TaskName "PDP One Local Deployment Agent"

& (Join-Path $PSScriptRoot "Register-PDPOneStartupTask.ps1") -ProjectRoot $ProjectRoot
Start-ScheduledTask -TaskName "PDP One Stable Startup"

Write-Host "Local deployment agent and stable startup watchdog installed. This one-time Windows action is complete." -ForegroundColor Green
