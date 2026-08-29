#requires -Version 5.1
Set-StrictMode -Version Latest

function Get-PDPOneImageMode {
    param([Parameter(Mandatory = $true)][string]$SourceRoot)
    $modePath = Join-Path $SourceRoot "release\component-image-mode.json"
    if (-not (Test-Path -LiteralPath $modePath)) { return "legacy-exact-sha" }
    try {
        $mode = Get-Content -LiteralPath $modePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$mode.mode -eq "content-addressed-v1") { return "content-addressed-v1" }
    } catch { }
    return "legacy-exact-sha"
}

function Get-PDPOneComponentContextConfig {
    param([Parameter(Mandatory = $true)][string]$SourceRoot)
    $path = Join-Path $SourceRoot "release\component-contexts.json"
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Component context policy is missing from the exact source commit."
    }
    return (Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Test-PDPOneComponentPathExcluded {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)]$ComponentConfig
    )
    $normalized = $RelativePath.Replace('\', '/')
    foreach ($prefix in @($ComponentConfig.exclude_prefixes)) {
        $value = [string]$prefix
        if ($value -and $normalized.StartsWith($value, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    foreach ($file in @($ComponentConfig.exclude_files)) {
        if ($normalized.Equals([string]$file, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    foreach ($suffix in @($ComponentConfig.exclude_suffixes)) {
        $value = [string]$suffix
        if ($value -and $normalized.EndsWith($value, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    foreach ($namePrefix in @($ComponentConfig.exclude_name_prefixes)) {
        $leaf = [System.IO.Path]::GetFileName($normalized)
        $value = [string]$namePrefix
        if ($value -and $leaf.StartsWith($value, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

function Get-PDPOneComponentFingerprint {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)][ValidateSet("backend", "mcp", "web")][string]$Component
    )
    $root = (Resolve-Path -LiteralPath $SourceRoot).Path.TrimEnd('\', '/')
    $policy = Get-PDPOneComponentContextConfig -SourceRoot $root
    $config = $policy.components.$Component
    if ($null -eq $config) { throw "Component context policy does not define '$Component'." }

    $componentRoot = if ([string]$config.root -eq ".") { $root } else { Join-Path $root ([string]$config.root) }
    if (-not (Test-Path -LiteralPath $componentRoot)) { throw "Component context root is missing for '$Component'." }

    $pathMap = @{}
    foreach ($file in @(Get-ChildItem -LiteralPath $componentRoot -File -Recurse -Force -ErrorAction Stop)) {
        $relative = $file.FullName.Substring($root.Length).TrimStart([char[]]"\/").Replace('\', '/')
        if (Test-PDPOneComponentPathExcluded -RelativePath $relative -ComponentConfig $config) { continue }
        $pathMap[$relative] = $file.FullName
    }

    [string[]]$paths = @($pathMap.Keys)
    [Array]::Sort($paths, [System.StringComparer]::Ordinal)
    $builder = New-Object System.Text.StringBuilder
    foreach ($relative in $paths) {
        $hash = (Get-FileHash -LiteralPath $pathMap[$relative] -Algorithm SHA256).Hash.ToLowerInvariant()
        [void]$builder.Append($relative)
        [void]$builder.Append("`t")
        [void]$builder.Append($hash)
        [void]$builder.Append("`n")
    }

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($builder.ToString())
        $digest = $sha.ComputeHash($bytes)
        return (($digest | ForEach-Object { $_.ToString("x2") }) -join "")
    } finally {
        $sha.Dispose()
    }
}

function Get-PDPOneComponentImageReference {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("backend", "mcp", "web")][string]$Component,
        [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$Fingerprint
    )
    return "ghcr.io/pdp-webbase/pdp-one-$Component`:content-$Fingerprint"
}

function Get-PDPOneReferenceEmbeddedRevision {
    param([string]$Image)
    if ([string]::IsNullOrWhiteSpace($Image)) { return "" }
    $match = [regex]::Match($Image, ':([0-9a-f]{40})$')
    if ($match.Success) { return $match.Groups[1].Value }
    return ""
}

function Get-PDPOneImageLabelValue {
    param(
        [Parameter(Mandatory = $true)][string]$Image,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $template = "{{ index .Config.Labels `"$Name`" }}"
    $value = [string](& docker image inspect --format $template $Image 2>$null | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value) -or $value -eq "<no value>") { return "" }
    return $value.Trim()
}

function Get-PDPOneImageRepositoryDigest {
    param([Parameter(Mandatory = $true)][string]$Image)
    $digestsJson = [string](& docker image inspect --format '{{json .RepoDigests}}' $Image 2>$null | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($digestsJson)) { return "" }
    try {
        $digests = @($digestsJson | ConvertFrom-Json)
        $repository = $Image.Substring(0, $Image.LastIndexOf(':'))
        foreach ($digest in $digests) {
            $value = [string]$digest
            if ($value.StartsWith($repository + "@sha256:", [System.StringComparison]::OrdinalIgnoreCase)) { return $value }
        }
        if ($digests.Count -gt 0) { return [string]$digests[0] }
    } catch { }
    return ""
}

function Assert-PDPOneReleaseImageIdentity {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("backend", "mcp", "web")][string]$Component,
        [Parameter(Mandatory = $true)][string]$Image,
        [Parameter(Mandatory = $true)][ValidateSet("legacy-exact-sha", "content-addressed-v1")][string]$ImageMode,
        [string]$ExpectedRevision = "",
        [string]$ExpectedFingerprint = ""
    )
    if ($ImageMode -eq "content-addressed-v1") {
        if ($ExpectedFingerprint -notmatch '^[0-9a-f]{64}$') { throw "Expected fingerprint is invalid for $Component." }
        $actual = Get-PDPOneImageLabelValue -Image $Image -Name "io.pdpone.component.fingerprint"
        if ($actual -ne $ExpectedFingerprint) { throw "Image fingerprint mismatch for $Component." }
        $declaredComponent = Get-PDPOneImageLabelValue -Image $Image -Name "io.pdpone.component"
        if ($declaredComponent -ne $Component) { throw "Image component label mismatch for $Component." }
        return
    }

    if ($ExpectedRevision -notmatch '^[0-9a-f]{40}$') { throw "Expected revision is invalid for $Component." }
    $actualRevision = Get-PDPOneImageLabelValue -Image $Image -Name "org.opencontainers.image.revision"
    if ($actualRevision -ne $ExpectedRevision) { throw "Image revision mismatch for $Component." }
}

function Get-PDPOneChangedFilePaths {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Headers,
        [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$PreviousCommit,
        [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$CommitSha
    )
    $url = "https://api.github.com/repos/PDP-WEBBASE/PDP-One/compare/$PreviousCommit...$CommitSha"
    $comparison = Invoke-RestMethod -Uri $url -Headers $Headers -TimeoutSec 45
    $paths = @()
    foreach ($file in @($comparison.files)) {
        if ($null -ne $file.filename) { $paths += [string]$file.filename }
    }
    return @($paths)
}

function Get-PDPOneChangeScope {
    param([string[]]$Paths = @(), [switch]$ConservativeFullStack)
    $backend = $false
    $mcp = $false
    $web = $false
    $hostChanged = $false
    $topology = [bool]$ConservativeFullStack
    $runtimeRelevant = [bool]$ConservativeFullStack

    foreach ($raw in @($Paths)) {
        $path = ([string]$raw).Replace('\', '/')
        if (-not $path) { continue }

        if ($path -eq "docker-compose.yml" -or $path -eq "HOST-RUNTIME-SOURCE" -or $path -eq "release/component-image-mode.json" -or $path.StartsWith("infra/nginx/", [System.StringComparison]::OrdinalIgnoreCase)) {
            $topology = $true
            $runtimeRelevant = $true
        }
        if ($path.StartsWith("backend/", [System.StringComparison]::OrdinalIgnoreCase)) { $backend = $true; $runtimeRelevant = $true }
        if ($path.StartsWith("services/pdp_mcp/", [System.StringComparison]::OrdinalIgnoreCase)) { $mcp = $true; $runtimeRelevant = $true }
        if (
            $path.StartsWith("app/", [System.StringComparison]::OrdinalIgnoreCase) -or
            $path.StartsWith("components/", [System.StringComparison]::OrdinalIgnoreCase) -or
            $path.StartsWith("lib/", [System.StringComparison]::OrdinalIgnoreCase) -or
            $path.StartsWith("public/", [System.StringComparison]::OrdinalIgnoreCase) -or
            $path.StartsWith("styles/", [System.StringComparison]::OrdinalIgnoreCase) -or
            $path -in @("package.json", "package-lock.json", "tsconfig.json", "eslint.config.mjs", "vinext.config.ts", "next.config.js", ".dockerignore", "infra/docker/web.Dockerfile", "scripts/build-verified.sh", "scripts/sites-env.sh", "scripts/install-ci.sh")
        ) { $web = $true; $runtimeRelevant = $true }
        if ($path.StartsWith("scripts/windows/", [System.StringComparison]::OrdinalIgnoreCase) -or $path.EndsWith(".bat", [System.StringComparison]::OrdinalIgnoreCase) -or $path -eq "HOST-RUNTIME-SOURCE") {
            $hostChanged = $true
            $runtimeRelevant = $true
        }
    }

    if ($topology) { $backend = $true; $mcp = $true; $web = $true }
    $services = @()
    if ($backend) { $services += "backend" }
    if ($mcp) { $services += "mcp" }
    if ($web) { $services += "web" }

    $profile = if ($topology) { "full" } elseif ($backend) { "backend" } elseif ($mcp) { "mcp" } elseif ($web) { "web" } elseif ($hostChanged) { "host" } else { "none" }
    return [pscustomobject][ordered]@{
        backend = $backend
        mcp = $mcp
        web = $web
        host = $hostChanged
        topology_sensitive = $topology
        runtime_relevant = $runtimeRelevant
        changed_services = @($services)
        health_profile = $profile
        paths = @($Paths)
    }
}

function Get-PDPOneManifestImageReferences {
    param([string]$ManifestPath)
    $references = @()
    if (-not $ManifestPath -or -not (Test-Path -LiteralPath $ManifestPath)) { return @() }
    try {
        $manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($component in @("backend", "mcp", "web")) {
            $entry = $manifest.services.$component
            if ($null -ne $entry -and $entry.reference) { $references += [string]$entry.reference }
        }
    } catch { }
    return @($references | Select-Object -Unique)
}

function Write-PDPOneReleaseManifest {
    param(
        [Parameter(Mandatory = $true)][string]$AgentRoot,
        [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ReleaseCommit,
        [Parameter(Mandatory = $true)][string]$DeploymentId,
        [Parameter(Mandatory = $true)][ValidateSet("legacy-exact-sha", "content-addressed-v1")][string]$ImageMode,
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Images,
        [Parameter(Mandatory = $true)][System.Collections.IDictionary]$Fingerprints,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$ChangedServices,
        [Parameter(Mandatory = $true)][string]$HealthProfile
    )
    $manifestRoot = Join-Path $AgentRoot "state\release-manifests"
    New-Item -ItemType Directory -Force -Path $manifestRoot | Out-Null
    $manifestPath = Join-Path $manifestRoot ($ReleaseCommit + ".json")
    $services = [ordered]@{}
    foreach ($component in @("backend", "mcp", "web")) {
        $reference = [string]$Images[$component]
        $services[$component] = [ordered]@{
            reference = $reference
            repository_digest = Get-PDPOneImageRepositoryDigest -Image $reference
            source_revision = Get-PDPOneImageLabelValue -Image $reference -Name "org.opencontainers.image.revision"
            component_fingerprint = [string]$Fingerprints[$component]
            changed_in_release = ($component -in $ChangedServices)
        }
    }
    [ordered]@{
        schema = "pdp-one.release-manifest.v1"
        release_commit = $ReleaseCommit
        deployment_id = $DeploymentId
        image_mode = $ImageMode
        health_profile = $HealthProfile
        created_at = [DateTime]::UtcNow.ToString("o")
        services = $services
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    return $manifestPath
}
