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

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('pdp-one-component-parity-' + [Guid]::NewGuid().ToString('N'))
$archive = Join-Path $temporary 'source.zip'
$sourceRoot = Join-Path $temporary 'source'
New-Item -ItemType Directory -Path $sourceRoot -Force | Out-Null

try {
    Push-Location $repositoryRoot
    try {
        & git archive --format=zip --output=$archive HEAD
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $archive)) {
            throw 'Could not create the exact Git source archive for fingerprint parity.'
        }
    } finally {
        Pop-Location
    }

    Expand-Archive -LiteralPath $archive -DestinationPath $sourceRoot -Force
    $nodeScript = Join-Path $sourceRoot 'scripts\ci\component-fingerprints.mjs'
    $releaseManifestScript = Join-Path $sourceRoot 'scripts\windows\PDPOne.ReleaseManifest.ps1'
    if (-not (Test-Path -LiteralPath $nodeScript)) { throw 'Node component fingerprint planner is missing from the exact archive.' }
    if (-not (Test-Path -LiteralPath $releaseManifestScript)) { throw 'PowerShell release-manifest helper is missing from the exact archive.' }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js is unavailable on the Windows compatibility runner.' }

    $nodeOutput = @(& node $nodeScript --repo-root $sourceRoot)
    if ($LASTEXITCODE -ne 0) { throw 'Node component fingerprint planner failed on the exact archive.' }
    $nodeFingerprints = @{}
    foreach ($line in $nodeOutput) {
        $text = [string]$line
        if ($text -match '^(backend|mcp|web)_fingerprint=([0-9a-f]{64})$') {
            $nodeFingerprints[$matches[1]] = $matches[2]
        }
    }

    . $releaseManifestScript
    foreach ($component in @('backend', 'mcp', 'web')) {
        $nodeFingerprint = [string]$nodeFingerprints[$component]
        if ($nodeFingerprint -notmatch '^[0-9a-f]{64}$') { throw "Node fingerprint was not captured for $component." }
        $powershellFingerprint = Get-PDPOneComponentFingerprint -SourceRoot $sourceRoot -Component $component
        Assert-PDPOneEqual $powershellFingerprint $nodeFingerprint $component
        Write-Host ("component_fingerprint_parity {0}={1}" -f $component, $powershellFingerprint)
    }

    Write-Host 'Node and Windows PowerShell 5.1 component fingerprints match on canonical Git archive bytes.' -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
