#requires -Version 5.1
Set-StrictMode -Version Latest

$script:PDPOnePortableMagic = [Text.Encoding]::ASCII.GetBytes('PDP1ENC1')
$script:PDPOnePortableTagLength = 32

function Get-PDPOnePlainTextFromSecureString([Security.SecureString]$SecureValue) {
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    }
}

function New-PDPOneRandomBytes([int]$Length) {
    $bytes = New-Object byte[] $Length
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return $bytes
}

function Get-PDPOnePortableKeys([string]$Password, [byte[]]$Salt, [int]$Iterations) {
    if ($Iterations -lt 200000) { throw 'Portable-backup KDF iterations are below the safe minimum.' }
    $kdf = [Security.Cryptography.Rfc2898DeriveBytes]::new($Password, $Salt, $Iterations, [Security.Cryptography.HashAlgorithmName]::SHA256)
    try { $material = $kdf.GetBytes(64) } finally { $kdf.Dispose() }
    $encryptionKey = New-Object byte[] 32
    $authenticationKey = New-Object byte[] 32
    [Array]::Copy($material, 0, $encryptionKey, 0, 32)
    [Array]::Copy($material, 32, $authenticationKey, 0, 32)
    [Array]::Clear($material, 0, $material.Length)
    return @{ EncryptionKey = $encryptionKey; AuthenticationKey = $authenticationKey }
}

function Test-PDPOneConstantTimeEqual([byte[]]$Left, [byte[]]$Right) {
    if ($null -eq $Left -or $null -eq $Right -or $Left.Length -ne $Right.Length) { return $false }
    $difference = 0
    for ($index = 0; $index -lt $Left.Length; $index++) { $difference = $difference -bor ($Left[$index] -bxor $Right[$index]) }
    return $difference -eq 0
}

function Protect-PDPOnePortableFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$DestinationPath,
        [Parameter(Mandatory = $true)][Security.SecureString]$Passphrase,
        [int]$Iterations = 310000
    )

    $source = Get-Item -LiteralPath $SourcePath -ErrorAction Stop
    if ($source.Length -le 0) { throw 'Portable-backup source is empty.' }
    $password = Get-PDPOnePlainTextFromSecureString $Passphrase
    if ($password.Length -lt 14) { throw 'Portable-backup passphrase must contain at least 14 characters.' }
    $salt = New-PDPOneRandomBytes 16
    $iv = New-PDPOneRandomBytes 16
    $keys = Get-PDPOnePortableKeys -Password $password -Salt $salt -Iterations $Iterations
    $temporary = "$DestinationPath.partial"
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue

    try {
        $headerStream = New-Object IO.MemoryStream
        $writer = New-Object IO.BinaryWriter($headerStream)
        try {
            $writer.Write([byte[]]$script:PDPOnePortableMagic)
            $writer.Write([int]1)
            $writer.Write([int]$Iterations)
            $writer.Write([int]$salt.Length)
            $writer.Write([int]$iv.Length)
            $writer.Write([long]$source.Length)
            $writer.Write([byte[]]$salt)
            $writer.Write([byte[]]$iv)
            $writer.Flush()
            $header = $headerStream.ToArray()
        } finally { $writer.Dispose(); $headerStream.Dispose() }

        $output = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $input = [IO.File]::OpenRead($source.FullName)
        $aes = [Security.Cryptography.Aes]::Create()
        try {
            $aes.KeySize = 256
            $aes.Mode = [Security.Cryptography.CipherMode]::CBC
            $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
            $aes.Key = $keys.EncryptionKey
            $aes.IV = $iv
            $output.Write($header, 0, $header.Length)
            $encryptor = $aes.CreateEncryptor()
            $crypto = New-Object Security.Cryptography.CryptoStream($output, $encryptor, [Security.Cryptography.CryptoStreamMode]::Write)
            try { $input.CopyTo($crypto); $crypto.FlushFinalBlock() } finally { $crypto.Dispose(); $encryptor.Dispose() }
        } finally { $input.Dispose(); $output.Dispose(); $aes.Dispose() }

        $signed = [IO.File]::OpenRead($temporary)
        $hmac = [Security.Cryptography.HMACSHA256]::new($keys.AuthenticationKey)
        try { $tag = $hmac.ComputeHash($signed) } finally { $hmac.Dispose(); $signed.Dispose() }
        $append = [IO.File]::Open($temporary, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $append.Write($tag, 0, $tag.Length) } finally { $append.Dispose() }
        Move-Item -LiteralPath $temporary -Destination $DestinationPath -Force
    } finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        [Array]::Clear($keys.EncryptionKey, 0, $keys.EncryptionKey.Length)
        [Array]::Clear($keys.AuthenticationKey, 0, $keys.AuthenticationKey.Length)
        $password = $null
    }
}

function Unprotect-PDPOnePortableFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)][string]$DestinationPath,
        [Parameter(Mandatory = $true)][Security.SecureString]$Passphrase
    )

    $source = Get-Item -LiteralPath $SourcePath -ErrorAction Stop
    if ($source.Length -lt 128) { throw 'Portable backup is truncated.' }
    $readerStream = [IO.File]::OpenRead($source.FullName)
    $reader = New-Object IO.BinaryReader($readerStream)
    try {
        $magic = $reader.ReadBytes(8)
        if (-not (Test-PDPOneConstantTimeEqual $magic $script:PDPOnePortableMagic)) { throw 'Portable backup format is invalid.' }
        $version = $reader.ReadInt32()
        $iterations = $reader.ReadInt32()
        $saltLength = $reader.ReadInt32()
        $ivLength = $reader.ReadInt32()
        $plainLength = $reader.ReadInt64()
        if ($version -ne 1 -or $saltLength -ne 16 -or $ivLength -ne 16 -or $plainLength -le 0) { throw 'Portable backup header is invalid.' }
        $salt = $reader.ReadBytes($saltLength)
        $iv = $reader.ReadBytes($ivLength)
        $headerLength = $readerStream.Position
    } finally { $reader.Dispose(); $readerStream.Dispose() }

    $password = Get-PDPOnePlainTextFromSecureString $Passphrase
    $keys = Get-PDPOnePortableKeys -Password $password -Salt $salt -Iterations $iterations
    $signedLength = $source.Length - $script:PDPOnePortableTagLength
    $cipherLength = $signedLength - $headerLength
    if ($cipherLength -le 0) { throw 'Portable backup ciphertext is missing.' }
    $buffer = New-Object byte[] 1048576

    try {
        $stream = [IO.File]::OpenRead($source.FullName)
        $hmac = [Security.Cryptography.HMACSHA256]::new($keys.AuthenticationKey)
        try {
            $remaining = $signedLength
            while ($remaining -gt 0) {
                $requested = [int][Math]::Min($buffer.Length, $remaining)
                $read = $stream.Read($buffer, 0, $requested)
                if ($read -le 0) { throw 'Portable backup ended during authentication.' }
                [void]$hmac.TransformBlock($buffer, 0, $read, $buffer, 0)
                $remaining -= $read
            }
            [void]$hmac.TransformFinalBlock((New-Object byte[] 0), 0, 0)
            $calculatedTag = $hmac.Hash
            $storedTag = New-Object byte[] $script:PDPOnePortableTagLength
            $readTag = $stream.Read($storedTag, 0, $storedTag.Length)
            if ($readTag -ne $storedTag.Length -or -not (Test-PDPOneConstantTimeEqual $calculatedTag $storedTag)) {
                throw 'Portable backup authentication failed. The passphrase is wrong or the file was modified.'
            }
        } finally { $hmac.Dispose(); $stream.Dispose() }

        $cipherPath = "$DestinationPath.cipher.$([Guid]::NewGuid().ToString('N'))"
        $temporaryOutput = "$DestinationPath.partial"
        try {
            $sourceStream = [IO.File]::OpenRead($source.FullName)
            $cipherStream = [IO.File]::Open($cipherPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try {
                $sourceStream.Position = $headerLength
                $remaining = $cipherLength
                while ($remaining -gt 0) {
                    $requested = [int][Math]::Min($buffer.Length, $remaining)
                    $read = $sourceStream.Read($buffer, 0, $requested)
                    if ($read -le 0) { throw 'Portable backup ciphertext is truncated.' }
                    $cipherStream.Write($buffer, 0, $read)
                    $remaining -= $read
                }
            } finally { $cipherStream.Dispose(); $sourceStream.Dispose() }

            $aes = [Security.Cryptography.Aes]::Create()
            $cipherInput = [IO.File]::OpenRead($cipherPath)
            $plainOutput = [IO.File]::Open($temporaryOutput, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try {
                $aes.KeySize = 256
                $aes.Mode = [Security.Cryptography.CipherMode]::CBC
                $aes.Padding = [Security.Cryptography.PaddingMode]::PKCS7
                $aes.Key = $keys.EncryptionKey
                $aes.IV = $iv
                $decryptor = $aes.CreateDecryptor()
                $crypto = New-Object Security.Cryptography.CryptoStream($cipherInput, $decryptor, [Security.Cryptography.CryptoStreamMode]::Read)
                try { $crypto.CopyTo($plainOutput) } finally { $crypto.Dispose(); $decryptor.Dispose() }
            } finally { $plainOutput.Dispose(); $cipherInput.Dispose(); $aes.Dispose() }
            if ((Get-Item -LiteralPath $temporaryOutput).Length -ne $plainLength) { throw 'Portable backup plaintext length is invalid.' }
            Move-Item -LiteralPath $temporaryOutput -Destination $DestinationPath -Force
        } finally {
            Remove-Item -LiteralPath $cipherPath -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $temporaryOutput -Force -ErrorAction SilentlyContinue
        }
    } finally {
        [Array]::Clear($buffer, 0, $buffer.Length)
        [Array]::Clear($keys.EncryptionKey, 0, $keys.EncryptionKey.Length)
        [Array]::Clear($keys.AuthenticationKey, 0, $keys.AuthenticationKey.Length)
        $password = $null
    }
}
