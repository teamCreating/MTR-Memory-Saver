# Early source display selection (v0.2.5 candidate)

Target: Minecraft 1.21.1 / NeoForge 21.1.265 / official MTR 4.1.0-beta.2. This variant starts from v0.2.2; its packed-mesh bytecode remains unchanged. It keeps 23 unrelated companion class entries byte-identical and changes source-cache/facade ownership plus three scoped mixins.

The exact released vehicle constructors create their loader, immediately construct ModelProperties, then store the model supplier. Vehicle-only constructor redirects return a facade that starts its source parse when those actual DISPLAY names are available. Sources retain raw display metadata only for those names. Geometry groups, textures, native properties, position definitions, floors and doorways are unchanged. Different display requirements belong to different source-cache keys; later aliases cannot consume a source missing their required display data.

ObjectResource and RailResource also call the public factory. They keep eager loading and full source display data. Unowned loaders are not filtered. Failed parser attempts release the source registry entry and complete its internal future exceptionally while preserving the native parser error and unloaded state. Native parseFinished still executes normally.

Source-key/predicate/publication/failure-cleanup checks pass. The independent unmodified-release consumer audit passes all 10 part/door cases and 16 display instances, including preserved floors, doorways, multiplicity and raw display identities. The packed geometry implementation is byte-identical to the previous fully audited build; it inherits the 391-model mesh checks without changing that algorithm. Native constructor/mixin execution, full-pack startup/reload, rendering and lower-heap acceptance remain pending. Keep the tested v0.2.2 delivery until runtime acceptance succeeds.

```powershell
python -X utf8 tools/build_vehicle_memory_mod.py --instance .cache/game-test/neoforge-instance --javac '<Java 21 javac.exe>' --packed-meshes --prune-displays --share-json --source-displays --output vehicle-memory/dist/experiments/source-displays/mtr-memory-sharing-neoforge-v025.jar
python -X utf8 tools/audit_source_display_selection.py --instance .cache/game-test/neoforge-instance --candidate vehicle-memory/dist/experiments/source-displays/mtr-memory-sharing-neoforge-v025.jar --baseline vehicle-memory/dist/releases/mtr-memory-sharing-neoforge-v022.jar --output vehicle-memory/experiments/source-displays/source-audit.json
```

Use fresh result paths to preserve another run. Exact-release bytecode and scope records are retained alongside the audit results. Runtime logs count retained/skipped raw display parts; these counters are not heap measurements. Ordinary checks use the read-only external JVM sampler, with diagnostic GC separate afterward. Install only into a stopped marked test client.

Runtime result: all 16 packs / 2,541 vehicles, 290 objects and 23 rails passed ordinary 5 GiB startup and the 60-second stable threshold. Both DC01 bodies rendered before reload. Source filtering retained 2,242 and skipped 2,505,577 raw display parts, but the 4 GiB startup and actual 5 GiB F3+T reload both exhausted the heap while reading model text. Startup sampled process working set was about 6.04 GiB and external heap sampling approached the full 5 GiB limit. No useful RAM improvement or lower heap is established. Keep v0.2.2 as the recommended delivery. [Runtime evidence](../../evidence/neoforge-v025-runtime-result.json).

The failed client closed normally after restoring its original outside survival player. Saved transport fields and all 16 pack hashes passed; selections and the stopped installation were restored to v0.2.2. No diagnostic GC was requested.
