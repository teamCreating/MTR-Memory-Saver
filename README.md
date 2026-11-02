# MTR client memory companions

Current optimization target: Minecraft **1.21.1 / NeoForge / MTR 4.1.0-beta.2**, with memory use first. The new NeoForge artifact is `mtr-memory-sharing-neoforge.jar`, built against official MTR release SHA-256 `ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa`. It uses the same parse-sharing, independent vehicle build caches, source-text cleanup and immutable white colors as the Fabric companion. Loader-specific source sets provide the appropriate Minecraft classes; the original Fabric artifact is retained.

The separate marked test instance uses NeoForge 21.1.265 and Java 21. With the v0.1.1 companion, all 16 packs passed ordinary startup and actual F3+T reload at an 8 GiB heap with the two-carrier scheduler settings below: 2,541 registrations, complete parsing and 60 seconds of continuous stable observations. Sampled heap / working set / private commit peaks were **7.52 / 9.09 / 9.26 GiB** at startup and **7.62 / 9.93 / 10.10 GiB** during reload. Neither acceptance run requested diagnostic GC. See [NeoForge evidence](evidence/neoforge-v011-acceptance.json). Keep the Fabric measurements below separate from these results.

Build and install exclusively in the stopped isolated NeoForge client:

```powershell
python -X utf8 tools/build_vehicle_memory_mod.py --instance '.cache/game-test/neoforge-instance' --javac '<Java 21 javac.exe>' --install-test
```

The optional `tools/build_neoforge_memory_probe.py` builds a read-only loading probe into that marked test instance; it is not part of the delivery companion. The load monitor records the actual loader/version, asynchronous parsing completion and separate Windows working-set/private-commit observations. Neither launching a window nor reaching the registration count establishes completed parsing or vehicle acceptance.

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
