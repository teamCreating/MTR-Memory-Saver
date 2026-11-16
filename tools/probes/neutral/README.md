# Official native observer

This independent client JAR observes official MTR 4.1.0-beta.2 on Minecraft
1.21.1, Java 21 and the selected exact NeoForge target. Its version is independent
of the companion. It has no companion dependency, class linkage or reflection.

Build without launching a game:

```powershell
./gradlew.bat -Ptarget=official-nf248 neutralProbeJar verifyNeutralProbe
./gradlew.bat -Ptarget=official-nf265 neutralProbeJar verifyNeutralProbe
```

Each target produces `build/libs/mtr-native-observer-<target>-<version>.jar` and the
adjacent `.build.json`. The embedded `mtr-native-observer-target.json` freezes the
native ABI identity and output paths. `capabilities.json` distinguishes supported
native observations from unsupported companion measurements. Install the exact
same JAR bytes in baseline, candidate and instrumentation arms on the same loader.
The required Mixin guard verifies runtime Minecraft, Java, exact NeoForge and
official MTR SHA-256 before applying accessors/injections. It rejects the old
`vehicle_performance_probe`; the launcher must additionally enforce one frame
provider and reject other unqualified probes.

Installing this mod registers its JFR event types, but does not start a recording.
Plain trials still write native snapshots/epochs. Profile trials enable JFR in the
launcher and retain `mtrtest.ClientFrame` (double `intervalMs`, booleans `inWorld`
and `paused`, string `screen`) and `mtrtest.ServerTick`. Frame intervals measure
successive actual `RenderFrameEvent.Pre` callbacks; the first callback has no
preceding interval. Server tick duration spans the native Pre/Post events.
Neither event is a GPU presentation timing measurement.

The observer itself allocates and writes snapshots and scans the native registry
and existing caches. A plain/profile pair with the same observer only measures
the additional JFR/GC instrumentation cost. It does not qualify the observer's
own cost; a separate observer-off calibration is still required before claiming
complete instrumentation controls.

The one-second atomic snapshot is `game-probe/native-observer.json`, schema 1,
`probe_kind=official-native-observer`. `observed_at`/`timestamp` are UTC; the
monotonic timestamp is from the same process. `process` contains PID, actual
`start_instant`, executable and Java identity; top-level `pid`/`process_created`
mirror those fields. Unavailable process fields are null and cannot qualify a
trial. Other fields are `paused`, `in_world`, `screen` (null in game), `game_time`,
`heap` (`used_bytes`, `committed_bytes`, `max_bytes`), `registered_count` (distinct
ID strings across modes), `registered_declarations`, `native_pending`,
`native_settled` and `resource_epochs`. Settlement is an atomic counter read;
the observer never waits for native parsing.

Snapshot timestamps represent completion of its reads. `capture_started_at` and
`capture_started_monotonic_nanos` preserve the capture start; completion is never
backdated when native pending work settles during the capture. Output may finish
later. Native epoch timestamps retain the actual hook entry time instead.

Snapshot publication uses the shared probe-only `AtomicSnapshot` helper. On
Windows it uses `ReplaceFileW` for existing destinations and an atomic rename for
first publication; readers must grant delete sharing (the Python
`windows_snapshot_io.read_snapshot_bytes` helper does so). Windows
`MoveFileExW(REPLACE_EXISTING)` rejects open destinations even when readers grant
delete sharing. Publication errors remain visible and count as observation
failures. The helper uses Minecraft's existing JNA library and is excluded from
the companion product JAR.

`world` is null outside a world; otherwise it contains dimension, game time and
player x/y/z/yaw/pitch (player can be null during transition). `train_state` is
null when no world/native client instance exists. Otherwise it is
`{available:true,vehicles:[...]}`. Vehicles contain ID, transport mode, speed,
rail progress, door value, reversed state, route/platform/station IDs and
route/station names plus `car_resources` in native car order.

`cache_state` is similarly null when the scene is unavailable, otherwise
`{available:true,resources:[...]}` for the active vehicles' referenced resources.
Each resource has transport mode, resource ID, registered state and `entries`.
Entries preserve actual native `car_key`/`total_cars_key` and existing floor/doorway
boxes (`min_x/min_y/min_z/max_x/max_y/max_z`). Native resources normalize their
keys to 0/0; legacy suppliers use car/formation keys. An empty entry list means no
existing cache was observed. This read does not create caches, calculate vehicle
positions, invoke native model suppliers or bake geometry. These data do not
certify visual rendering, door animation, boarding or floor traversal.

Native epoch JSONL is `game-probe/native-resource-epochs.jsonl`. Each observed
`CustomResourceLoader.reload()V` HEAD/RETURN records `phase=start|return`,
`event=native_reload_head|native_reload_return`, `sequence`/`epoch_id`, UTC and
monotonic timestamps, process identity, thread name/ID, actual render-thread
status and stack depth, registration/native counters and started/completed/
in-flight totals. Exception exits remain unmatched. An outer RETURN after a
caught inner failure pairs only with the outer invocation. RETURN certifies
method return; the first later settled snapshot anchors actual loading
completion when native parsing was still pending at RETURN. Qualification must
retain the entire epoch file, including prior unmatched records, and filter by
exact process identity. A keyboard receipt alone does not certify a full reload.

`module_counters`, `active_read_permits` and `text_workspace` capabilities are
false. Corresponding measurement fields are omitted, never zero-filled.
`observation_errors` accumulates failed output/observation operations or unmatched
RETURNs. Stale/missing files, unavailable native/process observations and any
nonzero error count cannot qualify a trial. Existing native diagnostics still
need separate log/scene assessment; zero pending counters do not establish
valid geometry. The JUnit/ABI/JFR checks and archive reference audit verify tool
engineering only. Actual loader application and client qualification require
the separate real-client runs.
