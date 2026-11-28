<img src="src/main/resources/pack.png" width="72" align="right" alt="MTR Memory Saver">

# MTR Memory Saver

**English** | [简体中文](README.zh-CN.md)

Minecraft `1.21.1` (Client) · NeoForge `21.1.265` · Java `21` · Official MTR `4.1.0-beta.2` · Mod ID: `mtr_memory_sharing` · License: [MIT](LICENSE)

**MTR Memory Saver** is a client-side optimization companion mod for **Minecraft Transit Railway (Official MTR `4.1.0-beta.2`)**. It reduces Java heap pressure and duplicate model/resource allocations during vehicle registration and resource reloads while keeping MTR's native parsing schemas, coordinate transformations, AABB boxes, display part behavior, and door/floor logic unchanged.

---

## Measured Progress (Official MTR `4.1.0-beta.2`)

### Memory Usage: Official MTR `4.1.0-beta.2` Alone vs With Memory Saver

| Metric | Official MTR `4.1.0-beta.2` Alone (No Memory Saver) | Official MTR + Memory Saver `v0.3.0` (Same Legacy 16 Packs) | Official MTR + Memory Saver `0.4.8` (Native-Catalogue 16 Packs) |
| :--- | :--- | :--- | :--- |
| **Test Fixture & Loader** | Legacy 16 packs (`2,541` vehicles), Fabric `0.20.1` | Legacy 16 packs (`2,541` vehicles), NeoForge `21.1.265` | Native-catalogue 16 packs (`1,092` decls / `1,091` IDs + `974` OBJ), NeoForge `21.1.248` / `21.1.265` |
| **Minimum Verified `-Xmx`** | **`> 12 GiB`** (OOM at `6 GiB` and `12 GiB`) | **`3 GiB`** (`-Xmx3072M`, `−75%+` vs `12 GiB` OOM) | **`3 GiB`** (`-Xms512M -Xmx3072M`) |
| **Sampled Java Heap Used** | Peaked at **`11.98 GiB`** (`12.87 GB` / `12 GiB` cap) before crashing | **`2.812–2.815 GiB`** (startup) / **`2.890–2.896 GiB`** (reload) | Steady **`2.299–2.307 GiB`** (`NF248`); 20-reload med **`2.346 GiB`** / peak **`2.873 GiB`** (`NF265`) |
| **Partial-Load Live Heap Histogram** | **`9.87 GiB`** shallow (`76.64M` `StoredVertexData` `3.43 GiB` + `75.31M` `Color` `2.24 GiB`) | **`0`** `StoredVertexData` (36 B lossless compressed blocks) | **`0`** `StoredVertexData` (`36` B lossless compressed blocks + streaming I/O) |
| **Windows Working Set** | Not recorded in early Fabric baseline (process RAM > heap) | Sampled **`3.86–4.77 GiB`** (OS lifetime peak **`5.24–5.36 GiB`**) | Steady **`4.25–4.31 GiB`** (`NF248`); 20-reload med **`4.39 GiB`** / lifetime peak **`5.59 GiB`** (`NF265`) |
| **Windows Private Commit** | Not recorded in early Fabric baseline | Sampled **`4.02–4.14 GiB`** (startup) / **`4.74–5.62 GiB`** (reload) | Steady **`4.46–4.47 GiB`** (`NF248`); 20-reload med **`4.87 GiB`** / peak **`5.86 GiB`** (`NF265`) |
| **Startup & `F3+T` Outcome** | Startup **`OutOfMemoryError`** (`exit -1`) before parsing completed | Passed startup + **`F3+T`** reload (`2/2` clients) | Passed startup + **`20 / 20`** consecutive `F3+T` reloads (`0` OOM, exit `0`) |

> Measurement scope: The unmodified no-companion baseline (`> 12 GiB` OOM, [without-companion-live-heap.txt](evidence/without-companion-live-heap.txt), [HISTORY.md](docs/HISTORY.md#L303-L306)) was captured on Fabric `0.20.1` + legacy 16 packs with `jcmd`/Java heap metrics only; a separate unmodified `NeoForge 21.1.265` no-companion baseline has not yet been sealed. Adding `-Djdk.virtualThreadScheduler.parallelism=2` and compacting pack models alone still OOMed at `-Xmx12G`. Direct same-fixture proof on legacy 16 packs comes from [`v0.3.0`](evidence/neoforge-v030-acceptance.json), while [`0.4.8`](evidence/engineering-056/nf265-reload20/README.md) extends `3 GiB` stability to streaming `.bbmodel`/`.obj`/`.mtl` and `20/20` reloads on the native-catalogue packs ([NF248 Spark steady data](evidence/engineering-054/practical-spark/assessment.json)). Remember `-Xmx` caps Java heap only — native/GPU allocations bring total Windows process RAM to ~`4.25–5.86 GiB`.

### Quantitative Breakdown (`v0.1.1`–`0.4.8`, Official MTR `4.1.0-beta.2`)

Across sixteen full test resource packs, vanilla MTR `4.1.0-beta.2` retains large CPU vertex graphs, non-display matrix transforms, duplicate vehicle JSON trees, unbounded resource text caches, and transient whole-file `String` allocations. Below are the verified step-by-step reductions across engineering milestones:

| Metric | Baseline / Earlier State | Current (`0.4.8` / Cumulative) | Fixture & Scope Notes |
| :--- | :--- | :--- | :--- |
| **Minimum Verified `-Xmx`** | **`> 12 GiB`** alone (OOM at `6 / 12 GiB`); `8 GiB` (`v0.1.1`); `v0.2.9` OOMs on `3 GiB` startup | **`3 GiB` (`-Xmx3072M`, `−75%+` vs `12 GiB` / `−62.5%` vs `v0.1.1`)** | Legacy & native-catalogue 16-pack fixtures; OS Working Set / Private Commit stays ~`4.25–5.86 GiB` |
| **CPU `StoredVertexData` Count** | `79,359,867` live instances (`v0.1.1`) | **`0`** (`v0.2.0+` 36 B/vertex `Deflater.BEST_SPEED` blocks) | Legacy 16-pack heap histogram; 391 Shanghai models (`47.37M` vertices) pack to `367.77 MB` |
| **Non-Display Matrix Metadata** | `2,494,194` `StoredMatrixTransformations` (~`753 MiB`) | **`2,234` (−99.91%)** (`PartType.DISPLAY` only) | `v0.2.1` `5 GiB` heap histogram: total shallow heap `3.04 -> 2.31 GiB` (−24.17%) |
| **Vehicle Config Gson Shallow Bytes** | `385,752,224` B (`385.75 MB`) | **`99,865,272` B (`99.87 MB`, −74.11%)** | `v0.2.2` `5 GiB` heap histogram: total shallow heap `−579 MiB` (−24.50%) |
| **Retained Resource Text Cache** | `2,000,187,675` code units / `592,010,155` B compressed | **`96 MiB` (`100,663,296` B) bounded LRU** (`v0.3.0+`) | Legacy 16-pack evicted `3,010` entries/epoch; oversized items bypass cache |
| **Large Text SHA-256 Allocation** | `16M` units: `134.22 MB` / `536.87 MB` / `738.20 MB` | **`136.7–136.9 KB` (−99.898% to −99.981%)** | Streamed fixed 4K/8K UTF-8 encoding (`v0.2.9+`, ASCII / Mixed / Unicode) |
| **Single-Pass Snapshot Digest (`0.4.8`)** | Prior `0.4.8` re-read disk channel to compute SHA-256 | **−19.24% median CPU / −19.37% wall time** (`official-nf265`) | [engineering-055](evidence/engineering-055/snapshot-digest/README.md) 6-pair real 65.26 MB BBModel benchmark (6/6 improved; single path) |
| **Consecutive 16-Pack `F3+T` Reloads** | `0.4.7` 4th-reload OOM; initial `0.4.8` 7th-reload OOM | **`20 / 20` consecutive reloads at `3 GiB` (0 OOM)** | [engineering-056](evidence/engineering-056/nf265-reload20/README.md) native-catalogue 16 packs (`1,092` decls / `1,091` IDs), exit `0`, readable JFR |
| **Abrupt Halt & Wrong-JAR Safety** | `0.4.6` left `.utf16` on `Runtime.halt`; `0.4.4` skipped Mixins | **`4 / 4` zero spill residue + exit code `1` before registration** | Single-channel `DELETE_ON_CLOSE` cleanup (`0.4.7+`); `MixinInitialisationError` (`0.4.5+`) |

> Note on scope: While `3 GiB` stability and `20/20` consecutive full-pack reloads are verified on `0.4.8` (`official-nf265`), full-client controlled performance acceptance remains pending — see [Current Validation Scope](#current-validation-scope).

---

## Supported Target & Installation

The **`0.4.8`** development pre-release targets **`official-nf265`** only (`config/targets.json` is the single authority for dependency hashes and loader versions):

| Parameter | Required Value |
| :--- | :--- |
| Target Preset | `official-nf265` |
| Minecraft / Java | `1.21.1` (Client only) · Java `21` |
| NeoForge | `21.1.265` (exact) |
| Official MTR `4.1.0-beta.2` SHA-256 | `ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa` |
| Tested Companion JAR (`0.4.8`) SHA-256 | `920c1f833b6f173c7443ff5956493b779acfeceb293fa640817a459985db3f5b` |

### Install / Rollback

1. Download **`mtr-memory-saver-official-nf265-0.4.8.zip`** from [GitHub Releases](https://github.com/teamCreating/MTR-Memory-Saver/releases/tag/v0.4.8) (see [v0.4.8 Release Notes](docs/releases/v0.4.8.md)).
2. Extract **`mtr-memory-saver-official-nf265-0.4.8.jar`** into your client's `mods/` folder alongside exact NeoForge `21.1.265` and official MTR `4.1.0-beta.2`.
3. Remove any older `mtr-memory-saver` / `mtr_memory_sharing` companion JAR first (do not install two versions together). The companion validates the loaded MTR JAR SHA-256 at startup and exits with code `1` via `MixinInitialisationError` if mismatched.
4. Keep your resource packs in `resourcepacks/` (unmodified). To roll back, close Minecraft and delete or replace the companion JAR.

See [docs/INSTALL.md](docs/INSTALL.md) and [docs/SUPPORT.md](docs/SUPPORT.md) for full rules and historical targets. Custom `Performance v6` target presets (`v6-nf248` / `v6-nf265`) remain in `config/targets.json` for source builds with new validation paused.

---

## Architecture Overview

Built around official MTR `4.1.0-beta.2`, the `0.4.8` runtime operates in four decoupled layers across 18 Mixins/Accessors (13 common + 5 official; detailed in [docs/TECHNICAL_PRINCIPLES.md](docs/TECHNICAL_PRINCIPLES.md) and [docs/RUNTIME_DESIGN.md](docs/RUNTIME_DESIGN.md)):

1. **Exact Binary Identity Gate (`CompatibilityPlugin` / `BinaryFingerprint`)**: Streams the active MTR JAR SHA-256 during Mixin `onLoad` and throws `MixinInitialisationError` before registration if bytes differ from the target manifest.
2. **Two-Level Bounded Single-Flight Scheduling (`GenerationWorkCache`)**: Evaluates L1 `(providerIdentity, modelId, textureId, flipV)` path keys before opening streams, decoding, or hashing; limits concurrent parse work via a fair `2 + 64` semaphore queue and lightweight descriptor suppliers; releases read permits before L2 Blockbench content-alias waiters attach; keeps `.obj` scoped per-path (`StreamedObjCache`) to isolate `.mtl` materials; retires generations atomically on reload.
3. **Owned Streaming Snapshots, Single-Pass Digest & `96 MiB` LRU**: Wraps the 5 audited official `ResourceProvider` entry points (`ResourceTextReadMixin`) to stream `.bbmodel`, `.obj`, and `.mtl` through a single `CREATE_NEW | READ | WRITE | DELETE_ON_CLOSE` UTF-16 channel, computes UTF-8 SHA-256 in a single `FilterReader` pass without a second disk read, spills oversized legacy `readResource` calls deadlock-free via fair-share `TextWorkspace`, and caps retained resource text in a `96 MiB` `Deflater.BEST_SPEED` LRU (`BoundedTextCache`).
4. **Lossless Packed Meshes, Display Pruning & Shared Vehicle JSON**: Compresses CPU-side `StoredVertexData` to fixed 36-byte `Deflater.BEST_SPEED` chunks (`PackedVertices` / `PackedModelGroupStore`) preserving exact raw float bits and AABB boxes, retains `PartType.DISPLAY` transforms only (`DisplayRetention`), and shares identical non-empty vehicle Gson trees per epoch (`VehicleJsonCache`).

---

## Current Validation Scope

### Verified for `0.4.8` (`official-nf265`, JAR `920c1f83...`)

- **Headless Java & Python Suites**: `106` Java unit/regression tests (including `-Xmx64M` streaming vs `String.join` OOM controls), `682` historical script index checks, and `354` Python tool tests pass.
- **Packaged Client & Fault Injection**: Actual `NeoForge 21.1.265` packaged client passes `24` lifecycle + `18` strict-resource + `27` OBJ checks (`69` total), full sixteen-pack startup (`1,092` declarations / `1,091` distinct IDs), readable JFR verification, and same-version wrong-MTR JAR exit code `1` (`engineering-056/nf265-packaged`).
- **20-Reload Endurance (`3 GiB` Heap)**: Passes `20 / 20` consecutive full sixteen-pack native `F3+T` reloads in a fresh `-Xms512M -Xmx3072M` G1 JVM (`epochs 3–22`, `19` intermediate dual-clock `>= 60 s` stability windows, `14/14` post-20 samples over `65.003 s`, clean `Alt+F4` exit `0`, readable `213,901,766`-byte JFR), independently verified via `verify_sealed.py` (`607` payloads).

### Not Yet Certified / Open Gates

- **Whole-Client Performance Acceptance Pending**: Earlier 12-JVM paired Spark trials on `NF248` (`engineering-054`, `0.4.8` `943b3d45...` vs `v0.3.0`) missed performance thresholds (`−0.282%` steady private memory vs `<= -10%`, `+9.840%` loading time vs `<= +5%`), with concurrent host load leaving wall-clock attribution `inconclusive`; the subsequent single-pass optimization (`920c1f83...`) has not yet completed a full 48-JVM controlled client trial ([client-experiment.json](config/client-experiment.json)).
- **Pending Runtime Gates (P1)**: Independent display-frame presentation capture (ETW/PresentMon blocked/empty on standard permissions), 2-hour uninterrupted route stability (historical attempts 01–03 failed), and exhaustive vehicle catalog visual/window/door/boarding interaction checks.

---

## Build & Verify

Requires a **Java 21 JDK** (`JAVA_HOME`). No live Minecraft launcher instance or external marker file is needed to build or run automated suites (see [BUILDING.md](BUILDING.md) and [tests/README.md](tests/README.md)):

```powershell
# Build & verify the default official-nf265 JAR and identity manifest
./gradlew.bat build -Ptarget=official-nf265

# Run headless Java regressions (106 tests on official-nf265)
./gradlew.bat test

# Build installable release ZIP + .build.json manifest in build/releases/
./gradlew.bat releaseBundle

# Run Python tool kit verification and regression suite (requires requirements-test.txt)
python -X utf8 -m minecraft_testkit verify
python -X utf8 -m minecraft_testkit test

# Offline cryptographic replay of sealed 0.4.8 NF265 20-reload evidence (read-only)
python -X utf8 evidence/engineering-056/nf265-reload20/verify_sealed.py
```

### Repository Layout

- `src/main/java/` — Shared Mixins, bounded scheduler, streaming snapshots, text workspace/LRU, packed store, JSON/display sharing
- `src/targets/official/java/` — Official MTR `4.1.0-beta.2` target adapters (`StreamedObjCache`, `ResourceTextReadMixin`, `VertexColorMixin`, etc.)
- `src/targets/v6/java/` — Historical custom `Performance v6` ABI target (currently paused)
- `config/` — Authoritative build matrix (`targets.json`) and frozen experiment policies
- `evidence/` & `performance/` — Immutable, hash-indexed failure/pass captures with offline `verify_sealed.py` replay scripts
- `tools/` & `tests/` — Acceptance harnesses, JFR/Spark exporters, and 354 Python regression tests

---

## Documentation & License

| Document | Topic |
| :--- | :--- |
| [docs/TECHNICAL_PRINCIPLES.md](docs/TECHNICAL_PRINCIPLES.md) | Comprehensive Chinese technical principles, architecture diagrams, controlled trial design & all trial results (`v0.1.1`–`0.4.8`) |
| [docs/releases/v0.4.8.md](docs/releases/v0.4.8.md) | Bilingual (`EN` / `zh-CN`) release notes for `v0.4.8` |
| [docs/RUNTIME_DESIGN.md](docs/RUNTIME_DESIGN.md) | Detailed runtime contract & concurrency invariants (`0.4.7+`) |
| [docs/SUPPORT.md](docs/SUPPORT.md) · [docs/INSTALL.md](docs/INSTALL.md) | Exact binary compatibility matrix, installation & rollback |
| [BUILDING.md](BUILDING.md) · [docs/CI_CD.md](docs/CI_CD.md) | Reproducible builds, protected `main` rules & release pipeline |
| [docs/OPTIMIZATION.md](docs/OPTIMIZATION.md) · [docs/CLIENT_EXPERIMENT.md](docs/CLIENT_EXPERIMENT.md) · [docs/ENGINEERING_REVIEW.md](docs/ENGINEERING_REVIEW.md) | Controlled experiment methodology & critical engineering review |
| [docs/HISTORY.md](docs/HISTORY.md) · [TECHNICAL.md](TECHNICAL.md) | Historical `0.1.x`–`0.3.x` research log & original English architecture archive |
| [LICENSE](LICENSE) · [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | MIT License (`Copyright (c) 2026 A-BenLi06`) & third-party notices |
