# Bounded resource-text retention (v0.3.0)

Target: Minecraft 1.21.1 / NeoForge 21.1.265 / official MTR 4.1.0-beta.2, Java 21.

The v0.2.9 compressed text cache retains every input until registration completes.
Earlier all-pack measurements record 592,010,155 compressed payload bytes. These
inputs can be read again from the resource manager; retaining all of them competes
with native parsing and model data at smaller heap limits.

The candidate admits compressed text to a least-recently-used cache with a default
budget of `Runtime.maxMemory() / 32` (96 MiB with `-Xmx3072M`). Entry weights include
compressed payload or a conservative two-byte-per-character raw String estimate,
key characters and an allowance for entry metadata. Empty values consume budget;
oversized entries are returned without retention. The optional JVM property
`mtr.memory.resourceTextCacheBytes` sets a byte budget, with zero disabling retention.
Evicted inputs are read normally on subsequent requests. This trades some repeat
reading/compression for less retained data; it does not omit resources.

Each reload swaps the whole cache epoch. In-flight readers retain only their old
epoch and cannot publish into a new one. Concurrent misses for a retained key use
the existing atomic reader operation. Admission/eviction bookkeeping is separate
from text decoding. The budget applies to admitted cache entries, not in-flight
reads, parser data, exact JVM object overhead, native allocations or GPU memory.

The codec and 30 other v0.2.9 classes are byte-identical. The enclosing cache and
its existing reload-log mixin change; one epoch class is added. Models, textures,
native parser algorithms, native movement/audio callback and mixin targets remain
unchanged.

```powershell
$testMarker = Get-Content .cache/game-test/neoforge-instance/vehicle-test-instance.json | ConvertFrom-Json
$testJavac = Join-Path (Split-Path $testMarker.java) javac.exe
python -X utf8 tools/build_vehicle_memory_mod.py --instance .cache/game-test/neoforge-instance --javac $testJavac --packed-meshes --prune-displays --share-json --compress-texts --segment-text-reads --segment-text-unpacks --stream-text-digests --bound-text-cache --output vehicle-memory/experiments/bounded-text-cache/mtr-memory-sharing-neoforge-v030.jar
python -X utf8 tools/audit_bounded_resource_text.py --instance .cache/game-test/neoforge-instance --candidate vehicle-memory/experiments/bounded-text-cache/mtr-memory-sharing-neoforge-v030.jar --baseline vehicle-memory/mtr-memory-sharing-neoforge-v029.jar --output vehicle-memory/experiments/bounded-text-cache/fresh-audit.json
```

[Offline checks](audit.json) pass all 8,534 real resource-text inputs, exact UTF-16
roundtrips, native first-read identity, null/error behavior, 64 concurrent same-key
requests, 500 concurrent churn inputs, 20,000 empty entries, oversize bypass, LRU
retention and reload isolation. The actual v0.2.9 negative control exceeds the
same 64 KiB test budget. The roundtrip audit deliberately uses a separate generous
cache budget to isolate codec semantics from eviction.

A fresh v0.2.9 client at exactly 3072 MiB fails startup with `OutOfMemoryError` and
falls back to 423 built-ins. The candidate's first startup completes all 16 packs,
2,541 vehicles and 651 unique source parses. Full native reload and repeated
process acceptance are being recorded separately; a title-screen count alone
does not establish gameplay availability.
