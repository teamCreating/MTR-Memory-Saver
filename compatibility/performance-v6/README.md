# MTR Performance v6 memory companion

**v0.3.1-v6** adapts the v0.3.0 memory features to the deployed custom v6 release. [Download the companion](mtr-memory-sharing-neoforge-v031-v6.jar). Two fresh clients pass the complete 16-pack fixture at **3072 MiB**, including startup, native F3+T, GPU ownership checks and DC01 rendering before/after reload. [Acceptance and fingerprints](acceptance.json).

## Install

Target: **Minecraft 1.21.1 / NeoForge 21.1.265 / Java 21 / MTR `4.1.0-beta.2-mc1.21.1-performance-v6`**.

| Artifact | SHA-256 |
| --- | --- |
| Audited custom MTR v6 | `8bd419bd798c2ab2fa03e08850409387804fdeb2e4f2987c66b9984236263585` |
| v0.3.1-v6 companion | `ab6d372f458299bf1ce116a5a05101de3cc110b731149d668f13324adfb23dcb` |
| Original official-MTR v0.3.0, retained unchanged | `eb21c0062f7944a7d2c015cb2eee5a1d24c11be4af2286bbbbfa4625d6cd2d54` |

1. Stop the client and retain its old companion outside `mods` for rollback.
2. Keep the matching v6 MTR JAR and replace the previous memory companion with `mtr-memory-sharing-neoforge-v031-v6.jar`. Install exactly one memory companion; its mod ID remains `mtr_memory_sharing`.
3. Keep the existing repaired resource packs enabled. The delivered companion is a client mod; the test-only `vehicle-performance-probe.jar` is not part of installation.

Tested JVM settings:

```text
-Xms1G -Xmx3072M
-Djdk.virtualThreadScheduler.parallelism=2
-Djdk.virtualThreadScheduler.maxPoolSize=2
```

These scheduler properties affect the JVM's default virtual-thread scheduler globally. The results below include them; other settings/mod combinations are unmeasured. Three GiB is the Java heap allocation, not total process RAM. The original v0.3.0 remains for official MTR: reverting to that release requires restoring the matching MTR/companion pair. This variant does not claim Fabric or other custom v6 builds.

## What changed

The original companion calls `StoredVertexData.color().getRGB()` and redirects `Color` construction. The actual v6 ABI stores integer ARGB. This variant compiles against that ABI, reads the integer directly and omits the obsolete redirect. The real old source fails compilation against v6 with `int cannot be dereferenced`, so editing the dependency version alone would not adapt it.

The packed group mixin now respects v6's native `builtModels` cache and `ensureMutable()` guard. It returns the same GPU model map on repeated builds, rejects later add/merge operations and releases the built destination's packed staging. Shared source groups remain available to other independent facades. A facade close hook serializes closure against late asynchronous publication while preserving v6's native GPU disposal.

Thirty classes remain byte-identical to v0.3.0, including bounded resource-text retention, digests, JSON caching and supporting vertex operations. Three classes change, one obsolete mixin is removed and one lifecycle mixin is added. Source sharing still reduces **4,608 Blockbench requests to 651 unique parses** per epoch. The compressed text cache retains its heap-scaled budget, 96 MiB at this heap size. No resource model or artwork bytes are changed.

The [earlier performance report](../../performance/20261105/README.md) recorded v6 alone exhausting an 8 GiB heap with these same 16 packs. Adding the adapted memory features now allows this fixture to load at 3 GiB. This establishes the combined configuration's viability; it does not isolate the contribution of each optimization or prove a rendering speed advantage over official MTR.

## Runtime results, 2026-11-06 (UTC+08:00)

| Measurement | First fresh client | Second fresh client |
| --- | ---: | ---: |
| Registered vehicle definitions / completed source parses | 2,541 / 651 | 2,541 / 651 |
| Startup to fresh in-world evidence | 155.16 s | 156.92 s |
| F3+T to fresh in-world evidence after the new epoch | 136.88 s | 133.99 s |
| Native GPU/cache/lifetime checks | 12/12 pass | 12/12 pass |
| Startup Full GC / total GC pauses | 2 / 7.530 s | 2 / 7.744 s |
| Reload Full GC / total GC pauses | 11 / 13.512 s | 10 / 13.635 s |
| Post-reload effective FPS | 58.91 | 58.87 |
| Post-reload frame interval p95 / p99 | 22.68 / 29.65 ms | 22.43 / 29.61 ms |
| Post-reload maximum frame interval | 55.31 ms | 102.51 ms |
| Post-reload Full GC | 0 | 0 |

Both startup and reload pass a nominal 60-second monitor with fresh snapshots throughout. Recorded first-to-last stable snapshot spans are 59.73–60.00 seconds. Timing ends only after native logs confirm the new epoch's 651 completed parses; an early reload snapshot carrying the old complete state is excluded. Loading times include other game work and snapshot latency. GC pause totals are cumulative; concurrent `G1Old` cycles are not counted as Full GCs.

The Intel HD P530 scene uses 1280×720, VSync and a 60 FPS cap, render distance 8 and simulation distance 5. Effective FPS measures render-hook intervals including pacing, not GPU presentation times. The second stable window contains one interval over 100 ms. These short windows do not establish uncapped throughput or eliminate occasional stutter. Loading/reload still produces considerable GC pressure.

| Highest sampled memory | First startup | First reload | Second startup | Second reload |
| --- | ---: | ---: | ---: | ---: |
| Java heap used | 2.829 GiB | 2.992 GiB | 2.800 GiB | 2.936 GiB |
| Current Windows working set | 4.644 GiB | 5.159 GiB | 4.422 GiB | 4.907 GiB |
| Private commitment | 4.838 GiB | 5.397 GiB | 4.592 GiB | 5.396 GiB |

Process-lifetime working-set watermarks reach 5.394 / 5.409 GiB by reload. These include unsampled intervals and are not phase-specific peaks. Jstat startup sampling begins about 60 / 43 seconds after launch, while parsing is still running; it misses earlier heap behavior. JFR and GC logging start with each JVM. Heap, working set, private commitment and GPU memory overlap and must not be summed. JFR instrumentation adds overhead. Offline model auditing overlaps part of the first reload; brief regression/export work overlaps the second startup. The second reload and both post-reload analysis windows exclude those tasks. These are acceptance repetitions, not controlled speed benchmarks.

Both clients retain the native MTR end-of-client-tick callback, render the two DC01 car bodies before/after, and keep exact floor/doorway caches matching the official fixture. Both restore the copied player and input layout, save normally and exit. Source marker/options/level.dat, all 16 source archives and all three source mods verify unchanged. The actual MTR and companion binaries are identical across trials; the separately packaged observer JARs have different archive hashes but all 18 member payloads are identical.

Known transparent-model/missing-sound warnings and SDK-profile Realms authentication messages remain in verbatim logs. No OOM, Mixin application failure, resource-reload failure or Blockbench/OBJ parsing failure occurs. Full-family visual/audio acceptance, physical boarding/cab traversal, dense production networks and long-session leak testing remain outside this round.

## Evidence and reproduction

- [First trial](runtime-first/trial.json), [profile](runtime-first/profile.json), [before](runtime-first/train.png), [after](runtime-first/after-reload.png).
- [Second trial](runtime-repeat/trial.json), [profile](runtime-repeat/profile.json), [before](runtime-repeat/train.png), [after](runtime-repeat/after-reload.png).
- [Native GPU checks, first](runtime-first/v6-compatibility-result.json) and [second](runtime-repeat/v6-compatibility-result.json): caching, mutation guards, staging retention/release, close-before-publication and independent GPU ownership/disposal.
- [Synthetic audit](offline/synthetic.json): 1,400,028 checked vertices, zero mismatches; explicitly classified arithmetic NaN payload variations retain the previous audit convention.
- [Actual v6-parsed models](offline/native-models.json): 9 DC01 model inputs, 1,267,536 source vertices, zero mismatches, including normal/mirrored transforms, groups, UV/ARGB/normals and bounds. [Jobs and original model hashes](dc01-jobs.json).
- [Binary/ABI audit](offline/audit.json), [old-source negative control](offline/old-source-negative.log), [official rebuild/regression](offline/official-regression.json). All 42 official v0.3.0 JAR member payloads rebuild identically; the old ABI synthetic audit also passes. Wrong target bytes and unsupported mesh-sharing combinations are rejected.
- [Evidence index](evidence-index.json) records exact files and raw JFR locations/hashes in the project cache. Test observers are separate from the delivered companion.

The explicit build requires a marked v6 NeoForge instance and the fingerprinted custom JAR. Official builder defaults remain unchanged. Example from the project root:

```powershell
$v6Java = (Get-Content .cache/game-test/v031-v6-3g-first/vehicle-test-instance.json -Raw | ConvertFrom-Json).java
$v6Jar = 'E:/yunniverse-server/client-pack/mods/[自修改]MTR-4.1.0-beta.2-mc1.21.1-performance-v6.jar'
python -X utf8 tools/build_vehicle_memory_mod.py `
  --instance .cache/game-test/v031-v6-3g-first `
  --javac ([IO.Path]::Combine([IO.Path]::GetDirectoryName($v6Java), 'javac.exe')) `
  --performance-v6 --mtr-jar $v6Jar `
  --packed-meshes --prune-displays --share-json --compress-texts `
  --segment-text-reads --segment-text-unpacks --stream-text-digests --bound-text-cache `
  --output .cache/game-test/v6-rebuild/mtr-memory-sharing-neoforge-v031-v6.jar
```

Use `tools/audit_v6_memory_compatibility.py` with `--instance`, `--candidate`, `--baseline`, `--mtr-jar`, a fresh `--output-dir` and the preserved `--jobs` file for offline validation. `tools/performance_test_instance.py` accepts `--companion-jar` and `--v6-compatibility-probe` to prepare a fresh copied trial. Run the startup/heap monitors, write its `v6-compatibility-request.json` after world entry, capture the native train camera, request real F3+T and monitor a new resource epoch. `tools/finish_v6_memory_trial.py` verifies caches, restores/closes the trial and preserves logs/windows. Analyze its closed JFR with `tools/analyze_performance_jfr.py`, then use `tools/summarize_v6_memory_trials.py` to verify both trials and source preservation. The [build metadata](mtr-memory-sharing-neoforge-v031-v6.build.json) pins all companion source hashes.
