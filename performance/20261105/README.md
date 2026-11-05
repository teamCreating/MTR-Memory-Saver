# Runtime performance and MTR Performance v6

Measured on 2026-11-05, **UTC+08:00**. The current full resource stack works with official MTR plus the v0.3.0 companion at a 3 GiB heap, but resource loading/reloading remains expensive. The deployed Performance v6 **without that incompatible companion fails the same full stack at 8 GiB**. A separate two-car DC01 registration subset successfully enters the world, renders, runs and reloads in v6 at 3 GiB.

This is a configuration-capacity and profiling study. Different heaps, companion presence, registration sets and scene states prevent a code-only A/B speed claim.

## Environment and identity

- Windows 10 Pro for Workstations 22H2, Xeon E3-1275 v5, 4 cores / 8 logical processors, approximately 32 GiB installed RAM.
- **Actual renderer: Intel HD Graphics P530**, driver 31.0.101.2111; confirmed by the [native F3 view](fixture-3g/debug-hardware.png). The installed NVIDIA adapter was not the active renderer.
- Minecraft 1.21.1, NeoForge 21.1.265, Temurin 21.0.11+10, 1280×720, VSync enabled, 60 FPS cap, render distance 8, simulation distance 5. No shader pack or production server connection.
- All runs use `-Xms1G`, G1, `jdk.virtualThreadScheduler.parallelism=2` and `jdk.virtualThreadScheduler.maxPoolSize=2`. Maximum heap is the table's explicit experimental variable.
- Official MTR SHA-256: `ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa`.
- Delivered v0.3.0 companion SHA-256: `eb21c0062f7944a7d2c015cb2eee5a1d24c11be4af2286bbbbfa4625d6cd2d54`.
- Tested v6 SHA-256: `8bd419bd798c2ab2fa03e08850409387804fdeb2e4f2987c66b9984236263585`. It matches both the current `E:\yunniverse-server\client-pack\mods` and server `mods` artifacts. Its mod version is `4.1.0-beta.2-mc1.21.1-performance-v6`; older historical v6 hashes are different builds.

The [launch manifests and raw recording index](evidence-index.json) preserve actual enabled packs, JAR fingerprints, PIDs and diagnostic-file locations. Each client uses its own copied world and an additive observation mod. [Original source preservation](source-preservation.json) verifies the source instance marker, options, level.dat, all 16 source archives and all three original mods remain unchanged.

## Results

| Configuration | Java heap | Registered vehicles | Startup / world entry | F3+T reload | Sustained observation |
| --- | ---: | ---: | --- | --- | --- |
| Official MTR + v0.3.0, all 16 repaired packs | 3 GiB | 2,541 | Pass; approximately 182.9 s | Pass; approximately 144.7 s | 120 s collected; 107.17 s clean analysis window |
| Performance v6 alone, same 16 repaired packs | 8 GiB | 2,541 registration announced; model loading incomplete | **Fail: heap-space OOM, exit 1, no world entry** | Not reached | Not reached |
| Performance v6 alone, DC01 subset | 3 GiB | 425: 423 built-ins + 2 custom cars | Pass; approximately 50.4 s | Pass; approximately 20.5 s | 120 s analyzed |

Startup times run from launcher timestamp to the first fresh in-world snapshot with parsing complete. Reload times run from foreground F3+T to fresh parsing-complete evidence after the new resource epoch. They include other game/resource work and up to about five seconds of observation latency; they are not model-parser-only timings. Each successful startup and reload also passes 60 seconds of fresh stability. All successful clients save and exit normally.

The subset retains the two existing DC01 car definitions and **every original model/artwork member byte**. Only registration metadata is reduced; it uses one enabled subset archive, SHA-256 `2edfdf5470b5f26e82dc7c9aa4be5d7fbe3106fc911296981c0049e5827fefda`. This success is not all-pack acceptance.

### Frame and server observations

| In-world window | Effective FPS | Frame interval p50 / p95 / p99 | Maximum frame interval | Mean / p95 server tick event span | Process CPU, fraction of whole machine |
| --- | ---: | --- | ---: | --- | ---: |
| Full-stack companion, stationary player, 107.17 s | 58.85 | 16.70 / 22.55 / 29.22 ms | 55.63 ms | 1.60 / 2.52 ms | 9.42% |
| v6 DC01 subset, train-view observer, 120 s | 59.23 | 16.68 / 21.93 / 26.37 ms | 45.50 ms | 1.18 / 2.06 ms | 7.19% |

These capped, small-scene results show usable frame pacing in their measured windows. They do not establish uncapped rendering throughput or a v6 speed improvement. Native trains continue their normal schedule; daylight, positions, movement and observer location are not locked between runs. The official window ends before an explicit JFR checkpoint dump.

Frame measurements are consecutive `RenderFrameEvent.Pre` intervals, including pacing, rather than GPU presentation timestamps. Server measurements cover NeoForge pre/post tick hooks, not complete authoritative MSPT. No sustained server-tick bottleneck appears in these small fixtures; a production world's TPS or entity/chunk load is not established.

### Garbage collection and loading pressure

| Phase | Full GCs | All top-level GC pauses, cumulative | Longest GC pause |
| --- | ---: | ---: | ---: |
| Companion full-stack startup | 4 | 10.904 s | 0.892 s |
| Companion full-stack stable window | 0 | 0.075 s | 0.016 s |
| Companion full-stack reload | 10 | 13.750 s | 1.017 s |
| v6 full-stack failed startup | **165** | **339.621 s** | **2.994 s** |
| v6 subset startup | 0 | 1.201 s | 0.084 s |
| v6 subset stable window | 0 | 0.083 s | 0.013 s |
| v6 subset reload | 0 | 0.686 s | 0.107 s |

The companion reload's Full GCs alone contribute 8.065 seconds; the rest of its 144.7-second observed reload cannot be called GC time. No frames from the blocked loading interval qualify as stable gameplay. A cumulative pause total is not one continuous freeze.

The failed v6 run spends approximately 71% of its 476.3-second observed startup window in GC pauses. Its final GC log shows `8182M->8175M(8192M)`: a Full GC recovers very little immediately before the heap-space failure. Registration count by itself was therefore insufficient evidence of a completed load. The external jstat observer times out under this pressure; JFR, GC log and exit evidence remain available.

### Windows and heap accounting

| Configuration | Highest sampled current working set | Highest sampled private commitment | Highest observed process-lifetime working-set watermark |
| --- | ---: | ---: | ---: |
| Companion, full stack, startup/game/reload | 4.657 GiB | 4.843 GiB | 5.362 GiB |
| v6, failed full stack | 9.015 GiB | 9.219 GiB | 9.018 GiB |
| v6, successful subset | 4.180 GiB | 4.398 GiB | 4.430 GiB |

The lifetime watermark includes gaps between samples and cannot be assigned to an individual phase. Working set, private commitment, Java heap and GPU accounting overlap and must not be summed. One Windows GPU counter snapshot records 0.656 GiB shared usage during the companion reload, and another records 0.619 GiB after the subset reload. These snapshots are not GPU peaks or leak measurements. Early jstat samples are incomplete for both startup runs; startup JFR/GC logging began with the JVM. The subset's separate reload jstat file covers only the tail.

## Bottleneck analysis

**High confidence: model loading and associated allocation/GC pressure are the main problems in these tests.** The stable windows are close to the configured frame cap with no Full GC, while startup/reload perform expensive resource work. In the companion's Java execution samples, `BlockbenchModelLoader.lambda$loadModel$5` appears in 4,091/6,457 startup stacks and 4,187/6,064 reload stacks. `NewOptimizedModelGroup`'s companion packing handler appears in 1,767 and 1,797 stacks respectively; these inclusive counts overlap and must not be added.

Java leaf samples highlight Gson JSON reading, string handling and growing arrays/lists. Native samples also catch compression/decompression: startup records 1,462 `Deflater.deflateBytesBytes` and 561 `Inflater.inflateBytesBytes` samples; reload records 360 and 119. Native samples additionally contain waiting calls such as `WEPoll.wait`; those are not evidence of CPU saturation. Java and native sample rankings are kept separate in the final summaries.

Allocation samples heavily feature byte/object/int arrays, strings, vectors and `StoredVertexData`. For example, byte-array allocation weights total approximately 25.8 GiB during companion startup and 23.4 GiB during reload. These are estimated allocation traffic, **not retained heap sizes**. No histogram or forced collection was requested, so these data cannot prove a memory leak or count surviving vertices.

**High confidence: the delivered v0.3.0 JAR cannot simply be combined with this v6 JAR.** Its dependency is pinned to `[4.1.0-beta.2]`. Independently, its `VertexColorMixin` targets construction of `java.awt.Color`, while its packed-vertex encoder calls `color().getRGB()`. The [actual v6 ABI](v6-stored-vertex-abi.txt) instead exposes `int color()` and an integer-color constructor. Relaxing the version constraint alone does not resolve those incompatible code paths. No dependency bypass or patched delivery was used in this study.

Recommended implementation priorities, not changes made here:

1. Create an explicit v6-compatible companion implementation against this exact ABI, respecting v6's CPU-list clearing and GPU buffer ownership. Validate reload lifetimes and exact rendered data before combining optimizations.
2. Eliminate repeated text restoration/digest work before the existing shared-model lookup, scoped to resource-provider identity and reload generation.
3. Bound queued parser inputs and MTR-local in-flight work. The v6 Full GC failure occurs before a usable world, so cleanup after GPU model construction is insufficient for this full loading workload.
4. Then measure heap headroom and scheduler settings one variable at a time. These runs do not establish the performance cost of the global scheduler limit, an optimum heap size, or the benefit of removing that limit.

## Native and evidence checks

- Reviewed [official train view](fixture-3g/train-view.png), [v6 before reload](v6-dc01-r2/train-view.png) and [v6 after reload](v6-dc01-r2/after-reload.png): both DC01 bodies render in the scoped views.
- [Native cache comparison](native-cache-verification.json) passes exact before/after floor and doorway fields in both successful runs. Physical boarding, cab traversal, all-family appearance and sound acceptance were not part of this performance round.
- [Official final profile](fixture-3g/final-summary.json), [failed full-stack v6 profile](v6-8g/summary.json), [successful subset profile](v6-dc01-r2/summary.json), raw logs and per-run windows are retained. Raw JFR recordings total about 51.4 MiB and remain in the project cache at the fingerprinted locations in the evidence index.
- MTR's beta notice appeared after the v6 world had saved. The first title-only close guard timed out; its [captured notice](v6-dc01-r2/exit-beta-warning.png) was dismissed with the displayed Escape instruction, then the original window keyboard layout was restored and the client closed normally. The helper now handles that explicit native screen.
- Four analysis regression controls pass; Java instrumentation/exporter compile and work on the real recordings. The exporter streams a small projection through `RecordingFile`, avoiding the standard JSON printer's recursive metadata expansion. The interrupted large JSON export was removed after recording its size/diagnosis; its source JFR is preserved.

JFR profile mode and the observation mod add overhead. This is one measured run per configuration, without an uninstrumented control; limited background preparation/analysis is documented in the walkthrough. The clean stable windows exclude the major export/launch work. The sample cannot establish long-session leaks, dense production-network behavior, shader performance, all-family gameplay or performance on the user's other hardware.

## Reproduce the profiling workflow

Use `tools/performance_test_instance.py` with a fresh copied instance/report directory, a stopped marked source, explicit heap/world and optional exact `--mtr-jar`. For v6 use `--without-companion`; the incompatible official companion is not silently adapted. The subset additionally requires `--subset-pack` and repeated exact `--vehicle-id` arguments from its launch provenance.

Capture startup/gameplay with the existing load monitor, issue native scene/reload/save actions with `tools/performance_gameplay.py`, then run `tools/analyze_performance_jfr.py` with the retained recording, explicit `windows.json`, JDK `jfr.exe`, the official MTR JAR as `--json-library`, and fresh `--export`/`--output` paths. The official summary uses the same raw recording as its initial summary and adds separate Java/native sample rankings. No production server commands or changes are required.
