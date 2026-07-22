#requires -Version 5.1
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $root 'PDPOne.Common.ps1')

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

$temporary = Join-Path $env:TEMP ('pdp-one-ps51-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
try {
    $plain = Join-Path $temporary 'environment.env'
    $protected = Join-Path $temporary 'environment.dpapi'
    $restored = Join-Path $temporary 'environment.restored'
    [IO.File]::WriteAllText($plain, "PDP_ONE_TEST=value-$(New-PDPOneSecret 24)", [Text.UTF8Encoding]::new($false))

    Protect-PDPOneSecretFile -InputPath $plain -OutputPath $protected
    Assert-True ((Get-Item -LiteralPath $protected).Length -gt 0) 'DPAPI output is empty.'
    Unprotect-PDPOneSecretFile -InputPath $protected -OutputPath $restored
    Assert-True ((Get-FileHash -LiteralPath $plain -Algorithm SHA256).Hash -eq (Get-FileHash -LiteralPath $restored -Algorithm SHA256).Hash) 'Windows DPAPI round-trip failed.'

    Assert-True (Test-PDPOneExplicitDeploymentApproval 'APPROVE DEPLOY') 'Windows PowerShell approval compatibility failed.'
    $redacted = ConvertTo-PDPOneRedactedText 'POSTGRES_PASSWORD=not-a-real-password'
    Assert-True ($redacted -eq 'POSTGRES_PASSWORD=[REDACTED]') 'Windows PowerShell redaction compatibility failed.'

    # Regression: Django shell can print informational lines before the count.
    $sampleCountOutput = @('9 objects imported automatically.', '9,2')
    $sampleCountText = ($sampleCountOutput | Out-String)
    $sampleCountMatch = [regex]::Match($sampleCountText, '(?m)^\s*(\d+),(\d+)\s*$')
    Assert-True $sampleCountMatch.Success 'Multiline Django count output was not parsed.'
    Assert-True ($sampleCountMatch.Value.Trim() -eq '9,2') 'Parsed Django counts are incorrect.'

    # Regression: a switch passed to a child powershell.exe must be added as a
    # standalone token. -RestoreDatabase:$bool is transformed into text by 5.1.
    $updateScript = [IO.File]::ReadAllText((Join-Path $root 'Update-PDPOne.ps1'))
    Assert-True ($updateScript -notmatch '-RestoreDatabase:\$migrationAttempted') 'Unsafe Boolean switch forwarding returned.'
    Assert-True ($updateScript -match '\$rollbackArgs \+= "-RestoreDatabase"') 'Conditional rollback switch token is missing.'
    Assert-True ($updateScript -match 'manual-update') 'Manual diagnostic fallback identifier is missing.'

    Write-Host 'Windows PowerShell 5.1 compatibility tests passed.' -ForegroundColor Green
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
