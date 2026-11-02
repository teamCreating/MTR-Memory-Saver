# Shared vehicle configuration JSON (v0.2.2)

Target: Minecraft 1.21.1 / NeoForge 21.1.265 / official MTR 4.1.0-beta.2. This candidate shares identical parsed property/position JSON trees inside VehicleModel constructors, while each vehicle keeps an independent JsonReader map, ModelProperties, PositionDefinitions and native build/cache state. All existing v0.2.1 class entries remain byte-identical.

The exact release JsonReader constructor copies top-level entries into a new map; reads consume children without modifying them. Its merge method modifies only that independent map. The candidate keys valid nonempty trees by SHA-256 of the input text and delegates parsing to the original Utilities.parseJson. Empty/malformed/null handling remains delegated without caching empty fallback objects. Registration completion releases cache-owned trees and reload starts a fresh cache; readers retain needed children. The mixin is scoped to property/position parsing in VehicleModel constructors and does not intercept worker parsing of Blockbench models.

The effective native inventory contains 4,026 model entries, 8,052 JSON requests and 1,397 distinct inputs by kind. Repeated input text totals 118,245,455 bytes versus 32,224,402 unique bytes; these are input sizes, not measured heap savings. Built-in and constructed legacy requests are excluded from that inventory.

The independent unmodified-release audit passes all 1,397 real inputs and 2,818 native-reader comparisons. Native serialization, unchanged source trees, reader-local merges, malformed/empty handling, registration release and reload checks pass. All v0.2.1 class entries match exactly. Offline Log4j format warnings are preserved separately. A fresh full-16-pack 4 GiB startup is running; runtime startup/reload/render/memory results remain pending. v0.2.1 remains the recommended tested delivery.

```powershell
python -X utf8 tools/build_vehicle_memory_mod.py --instance .cache/game-test/neoforge-instance --javac <javac.exe> --packed-meshes --prune-displays --share-json --output vehicle-memory/experiments/json-sharing/mtr-memory-sharing-neoforge-v022.jar
python -X utf8 tools/inventory_vehicle_json.py --instance .cache/game-test/neoforge-instance --jobs vehicle-memory/experiments/json-sharing/consumer-jobs.json --report vehicle-memory/experiments/json-sharing/native-input-inventory.json
python -X utf8 tools/audit_vehicle_json_sharing.py --instance .cache/game-test/neoforge-instance --candidate vehicle-memory/experiments/json-sharing/mtr-memory-sharing-neoforge-v022.jar --baseline vehicle-memory/mtr-memory-sharing-neoforge-v021.jar --jobs vehicle-memory/experiments/json-sharing/consumer-jobs.json --output vehicle-memory/experiments/json-sharing/consumer-audit.json
```

Install into the stopped marked test client only after auditing. Ordinary acceptance excludes diagnostic GC. No lower-heap or broad passenger/window acceptance is claimed by the offline audit.
