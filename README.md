# MTR client memory companion

Target: Minecraft 1.21.1, Fabric, official MTR 4.1.0-beta.2 release SHA-256 `5da075f7d63daea89da17348ace0959a0c216cbaf14a322d063a64bec44aae94`.

The 16-pack set still exhausted a 12 GB Java heap after Shanghai model compaction and supported-field serialization. Reducing Java virtual-thread parallelism to two carriers also failed at 12 GB. A live heap histogram at a partial load counted 76,641,609 vertex records (3.68 GB of shallow object bytes) and 75,312,045 color objects (2.41 GB). These are sampled live objects, not a full retained-graph measurement.

The companion shares completed Blockbench parse groups using source-content SHA-256, resolved texture and V-flip setting. Each vehicle keeps an independent loader facade and property/position-dependent build cache. Door, display, mirror and car conditions continue through the original release implementation. Opaque white Blockbench vertex colors reuse the identical immutable `Color.WHITE` value. The read-through source-text cache is released after registration; active parsers retain their own input strings and subsequent requests can read resources again. Resource reload starts a fresh sharing epoch.

The original MTR JAR, vehicle definitions, geometry and artwork remain unchanged. With source-text cleanup, ordinary startup and F3+T resource reload both passed at an 8 GiB Java heap with all 16 packs: 2,541 registrations, completed model parsing and 60 seconds of stable observations without model-load errors. The test world rendered both native DC01 cars, with ready and distinct interaction caches. See [startup evidence](../vehicle-door-repair/game-test/all-16-memory-companion-v011-8gb-ordinary-startup.json) and [reload evidence](../vehicle-door-repair/game-test/all-16-memory-companion-v011-8gb-reload.json). The earlier run that requested diagnostic GC is recorded separately.

Install `mtr-memory-sharing.jar` in the **Fabric client's `mods` folder**, alongside the audited MTR release. Keep the repaired ZIPs enabled in `resourcepacks`. Set an **8 GiB maximum Java heap** and add these JVM arguments, as used in the passing tests:

```text
-Djdk.virtualThreadScheduler.parallelism=2
-Djdk.virtualThreadScheduler.maxPoolSize=2
```

This tested configuration uses Java 21 and Fabric Loader 0.20.1. The companion currently targets Fabric; NeoForge is not tested or packaged. The observed Java heap limit is not total process RAM: native and graphics allocations add to it. Peak sampled usage does not capture every allocation spike. Wider vehicle gameplay and lower heap limits remain unverified.

Build against the marked isolated client with Java 21:

```powershell
python -X utf8 tools/build_vehicle_memory_mod.py --javac '<Java 21 javac.exe>'
```

`--install-test` installs exclusively into the stopped, marked test client. The build rejects a different MTR release fingerprint and records source/JAR hashes. The companion belongs in the client's `mods` directory alongside MTR. The replacement ZIPs belong in `resourcepacks`. Removing the companion restores the original loader behavior.

The scheduler arguments affect Java virtual threads and are part of the tested configuration; alone they did not resolve the 12 GiB failure. The test launcher records them and installed mod hashes in each new benchmark report. Startup and reload still exceeded MTR's 60-second preload wait before parsing eventually completed, so the pack set can take several minutes to finish loading.
