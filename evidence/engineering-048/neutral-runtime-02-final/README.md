# Completed neutral observer 1.0.2 diagnostic run

Sealed on 2026-11-16 (UTC+08:00). `sealed-02/assessment.json` verifies the prior
official NeoForge 21.1.248 client, **Memory Saver 0.4.6**, official MTR
4.1.0-beta.2 and neutral observer 1.0.2. PID 41800 was independently observed
with creation time `2026-11-16T06:10:21.0898600Z`; it saved and exited normally
with code 0 at `06:37:59.183928Z`. This archive does not validate 0.4.7.

The completed collector preserves 1,199 distinct advancing native snapshots,
including 1,148 unpaused and settled in-world snapshots. The native registry
reports 1,092 declarations and 1,091 distinct ID strings. Both DC01 cache
entries retain 5/6 floors and 10 doorways each. All sixteen original and
installed pack hashes and the three actual mod hashes match the frozen plan.
Every input hashed during sealing remains unchanged afterward.

Two complete native resource epochs have paired HEAD/RETURN events on the
render thread and no in-flight work. Each of the two raw `Invalid model!` lines
has a matching empty-model/empty-texture official default `RailResource` call
and actual `BlockbenchModelLoader` fallback return. The frozen fail-closed
consumer accepts that attribution; `Failed to fetch user properties` remains
in the raw log and in the contextual-review list. Native attribution does not
establish visual harmlessness or whole-client performance.

`acceptance.jfr` and the live `diagnostic-01.jfr` dump are preserved byte-for-byte.
Both pass the actual JDK `jfr summary` command. The final recording contains
67,062 native frame events and 24,106 native server-tick events; 64,443 frame
events are unpaused and in-world. The exact bounded event export and its
uncompressed SHA-256 are retained. Event counts are observations, not an FPS
comparison or an endurance pass.

## Reload and gameplay limits

Both external F3+T receipts and both original before snapshots remain intact.
The IME-active attempt has no new native epoch. The later English-input attempt
does produce epoch 2, but its before snapshot is **17.005899 seconds** old,
exceeding the existing 15-second requirement. Strict accepted reloads remain
**0/20**. No input is discarded or approved retroactively.

The three original F2 images were independently inspected again: they show
station platforms or empty track, without a train body. They cannot grant
rendering, geometry, displays, doors, floors or boarding acceptance. UI debugging,
teleport commands, concurrent engineering and this instrumented diagnostic
collection also exclude controlled performance and two-hour route acceptance.

## Reproduce the sealed review

From the repository root, use a fresh report path:

```powershell
.venv/Scripts/python.exe -X utf8 evidence/engineering-048/neutral-runtime-02-final/verify.py `
  --sealed evidence/engineering-048/neutral-runtime-02-final/sealed-02 `
  --output .cache/neutral-runtime-02-verification.json
```

`verification-result.json` records the independent completed verification: all
116 sealed payloads and 54 frozen prefix payloads match their inventories, the
original diagnostic consumer reproduces its saved result exactly, and the
snapshot/JFR counts, normal exit and stale reload before are recomputed from
the retained raw data. This does not start or attach to a JVM.

`sealed-01/` preserves the initial archive failure and its exact script. That
prepared script incorrectly read the prefix index as a flat map; the existing
schema-1 index actually stores `files[path] = {sha256, bytes}`. The corrected
`archive.py` verifies that explicit schema, SHA and byte count. No source
evidence changed and the failed archive receives no acceptance. `sealed-02/`
is the fresh successful archive; both attempts remain in this directory.

The archive script only reads the stopped existing instance and invokes JDK
tools against copied JFR files. It does not launch/stop Minecraft or change
worlds, resource packs, mod artifacts, product code or v6 status. New 0.4.7
runtime evidence must use a fresh copied fixture and its own artifact identity.
