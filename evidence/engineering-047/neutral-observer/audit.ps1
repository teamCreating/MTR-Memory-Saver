param([Parameter(Mandatory)][string]$RepositoryRoot)
$ErrorActionPreference = 'Stop'
$neutralRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$neutralSpec = Get-Content -LiteralPath (Join-Path $neutralRoot 'tools/probes/neutral/observer.json') -Raw | ConvertFrom-Json -AsHashtable
$neutralMatrix = Get-Content -LiteralPath (Join-Path $neutralRoot 'config/targets.json') -Raw | ConvertFrom-Json -AsHashtable
$neutralResults = @()
foreach ($neutralTargetName in @('official-nf248', 'official-nf265')) {
    $neutralDirectory = Join-Path $neutralRoot "evidence/engineering-047/neutral-observer/$neutralTargetName/final"
    $neutralJar = Join-Path $neutralDirectory "mtr-native-observer-$neutralTargetName-1.0.0.jar"
    $neutralManifest = Get-Content -LiteralPath (Join-Path $neutralDirectory "mtr-native-observer-$neutralTargetName-1.0.0.build.json") -Raw | ConvertFrom-Json -AsHashtable
    $neutralHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $neutralJar).Hash.ToLowerInvariant()
    if ($neutralManifest.sha256 -ne $neutralHash) { throw 'Observer artifact differs from its manifest' }
    foreach ($neutralInput in $neutralManifest.inputs.GetEnumerator()) {
        $neutralActual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $neutralRoot $neutralInput.Key)).Hash.ToLowerInvariant()
        if ($neutralActual -ne $neutralInput.Value) { throw "Observer input mismatch: $($neutralInput.Key)" }
    }
    $neutralZip = [IO.Compression.ZipFile]::OpenRead($neutralJar)
    try {
        $neutralRead = {
            param([string]$EntryName)
            $neutralEntry = $neutralZip.GetEntry($EntryName)
            if ($null -eq $neutralEntry) { throw "Missing observer entry $EntryName" }
            $neutralReader = [IO.StreamReader]::new($neutralEntry.Open(), [Text.Encoding]::UTF8)
            try { $neutralReader.ReadToEnd() } finally { $neutralReader.Dispose() }
        }
        $neutralIdentity = (& $neutralRead 'mtr-native-observer-target.json') | ConvertFrom-Json -AsHashtable
        $neutralCapabilities = (& $neutralRead 'capabilities.json') | ConvertFrom-Json -AsHashtable
        $neutralToml = & $neutralRead 'META-INF/neoforge.mods.toml'
        $neutralMixins = (& $neutralRead 'mtr-native-observer.mixins.json') | ConvertFrom-Json -AsHashtable
        if ($neutralIdentity.target -ne $neutralTargetName -or $neutralIdentity.variant -ne 'official' -or
                $neutralIdentity.minecraft -ne $neutralMatrix.minecraft -or $neutralIdentity.java -ne $neutralMatrix.java -or
                $neutralIdentity.neoForge -ne $neutralMatrix.targets[$neutralTargetName].neoForge -or
                $neutralIdentity.mtrSha256 -ne $neutralMatrix.mtr.official.sha256 -or
                $neutralIdentity.mtrVersion -ne $neutralMatrix.mtr.official.version -or
                $neutralIdentity.observer_version -ne $neutralSpec.observer_version -or
                $neutralIdentity.mod_id -ne $neutralSpec.mod_id) { throw 'Observer native ABI metadata mismatch' }
        if ($neutralIdentity.frame_event -ne $neutralSpec.frame_event -or
                $neutralIdentity.server_tick_event -ne $neutralSpec.server_tick_event) { throw 'Observer event schema mismatch' }
        foreach ($neutralCapability in $neutralSpec.capabilities.GetEnumerator()) {
            if ($neutralCapabilities.capabilities[$neutralCapability.Key] -isnot [bool] -or
                    $neutralCapabilities.capabilities[$neutralCapability.Key] -ne $neutralCapability.Value) {
                throw "Observer capability mismatch: $($neutralCapability.Key)"
            }
        }
        if ($neutralCapabilities.capabilities.Count -ne $neutralSpec.capabilities.Count -or
                $neutralToml -notmatch 'modId="mtr_native_observer"' -or
                $neutralToml -match 'modId="mtr_memory_sharing"' -or
                !$neutralMixins.required -or $neutralMixins.injectors.defaultRequire -ne 1) { throw 'Observer packaging mismatch' }
        $neutralClasses = 0
        foreach ($neutralEntry in $neutralZip.Entries) {
            if (!$neutralEntry.FullName.EndsWith('.class')) { continue }
            if (!$neutralEntry.FullName.StartsWith('dev/abenli/neutralprobe/')) { throw 'Observer contains a foreign class' }
            $neutralStream = $neutralEntry.Open()
            $neutralBytes = [IO.MemoryStream]::new()
            try { $neutralStream.CopyTo($neutralBytes); $neutralPool = [Text.Encoding]::Latin1.GetString($neutralBytes.ToArray()) }
            finally { $neutralStream.Dispose(); $neutralBytes.Dispose() }
            foreach ($neutralForbidden in @('site/benli06', 'site.benli06', 'getCachedVehicleResource', 'awaitParsing', 'java/lang/reflect')) {
                if ($neutralPool.Contains($neutralForbidden)) { throw "Forbidden observer reference: $neutralForbidden" }
            }
            $neutralClasses++
        }
    } finally { $neutralZip.Dispose() }
    $neutralTests = 0
    foreach ($neutralReport in Get-ChildItem -LiteralPath (Join-Path $neutralDirectory 'junit') -Filter 'TEST-*.xml') {
        $neutralSuite = ([xml](Get-Content -LiteralPath $neutralReport.FullName -Raw)).testsuite
        if ([int]$neutralSuite.failures -ne 0 -or [int]$neutralSuite.errors -ne 0 -or [int]$neutralSuite.skipped -ne 0) { throw 'Observer JUnit failures' }
        $neutralTests += [int]$neutralSuite.tests
    }
    $neutralJfr = Get-Content -LiteralPath (Join-Path $neutralDirectory 'frame-events.json') -Raw | ConvertFrom-Json
    $neutralFrameCount = @($neutralJfr.recording.events | Where-Object type -EQ $neutralSpec.frame_event).Count
    $neutralTickCount = @($neutralJfr.recording.events | Where-Object type -EQ $neutralSpec.server_tick_event).Count
    if ($neutralTests -ne 14 -or $neutralFrameCount -ne 1 -or $neutralTickCount -ne 1) { throw 'Observer engineering evidence is incomplete' }
    $neutralResults += [ordered]@{target=$neutralTargetName; artifact=$neutralJar; sha256=$neutralHash;
        class_count=$neutralClasses; manifest_inputs=$neutralManifest.inputs.Count; junit_tests=$neutralTests;
        junit_failures=0; jfr_frame_events=$neutralFrameCount; jfr_tick_events=$neutralTickCount;
        packaging_and_source_integrity=$true; actual_mixin_client_run=$false}
}
[ordered]@{timestamp=[DateTimeOffset]::Now.ToString('o'); utc_offset=[DateTimeOffset]::Now.ToString('zzz');
    scope='Official native observer tool engineering only'; targets=$neutralResults;
    remaining=@('Actual NeoForge client Mixin application on both exact loaders',
        'Current-input qualification of baseline and candidate with identical observer bytes',
        'Real native reload and steady frame/JFR coverage', 'Observer-off instrumentation calibration')} |
    ConvertTo-Json -Depth 10 | Set-Content -Encoding utf8 (Join-Path $neutralRoot 'evidence/engineering-047/neutral-observer/assessment.json')
