#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet("full", "backend", "mcp", "web", "host", "none")][string]$Profile = "full",
    [int]$TimeoutSeconds = 75,
    [switch]$SkipPublicCheck
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "PDPOne.Common.ps1")

function Wait-PDPOneHttp {
    param([Parameter(Mandatory = $true)][string]$Url, [string]$ExpectedPattern = "", [int]$Timeout = 60)
    $deadline = (Get-Date).AddSeconds([Math]::Max(5, $Timeout))
    $lastError = ""
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10
            $text = ConvertTo-PDPOneResponseText $response.Content
            if ($response.StatusCode -eq 200 -and (-not $ExpectedPattern -or $text -match $ExpectedPattern)) { return $true }
            $lastError = "HTTP $($response.StatusCode) returned unexpected content."
        } catch { $lastError = $_.Exception.Message }
        Start-Sleep -Seconds 2
    }
    throw "Scoped health endpoint did not become ready: $(ConvertTo-PDPOneRedactedText $lastError)"
}

function Wait-PDPOneContainerState {
    param([Parameter(Mandatory = $true)][string]$Service, [switch]$RequireHealthy, [int]$Timeout = 60)
    $deadline = (Get-Date).AddSeconds([Math]::Max(5, $Timeout))
    while ((Get-Date) -lt $deadline) {
        $id = [string](& docker compose ps -q $Service 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($id)) {
            $status = [string](& docker inspect --format '{{.State.Status}}' $id 2>$null | Select-Object -First 1)
            if ($status.Trim() -eq "running") {
                if (-not $RequireHealthy) { return $true }
                $health = [string](& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $id 2>$null | Select-Object -First 1)
                if ($health.Trim() -eq "healthy") { return $true }
            }
        }
        Start-Sleep -Seconds 2
    }
    throw "$Service did not reach the required scoped health state."
}

function Invoke-PDPOneFullHealthFallback {
    param([switch]$SkipPublic)
    $fullHealthScript = Join-Path $PSScriptRoot "Test-PDPOne.ps1"
    if (-not (Test-Path -LiteralPath $fullHealthScript)) { throw "Full PDP One health script is missing." }
    $arguments = @(
        "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $fullHealthScript,
        "-SkipChatGPTToolCheck"
    )
    if ($SkipPublic) { $arguments += "-SkipPublicCheck" }
    & powershell.exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "Full PDP One health check failed." }
}

$projectRoot = Get-PDPOneProjectRoot
$envPath = Assert-PDPOneConfiguration -ProjectRoot $projectRoot
Set-Location $projectRoot
if (-not (Test-PDPOneDockerEngine)) { throw "Docker Engine is unavailable." }
& docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw "Docker Compose configuration is invalid." }

if ($Profile -eq "full") {
    Invoke-PDPOneFullHealthFallback -SkipPublic:$SkipPublicCheck
    return
}

try {
    $requiredCommon = @("db", "redis", "nginx", "tailscale")
    foreach ($service in $requiredCommon) {
        Wait-PDPOneContainerState -Service $service -Timeout $TimeoutSeconds | Out-Null
    }

    & docker compose exec -T db pg_isready *> $null
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL is not ready." }

    switch ($Profile) {
        "backend" {
            foreach ($service in @("backend", "worker", "beat")) {
                Wait-PDPOneContainerState -Service $service -Timeout $TimeoutSeconds | Out-Null
            }
            & docker compose exec -T backend python manage.py check --database default *> $null
            if ($LASTEXITCODE -ne 0) { throw "Backend Django/database check failed." }
            Wait-PDPOneHttp -Url "http://127.0.0.1:8080/api/v1/auth/session/" -ExpectedPattern '"authenticated"' -Timeout $TimeoutSeconds | Out-Null
        }
        "mcp" {
            Wait-PDPOneContainerState -Service "mcp" -RequireHealthy -Timeout $TimeoutSeconds | Out-Null
            $pathToken = Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN"
            if (-not $pathToken) { throw "MCP path token is missing." }
            Wait-PDPOneHttp -Url ("http://127.0.0.1:8080/mcp/" + $pathToken + "/healthz") -ExpectedPattern '(?i)pdp-one-mcp' -Timeout $TimeoutSeconds | Out-Null
        }
        "web" {
            Wait-PDPOneContainerState -Service "web" -RequireHealthy -Timeout $TimeoutSeconds | Out-Null
            Wait-PDPOneHttp -Url "http://127.0.0.1:8080/pdp-build.json" -ExpectedPattern '"build_id"' -Timeout $TimeoutSeconds | Out-Null
        }
        "host" {
            Wait-PDPOneHttp -Url "http://127.0.0.1:8080/healthz" -ExpectedPattern '(?i)(PDP One ready|ready|healthy|ok)' -Timeout $TimeoutSeconds | Out-Null
        }
        "none" {
            Wait-PDPOneHttp -Url "http://127.0.0.1:8080/healthz" -ExpectedPattern '(?i)(PDP One ready|ready|healthy|ok)' -Timeout $TimeoutSeconds | Out-Null
        }
    }

    if (-not $SkipPublicCheck) {
        $publicBase = [string](Get-PDPOneEnvValue -Path $envPath -Name "PDP_PUBLIC_BASE_URL")
        if ($publicBase) {
            $base = $publicBase.TrimEnd('/')
            $publicHealth = Test-PDPOnePublicHealth -Url ($base + "/healthz") -ExpectedPattern 'PDP One ready' -TimeoutSeconds 25
            if (-not [bool]$publicHealth.Success) { throw "Scoped public health failed: $($publicHealth.Detail)" }
            switch ($Profile) {
                "backend" {
                    $componentHealth = Test-PDPOnePublicHealth -Url ($base + "/api/v1/auth/session/") -ExpectedPattern '"authenticated"' -TimeoutSeconds 25
                    if (-not [bool]$componentHealth.Success) { throw "Scoped public backend health failed: $($componentHealth.Detail)" }
                }
                "mcp" {
                    $pathToken = Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN"
                    $componentHealth = Test-PDPOnePublicHealth -Url ($base + "/mcp/" + $pathToken + "/healthz") -ExpectedPattern 'pdp-one-mcp' -TimeoutSeconds 25
                    if (-not [bool]$componentHealth.Success) { throw "Scoped public MCP health failed: $($componentHealth.Detail)" }
                }
                "web" {
                    $componentHealth = Test-PDPOnePublicHealth -Url ($base + "/pdp-build.json") -ExpectedPattern '"build_id"' -TimeoutSeconds 25
                    if (-not [bool]$componentHealth.Success) { throw "Scoped public web health failed: $($componentHealth.Detail)" }
                }
            }
        }
    }
} catch {
    $scopedError = ConvertTo-PDPOneRedactedText $_.Exception.Message
    Write-Warning "Scoped health did not pass; running stronger full-health fallback."
    try {
        Invoke-PDPOneFullHealthFallback -SkipPublic:$SkipPublicCheck
    } catch {
        $fullError = ConvertTo-PDPOneRedactedText $_.Exception.Message
        throw "Scoped health failed and full-health fallback also failed. Scoped: $scopedError Full: $fullError"
    }
    Write-Host "Scoped health fallback accepted because full PDP One health passed." -ForegroundColor Yellow
}
