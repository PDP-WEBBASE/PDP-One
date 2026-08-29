#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$AgentRoot = "C:\ProgramData\PDP-One\deployment-agent"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

function Invoke-PDPOneDockerQuiet {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$StandardInput = ""
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        if ([string]::IsNullOrEmpty($StandardInput)) {
            & docker @Arguments *> $null
        } else {
            $StandardInput | & docker @Arguments *> $null
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

$secretsRoot = Join-Path $AgentRoot "secrets"
$stateRoot = Join-Path $AgentRoot "state"
$secretPath = Join-Path $secretsRoot "github-token.dpapi"
$lastDeploymentPath = Join-Path $stateRoot "last-deployment.json"
$healthScript = Join-Path $PSScriptRoot "Test-PDPOneGhcrCredential.ps1"
New-Item -ItemType Directory -Force -Path $secretsRoot,$stateRoot | Out-Null

Write-Host "PDP One persistent GHCR credential refresh" -ForegroundColor Cyan
Write-Host "This is a one-time secret refresh. The token will be validated, DPAPI-protected, and never printed or committed." -ForegroundColor Yellow
Write-Host "Use a GitHub PAT classic with minimum read:packages from an account that can read the PDP One container packages." -ForegroundColor Yellow
$secureToken = Read-Host "Paste the GitHub PAT classic with read:packages" -AsSecureString
if ($secureToken.Length -lt 20) { throw "A GitHub token was not supplied." }

$pointer = [IntPtr]::Zero
$plainToken = $null
$loggedIn = $false
$tempPath = Join-Path $secretsRoot ("github-token." + [Guid]::NewGuid().ToString("N") + ".tmp")
$backupPath = $null
$probeImage = ""

try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI is unavailable." }
    if ((Invoke-PDPOneDockerQuiet -Arguments @("info")) -ne 0) { throw "Docker Engine must be ready before GHCR credential validation." }

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($plainToken)) { throw "The supplied token could not be opened for validation." }

    if ((Invoke-PDPOneDockerQuiet -Arguments @("login", "ghcr.io", "--username", "PDP-WEBBASE", "--password-stdin") -StandardInput $plainToken) -ne 0) {
        throw "GHCR authentication failed. Use a PAT classic with read:packages and package-read access."
    }
    $loggedIn = $true

    if (Test-Path -LiteralPath $lastDeploymentPath) {
        try {
            $state = Get-Content -LiteralPath $lastDeploymentPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($name in @("backend", "mcp", "web")) {
                if ($null -ne $state.active_images) {
                    $property = $state.active_images.PSObject.Properties[$name]
                    if ($null -ne $property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
                        $probeImage = [string]$property.Value
                        break
                    }
                }
            }
        } catch { $probeImage = "" }
    }

    if (-not [string]::IsNullOrWhiteSpace($probeImage)) {
        if ((Invoke-PDPOneDockerQuiet -Arguments @("manifest", "inspect", $probeImage)) -ne 0) {
            throw "GHCR authentication succeeded but package-read validation failed for an accepted PDP One image."
        }
    }

    $secureToken | ConvertFrom-SecureString | Set-Content -LiteralPath $tempPath -Encoding ASCII
    if (-not (Test-Path -LiteralPath $tempPath) -or (Get-Item -LiteralPath $tempPath).Length -le 0) { throw "The DPAPI-protected credential could not be staged." }

    if (Test-Path -LiteralPath $secretPath) {
        $backupPath = Join-Path $secretsRoot ("github-token.dpapi.backup-" + [DateTime]::UtcNow.ToString("yyyyMMddHHmmss"))
        Copy-Item -LiteralPath $secretPath -Destination $backupPath -Force
    }
    Move-Item -LiteralPath $tempPath -Destination $secretPath -Force

    if (-not (Test-Path -LiteralPath $healthScript)) { throw "GHCR credential health helper is missing from the installed Agent." }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $healthScript -AgentRoot $AgentRoot
    if ($LASTEXITCODE -ne 0) {
        if ($backupPath -and (Test-Path -LiteralPath $backupPath)) { Copy-Item -LiteralPath $backupPath -Destination $secretPath -Force }
        throw "The new protected credential failed independent health verification; the previous credential was restored when available."
    }

    Write-Host "Persistent GHCR credential is healthy and stored with Windows DPAPI. Future deployments will reuse it automatically." -ForegroundColor Green
} finally {
    if ($loggedIn) { [void](Invoke-PDPOneDockerQuiet -Arguments @("logout", "ghcr.io")) }
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $plainToken = $null
    if (Test-Path -LiteralPath $tempPath) { Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue }
}
