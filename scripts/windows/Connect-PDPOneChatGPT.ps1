#requires -Version 5.1
#requires -RunAsAdministrator
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

function New-RandomSecret([int]$Bytes = 36) {
    $buffer = New-Object byte[] $Bytes
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Test-DockerEngine {
    cmd /c "docker info >nul 2>&1"
    return $LASTEXITCODE -eq 0
}

function Find-InstalledProjectRoot {
    $sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    if (Test-Path -LiteralPath (Join-Path $sourceRoot ".env")) { return $sourceRoot }

    $containerId = docker ps -a `
        --filter "label=com.docker.compose.project=pdp-one" `
        --filter "label=com.docker.compose.service=nginx" `
        --format "{{.ID}}" 2>$null | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($containerId)) {
        throw "PDP One installation was not found. Run INSTALL-PDP-ONE.bat first."
    }
    $inspect = @((docker inspect $containerId | ConvertFrom-Json))[0]
    $root = $inspect.Config.Labels.'com.docker.compose.project.working_dir'
    if ([string]::IsNullOrWhiteSpace($root) -or -not (Test-Path -LiteralPath $root)) {
        throw "The installed PDP One folder could not be found."
    }
    return (Resolve-Path -LiteralPath $root).Path
}

function Get-EnvValue([string]$Path, [string]$Name) {
    $match = Select-String -LiteralPath $Path -Pattern "^$([regex]::Escape($Name))=(.*)$" | Select-Object -Last 1
    if ($null -eq $match) { return $null }
    return $match.Matches[0].Groups[1].Value.Trim()
}

function Set-EnvValue([string]$Path, [string]$Name, [string]$Value) {
    $content = [IO.File]::ReadAllText($Path)
    $pattern = "(?m)^$([regex]::Escape($Name))=.*$"
    if ([regex]::IsMatch($content, $pattern)) {
        $content = [regex]::Replace($content, $pattern, "$Name=$Value")
    } else {
        $content = $content.TrimEnd() + "`r`n$Name=$Value`r`n"
    }
    [IO.File]::WriteAllText($Path, $content, [Text.UTF8Encoding]::new($false))
}

function Wait-ForUrl([string[]]$Paths, [string]$Pattern, [int]$Seconds = 35) {
    foreach ($attempt in 1..$Seconds) {
        foreach ($logPath in $Paths) {
            if (-not (Test-Path -LiteralPath $logPath)) { continue }

            $text = [string]::Empty
            try {
                $rawText = Get-Content -LiteralPath $logPath -Raw -ErrorAction Stop
                if ($null -ne $rawText) { $text = [string]$rawText }
            } catch {
                # The tunnel process may still be creating or writing the log.
                continue
            }

            if ([string]::IsNullOrWhiteSpace($text)) { continue }
            # SSH tunnel providers often insert ANSI colour codes inside the URL.
            $cleanText = [regex]::Replace($text, "$([char]27)\\[[0-9;?]*[ -/]*[@-~]", "")
            $cleanText = $cleanText.Replace("`b", "")
            $match = [regex]::Match($cleanText, $Pattern)
            if ($match.Success) { return $match.Value.TrimEnd('/', '.', ')') }
        }
        Start-Sleep -Seconds 1
    }
    return $null
}

function Test-PublicTunnel([string]$BaseUrl, $Process, [switch]$ServiceManaged) {
    if ([string]::IsNullOrWhiteSpace($BaseUrl)) { return $false }
    if (-not $ServiceManaged -and ($null -eq $Process -or $Process.HasExited)) { return $false }

    foreach ($attempt in 1..3) {
        try {
            $healthUrl = "$($BaseUrl.TrimEnd('/'))/healthz"
            $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 10
            if ($response.StatusCode -eq 200 -and $response.Content -match "PDP One ready") {
                if ($ServiceManaged) { return $true }
                return (-not $Process.HasExited)
            }
        } catch {
            if (-not $ServiceManaged -and $null -ne $Process -and $Process.HasExited) { return $false }
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Find-TailscaleCli {
    $command = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in @(
        "C:\Program Files\Tailscale\tailscale.exe",
        (Join-Path $env:LOCALAPPDATA "Tailscale\tailscale.exe")
    )) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Ensure-TailscaleCli {
    $cli = Find-TailscaleCli
    if ($cli) { return $cli }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $null }

    Write-Host "Installing Tailscale for a reliable free HTTPS Funnel ..." -ForegroundColor Cyan
    winget install --id Tailscale.Tailscale --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { return $null }

    foreach ($attempt in 1..30) {
        $cli = Find-TailscaleCli
        if ($cli) { return $cli }
        Start-Sleep -Seconds 2
    }
    return $null
}

Write-Host "PDP One - automatic ChatGPT connection 2026.07.18.5" -ForegroundColor Green
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker command is unavailable." }
if (-not (Test-DockerEngine)) { throw "Open Rancher Desktop and wait until the Moby engine is ready." }

$ProjectRoot = Find-InstalledProjectRoot
Set-Location $ProjectRoot
$EnvPath = Join-Path $ProjectRoot ".env"
if (-not (Test-Path -LiteralPath $EnvPath)) { throw "The secure .env file is missing." }

$mcpPathToken = Get-EnvValue -Path $EnvPath -Name "PDP_MCP_PATH_TOKEN"
if ([string]::IsNullOrWhiteSpace($mcpPathToken) -or $mcpPathToken -eq "replace-with-a-random-path-token") {
    $mcpPathToken = New-RandomSecret 32
    Set-EnvValue -Path $EnvPath -Name "PDP_MCP_PATH_TOKEN" -Value $mcpPathToken
}
Set-EnvValue -Path $EnvPath -Name "PDP_TRIAL_MODE" -Value "true"
$trialAdminUser = Get-EnvValue -Path $EnvPath -Name "PDP_TRIAL_ADMIN_USERNAME"
if ([string]::IsNullOrWhiteSpace($trialAdminUser)) {
    $trialAdminUser = "pdp-admin"
    Set-EnvValue -Path $EnvPath -Name "PDP_TRIAL_ADMIN_USERNAME" -Value $trialAdminUser
}
$trialAdminPassword = Get-EnvValue -Path $EnvPath -Name "PDP_TRIAL_ADMIN_PASSWORD"
if ([string]::IsNullOrWhiteSpace($trialAdminPassword) -or $trialAdminPassword.StartsWith("replace-with-")) {
    $trialAdminPassword = New-RandomSecret 24
    Set-EnvValue -Path $EnvPath -Name "PDP_TRIAL_ADMIN_PASSWORD" -Value $trialAdminPassword
}

Write-Host "Starting PDP One and checking PostgreSQL ..." -ForegroundColor Cyan
docker compose up --build --detach
if ($LASTEXITCODE -ne 0) { throw "PDP One services failed to start." }

$ready = $false
foreach ($attempt in 1..75) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8080/healthz" -TimeoutSec 5
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if (-not $ready) {
    docker compose logs --tail 100 nginx backend mcp
    throw "PDP One did not become healthy."
}

$logDir = Join-Path $ProjectRoot "work\chatgpt-connection"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$tunnelProcess = $null
$publicBase = $null
$provider = $null
$cfOut = $null
$cfErr = $null
$pgOut = $null
$pgErr = $null
$lrOut = $null
$lrErr = $null
$tailscaleCli = $null
$tailscaleActive = $false
$tsLog = Join-Path $logDir "tailscale-funnel.log"

# Tailscale Funnel is the primary route because anonymous tunnel providers are
# commonly blocked by managed DNS or regional firewalls.
$tailscaleCli = Ensure-TailscaleCli
if ($tailscaleCli) {
    Write-Host "Preparing the free Tailscale HTTPS Funnel ..." -ForegroundColor Cyan

    $isLoggedIn = $false
    try {
        $statusJson = (& $tailscaleCli status --json 2>$null | Out-String)
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($statusJson)) {
            $status = $statusJson | ConvertFrom-Json
            $isLoggedIn = $status.BackendState -eq "Running"
        }
    } catch {
        $isLoggedIn = $false
    }

    if (-not $isLoggedIn) {
        Write-Host ""
        Write-Host "One-time action: complete the Tailscale sign-in in the browser that opens." -ForegroundColor Yellow
        & $tailscaleCli up
        $isLoggedIn = $LASTEXITCODE -eq 0
    }

    if ($isLoggedIn) {
        foreach ($funnelAttempt in 1..2) {
            $funnelLines = @()
            & $tailscaleCli funnel --bg --yes 8080 2>&1 | Tee-Object -Variable funnelLines | Out-Host
            $funnelStatus = (& $tailscaleCli funnel status 2>&1 | Out-String)
            $funnelText = (($funnelLines | Out-String) + "`r`n" + $funnelStatus)
            [IO.File]::WriteAllText($tsLog, $funnelText, [Text.UTF8Encoding]::new($false))

            $urlMatch = [regex]::Match($funnelText, 'https://[A-Za-z0-9.-]+\.ts\.net')
            if ($urlMatch.Success) {
                $candidateUrl = $urlMatch.Value.TrimEnd('/')
                if (Test-PublicTunnel -BaseUrl $candidateUrl -Process $null -ServiceManaged) {
                    $publicBase = $candidateUrl
                    $provider = "Tailscale Funnel"
                    $tailscaleActive = $true
                    break
                }
            }

            $approvalMatch = [regex]::Match($funnelText, 'https://login\.tailscale\.com/[^\s]+')
            if ($approvalMatch.Success -and $funnelAttempt -eq 1) {
                Start-Process $approvalMatch.Value
                Write-Host ""
                Read-Host "Approve Funnel in the opened Tailscale page, then press Enter here"
            } else {
                break
            }
        }
    }
}

if (-not $publicBase -and (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "Creating a free temporary HTTPS address with Cloudflare ..." -ForegroundColor Cyan
    $cfOut = Join-Path $logDir "cloudflared.out.log"
    $cfErr = Join-Path $logDir "cloudflared.err.log"
    Remove-Item $cfOut, $cfErr -Force -ErrorAction SilentlyContinue
    $tunnelProcess = Start-Process cloudflared -ArgumentList @("tunnel", "--url", "http://127.0.0.1:8080", "--no-autoupdate") -PassThru -WindowStyle Hidden -RedirectStandardOutput $cfOut -RedirectStandardError $cfErr
    $publicBase = Wait-ForUrl -Paths @($cfErr, $cfOut) -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -Seconds 35
    if ($publicBase -and (Test-PublicTunnel -BaseUrl $publicBase -Process $tunnelProcess)) {
        $provider = "Cloudflare Quick Tunnel"
    } else {
        $publicBase = $null
        if ($null -ne $tunnelProcess -and -not $tunnelProcess.HasExited) {
            Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
        }
        $tunnelProcess = $null
    }
}

if (-not $publicBase) {
    $ssh = Get-Command ssh.exe -ErrorAction SilentlyContinue
    if (-not $ssh) { throw "Neither Cloudflare Quick Tunnel nor Windows OpenSSH is available." }
    Write-Host "Cloudflare is unavailable; using the free Pinggy fallback ..." -ForegroundColor Yellow
    $pgOut = Join-Path $logDir "pinggy.out.log"
    $pgErr = Join-Path $logDir "pinggy.err.log"
    Remove-Item $pgOut, $pgErr -Force -ErrorAction SilentlyContinue
    $arguments = @(
        "-p", "443", "-T", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20",
        "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", "-o", "ExitOnForwardFailure=yes",
        "-R", "0:127.0.0.1:8080", "free.pinggy.io"
    )
    $tunnelProcess = Start-Process $ssh.Source -ArgumentList $arguments -PassThru -WindowStyle Hidden -RedirectStandardOutput $pgOut -RedirectStandardError $pgErr
    $publicBase = Wait-ForUrl -Paths @($pgOut, $pgErr) -Pattern 'https://[A-Za-z0-9.-]*pinggy[^\s\x1b]*' -Seconds 35
    if ($publicBase -and -not $tunnelProcess.HasExited) {
        $provider = "Pinggy free tunnel"
    } else {
        $publicBase = $null
    }
}

if (-not $publicBase) {
    if ($null -ne $tunnelProcess -and -not $tunnelProcess.HasExited) {
        Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    }
    $tunnelProcess = $null
    Write-Host "Pinggy is unavailable; using the free localhost.run fallback ..." -ForegroundColor Yellow
    $lrOut = Join-Path $logDir "localhost-run.out.log"
    $lrErr = Join-Path $logDir "localhost-run.err.log"
    Remove-Item $lrOut, $lrErr -Force -ErrorAction SilentlyContinue
    $lrArguments = @(
        "-p", "443", "-T", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20",
        "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3", "-o", "ExitOnForwardFailure=yes",
        "-R", "80:127.0.0.1:8080", "nokey@localhost.run"
    )
    $tunnelProcess = Start-Process $ssh.Source -ArgumentList $lrArguments -PassThru -WindowStyle Hidden -RedirectStandardOutput $lrOut -RedirectStandardError $lrErr
    $publicBase = Wait-ForUrl -Paths @($lrOut, $lrErr) -Pattern 'https://[A-Za-z0-9.-]+(?:lhr\.life|localhost\.run)' -Seconds 40
    if ($publicBase -and -not $tunnelProcess.HasExited) {
        $provider = "localhost.run free tunnel"
    } else {
        $publicBase = $null
    }
}

if (-not $publicBase -or $null -eq $tunnelProcess -or $tunnelProcess.HasExited) {
    if ($null -ne $tunnelProcess -and -not $tunnelProcess.HasExited) {
        Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    }
    $diagnosticPath = Join-Path $ProjectRoot "PDP-ONE-TUNNEL-DIAGNOSTICS.txt"
    $diagnosticLines = @(
        "PDP One tunnel diagnostics",
        "Generated: $(Get-Date -Format s)",
        "Local health: http://127.0.0.1:8080/healthz",
        ""
    )
    foreach ($logFile in @($cfOut, $cfErr, $pgOut, $pgErr, $lrOut, $lrErr)) {
        if (-not [string]::IsNullOrWhiteSpace($logFile) -and (Test-Path -LiteralPath $logFile)) {
            $diagnosticLines += "===== $([IO.Path]::GetFileName($logFile)) ====="
            $diagnosticLines += (Get-Content -LiteralPath $logFile -ErrorAction SilentlyContinue | Select-Object -Last 80)
            $diagnosticLines += ""
        }
    }
    [IO.File]::WriteAllLines($diagnosticPath, $diagnosticLines, [Text.UTF8Encoding]::new($false))
    Start-Process notepad.exe -ArgumentList $diagnosticPath
    throw "All free HTTPS tunnel providers are blocked or unavailable. Diagnostics were opened in Notepad."
}

$mcpEndpoint = "$($publicBase.TrimEnd('/'))/mcp/$mcpPathToken"
$instructionPath = Join-Path $ProjectRoot "PDP-ONE-CHATGPT-CONNECTION.txt"
$instructions = @"
PDP One - ChatGPT connection
================================

Name: PDP One
Description: Private trial connector for contracts, receivables and management analysis.
MCP URL: $mcpEndpoint
Authentication: No Authentication
Tunnel: $provider

ChatGPT Business setup (one-time manual confirmation):
1. Open https://chatgpt.com/plugins
2. Enable Developer mode for the workspace if it is not enabled.
3. Create a new app/connector.
4. Enter the name, description and MCP URL shown above.
5. Choose No Authentication, scan the tools, and confirm Create/Save.

The URL works only while this window and Rancher Desktop remain open.
Closing this window revokes the temporary internet connection.
No OpenAI API key is used by PDP One.
"@
[IO.File]::WriteAllText($instructionPath, $instructions, [Text.UTF8Encoding]::new($false))
Set-Clipboard -Value $mcpEndpoint

Write-Host "" 
Write-Host "PDP One is connected to the internet." -ForegroundColor Green
Write-Host "MCP URL (already copied to clipboard):" -ForegroundColor Cyan
Write-Host $mcpEndpoint -ForegroundColor White
Write-Host "" 
Write-Host "ChatGPT setup instructions were opened in Notepad." -ForegroundColor Green
Write-Host "Keep this window open. Press Ctrl+C to revoke the link." -ForegroundColor Yellow
Start-Process notepad.exe -ArgumentList $instructionPath
Start-Process "https://chatgpt.com/plugins"

try {
    Wait-Process -Id $tunnelProcess.Id
} finally {
    if ($null -ne $tunnelProcess -and -not $tunnelProcess.HasExited) {
        Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
