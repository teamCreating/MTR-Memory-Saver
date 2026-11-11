# Compressed resource text (v0.2.6 candidate)

Target: Minecraft 1.21.1 / NeoForge 21.1.265 / official MTR 4.1.0-beta.2. This variant starts from v0.2.2. Every existing companion class remains byte-identical, including geometry, properties, displays and interaction data. The rejected source-selection/mesh-view/block-pool experiments are excluded.

Both v0.2.5 allocation-failure stacks ended while the native read-through cache was collecting another full model String. This candidate redirects only that cache operation to compressed immutable text. It calls the exact original native reader function on a miss, preserving resource resolution, pack priority, debug reading, missing/empty behavior and original failures. Keys preserve the complete native resource ID; there are no special cases for individual vehicles or packs.

Compression stores exact UTF-16 code units, including BOM, newlines, supplementary characters, NUL and isolated surrogates. A miss returns the original String; a hit restores equal text. Incompressible data retains the original String rather than enlarging its payload. Reload and registration completion replace the map, so an older in-flight read cannot publish into a new epoch. Compression/decoder objects release their native state. Cache counters describe payloads, not measured JVM savings.

All 8,534 text files in the original MTR JAR and 16 selected pack archives pass exact roundtrips. Synthetic, empty/null/error/retry, namespace isolation, 64 concurrent reads with one native miss and overlapping reload checks pass. Offline requested inputs total 2,902,944,597 code units; compressed payloads total 1,026,235,694 bytes with 150,148 code units retained uncompressed. These are archive input totals, not the effective native cache population or runtime RAM measurements. [Audit](text-audit.json).

```powershell
python -X utf8 tools/build_vehicle_memory_mod.py --instance .cache/game-test/neoforge-instance --javac '<Java 21 javac.exe>' --packed-meshes --prune-displays --share-json --compress-texts --output vehicle-memory/dist/experiments/compressed-text/mtr-memory-sharing-neoforge-v026.jar
python -X utf8 tools/audit_compressed_resource_text.py --instance .cache/game-test/neoforge-instance --candidate vehicle-memory/dist/experiments/compressed-text/mtr-memory-sharing-neoforge-v026.jar --baseline vehicle-memory/dist/releases/mtr-memory-sharing-neoforge-v022.jar --output vehicle-memory/experiments/compressed-text/text-audit.json
```

Native mixin execution, full-pack startup/reload, DC01 rendering and 4 GiB acceptance now pass as recorded below. v0.2.6 is the recommended tested delivery; retain v0.2.2 for rollback.

Runtime acceptance passed: all 16 packs / 2,541 registrations, 290 objects and 23 rails complete at 4 GiB on startup and actual F3+T reload, each passing the 60-second stable threshold. Both DC01 bodies render before/after; exact floors and doorways match v0.2.2. Sampled process working-set peaks are 4.97 / 5.57 GiB versus baseline 6.00 / 6.57 GiB. No diagnostic GC was requested. Published the unchanged artifact as v0.2.6, retained v0.2.2 rollback, restored original player state and closed normally; original saved transport fields and all 16 pack selections/hashes passed. [Runtime acceptance](../../evidence/neoforge-v026-4gb-acceptance.json).
