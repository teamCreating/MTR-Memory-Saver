# Segmented native resource-text reader v0.2.7

Target: Minecraft 1.21.1 / NeoForge 21.1.265 / official MTR 4.1.0-beta.2. This separate candidate adds two classes to v0.2.6; every existing v0.2.6 class entry remains byte-identical.

A later 4 GiB full-pack v0.2.6 run exhausted the heap while native IOUtils repeatedly grew a complete model-text StringBuilder. This candidate redirects only IOUtils.toString inside the exact released ResourceManagerHelper UTF-8 string-reading lambda. The same InputStreamReader decoder fills bounded character segments, and public String.join builds the final String once. It preserves UTF-16 code units across segment boundaries. Resource lookup, priority, debug reading, outer stream closure and native error handling remain intact; no model, texture or interaction behavior changes.

The audit compares against the unique active commons-io 2.15.1 JAR, covering all 8,534 asset JSON/Blockbench/OBJ/MTL inputs in the official release and selected 16 archives. It passes 51 synthetic comparisons including multiple charsets, malformed sequences, split supplementary characters, BOM, NUL and short reads. Ownership and propagated I/O failure checks pass.

Isolated allocation counters across three warmed reads measure 127,270,416 native bytes versus 53,278,992 candidate bytes for 8,800,000 ASCII code units (58.1% lower); 129,588,240 versus 72,326,808 for 4,800,000 Unicode code units (44.2% lower). These controls establish allocation reduction in the reader, not full-client peak memory or 4 GiB reliability. [Audit](reader-audit.json).

Native mixin application, full-pack startup/reload, rendering and repeatable heap acceptance remain pending. Keep v0.2.6 as the delivered artifact, with its documented 4 GiB repeatability limitation. The live passenger client still runs unchanged v0.2.6.

```powershell
python -X utf8 tools/build_vehicle_memory_mod.py --instance .cache/game-test/neoforge-instance --javac '<Java 21 javac.exe>' --packed-meshes --prune-displays --share-json --compress-texts --segment-text-reads --output vehicle-memory/experiments/segmented-reader/mtr-memory-sharing-neoforge-v027.jar
python -X utf8 tools/audit_segmented_resource_text.py --instance .cache/game-test/neoforge-instance --candidate vehicle-memory/experiments/segmented-reader/mtr-memory-sharing-neoforge-v027.jar --baseline vehicle-memory/mtr-memory-sharing-neoforge-v026.jar --output vehicle-memory/experiments/segmented-reader/reader-audit.json
```

Use fresh output paths and install only into a stopped marked test client. Removal/replacement with unchanged v0.2.6 provides rollback.
