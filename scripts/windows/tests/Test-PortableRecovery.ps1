#requires -Version 7.2
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $root 'PDPOne.Common.ps1')
. (Join-Path $root 'PDPOne.PortableCrypto.ps1')

function Assert-True([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('pdp-one-portable-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary -Force | Out-Null
try {
    $source = Join-Path $temporary 'source.bin'
    $encrypted = Join-Path $temporary 'backup.pdpone'
    $decrypted = Join-Path $temporary 'decrypted.bin'
    $bytes = New-Object byte[] 131071
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    [IO.File]::WriteAllBytes($source, $bytes)
    $passphrase = ConvertTo-SecureString 'correct horse battery staple' -AsPlainText -Force
    Protect-PDPOnePortableFile -SourcePath $source -DestinationPath $encrypted -Passphrase $passphrase -Iterations 200000
    Unprotect-PDPOnePortableFile -SourcePath $encrypted -DestinationPath $decrypted -Passphrase $passphrase
    Assert-True ((Get-FileHash $source -Algorithm SHA256).Hash -eq (Get-FileHash $decrypted -Algorithm SHA256).Hash) 'Portable crypto round-trip failed.'

    $wrongRejected = $false
    try { Unprotect-PDPOnePortableFile -SourcePath $encrypted -DestinationPath (Join-Path $temporary 'wrong.bin') -Passphrase (ConvertTo-SecureString 'wrong passphrase value' -AsPlainText -Force) } catch { $wrongRejected = $true }
    Assert-True $wrongRejected 'Wrong portable passphrase was not rejected.'

    $tampered = Join-Path $temporary 'tampered.pdpone'
    Copy-Item $encrypted $tampered
    $tamperedBytes = [IO.File]::ReadAllBytes($tampered)
    $tamperedBytes[80] = $tamperedBytes[80] -bxor 0x01
    [IO.File]::WriteAllBytes($tampered, $tamperedBytes)
    $tamperRejected = $false
    try { Unprotect-PDPOnePortableFile -SourcePath $tampered -DestinationPath (Join-Path $temporary 'tampered.bin') -Passphrase $passphrase } catch { $tamperRejected = $true }
    Assert-True $tamperRejected 'Tampered portable backup was not rejected.'

    $approved = New-PDPOneCodePointString @(0x062A,0x0623,0x06CC,0x06CC,0x062F,0x0020,0x0627,0x0633,0x062A,0x060C,0x0020,0x0044,0x0065,0x0070,0x006C,0x006F,0x0079,0x0020,0x06A9,0x0646)
    Assert-True (Test-PDPOneExplicitDeploymentApproval $approved) 'Unicode deployment approval was rejected.'
    Assert-True (Test-PDPOneExplicitDeploymentApproval 'APPROVE DEPLOY') 'ASCII deployment approval was rejected.'
    Assert-True (-not (Test-PDPOneExplicitDeploymentApproval 'APPROVE SOMETHING ELSE')) 'Invalid deployment approval was accepted.'

    $fakeGithubToken = 'gh' + 'p_' + ('1' * 30)
    $redacted = ConvertTo-PDPOneRedactedText ("Authorization: Bearer " + $fakeGithubToken)
    Assert-True ($redacted -notmatch 'ghp_') 'Secret redaction failed.'
    Assert-True ((ConvertTo-PDPOneResponseText ([Text.Encoding]::UTF8.GetBytes('healthy'))) -eq 'healthy') 'Byte response decoding failed.'

    $portableBackupScript = [IO.File]::ReadAllText((Join-Path $root 'New-PDPOnePortableBackup.ps1'))
    Assert-True ($portableBackupScript.Contains("D:\BackUp PDP-0NE-14050429-01")) 'The required automatic local archive path is missing.'
    Assert-True ($portableBackupScript.Contains('copies_sha256_verified')) 'Portable backup copies are not recorded as hash-verified.'
    Assert-True ($portableBackupScript.Contains('failed-safely')) 'Portable backup does not emit a safe failure report.'
    Write-Host 'Portable recovery, approval compatibility, and redaction tests passed.' -ForegroundColor Green
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue }
