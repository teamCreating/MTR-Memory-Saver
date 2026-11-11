# Property-selected display retention (v0.2.1)

Target: Minecraft 1.21.1 / NeoForge 21.1.265 / official MTR 4.1.0-beta.2. This separate candidate keeps the v0.2.0 packed mesh implementation byte-identical and retains raw display transforms only for names declared by each vehicle model as `PartType.DISPLAY`. Selection uses the actual release-created `ModelProperties`; display groups shared with normal geometry remain available. Each vehicle keeps its own model loader and native build cache. Unconfigured uses of the public loader factory retain all displays.

Source callbacks and display selection synchronize on the facade, supporting either ordering without losing required groups. Shared source loaders are released at registration return. Completed facades already own their mesh/display references; in-flight parses retain their completion entries. Later factory requests read and parse resources normally. Reload starts a new epoch. The parse counter is independent of the released cache size.

The independent unmodified-release consumer audit passes 10 part cases and compares 16 actual display instances, including duplicate/missing names, normal/door/floor/doorway/display types and ordinary/mirrored positions. Selected values retain their original object identities; native floors and doorways are unchanged. All 10 packed-mesh class entries match the previously accepted v0.2.0 JAR exactly.

The archived interim build failed full-pack startup at 4 GiB with heap exhaustion during registration and recovery to 423 built-ins. It passed ordinary 5 GiB startup with all 2,541 registrations, unfinished-to-complete parsing and 60 seconds of fresh stable samples. The final build corrects only the unique-parse metric and passed fresh ordinary 5 GiB startup plus actual F3+T reload, complete 2,541 registrations/parsing and 60 seconds of continuous fresh completed samples. Both native DC01 car bodies rendered before reload in survival mode and after reload from a spectator camera; both native floor/doorway caches remain unchanged. No diagnostic GC was requested during ordinary acceptance. The separate post-acceptance histogram reduced shallow live bytes from 3.04 to 2.31 GiB (24.17%), including StoredMatrixTransformations from 2,494,194 to 2,234. Total process peaks remain essentially unchanged. See [final acceptance](../../evidence/neoforge-v021-5gb-acceptance.json). v0.2.1 is the recommended tested NeoForge candidate.

Build with Java 21 into an explicit output, adding `--install-test` only for a stopped marked client:

```powershell
python -X utf8 tools/build_vehicle_memory_mod.py --instance .cache/game-test/neoforge-instance --javac <javac.exe> --packed-meshes --prune-displays --output vehicle-memory/dist/experiments/display-retention/mtr-memory-sharing-neoforge-v021.jar
python -X utf8 tools/audit_display_retention.py --instance .cache/game-test/neoforge-instance --candidate vehicle-memory/dist/experiments/display-retention/mtr-memory-sharing-neoforge-v021.jar --baseline vehicle-memory/dist/releases/mtr-memory-sharing-neoforge-v020.jar --output vehicle-memory/experiments/display-retention/consumer-audit.json
```

Ordinary memory measurements exclude diagnostic GC. Five GiB is still the lowest previously verified full-pack heap; this candidate does not establish 4 GiB support or repair the pending passenger exit/window issues.
