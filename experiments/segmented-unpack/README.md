# Bounded compressed resource-text restoration

Target: Minecraft 1.21.1 / NeoForge 21.1.265 / official MTR 4.1.0-beta.2. Delivered: [mtr-memory-sharing-neoforge-v028.jar](../../mtr-memory-sharing-neoforge-v028.jar), version 0.2.8. **Two fresh 4 GiB clients pass startup and actual F3+T reload. Three GiB startup and repeat 3.5 GiB reload fail.** Keep v0.2.7 for rollback. [Final acceptance](../../evidence/neoforge-v028-acceptance.json).

v0.2.7 restores a compressed cache hit through a complete `char[length]` and then copies it into a String. v0.2.8 bounds that temporary array to 4096 UTF-16 units, restores each inflater read as a String segment, and joins the segments once. Inputs up to 4096 units retain the original one-array path. Arbitrary UTF-16 units, including unpaired surrogates, are preserved; odd byte reads carry their high byte into the next read. Length validation and native cache ownership are preserved. Packing, first-read identity, null/error handling, epoch replacement and the existing native reader are unchanged.

Thirty v0.2.7 class entries remain byte-identical. The nested Text class changes; its enclosing cache class has shifted debug line numbers but identical `javap -p -c` instructions/signatures/exception tables. There are no added or removed classes. Geometry, texture data, JSON sharing, packed meshes and native floor/doorway calculations are untouched.

`batched-unpack-audit.json` fingerprints the exact release, all 16 selected packs, candidate and sources. The unchanged original roundtrip audit passes all 8,534 real text inputs, 64 concurrent reads, one native miss, overlapping reloads and release. An independent classloader invokes actual v0.2.7 for 44 synthetic comparisons, including empty/small/raw/compressed text, 4096-unit boundaries, surrogate boundaries, BOM, CRLF and NUL. Packed payload statistics are identical.

Eight isolated cache hits on 16,777,216-unit text:

| Text | v0.2.7 allocated bytes | v0.2.8 allocated bytes | Change |
| --- | ---: | ---: | ---: |
| ASCII | 402,726,144 | 270,839,584 | -32.75% |
| Mixed ASCII and Unicode | 671,161,568 | 405,298,208 | -39.61% |
| Unicode | 671,176,064 | 674,264,712 | +0.46% |
| Small compressed text, 1200 units | 101,600 | 101,600 | unchanged |

These are current-thread allocated bytes measured through ThreadMXBean, excluding compression/setup, not retained heap or ordinary process RAM. The batching revision's single timing samples were 491/493 ms for ASCII, 557/540 ms for mixed text and 556/596 ms for Unicode across eight hits. Tiny-input timings are too short to support a performance conclusion. A negative control using unchanged v0.2.7 as its own candidate fails the required ASCII allocation reduction. The initial per-character-flush candidate and its complete audit are retained in `archive/` and `unpack-audit*`; its slower isolated timings motivated batching.

Build and audit from the project root:

```powershell
$testMarker = Get-Content .cache/game-test/neoforge-instance/vehicle-test-instance.json | ConvertFrom-Json
$testJavac = Join-Path (Split-Path $testMarker.java) 'javac.exe'
python -X utf8 tools/build_vehicle_memory_mod.py --instance .cache/game-test/neoforge-instance --javac $testJavac --packed-meshes --prune-displays --share-json --compress-texts --segment-text-reads --segment-text-unpacks --output vehicle-memory/experiments/segmented-unpack/mtr-memory-sharing-neoforge-v028.jar
python -X utf8 tools/audit_segmented_resource_unpack.py --instance .cache/game-test/neoforge-instance --candidate vehicle-memory/experiments/segmented-unpack/mtr-memory-sharing-neoforge-v028.jar --baseline vehicle-memory/mtr-memory-sharing-neoforge-v027.jar --output vehicle-memory/experiments/segmented-unpack/fresh-audit.json
```

Use fresh evidence output names. Build alone does not install into the test instance; installation requires the recorded client to be stopped. No lower process peak or reduced minimum heap is claimed from the isolated allocation tests.

## First ordinary 4 GiB game run

[Acceptance and fingerprints](../../evidence/neoforge-v028-4gb-acceptance.json): all 16 packs / 2541 vehicles / 290 objects / 23 rails, 651 unique parses per epoch, 60 seconds of continuous fresh stable observations at startup and reload. No diagnostic GC requested. Both actual DC01 car bodies and closed/open doors render; their distinct 5/6 floor and 10/10 doorway caches match v0.2.7 exactly before/after reload. Player, window input layout, saved transport fields, pack hashes/order and launch mod identities are restored/verified after normal shutdown. The experimental passenger companion stays fixed at v0.1.1; the fixture-control probe is absent.

| Epoch | Sampled heap peak | Windows working set peak | Private committed peak |
| --- | ---: | ---: | ---: |
| Startup | 3.807 GiB | 5.015 GiB | 5.184 GiB |
| F3+T reload | 3.841 GiB | 5.551 GiB | 5.720 GiB |

This is one process; sampled values are not true maxima or production-world limits. The first reload process-monitor invocation failed when PowerShell converted the offset timestamp into a locale date. The successful retry began during parsing; the separate heap monitor covered the reload event. Initial failure evidence is retained. Existing transparent-model, sound and SDK-session authentication messages also occur in the previous tested client and remain visible in complete logs. Wider Shanghai windows and passenger/vehicle gameplay remain separate unfinished work.

## Lower-heap boundary

[Three GiB failure](../../evidence/neoforge-v028-3gb-failure.json): full-pack startup reached 500 completed source parses, then explicit Java heap-space errors and heavy full GC. It never opened an integrated world. Actual foreground Alt+F4 closed the client; no forced stop was required. The complete failure, independent heap monitor and unchanged mod context are preserved, and all 16 verified pack selections were restored. **Three GiB is not accepted.**

The marked test launcher supports an exact MiB limit through `--heap-mb`, mutually exclusive with `--heap-gb`. A 3584 MiB experiment uses the valid native Java argument `-Xmx3584M`, recorded as 3.5 GiB; integer GiB launches keep their previous arguments. Its [first acceptance](../../evidence/neoforge-v028-3584mb-acceptance.json) passes startup and actual F3+T, all selected packs and 651 parses per epoch, each with 60 seconds of continuous fresh stability. Both DC01 bodies render, native caches match v0.2.7 exactly, and saved native fields/player/pack order/mod fingerprints verify after normal shutdown. No time commands or diagnostic GC. Startup process peak is 4.482 GiB and reload 5.100 GiB.

The [fresh repeat](../../evidence/neoforge-v028-3584mb-repeat-failure.json) passes startup but fails actual F3+T: the final native resource-text join allocation exhausts the heap and recovery loads only 423 built-ins. This is the unchanged v0.2.7 reader's final String payload, not an altered mesh or window material. The single earlier pass remains historical evidence; **3.5 GiB is not repeatably accepted or recommended**. The client closes normally after original-player/window-layout restoration, and native saved fields/all 16 selections/mod fingerprints verify after restoring selections.

The subsequent fresh 4 GiB repeat passes startup and actual F3+T, all 16 packs and 651 parses per epoch, each with 60 seconds of continuous fresh stability. Both DC01 bodies render, their exact floor/doorway caches match v0.2.7, and original player/window/native fields/pack hashes/order/mod context verify after normal shutdown. Repeat startup/reload process peaks are 5.018/5.593 GiB. Four GiB is now the lowest repeatably verified heap. The exact audited artifact is copied unchanged to the delivery folder; native mesh/texture/interaction semantics remain preserved. Reload process RAM still approaches 5.6 GiB, so no reduction of total reload peak below v0.2.7 is claimed.
