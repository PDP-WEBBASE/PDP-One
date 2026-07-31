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
    Assert-True ($portableBackupScript.Contains('$backupOutput = @(& $baseBackupScript')) 'Base backup is not invoked safely in-process.'
    Assert-True (-not [regex]::IsMatch($portableBackupScript, 'New-PDPOneBackup\.ps1[^\r\n]*2>&1')) 'Native stderr can still be promoted to a terminating wrapper error.'

    $baseBackupScript = [IO.File]::ReadAllText((Join-Path $root 'New-PDPOneBackup.ps1'))
    $restoreScript = [IO.File]::ReadAllText((Join-Path $root 'Test-PDPOneBackupRestore.ps1'))
    $activationScript = [IO.File]::ReadAllText((Join-Path $root 'Activate-PDPOneStandardMode.ps1'))
    $stableMarkerPath = Join-Path (Resolve-Path (Join-Path $root '..\..')).Path 'release\stable-mode.json'
    Assert-True (Test-Path -LiteralPath $stableMarkerPath) 'Stable release marker is missing.'
    $stableMarker = Get-Content -LiteralPath $stableMarkerPath -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-True ([string]$stableMarker.change_management_mode -eq 'standard') 'Stable release marker does not request standard mode.'
    Assert-True (-not [bool]$stableMarker.trial_mode) 'Stable release marker still enables trial mode.'
    Assert-True ([string]$stableMarker.external_backup_root -eq 'D:\BackUp PDP-0NE-14050429-01') 'Stable release external backup path changed.'
    Assert-True ($baseBackupScript.Contains('stable_release_requested')) 'Base backup is not bound to the stable release marker.'
    Assert-True ($baseBackupScript.Contains('external_backup_copied')) 'Base backup does not record the external mirror.'
    Assert-True ($restoreScript.Contains('Activate-PDPOneStandardMode.ps1')) 'Restore verification does not gate standard-mode activation.'
    Assert-True ($restoreScript.Contains('Sync-PDPOneVerifiedExternalBackup')) 'Verified backup is not resynchronized externally.'
    Assert-True ($activationScript.Contains('PDP_CHANGE_MANAGEMENT_MODE') -and $activationScript.Contains('standard')) 'Standard change management is not activated.'
    Assert-True ($activationScript.Contains('PDP_TRIAL_MODE') -and $activationScript.Contains('false')) 'Trial mode is not disabled.'
    Assert-True ($activationScript.Contains('Restore-PDPOneEnvSetting')) 'Stable-mode activation has no environment rollback.'
    Assert-True ($activationScript.Contains('Register-PDPOneStartupTask.ps1')) 'Stable release does not re-register Windows startup tasks.'
    Assert-True (-not [regex]::IsMatch(($baseBackupScript + $restoreScript + $activationScript), 'docker\s+(compose\s+down\s+-v|volume\s+rm|system\s+prune.*--volumes)', [Text.RegularExpressions.RegexOptions]::IgnoreCase)) 'Stable release scripts contain a destructive volume operation.'

    Write-Host 'Portable recovery, stable release, approval compatibility, and redaction tests passed.' -ForegroundColor Green
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue }
