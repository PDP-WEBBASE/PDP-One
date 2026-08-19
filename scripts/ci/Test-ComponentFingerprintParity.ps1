#requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-PDPOneEqual([string]$Actual, [string]$Expected, [string]$Label) {
    if (-not [string]::Equals($Actual, $Expected, [System.StringComparison]::Ordinal)) {
        throw "Component fingerprint parity failed for $Label."
    }
}

function Get-PDPOneNodeFingerprints([string]$SourceRoot) {
    $nodeScript = Join-Path $SourceRoot 'scripts\ci\component-fingerprints.mjs'
    if (-not (Test-Path -LiteralPath $nodeScript)) { throw 'Node component fingerprint planner is missing.' }
    $output = @(& node $nodeScript --repo-root $SourceRoot)
    if ($LASTEXITCODE -ne 0) { throw 'Node component fingerprint planner failed.' }
    $fingerprints = @{}
    foreach ($line in $output) {
        $text = [string]$line
        if ($text -match '^(backend|mcp|web)_fingerprint=([0-9a-f]{64})$') {
            $fingerprints[$matches[1]] = $matches[2]
        }
    }
    return $fingerprints
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js is unavailable on the Windows compatibility runner.' }
if ($env:PDP_PR_HEAD_SHA -notmatch '^[0-9a-f]{40}$') { throw 'Exact PR head SHA is missing for zipball parity.' }
if ([string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) { throw 'GitHub Actions token is missing for exact zipball parity.' }

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('pdp-one-component-parity-' + [Guid]::NewGuid().ToString('N'))
$archive = Join-Path $temporary 'github-source.zip'
$extractRoot = Join-Path $temporary 'source'
New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null

try {
    $headers = @{
        Authorization = "Bearer $($env:GITHUB_TOKEN)"
        Accept = 'application/vnd.github+json'
        'X-GitHub-Api-Version' = '2022-11-28'
        'User-Agent' = 'PDP-One-Component-Parity'
    }
    $url = "https://api.github.com/repos/PDP-WEBBASE/PDP-One/zipball/$($env:PDP_PR_HEAD_SHA)"
    Invoke-WebRequest -UseBasicParsing -Uri $url -Headers $headers -OutFile $archive -TimeoutSec 120
    if (-not (Test-Path -LiteralPath $archive) -or (Get-Item -LiteralPath $archive).Length -le 0) {
        throw 'Exact GitHub source zipball is empty.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot -Force
    $sourceDirectory = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
    if ($null -eq $sourceDirectory) { throw 'Exact GitHub source zipball did not contain a source directory.' }
    $zipballRoot = $sourceDirectory.FullName

    $checkoutFingerprints = Get-PDPOneNodeFingerprints -SourceRoot $repositoryRoot
    $zipballNodeFingerprints = Get-PDPOneNodeFingerprints -SourceRoot $zipballRoot
    $releaseManifestScript = Join-Path $zipballRoot 'scripts\windows\PDPOne.ReleaseManifest.ps1'
    if (-not (Test-Path -LiteralPath $releaseManifestScript)) { throw 'PowerShell release-manifest helper is missing from the exact zipball.' }
    . $releaseManifestScript

    foreach ($component in @('backend', 'mcp', 'web')) {
        $checkoutFingerprint = [string]$checkoutFingerprints[$component]
        $zipballNodeFingerprint = [string]$zipballNodeFingerprints[$component]
        $powershellFingerprint = Get-PDPOneComponentFingerprint -SourceRoot $zipballRoot -Component $component
        foreach ($value in @($checkoutFingerprint, $zipballNodeFingerprint, $powershellFingerprint)) {
            if ($value -notmatch '^[0-9a-f]{64}$') { throw "A fingerprint was not captured for $component." }
        }
        Write-Host ("component_fingerprint_checkout {0}={1}" -f $component, $checkoutFingerprint)
        Write-Host ("component_fingerprint_zipball_node {0}={1}" -f $component, $zipballNodeFingerprint)
        Write-Host ("component_fingerprint_zipball_ps51 {0}={1}" -f $component, $powershellFingerprint)
        Assert-PDPOneEqual $powershellFingerprint $zipballNodeFingerprint "$component Node-vs-PowerShell zipball"
        Assert-PDPOneEqual $zipballNodeFingerprint $checkoutFingerprint "$component checkout-vs-GitHub-zipball"
    }

    Write-Host 'Linux/Windows planner semantics and the exact GitHub deployment zipball fingerprints are equivalent.' -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
