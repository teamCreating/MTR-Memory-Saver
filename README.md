# MTR client memory companions

Current optimization target: **Minecraft 1.21.1 / NeoForge 21.1.265 / MTR 4.1.0-beta.2**, prioritizing memory use. The recommended tested candidate is [mtr-memory-sharing-neoforge-v021.jar](mtr-memory-sharing-neoforge-v021.jar), version **0.2.1**.

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
