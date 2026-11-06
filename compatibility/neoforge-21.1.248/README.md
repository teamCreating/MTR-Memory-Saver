# NeoForge 21.1.248 memory companions

Target: **Minecraft 1.21.1 / NeoForge 21.1.248 / FML 4.0.43 / Java 21**. These separate builds retain the memory features of the existing companions and compile against the actual 21.1.248 client patch and active runtime libraries.

| MTR release | Companion | SHA-256 |
| --- | --- | --- |
| Custom `4.1.0-beta.2-mc1.21.1-performance-v6` | [v0.3.1-v6 for 21.1.248](mtr-memory-sharing-neoforge-v031-v6-nf248.jar) | `43da91dce144cc0a1a1e65307ba385cc9d89eb3a5057f07e7eab7529dca39174` |
| Official `4.1.0-beta.2` | [v0.3.0 for 21.1.248](mtr-memory-sharing-neoforge-v030-nf248.jar) | `b9c95bbe79c6c76fe6a0c9af6bdb4f9ed7ce6b007fecdb1c9f543544ce562f02` |

Stop the client, retain the previous memory companion outside `mods`, and install exactly one companion matching the MTR release. The custom v6 JAR must have SHA-256 `8bd419bd798c2ab2fa03e08850409387804fdeb2e4f2987c66b9984236263585`; the official NeoForge MTR JAR must have SHA-256 `ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa`. Keep the existing repaired resource packs enabled. Test observer mods are separate from installation.

The original 21.1.265 builds declare a minimum NeoForge version of 21.1.265 and are rejected by 21.1.248. The rebuilt artifacts declare `[21.1.248,)`. Exact member comparison verifies that **all 34 classes, Mixin configuration and every other JAR member payload remain identical** to the corresponding previous delivery; only this dependency declaration changes. The loader minimum follows the build instance rather than a hardcoded replacement. The builder selects the marked client's patch explicitly and rejects a mismatch with launch metadata, a missing active patch or a patch lacking required Minecraft classes. [Build comparison and fingerprints](build-audit.json).

Use the documented Java 21 settings for the complete sixteen-pack fixture:

```text
-Xms1G -Xmx3072M
-Djdk.virtualThreadScheduler.parallelism=2
-Djdk.virtualThreadScheduler.maxPoolSize=2
```

The scheduler settings affect the JVM globally. Three GiB is the Java heap allocation; process, native and GPU memory are additional. The existing [v6 implementation guide](../performance-v6/README.md) and [official memory guide](../../README.md) describe unchanged cache behavior and prior 21.1.265 evidence. Those historical trials retain their original loader identity.

## Validation

The official installer generated the real 21.1.248 client patch. Both companions compile successfully against it and their matching MTR releases. Four active-patch selection controls and four existing performance-analysis tests pass. [Final acceptance](acceptance.json) and [evidence fingerprints](evidence-index.json) verify the actual artifacts and original fixture preservation.

Each release passes **one fresh full-16-pack client at 3072 MiB**, startup and actual foreground F3+T, with 2,541 registered vehicles and 651 completed unique source parses per epoch. Nominal sixty-second fresh stable observations follow each phase. Both native DC01 car bodies render before/after; their independent 5/6-floor and 10/10-doorway caches match the official reference exactly. The native MTR end-of-client-tick callback remains intact. Both copied clients restore their player/input layout, save and exit normally; saved transport fields, sixteen archive hashes/order and launched mod hashes verify.

| Runtime observation, 2026-11-06 (UTC+08:00) | Performance v6 | Official MTR |
| --- | ---: | ---: |
| Startup to fresh in-world evidence | 165.81 s | 166.74 s |
| F3+T to fresh in-world evidence from the new parsing epoch | 136.72 s | 143.54 s |
| Startup / reload acceptance | Pass / pass | Pass / pass |
| Native GPU/cache/lifetime checks | 12/12 pass | Existing official lifecycle; no v6 probe |
| Normal shutdown and saved-fixture verification | Pass | Pass |

These are acceptance observations with JFR, heap sampling and an existing background server, not controlled loading-speed comparisons. Sampled memory is recorded separately in the acceptance JSON and is not a true maximum. Each release has one new trial here; the previous 21.1.265 repetitions retain their original scope. Native completion of the new resource epoch excludes stale pre-reload complete snapshots.

- v6: [trial](runtime-v6/trial.json), [GPU checks](runtime-v6/v6-compatibility-result.json), [before](runtime-v6/train.png), [after](runtime-v6/after-reload.png), [visual review](runtime-v6/visual-review.json).
- Official: [trial](runtime-official/trial.json), [before](runtime-official/train.png), [after](runtime-official/after-reload.png), [visual review](runtime-official/visual-review.json).

Known transparent-model, missing authored sound and SDK-profile Realms warnings remain in the verbatim logs. Neither trial reports OOM, Mixin application failure, resource-reload failure or Blockbench/OBJ parsing failure. JFR recordings remain in the project cache with exact paths/hashes recorded in each trial. The original source marker/options/level.dat, all sixteen source packs and all three source mods verify unchanged.

This adaptation does not change any model, texture, geometry, native interaction configuration or world. Wider vehicle-family visuals, physical boarding/cab traversal, other mod combinations and long-session memory behavior require their own acceptance.

## Rebuild

Use the marked copied 21.1.248 instance matching the desired MTR release. The build manifests pin every companion source and both release/client JAR identities. For v6, select the exact custom MTR JAR inside the closed runtime fixture:

```powershell
$nfInstance = '.cache/game-test/nf248-v6-3g'
$nfMarker = Get-Content "$nfInstance/vehicle-test-instance.json" -Raw | ConvertFrom-Json
$nfJavac = [IO.Path]::Combine([IO.Path]::GetDirectoryName($nfMarker.java), 'javac.exe')
$nfMtr = Get-ChildItem -LiteralPath "$nfInstance/mods" -Filter '*.jar' |
    Where-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash -eq $nfMarker.mtr_sha256 } |
    Select-Object -ExpandProperty FullName
python -X utf8 tools/build_vehicle_memory_mod.py `
  --instance $nfInstance --javac $nfJavac --performance-v6 --mtr-jar $nfMtr `
  --packed-meshes --prune-displays --share-json --compress-texts `
  --segment-text-reads --segment-text-unpacks --stream-text-digests --bound-text-cache `
  --output .cache/game-test/nf248-rebuild/mtr-memory-sharing-neoforge-v031-v6-nf248.jar
```

For official MTR, use `.cache/game-test/neoforge-21.1.248-base`, omit `--performance-v6` and `--mtr-jar`, and select a separate output filename. JAR archive timestamps can vary; compare member payloads and the generated build manifest. Existing 21.1.265 deliveries remain available for rollback.
