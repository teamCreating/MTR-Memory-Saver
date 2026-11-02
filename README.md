# MTR client memory companions

**Validation update:** the earlier read-only diagnostic replaced MTR's single native end-client-tick callback, affecting deferred player movement and scheduled sounds. The corrected additive observer preserves that callback and **passes two fresh full 4 GiB startup / actual F3+T reload runs**, all 16 packs / 2,541 registrations / 651 completed unique source parses per epoch, 60 seconds of fresh stability, both DC01 bodies and exact individual caches. The experimental passenger companion is absent in both comparisons. The earlier passes below retain their instrumented context. [Corrected-lifecycle acceptance and fingerprints](evidence/neoforge-v028-native-acceptance.json) and [investigation](../vehicle-door-repair/game-test/experiments/native-client-lifecycle/README.md).

Current optimization target: **Minecraft 1.21.1 / NeoForge 21.1.265 / official MTR 4.1.0-beta.2**. Recommended tested companion: [mtr-memory-sharing-neoforge-v028.jar](mtr-memory-sharing-neoforge-v028.jar), version **0.2.8**.

v0.2.8 restores large compressed resource-text cache hits through bounded UTF-16 segments, avoiding a complete temporary char array. Small inputs retain the previous path. It preserves exact code units, first-read identity, packing, concurrent reads, reload ownership, geometry, textures and native interaction data. Thirty v0.2.7 classes are byte-identical; only the nested Text implementation changes behavior, while its enclosing cache has identical native instructions with shifted debug lines. All 8,534 real input roundtrips and 44 actual-baseline boundary comparisons pass. Isolated cache-hit allocations fall **32.75% for ASCII / 39.61% for mixed text**; full Unicode grows 0.46% and small input allocation is unchanged. [Implementation, controls and reproduction](experiments/segmented-unpack/README.md).

Current corrected-lifecycle measurements:

| Test | External sampled Java heap peak | Windows working set peak | Private committed peak |
| --- | ---: | ---: | ---: |
| First startup | Not recorded externally | 4.969 GiB | 5.138 GiB |
| First reload | 3.783 GiB | 5.648 GiB | 5.795 GiB |
| Repeat startup | 3.676 GiB | 5.014 GiB | 5.182 GiB |
| Repeat reload | 3.902 GiB | 5.583 GiB | 5.761 GiB |

First-startup render-thread heap observations omit blocked parsing; the first reload's external sampler starts after F3+T. The repeat's external sampler covers blocked startup parsing and starts before the reload event. These are sampled peaks, not true maxima. Four GiB denotes the Java heap limit; total process RAM still reaches about 5.6 GiB during reload. Both processes close normally after original player/window-layout restoration; saved transport fields, all pack hashes/order and exact mod fingerprints verify. No diagnostic GC or clock command was requested.

An experimental [v0.2.9 candidate](experiments/streamed-digest/README.md) bounds UTF-8 hashing buffers for both shared caches. Exact keys for all 8,534 real inputs, Unicode boundaries, concurrent hashing and an unchanged-baseline allocation control pass. Large hashing allocations fall over 99.8%, with unchanged small-input allocation and a Unicode timing tradeoff. These are isolated allocations; native startup/reload and actual process peaks remain pending. Keep v0.2.8 installed until acceptance.

**Historical instrumented acceptance:** two fresh 4 GiB clients each pass startup and actual foreground F3+T reload, all **16 packs / 2,541 vehicles / 290 objects / 23 rails**, with 651 unique source parses and 60 seconds of continuous fresh completed observations in every epoch. Both actual DC01 bodies render; their distinct 5/6-floor and 10/10-doorway caches match v0.2.7 exactly before/after reload. The first run captures open doors and the repeat captures closed doors. No diagnostic GC was requested. Original player/window layout, saved transport inventory/fields, pack hashes/order and mod identities verify after normal shutdown. Those runs used the former singleton-callback observer; the corrected native lifecycle comparison is reported above. [Historical acceptance and fingerprints](evidence/neoforge-v028-acceptance.json).

| Test | Sampled Java heap peak | Windows working set peak | Private committed peak |
| --- | ---: | ---: | ---: |
| First startup | 3.807 GiB | 5.015 GiB | 5.184 GiB |
| First reload | 3.841 GiB | 5.551 GiB | 5.720 GiB |
| Repeat startup | 3.793 GiB | 5.018 GiB | 5.185 GiB |
| Repeat reload | 3.964 GiB | 5.593 GiB | 5.758 GiB |

These are sampled peaks in an isolated fixture, not true maxima or production-world guarantees. Process startup peaks are about 5.02 GiB; reload still reaches about 5.6 GiB. The allocation reduction does not establish lower retained heap or lower total reload RAM than v0.2.7. Both runs kept experimental passenger v0.1.1 and the unchanged read-only probe fixed; the fixture-control probe was absent.

**4 GiB is the lowest repeatably verified heap.** Three GiB exhausts the heap during startup. One complete 3.5 GiB run passed, but its fresh repeat reload failed at the native reader's final String allocation and recovered to only 423 built-ins; that recovery is not all-pack success. Both failures and restored selections are preserved. Wider Shanghai windows, all-vehicle gameplay and passenger re-entry/exit acceptance remain open; the passenger companion is still experimental.

Install exactly one memory companion in the NeoForge client's `mods` directory alongside the matching official MTR release, replacing the previous memory companion. Keep repaired ZIPs in `resourcepacks`. Use Java 21 and these tested arguments:

```text
-Xms1G -Xmx4G
-Djdk.virtualThreadScheduler.parallelism=2
-Djdk.virtualThreadScheduler.maxPoolSize=2
```

SHA-256: `d934a8d255be16253c753b061e7d92d942985c0ee7debc1892c90ef7ecfdb40c`. Keep [v0.2.7](mtr-memory-sharing-neoforge-v027.jar) and [v0.2.2](mtr-memory-sharing-neoforge-v022.jar) for rollback. The stopped isolated client retains the exact tested v0.2.8/mod context; no production instance was replaced.

## Earlier v0.2.7 results

Previously tested companion target: **Minecraft 1.21.1 / NeoForge 21.1.265 / official MTR 4.1.0-beta.2**. Earlier companion: [mtr-memory-sharing-neoforge-v027.jar](mtr-memory-sharing-neoforge-v027.jar), version **0.2.7**.

v0.2.7 retains v0.2.6's lossless compressed text cache and changes the native resource-text reader to bounded segments with one final String allocation. All 30 v0.2.6 class entries remain byte-identical. The active commons-io decoder comparison passes all 8,534 real text inputs and 51 synthetic cases; isolated reader allocations fall 58.1% for ASCII and 44.2% for Unicode. Geometry, textures and native interaction data are preserved. [Implementation and reproduction](experiments/segmented-reader/README.md).

**Two fresh 4 GiB clients each passed startup and actual foreground F3+T reload**, all 16 packs / 2,541 vehicles / 290 objects / 23 rails, with 651 completed unique source parses and 60-second stable fresh observations in every epoch. No OOM, model-load failure or diagnostic GC occurred. Both DC01 bodies and open/closed door states render; independent 5/6-floor and 10/10-doorway caches match v0.2.6 exactly. [Acceptance and fingerprints](evidence/neoforge-v027-4gb-acceptance.json).

| Test | Heap limit | Sampled JVM heap peak | Sampled Windows working set peak |
| --- | ---: | ---: | ---: |
| v0.2.7 first startup | 4 GiB | 3.734 GiB | 5.369 GiB |
| v0.2.7 repeat startup | 4 GiB | 3.768 GiB | 5.596 GiB |
| v0.2.7 first reload | 4 GiB | 3.777 GiB | 5.592 GiB |
| v0.2.7 repeat reload | 4 GiB | 3.871 GiB | 5.581 GiB |
| Earlier v0.2.2 startup | 5 GiB | See historical sampling limits below | 6.00 GiB |
| Earlier v0.2.2 reload | 5 GiB | See historical sampling limits below | 6.57 GiB |

Read-only external jstat covers blocked rendering. These are sampled peaks in an isolated fixture, not true maxima or production-world guarantees. Four GiB passed twice with all selected packs; total process RAM still reached about 5.6 GiB. Both v0.2.7 runs kept experimental passenger v0.1.1 fixed, whereas the historical v0.2.2 baseline used a different heap limit and omitted that companion. The two successful runs support repeatability in this fixture; they do not establish lower process RAM than v0.2.6's earlier successful run. Original player, saved transport fields, all 16 ZIP hashes/selections and test mod identities passed verification after normal shutdown. Wider Shanghai window and vehicle gameplay coverage remains open; the passenger companion remains experimental.

Install exactly one memory companion in `mods` alongside the official matching MTR release, replacing the previous memory companion. Keep the repaired ZIPs in `resourcepacks`. Use Java 21 and the tested arguments:

```text
-Xms1G -Xmx4G
-Djdk.virtualThreadScheduler.parallelism=2
-Djdk.virtualThreadScheduler.maxPoolSize=2
```

SHA-256: `3efb9abd068998f1605639a1d6d6145a67cee978f1f3dae29bcfc4ac542badd5`. Retain [v0.2.6](mtr-memory-sharing-neoforge-v026.jar) and [v0.2.2](mtr-memory-sharing-neoforge-v022.jar) for rollback; v0.2.6 has the 4 GiB limitation recorded below and v0.2.2 passed at 5 GiB.

## Earlier v0.2.6 results

Previously delivered companion: [mtr-memory-sharing-neoforge-v026.jar](mtr-memory-sharing-neoforge-v026.jar), version **0.2.6**.

v0.2.6 keeps cached resource text compressed until registration completes, then releases the cache. Misses use the unchanged native reader; hits restore exact UTF-16 content. Every v0.2.2 model-processing class remains byte-identical. All 8,534 archive text inputs, concurrent reads and overlapping reload checks pass. [Implementation and reproduction](experiments/compressed-text/README.md).

All **16 packs / 2,541 vehicles, 290 objects and 23 rails** pass ordinary startup and actual foreground **F3+T reload at 4 GiB**, each with a 60-second stable check. Both DC01 bodies render before and after reload; their exact independent 5/6-floor and 10/10-doorway caches match v0.2.2. No diagnostic GC was requested. [Acceptance and fingerprints](evidence/neoforge-v026-4gb-acceptance.json).

| Candidate / test | Heap limit | Windows working set peak | Private committed peak |
| --- | ---: | ---: | ---: |
| v0.2.2 startup | 5 GiB | 6.00 GiB | 6.19 GiB |
| v0.2.6 startup | 4 GiB | 4.97 GiB | 5.16 GiB |
| v0.2.2 reload | 5 GiB | 6.57 GiB | 6.75 GiB |
| v0.2.6 reload | 4 GiB | 5.57 GiB | 5.75 GiB |

These are single-run sampled process values. The external JVM sampler covered blocked render-thread loading; its startup/reload heap peaks were 3.91 / 3.92 GiB. Each native registration epoch cached 2,000,187,675 text code units as 592,010,155 compressed bytes plus 13,792 uncompressed code units, then released the cache. This payload accounting is separate from process measurements. Four GiB is the lowest verified heap in the saved fixture; larger worlds may require more. Wider vehicle, Shanghai-window and passenger-exit checks remain open.

A later full-pack **4 GiB startup failed** during native resource-text reading, with unchanged v0.2.6 alongside the experimental passenger v0.1.1. It recovered to 423 built-ins without opening a world. The additional companion is recorded as test context; this does not establish it as the cause. The earlier 4 GiB startup/reload success remains valid, but **4 GiB repeatability is not established**. Follow-up testing at 5 GiB and transient-allocation investigation are in progress. [Failure evidence](../vehicle-interaction/evidence/neoforge-passenger-v011-4gb-failure.json).

Install exactly one companion in `mods` alongside the fingerprinted official MTR release, replacing the previous companion. Keep all 16 repaired ZIPs enabled in `resourcepacks`. The earlier successful Java 21 run used the following settings; they are a recorded result, not a repeatably reliable 4 GiB recommendation:

```text
-Xms1G -Xmx4G
-Djdk.virtualThreadScheduler.parallelism=2
-Djdk.virtualThreadScheduler.maxPoolSize=2
```

SHA-256: `0fabb984dfec04ef7f4f921433730499c7c0cd242f238d656b094c389ba06c93`. The test client closed normally after restoring its original player; original saved transport fields, all pack hashes and selections passed. Keep [v0.2.2](mtr-memory-sharing-neoforge-v022.jar) for rollback with its tested 5 GiB settings.

## Earlier v0.2.2 results

Current optimization target: **Minecraft 1.21.1 / NeoForge 21.1.265 / MTR 4.1.0-beta.2**, prioritizing memory use. The previous tested companion is [mtr-memory-sharing-neoforge-v022.jar](mtr-memory-sharing-neoforge-v022.jar), version **0.2.2**.

v0.2.2 shares identical nonempty property/position JSON trees by input-text SHA-256. Each vehicle keeps an independent native JsonReader map, ModelProperties, PositionDefinitions and build caches. Registration releases cache-owned trees; resource reload starts a fresh cache. All 24 existing v0.2.1 class entries are byte-identical. The unmodified-release audit passed 1,397 real inputs and 2,818 native-reader comparisons, including independent merges and unchanged input trees. [Implementation and reproduction](experiments/json-sharing/README.md).

All **16 packs / 2,541 registrations** passed ordinary startup and actual F3+T reload at **5 GiB**, with 60 seconds of continuous fresh completed samples in each check. Startup sampling began after parsing completed; reload observed unfinished parsing followed by completion. Both original DC01 bodies rendered before and after reload; their distinct 5/6-floor and 10/10-doorway caches stayed identical. No diagnostic GC was requested during ordinary acceptance. [Acceptance and exact fingerprints](evidence/neoforge-v022-5gb-acceptance.json).

| Candidate / test | Sampled Java heap | Windows working set | Private committed memory |
| --- | ---: | ---: | ---: |
| v0.2.1 startup | 3.97 GiB | 6.02 GiB | 6.17 GiB |
| v0.2.2 startup | 2.13 GiB* | 6.00 GiB | 6.19 GiB |
| v0.2.1 reload | 4.58 GiB | 6.63 GiB | 6.79 GiB |
| v0.2.2 reload | 4.60 GiB | 6.57 GiB | 6.75 GiB |

*The render-thread probe could not sample startup allocations while parsing blocked it. Its 2.13 GiB result covers completed observations and cannot establish the true startup heap peak. These are single-run sampled values; total process peaks changed little.

The separate post-acceptance GC histogram measured **1,871,160,520 shallow live bytes (1.74 GiB)**, versus 2,478,233,672 for v0.2.1: **607,073,152 bytes / 579 MiB / 24.50% less**. Core MTR Gson rows fell from 385,752,224 to 99,865,272 shallow bytes. These diagnostics both requested GC at 5 GiB and measure shallow live objects, not retained graphs, ordinary peaks or production-world limits. [Diagnostic comparison](evidence/neoforge-v022-json-sharing-diagnostic-comparison.json).

Install exactly one companion in the NeoForge client's `mods` directory alongside the fingerprinted official MTR release, replacing the previous companion. Keep all 16 repaired ZIPs enabled in `resourcepacks`. Use Java 21 and the tested arguments:

```text
-Xmx5G
-Djdk.virtualThreadScheduler.parallelism=2
-Djdk.virtualThreadScheduler.maxPoolSize=2
```

**5 GiB remains the lowest verified heap.** v0.2.2 exhausted 4 GiB during registration; its attempted fallback became unresponsive and was cleaned up after verifying the marked process identity. That attempt opened no integrated world and all 16 selections were restored. The successful 5 GiB client closed normally, saving its world and player through server shutdown; original formation/timetable/platform fields and every selected ZIP hash were verified. Passenger exit and broad Shanghai window/vehicle coverage remain open. Removing this companion or replacing it with the retained [v0.2.1 JAR](mtr-memory-sharing-neoforge-v021.jar) provides rollback.

## Earlier v0.2.1 results

The previous tested companion is [mtr-memory-sharing-neoforge-v021.jar](mtr-memory-sharing-neoforge-v021.jar), version **0.2.1**.

v0.2.1 retains raw display transforms only for actual `DISPLAY` part names and releases shared source-loader references after registration. It keeps all 10 v0.2.0 packed-mesh class entries byte-identical. The independent official-release cache-consumer audit passes 10 cases and 16 actual display instances; required display data retains its original identities and native floor/doorway semantics.

All 16 repaired packs passed ordinary startup and actual F3+T reload at a **5 GiB heap**, with 2,541 registrations, observed unfinished-to-complete parsing and 60 seconds of continuous fresh completed samples. Both native DC01 bodies rendered before/after reload, and both distinct floor/doorway caches remain identical. The post-reload rendering observation used a spectator camera after ordinary acceptance. No diagnostic GC was requested during those ordinary checks. See [v0.2.1 acceptance and fingerprints](evidence/neoforge-v021-5gb-acceptance.json).

| Candidate / test | Sampled Java heap peak | Windows working set | Private committed memory |
| --- | ---: | ---: | ---: |
| v0.2.0 startup | 4.58 GiB | 6.03 GiB | 6.19 GiB |
| v0.2.1 startup | 3.97 GiB | 6.02 GiB | 6.17 GiB |
| v0.2.0 reload | 4.66 GiB | 6.59 GiB | 6.77 GiB |
| v0.2.1 reload | 4.58 GiB | 6.63 GiB | 6.79 GiB |

The separate post-acceptance diagnostic histogram found **2.31 GiB of shallow live objects**, versus 3.04 GiB for v0.2.0: **753 MiB / 24.17% less**. Retained `StoredMatrixTransformations` fell from 2,494,194 to 2,234; no `StoredVertexData` row remains in either packed candidate. Both diagnostics requested GC at different tested heap limits and are excluded from ordinary acceptance. This shows less live metadata; total process peaks are essentially unchanged in these single runs. See [diagnostic comparison](evidence/neoforge-v021-display-retention-diagnostic-comparison.json).

Install exactly one memory companion in the NeoForge client `mods` directory alongside the fingerprinted official MTR release, replacing the previous companion. Keep the 16 repaired ZIPs enabled in `resourcepacks`. The verified Java 21 settings remain:

```text
-Xmx5G
-Djdk.virtualThreadScheduler.parallelism=2
-Djdk.virtualThreadScheduler.maxPoolSize=2
```

Five GiB remains the lowest verified heap. The interim 4 GiB attempt exhausted the heap during registration; the final logging-counter correction does not establish 4 GiB support. Broader vehicle/window/passenger checks remain open. The isolated client is closed, its original formation/timetable/platform settings and selected pack hashes were verified, and the test player was returned to survival mode at the original platform. [Implementation and reproduction](experiments/display-retention/README.md).

## Earlier v0.2.0 and Fabric results

Earlier v0.2.0 target: **Minecraft 1.21.1 / NeoForge 21.1.265 / MTR 4.1.0-beta.2**. The earlier tested candidate is [mtr-memory-sharing-neoforge-v020.jar](mtr-memory-sharing-neoforge-v020.jar), version **0.2.0**. It compresses retained parsed meshes without changing vertex values, geometry, textures or native interaction boxes. The original MTR JAR and repaired pack ZIPs are unchanged.

All 16 repaired packs passed ordinary startup and actual **F3+T reload at a 5 GiB Java heap**: 2,541 registrations, observed unfinished -> complete parsing and 60 seconds of continuous fresh stable observations in each check. Both DC01 car bodies, interiors and open doors rendered before and after reload; their distinct floor/doorway caches remained individually identical. No diagnostic GC was requested during the 5 GiB tests. See [5 GiB acceptance and exact fingerprints](evidence/neoforge-v020-5gb-acceptance.json).

Install the v0.2.0 JAR in the **NeoForge client's `mods` directory**, in place of the older memory companion. Keep exactly one companion JAR alongside official MTR release SHA-256 `ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa`. Enable the repaired ZIPs in `resourcepacks`. The tested Java 21 settings are:

```text
-Xmx5G
-Djdk.virtualThreadScheduler.parallelism=2
-Djdk.virtualThreadScheduler.maxPoolSize=2
```

Measured sampled peaks in the isolated acceptance instance:

| Companion / test | Maximum Java heap | Sampled heap | Windows working set | Private committed memory |
| --- | ---: | ---: | ---: | ---: |
| v0.1.1 startup | 8 GiB | 7.52 GiB | 9.09 GiB | 9.26 GiB |
| v0.1.1 reload | 8 GiB | 7.62 GiB | 9.93 GiB | 10.10 GiB |
| v0.2.0 startup | 5 GiB | 4.58 GiB | 6.03 GiB | 6.19 GiB |
| v0.2.0 reload | 5 GiB | 4.66 GiB | 6.59 GiB | 6.77 GiB |

These are separate Java/process measurements and sampled peaks, not true maxima or arbitrary production-world limits. Preparing this large model set still takes minutes. [6 GiB tests](evidence/neoforge-v020-6gb-acceptance.json) also passed; the [4 GiB attempt](evidence/neoforge-v020-4gb-result.json) failed with heap exhaustion and fallback to 423 built-ins. That recovery is not full-pack success.

Independent comparisons with unmodified actual release methods passed all **391 Shanghai models / 47,373,240 parsed vertices**, plus **1,200,028 synthetic vertex comparisons**. Raw float bits, ARGB, emitted lighting/overlay arguments, vertex order/multiplicity and native boxes are preserved. Only synthetic arithmetic NaNs permit Java's unspecified payload variation; actual model comparisons remain bit-exact. A separate post-6-GiB-acceptance GC histogram found no retained `StoredVertexData` row, versus 79,359,867 records in the old baseline. Its 3,267,958,752 total shallow live bytes are diagnostic data and are excluded from ordinary memory acceptance. See [implementation/audit details](experiments/packed-mesh/README.md).

The ordinary first-DC01-car smoke check passed entry and failed exit. That failure and wider window/passenger/vehicle coverage remain open; the memory result does not claim all vehicle gameplay is repaired. The original formation, timetable and platform fields were verified after testing, all 16 selections remain enabled, and the isolated client is closed.

The unversioned `mtr-memory-sharing-neoforge.jar` and default build remain the older **v0.1.1** at 8 GiB. The v0.1.2 identity-reuse experiment did not reduce retained vertex counts and failed at 6 GiB; it is archived. Build the tested packed candidate explicitly with Java 21:

```powershell
python -X utf8 tools/build_vehicle_memory_mod.py --instance '.cache/game-test/neoforge-instance' --javac '<Java 21 javac.exe>' --packed-meshes --output 'vehicle-memory/experiments/packed-mesh/mtr-memory-sharing-neoforge-v020.jar'
```

Add `--install-test` only for the stopped marked test client. Build metadata records exact source, game, MTR and output fingerprints. The optional read-only `tools/build_neoforge_memory_probe.py` is exclusively for that test instance and is not part of the delivery companion.

Verified Fabric target: Minecraft 1.21.1, official MTR 4.1.0-beta.2 release SHA-256 `5da075f7d63daea89da17348ace0959a0c216cbaf14a322d063a64bec44aae94`.

The 16-pack set still exhausted a 12 GB Java heap after Shanghai model compaction and supported-field serialization. Reducing Java virtual-thread parallelism to two carriers also failed at 12 GB. A live heap histogram at a partial load counted 76,641,609 vertex records (3.68 GB of shallow object bytes) and 75,312,045 color objects (2.41 GB). These are sampled live objects, not a full retained-graph measurement.

The companion shares completed Blockbench parse groups using source-content SHA-256, resolved texture and V-flip setting. Each vehicle keeps an independent loader facade and property/position-dependent build cache. Door, display, mirror and car conditions continue through the original release implementation. Opaque white Blockbench vertex colors reuse the identical immutable `Color.WHITE` value. The read-through source-text cache is released after registration; active parsers retain their own input strings and subsequent requests can read resources again. Resource reload starts a fresh sharing epoch.

The original MTR JAR, vehicle definitions, geometry and artwork remain unchanged. With source-text cleanup, ordinary startup and F3+T resource reload both passed at an 8 GiB Java heap with all 16 packs: 2,541 registrations, completed model parsing and 60 seconds of stable observations without model-load errors. The test world rendered both native DC01 cars, with ready and distinct interaction caches. See [startup evidence](../vehicle-door-repair/game-test/all-16-memory-companion-v011-8gb-ordinary-startup.json) and [reload evidence](../vehicle-door-repair/game-test/all-16-memory-companion-v011-8gb-reload.json). The earlier run that requested diagnostic GC is recorded separately.

Install `mtr-memory-sharing.jar` in the **Fabric client's `mods` folder**, alongside the audited MTR release. Keep the repaired ZIPs enabled in `resourcepacks`. Set an **8 GiB maximum Java heap** and add these JVM arguments, as used in the passing tests:

```text
-Djdk.virtualThreadScheduler.parallelism=2
-Djdk.virtualThreadScheduler.maxPoolSize=2
```

This tested Fabric configuration uses Java 21 and Fabric Loader 0.20.1. NeoForge is packaged and measured separately above. The observed Java heap limit is not total process RAM: native and graphics allocations add to it. Peak sampled usage does not capture every allocation spike. Wider vehicle gameplay and lower heap limits remain unverified.

Build against the marked isolated client with Java 21:

```powershell
python -X utf8 tools/build_vehicle_memory_mod.py --javac '<Java 21 javac.exe>'
```

`--install-test` installs exclusively into the stopped, marked test client. The build rejects a different MTR release fingerprint and records source/JAR hashes. The companion belongs in the client's `mods` directory alongside MTR. The replacement ZIPs belong in `resourcepacks`. Removing the companion restores the original loader behavior.

The scheduler arguments affect Java virtual threads and are part of the tested configuration; alone they did not resolve the 12 GiB failure. The test launcher records them and installed mod hashes in each new benchmark report. Startup and reload still exceeded MTR's 60-second preload wait before parsing eventually completed, so the pack set can take several minutes to finish loading.

The subsequent all-pack session rendered DC01 Update, 02A02 and 11A01. A [gameplay memory sample](evidence/shanghai-window-session-observation.json) recorded 7.55 GiB of Java heap, 10.24 GiB of Windows process working set and 10.42 GiB of private committed memory. These are separate measurements from one observation, not peak or long-session limits. The [window checks](../vehicle-door-repair/game-test/shanghai-02a02-11a01-windows.json) cover ordinary entry and both side-window views of the first selected car of 02A02 and 11A01. The isolated fixture was restored and the client closed normally after testing.

The ordinary post-reload DC01 smoke test passed empty-hand entry but failed ordinary exit; the player remained mounted at the doorway. This failure is preserved for the vehicle investigation. A separate **post-acceptance** GC histogram found no retained `StoredVertexData` row and 3,267,958,752 total shallow live bytes (about 3.04 GiB), versus 79,359,867 vertex records in the older baseline. This diagnostic requested GC and is excluded from ordinary startup/reload measurements. The fresh 4 GiB attempt failed with heap exhaustion and automatic fallback to 423 built-ins. The restored all-16-pack 5 GiB startup and reload both passed; 5 GiB is now the lowest verified heap for this candidate.
