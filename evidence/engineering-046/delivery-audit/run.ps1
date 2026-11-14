[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$JavaHome)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$auditProject = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$auditExpected = [ordered]@{
    'official-nf248' = 'dd47f6ae4daa4139b9ada9196d757db634a79ebdd7fa5f06083719d764285997'
    'official-nf265' = 'fbcb608fd5b2452f650c656bc930934ac4e4880addae4d24846faa5df5d9f63e'
}
function Get-AuditTime { [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('o') }
function Get-AuditHash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Assert-Audit([bool]$Condition, [string]$Message) { if (!$Condition) { throw $Message } }
function Write-AuditJson([string]$Name, $Data) {
    [IO.File]::WriteAllText((Join-Path $PSScriptRoot $Name), ($Data | ConvertTo-Json -Depth 30) + "`n", [Text.UTF8Encoding]::new($false))
}
function Get-AuditEntryHash($Entry) {
    $auditStream = $Entry.Open()
    try {
        $auditHasher = [Security.Cryptography.SHA256]::Create()
        try { [Convert]::ToHexString($auditHasher.ComputeHash($auditStream)).ToLowerInvariant() }
        finally { $auditHasher.Dispose() }
    } finally { $auditStream.Dispose() }
}
function Get-AuditEntryText($Entry) {
    $auditReader = [IO.StreamReader]::new($Entry.Open(), [Text.Encoding]::UTF8)
    try { $auditReader.ReadToEnd() } finally { $auditReader.Dispose() }
}
function Get-AuditBundle([string]$Target) {
    $auditJarName = "mtr-memory-saver-$Target-0.4.6.jar"
    $auditManifestName = "mtr-memory-saver-$Target-0.4.6.build.json"
    $auditJarPath = Join-Path $auditProject "build/libs/$auditJarName"
    $auditManifestPath = Join-Path $auditProject "build/libs/$auditManifestName"
    $auditZipPath = Join-Path $auditProject "build/releases/mtr-memory-saver-$Target-0.4.6.zip"
    $auditJarHash = Get-AuditHash $auditJarPath
    Assert-Audit ($auditJarHash -ceq $auditExpected[$Target]) "Product JAR changed for $Target"
    $auditManifest = Get-Content -LiteralPath $auditManifestPath -Raw | ConvertFrom-Json -AsHashtable
    Assert-Audit ($auditManifest.sha256 -ceq $auditJarHash) "Manifest JAR hash is stale for $Target"
    Assert-Audit ($auditManifest.target -ceq $Target -and $auditManifest.version -ceq '0.4.6') "Manifest target/version differs for $Target"
    $auditManifestInputChecks = foreach ($auditInput in $auditManifest.inputs.GetEnumerator()) {
        $auditActualInputHash = Get-AuditHash (Join-Path $auditProject $auditInput.Key)
        Assert-Audit ($auditActualInputHash -ceq $auditInput.Value) "Recorded source input differs: $($auditInput.Key)"
        [ordered]@{ path = $auditInput.Key; sha256 = $auditActualInputHash; matched = $true }
    }
    $auditArchivedManifestPath = Join-Path $auditProject "evidence/engineering-046/$Target/$auditManifestName"
    Assert-Audit ((Get-AuditHash $auditArchivedManifestPath) -ceq (Get-AuditHash $auditManifestPath)) "Archived manifest differs for $Target"
    $auditJar = [IO.Compression.ZipFile]::OpenRead($auditJarPath)
    try {
        $auditForbidden = @($auditJar.Entries | Where-Object { $_.FullName -match '^site/benli06/probe/|mtr-memory-acceptance|NativeResourceReadFixture|LoaderLifecycleProbe|PackagedClientObservation' } | ForEach-Object FullName)
        Assert-Audit ($auditForbidden.Count -eq 0) "Acceptance probe content found in product JAR"
        $auditMetadata = Get-AuditEntryText ($auditJar.GetEntry('mtr-memory-target.json')) | ConvertFrom-Json -AsHashtable
        Assert-Audit ($auditMetadata.target -ceq $Target) "Embedded product target differs"
        Assert-Audit ($auditMetadata.mtrSha256 -ceq $auditManifest.mtrSha256) "Embedded MTR identity differs"
    } finally { $auditJar.Dispose() }
    $auditZip = [IO.Compression.ZipFile]::OpenRead($auditZipPath)
    try {
        $auditExpectedFiles = @($auditJarName, $auditManifestName, 'LICENSE', 'README.md', 'docs/INSTALL.md', 'docs/SUPPORT.md', 'config/targets.json') | Sort-Object
        $auditActualFiles = @($auditZip.Entries | Where-Object { !$_.FullName.EndsWith('/') } | ForEach-Object FullName | Sort-Object)
        Assert-Audit (($auditExpectedFiles -join "`n") -ceq ($auditActualFiles -join "`n")) "ZIP file inventory differs for $Target"
        $auditEntries = foreach ($auditEntry in $auditZip.Entries) {
            if ($auditEntry.FullName.EndsWith('/')) { continue }
            $auditSource = switch ($auditEntry.FullName) {
                $auditJarName { "build/libs/$auditJarName" }
                $auditManifestName { "build/libs/$auditManifestName" }
                'README.md' { "build/generated/delivery/$Target/README.md" }
                default { $auditEntry.FullName }
            }
            $auditEntryHash = Get-AuditEntryHash $auditEntry
            $auditSourceHash = Get-AuditHash (Join-Path $auditProject $auditSource)
            Assert-Audit ($auditEntryHash -ceq $auditSourceHash) "ZIP entry differs from current source: $($auditEntry.FullName)"
            [ordered]@{ entry = $auditEntry.FullName; bytes = $auditEntry.Length; sha256 = $auditEntryHash; source = $auditSource; source_sha256 = $auditSourceHash; matched = $true }
        }
        $auditNavigation = foreach ($auditEntry in $auditZip.Entries) {
            if (!$auditEntry.FullName.EndsWith('.md')) { continue }
            $auditText = Get-AuditEntryText $auditEntry
            foreach ($auditMatch in [regex]::Matches($auditText, '\[[^\]]+\]\(([^)]+)\)')) {
                $auditLink = $auditMatch.Groups[1].Value
                if ($auditLink.StartsWith('#') -or $auditLink -match '^[a-zA-Z][a-zA-Z0-9+.-]*:') { continue }
                $auditBaseUri = [Uri]::new('https://delivery-audit.invalid/' + $auditEntry.FullName)
                $auditResolvedLink = [Uri]::UnescapeDataString([Uri]::new($auditBaseUri, $auditLink).AbsolutePath.TrimStart('/'))
                Assert-Audit ($null -ne $auditZip.GetEntry($auditResolvedLink)) "Broken ZIP navigation: $($auditEntry.FullName) -> $auditLink"
                [ordered]@{ source = $auditEntry.FullName; link = $auditLink; resolved_entry = $auditResolvedLink; exists = $true }
            }
        }
    } finally { $auditZip.Dispose() }
    [ordered]@{
        timestamp = Get-AuditTime
        passed = $true
        target = $Target
        artifact = "build/libs/$auditJarName"
        expected_jar_sha256 = $auditExpected[$Target]
        actual_jar_sha256 = $auditJarHash
        product_jar_unchanged = $true
        acceptance_probe_excluded = $true
        embedded_target = $auditMetadata
        manifest = "build/libs/$auditManifestName"
        manifest_sha256 = Get-AuditHash $auditManifestPath
        archived_manifest_matches = $true
        recorded_source_inputs = @($auditManifestInputChecks)
        release_zip = "build/releases/mtr-memory-saver-$Target-0.4.6.zip"
        release_zip_sha256 = Get-AuditHash $auditZipPath
        release_zip_bytes = (Get-Item -LiteralPath $auditZipPath).Length
        exact_file_inventory_matches = $true
        file_entries = @($auditEntries)
        markdown_navigation = @($auditNavigation)
        current_support_sha256 = Get-AuditHash (Join-Path $auditProject 'docs/SUPPORT.md')
        current_install_sha256 = Get-AuditHash (Join-Path $auditProject 'docs/INSTALL.md')
        tests = 'Skipped only during delivery rebuild (-x test); the exact unchanged product artifacts each have 61 archived passing Java tests'
        limits = 'Exact local delivery/source identity audit; no new full-client, geometry, GPU, route or performance acceptance'
    }
}

$auditOldJavaHome = $env:JAVA_HOME
$auditOldPath = $env:PATH
$auditOldNativePreference = $PSNativeCommandUseErrorActionPreference
$auditRecords = [Collections.Generic.List[object]]::new()
$auditReport = [ordered]@{
    timestamp = Get-AuditTime
    status = 'running'
    project = $auditProject
    java_home = [IO.Path]::GetFullPath($JavaHome)
    target_execution = 'sequential; both targets share build directory'
    commands = @()
}
Write-AuditJson 'execution.json' $auditReport
try {
    $env:JAVA_HOME = [IO.Path]::GetFullPath($JavaHome)
    $env:PATH = (Join-Path $env:JAVA_HOME 'bin') + [IO.Path]::PathSeparator + $auditOldPath
    $PSNativeCommandUseErrorActionPreference = $false
    Assert-Audit (Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin/java.exe') -PathType Leaf) 'Java executable missing'
    & (Join-Path $env:JAVA_HOME 'bin/java.exe') -version 1> (Join-Path $PSScriptRoot 'java-version.stdout.log') 2> (Join-Path $PSScriptRoot 'java-version.stderr.log')
    Assert-Audit ($LASTEXITCODE -eq 0) 'Java version check failed'
    $auditReport.java_version = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'java-version.stderr.log') -Raw
    $auditReport.java_executable_sha256 = Get-AuditHash (Join-Path $env:JAVA_HOME 'bin/java.exe')
    $auditReport.frozen_delivery_inputs = [ordered]@{}
    foreach ($auditFrozenSource in @('build.gradle', 'gradle.properties', 'config/targets.json', 'LICENSE', 'docs/SUPPORT.md', 'docs/INSTALL.md')) {
        $auditReport.frozen_delivery_inputs[$auditFrozenSource] = Get-AuditHash (Join-Path $auditProject $auditFrozenSource)
    }
    Push-Location -LiteralPath $auditProject
    try {
        foreach ($auditTarget in $auditExpected.Keys) {
            $auditProductPath = Join-Path $auditProject "build/libs/mtr-memory-saver-$auditTarget-0.4.6.jar"
            Assert-Audit ((Get-AuditHash $auditProductPath) -ceq $auditExpected[$auditTarget]) "Pre-build JAR identity differs: $auditTarget"
            $auditArguments = @('releaseBundle', "-Ptarget=$auditTarget", '-x', 'test', '--console=plain')
            $auditRecord = [ordered]@{ target = $auditTarget; started_at = Get-AuditTime; command = @((Join-Path $auditProject 'gradlew.bat')) + $auditArguments }
            & (Join-Path $auditProject 'gradlew.bat') @auditArguments 1> (Join-Path $PSScriptRoot "$auditTarget.stdout.log") 2> (Join-Path $PSScriptRoot "$auditTarget.stderr.log")
            $auditRecord.exit_code = $LASTEXITCODE
            $auditRecord.finished_at = Get-AuditTime
            $auditRecords.Add($auditRecord)
            $auditReport.commands = $auditRecords.ToArray()
            Write-AuditJson 'execution.json' $auditReport
            Assert-Audit ($auditRecord.exit_code -eq 0) "Release build failed for $auditTarget"
            foreach ($auditFrozenInput in $auditReport.frozen_delivery_inputs.GetEnumerator()) {
                Assert-Audit ((Get-AuditHash (Join-Path $auditProject $auditFrozenInput.Key)) -ceq $auditFrozenInput.Value) "Frozen delivery input changed during build: $($auditFrozenInput.Key)"
            }
            $auditBundleReport = Get-AuditBundle $auditTarget
            Write-AuditJson "$auditTarget.audit.json" $auditBundleReport
            $auditRecord.audit = "$auditTarget.audit.json"
            $auditRecord.release_zip_sha256 = $auditBundleReport.release_zip_sha256
            $auditReport.commands = $auditRecords.ToArray()
            Write-AuditJson 'execution.json' $auditReport
        }
    } finally { Pop-Location }
    $auditReport.status = 'completed'
    $auditReport.passed = $true
} catch {
    $auditReport.status = 'failed'
    $auditReport.passed = $false
    $auditReport.failure = $_.ToString()
    $auditReport.failure_position = $_.InvocationInfo.PositionMessage
    throw
} finally {
    $auditReport.finished_at = Get-AuditTime
    $auditReport.commands = $auditRecords.ToArray()
    Write-AuditJson 'execution.json' $auditReport
    $env:JAVA_HOME = $auditOldJavaHome
    $env:PATH = $auditOldPath
    $PSNativeCommandUseErrorActionPreference = $auditOldNativePreference
}
Write-Output "Sequential official delivery build and audit completed: $PSScriptRoot"
