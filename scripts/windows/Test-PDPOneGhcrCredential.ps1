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

$stateRoot = Join-Path $AgentRoot "state"
$secretPath = Join-Path $AgentRoot "secrets\github-token.dpapi"
$lastDeploymentPath = Join-Path $stateRoot "last-deployment.json"
$healthPath = Join-Path $stateRoot "ghcr-credential-health.json"
New-Item -ItemType Directory -Force -Path $stateRoot | Out-Null

$pointer = [IntPtr]::Zero
$plainToken = $null
$loggedIn = $false
$probeImage = ""
$report = [ordered]@{
    schema = "pdp-one.ghcr-credential-health.v1"
    checked_at = [DateTime]::UtcNow.ToString("o")
    status = "unhealthy"
    protected_secret_present = $false
    protected_secret_decryptable = $false
    registry_login_verified = $false
    package_read_verified = $false
    package_probe_performed = $false
    refresh_required = $true
    secrets_included = $false
    error = $null
}

try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI is unavailable." }
    if ((Invoke-PDPOneDockerQuiet -Arguments @("info")) -ne 0) { throw "Docker Engine is not ready." }

    if (-not (Test-Path -LiteralPath $secretPath)) { throw "The protected GHCR credential is missing." }
    $report.protected_secret_present = $true

    $cipherText = (Get-Content -LiteralPath $secretPath -Raw -Encoding ASCII).Trim()
    if ([string]::IsNullOrWhiteSpace($cipherText)) { throw "The protected GHCR credential file is empty." }
    $secureToken = $cipherText | ConvertTo-SecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($plainToken)) { throw "The protected GHCR credential could not be decrypted for this Windows account." }
    $report.protected_secret_decryptable = $true

    if ((Invoke-PDPOneDockerQuiet -Arguments @("login", "ghcr.io", "--username", "PDP-WEBBASE", "--password-stdin") -StandardInput $plainToken) -ne 0) {
        throw "GHCR authentication failed. Refresh the protected credential once with a PAT classic that has read:packages."
    }
    $loggedIn = $true
    $report.registry_login_verified = $true

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
        $report.package_probe_performed = $true
        if ((Invoke-PDPOneDockerQuiet -Arguments @("manifest", "inspect", $probeImage)) -ne 0) {
            throw "GHCR login succeeded but package read verification failed for an accepted PDP One image. Ensure the token owner can read the PDP One container packages."
        }
        $report.package_read_verified = $true
    } else {
        $report.package_read_verified = $true
    }

    $report.status = "healthy"
    $report.refresh_required = $false
    $report.error = $null
    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $healthPath -Encoding UTF8
    Write-Output $healthPath
    exit 0
} catch {
    $report.status = "unhealthy"
    $report.refresh_required = $true
    $report.error = [string]$_.Exception.Message
    $report.checked_at = [DateTime]::UtcNow.ToString("o")
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $healthPath -Encoding UTF8
    # This helper is invoked by a fail-closed parent that inspects LASTEXITCODE.
    # Do not write expected preflight failures to the Error stream: Windows
    # PowerShell 5.1 can promote redirected native/child stderr to a terminating
    # error before the parent records the exit code and durable deployment report.
    Write-Output $report.error
    exit 1
} finally {
    if ($loggedIn) { [void](Invoke-PDPOneDockerQuiet -Arguments @("logout", "ghcr.io")) }
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $plainToken = $null
}
