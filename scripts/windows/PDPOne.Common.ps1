#requires -Version 5.1
Set-StrictMode -Version Latest

function New-PDPOneSecret([int]$Bytes = 36) {
    $buffer = New-Object byte[] $Bytes
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Get-PDPOneEnvValue([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $match = Select-String -LiteralPath $Path -Pattern "^$([regex]::Escape($Name))=(.*)$" | Select-Object -Last 1
    if ($null -eq $match) { return $null }
    return $match.Matches[0].Groups[1].Value.Trim()
}

function Set-PDPOneEnvValue([string]$Path, [string]$Name, [string]$Value) {
    $content = [IO.File]::ReadAllText($Path)
    $pattern = "(?m)^$([regex]::Escape($Name))=.*$"
    if ([regex]::IsMatch($content, $pattern)) {
        $content = [regex]::Replace($content, $pattern, "$Name=$Value")
    } else {
        $content = $content.TrimEnd() + "`r`n$Name=$Value`r`n"
    }
    [IO.File]::WriteAllText($Path, $content, [Text.UTF8Encoding]::new($false))
}

function Get-PDPOneProjectRoot {
    $sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    if (Test-Path -LiteralPath (Join-Path $sourceRoot ".env")) { return $sourceRoot }

    $rootFile = Join-Path $env:LOCALAPPDATA "PDP-One\installation-root.txt"
    if (Test-Path -LiteralPath $rootFile) {
        $savedRoot = ([IO.File]::ReadAllText($rootFile)).Trim()
        if ($savedRoot -and (Test-Path -LiteralPath (Join-Path $savedRoot ".env"))) {
            return (Resolve-Path -LiteralPath $savedRoot).Path
        }
    }
    throw "PDP One installation was not found. Run the installer first."
}

function Test-PDPOneDockerEngine {
    cmd.exe /d /c "docker info >nul 2>&1"
    return $LASTEXITCODE -eq 0
}

function Start-PDPOneRancherDesktop([int]$TimeoutSeconds = 300) {
    if (Test-PDPOneDockerEngine) { return }
    $rdctl = Get-Command rdctl.exe -ErrorAction SilentlyContinue
    if ($rdctl) { & $rdctl.Source start --application.start-in-background *> $null }
    if (-not (Get-Process -Name "Rancher Desktop" -ErrorAction SilentlyContinue)) {
        $candidates = @(
            "C:\Program Files\Rancher Desktop\Rancher Desktop.exe",
            (Join-Path $env:LOCALAPPDATA "Programs\Rancher Desktop\Rancher Desktop.exe")
        )
        $desktop = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $desktop) { throw "Rancher Desktop executable was not found." }
        Start-Process -FilePath $desktop | Out-Null
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PDPOneDockerEngine) { return }
        Start-Sleep -Seconds 3
    }
    throw "Docker did not become ready within $TimeoutSeconds seconds."
}

function Assert-PDPOneConfiguration([string]$ProjectRoot) {
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) { throw "The secure .env file is missing." }
    foreach ($name in @("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "PDP_MCP_TOKEN", "PDP_MCP_PATH_TOKEN")) {
        $value = Get-PDPOneEnvValue -Path $envPath -Name $name
        if ([string]::IsNullOrWhiteSpace($value) -or $value -match '^(change-me|replace-with-|trial-path-not-configured)') {
            throw "Required setting $name is missing or still uses a placeholder."
        }
    }
    return $envPath
}

function Get-PDPOneTokenFingerprint([string]$Token) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Token)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Test-PDPOneTokenContinuity([string]$ProjectRoot, [switch]$AcceptCurrent) {
    $envPath = Join-Path $ProjectRoot ".env"
    $token = Get-PDPOneEnvValue -Path $envPath -Name "PDP_MCP_PATH_TOKEN"
    if (-not $token) { throw "PDP_MCP_PATH_TOKEN is missing." }
    $fingerprint = Get-PDPOneTokenFingerprint -Token $token
    $stateDir = Join-Path $ProjectRoot "work\state"
    $statePath = Join-Path $stateDir "mcp-path-token.sha256"
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    if (-not (Test-Path -LiteralPath $statePath) -or $AcceptCurrent) {
        [IO.File]::WriteAllText($statePath, $fingerprint, [Text.UTF8Encoding]::new($false))
        return $true
    }
    $expected = ([IO.File]::ReadAllText($statePath)).Trim()
    # This is a one-way fingerprint, not a secret. Ordinal comparison keeps
    # the helper compatible with Windows PowerShell 5.1 / .NET Framework.
    return [string]::Equals($expected, $fingerprint, [StringComparison]::Ordinal)
}

function Wait-PDPOneUrl([string]$Url, [int]$TimeoutSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 8
            if ($response.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

function ConvertTo-PDPOneResponseText($Content) {
    if ($null -eq $Content) { return "" }
    if ($Content -is [byte[]]) { return [Text.Encoding]::UTF8.GetString($Content) }
    return [string]$Content
}

function New-PDPOneCodePointString([int[]]$Points) {
    return -join @($Points | ForEach-Object { [char]$_ })
}

function Test-PDPOneExplicitDeploymentApproval([string]$Text) {
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    $normalized = $Text.Normalize([Text.NormalizationForm]::FormKC).Trim()
    foreach ($codePoint in @(0xFEFF, 0x200C, 0x200E, 0x200F)) {
        $normalized = $normalized.Replace([string][char]$codePoint, "")
    }
    $normalized = $normalized.Replace([char]0x064A, [char]0x06CC).Replace([char]0x0643, [char]0x06A9)
    $normalized = [regex]::Replace($normalized, '\s+', ' ')
    $withHamza = New-PDPOneCodePointString @(0x062A,0x0623,0x06CC,0x06CC,0x062F,0x0020,0x0627,0x0633,0x062A,0x060C,0x0020,0x0044,0x0065,0x0070,0x006C,0x006F,0x0079,0x0020,0x06A9,0x0646)
    $withoutHamza = New-PDPOneCodePointString @(0x062A,0x0627,0x06CC,0x06CC,0x062F,0x0020,0x0627,0x0633,0x062A,0x060C,0x0020,0x0044,0x0065,0x0070,0x006C,0x006F,0x0079,0x0020,0x06A9,0x0646)
    return $normalized -in @($withHamza, $withoutHamza, 'APPROVE DEPLOY')
}

function Protect-PDPOneSecretFile([string]$InputPath, [string]$OutputPath) {
    $bytes = [IO.File]::ReadAllBytes($InputPath)
    $protected = [Security.Cryptography.ProtectedData]::Protect($bytes, $null, 'CurrentUser')
    [IO.File]::WriteAllBytes($OutputPath, $protected)
}

function Unprotect-PDPOneSecretFile([string]$InputPath, [string]$OutputPath) {
    $bytes = [IO.File]::ReadAllBytes($InputPath)
    $plain = [Security.Cryptography.ProtectedData]::Unprotect($bytes, $null, 'CurrentUser')
    [IO.File]::WriteAllBytes($OutputPath, $plain)
}

function ConvertTo-PDPOneRedactedText([string]$Text) {
    if ($null -eq $Text) { return "" }
    $result = $Text
    $secretNames = 'PDP_MCP_TOKEN|PDP_MCP_PATH_TOKEN|POSTGRES_PASSWORD|DATABASE_URL|DJANGO_SECRET_KEY|PDP_DEPLOYMENT_AGENT_SIGNING_KEY|GITHUB_TOKEN|TAILSCALE_AUTHKEY|Authorization'
    $result = [regex]::Replace($result, "(?im)^($secretNames)\s*[:=].*$", '$1=[REDACTED]')
    $result = [regex]::Replace($result, '(?i)(Bearer\s+)[A-Za-z0-9._~+\-/=]+', '$1[REDACTED]')
    $result = [regex]::Replace($result, '(https://[^\s/]+/mcp/)[A-Za-z0-9_-]+', '$1[REDACTED]')
    $result = [regex]::Replace($result, '(?i)\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|tskey-[A-Za-z0-9_-]{20,})\b', '[REDACTED]')
    $result = [regex]::Replace($result, '(?i)("(?:token|password|secret|signing_key|authorization)"\s*:\s*")[^"]+(")', '$1[REDACTED]$2')
    return $result
}
