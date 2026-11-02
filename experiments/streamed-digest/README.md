# Bounded resource-text digests (v0.2.9 candidate)

Target: Minecraft 1.21.1 / NeoForge 21.1.265 / official MTR 4.1.0-beta.2. This is an experimental extension of the delivered v0.2.8 memory companion. v0.2.8 remains recommended until native startup, reload and rendering acceptance passes.

The shared Blockbench and vehicle-configuration caches calculate their content keys from `raw.getBytes(UTF_8)`. Each large request therefore allocates a complete encoded copy before hashing, even when a parsed input is already shared. This candidate hashes the same bytes through an 8192-byte UTF-8 encoder buffer. It reuses a 4096-unit array-backed character buffer filled from the original String. An unfinished high surrogate is carried into the next segment; the encoder uses its array path. The encoder uses the charset's default replacement for malformed UTF-16, matching String.getBytes. Supplementary characters remain intact at buffer boundaries. Inputs up to 4096 code units retain the former path.

Only the two private digest methods change; their remaining cache instructions, error/null handling, resource resolution, registration/reload ownership, mesh and texture processing stay fixed. One helper class is added. The builder keeps v0.2.8 sources unchanged and selects explicit candidate sources with `--stream-text-digests`. Exact experimental sources and reports retain their bytes through .gitattributes.

Build and independently audit from the project root:

```powershell
$testMarker = Get-Content .cache/game-test/neoforge-instance/vehicle-test-instance.json | ConvertFrom-Json
$testJavac = Join-Path (Split-Path $testMarker.java) 'javac.exe'
python -X utf8 tools/build_vehicle_memory_mod.py --instance .cache/game-test/neoforge-instance --javac $testJavac --packed-meshes --prune-displays --share-json --compress-texts --segment-text-reads --segment-text-unpacks --stream-text-digests --output vehicle-memory/experiments/streamed-digest/mtr-memory-sharing-neoforge-v029.jar
python -X utf8 tools/audit_streamed_resource_digest.py --instance .cache/game-test/neoforge-instance --candidate vehicle-memory/experiments/streamed-digest/mtr-memory-sharing-neoforge-v029.jar --baseline vehicle-memory/mtr-memory-sharing-neoforge-v028.jar --output vehicle-memory/experiments/streamed-digest/fresh-audit.json
```

The audit loads the actual v0.2.8 cache classes in a separate classloader and compares both private cache digest methods in both versions. It covers all archive text inputs, Unicode and unpaired-surrogate boundaries, null failures, concurrent hashing and thread allocation counters. An unchanged-baseline negative control must fail the allocation requirement. The disassembly comparison excludes only the digest body and normalizes constant-pool reference numbering and comment-column padding; native instruction offsets, operands, comments and other method bodies remain compared.

Build, Python compilation and the [array-buffer audit](array-digest-audit.json) pass. All 8,534 real text inputs (2,902,870,923 code units), 85 synthetic cases, 64 concurrent reads and null-failure comparisons preserve both actual cache keys. 30 baseline class entries remain byte-identical; only the two cache classes change and one helper is added. Other methods in both cache classes retain their native instructions. The unchanged-baseline negative control correctly fails the allocation requirement; its expected AssertionError remains in the audit stderr log.

Eight isolated hashes of 16,777,216-unit text:

| Input | v0.2.8 allocated bytes | Candidate allocated bytes | Allocation reduction | Baseline / candidate timing |
| --- | ---: | ---: | ---: | ---: |
| ASCII | 134,221,760 | 136,736 | 99.898% | 402 / 358 ms |
| Mixed text | 536,874,976 | 136,928 | 99.974% | 456 / 368 ms |
| Unicode | 738,201,504 | 136,928 | 99.981% | 1439 / 1602 ms |
| Small text, 1200 units | 13,472 | 13,472 | Unchanged | Too short for a timing conclusion |

These measure isolated thread allocations. Single timings show a Unicode tradeoff and do not establish overall loading performance. The [initial String-backed-buffer candidate](archive/string-charbuffer/README.md) also preserved exact keys and reduced allocation but was slower, motivating the reusable array buffer. Its artifact, source and complete audit remain archived. Only the helper source changes between the two candidates; all other 24 build sources retain identical hashes.

Current candidate SHA-256: `b8e903a3292cca032d6b1038d58f5f0b18be4823148e633ca4114263e2a83b6d`. One corrected-native-lifecycle [4 GiB startup / actual F3+T run](../../evidence/neoforge-v029-streamed-digest-acceptance.json) passes all 16 packs / 2,541 registrations / 651 completed unique source parses per epoch and 60 seconds of fresh stability. Both DC01 bodies render, with their distinct 5/6-floor and 10/10-doorway caches exactly equal before/after and corrected v0.2.8. The external sampler covers blocked startup parsing and starts before F3+T. No diagnostic GC was requested. The unchanged native callback is recorded in both snapshots.

| Phase | External sampled heap peak | Windows working set peak | Private committed peak |
| --- | ---: | ---: | ---: |
| Startup | 3.786 GiB | 4.976 GiB | 5.173 GiB |
| Actual F3+T | 3.816 GiB | 5.553 GiB | 5.736 GiB |

These are one-run sampled values, not true maxima or a demonstrated process-RAM reduction against the two corrected v0.2.8 runs. Original survival player/window layout and all saved transport fields/inventory, pack hashes/order and fixed other mod hashes verify after normal shutdown. Saved DayTime advances naturally to 338985. The tested instance now holds this candidate; exact v0.2.8 rollback is preserved. Fresh repeat and lower-heap acceptance remain pending. v0.2.8 remains delivered; the candidate has not replaced a production instance.


## First lower-heap run

The [first 3584 MiB run](../../evidence/neoforge-v029-streamed-digest-3584mb-acceptance.json) passes all-pack startup and actual F3+T, each with 2,541 registrations / 651 completed unique parses / 60 seconds of fresh stability. Both native snapshots confirm a 3.5 GiB actual heap maximum and the original MTR callback. Both DC01 bodies render and exact individual caches match before/after and corrected v0.2.8. Original player/window layout, saved native transport fields, all 16 pack hashes/order and fixed mod hashes verify after normal shutdown. Saved DayTime advances naturally to 343786.

| Phase | External sampled heap peak | Windows working set peak | Private committed peak |
| --- | ---: | ---: | ---: |
| Startup | 3.440 GiB | 4.498 GiB | 4.661 GiB |
| Actual F3+T | 3.412 GiB | 5.058 GiB | 5.232 GiB |

The changed heap cap contributes to process memory differences; this is not a measured code-only RAM reduction. The previous v0.2.8 3.5 GiB repeat failed, so this single candidate pass does not establish a safe lower recommendation. A fresh identical repeat is required. v0.2.8 at 4 GiB remains the recommendation until repeatable candidate acceptance.
