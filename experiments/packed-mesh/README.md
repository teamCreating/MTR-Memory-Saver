# Experimental packed meshes (v0.2.0)

This NeoForge-only prototype replaces retained `StoredVertexData` lists with losslessly compressed blocks. Every vertex stores eight raw float bit patterns and exact ARGB, without quantization, deduplication, reordered geometry or changed texture resolution. Encode/decode staging buffers hold at most 1,024 vertices. Native Deflater/Inflater resources are closed after use.

The mixin replaces the audited release's `NewOptimizedModelGroup.add`, `merge` and `build` methods. It preserves the original stage/texture map implementation, vertex order/multiplicity, supplied and generated interaction boxes, mirror/offset arithmetic, and empty mesh behavior. GPU upload uses the original `NewOptimizedModel` with the same bulk vertex arguments, default lighting and overlay. Decompression runs while preparing meshes and uploading GPU buffers; the release's per-frame renderer is unchanged.

The candidate is excluded from default builds. Build it explicitly:

```powershell
python -X utf8 tools/build_vehicle_memory_mod.py --instance '.cache/game-test/neoforge-instance' --javac '<Java 21 javac.exe>' --packed-meshes --output 'vehicle-memory/experiments/packed-mesh/mtr-memory-sharing-neoforge-v020.jar'
```

`tools/audit_packed_mesh.py` runs unmodified official NeoForge MTR beta.2 methods outside a mixin runtime. The synthetic audit checks raw round trips, all 11 emitted GPU arguments, transformations, appended blocks, empty meshes, transparent colors, stage/texture keys and bounds. The real-model audit invokes the official Blockbench parser and compares every parsed group, generated bounds, ordinary merges and mirrored merges, with strict raw bit checks.

Raw storage, UVs, ARGB, unchanged normals, finite transformed values and signed zero remain exact. Java does not specify arithmetic NaN payload selection. The synthetic audit allows equivalent NaNs only in arithmetic-modified fields and reports raw payload variations explicitly; it does not normalize stored data. The real-model comparisons do not permit this exception. Offline Log4j format warnings are preserved in the logs; parser success and geometry comparisons are checked separately.

Independent audits passed 1,200,028 synthetic vertex comparisons and all 391 Shanghai models (47,373,240 parsed vertices, 35,688 generated bounds). The DC01 sample also passed independently. The Shanghai compressed payload totals 367,774,154 bytes; this excludes storage overhead and does not predict the full client heap. The candidate passed ordinary full-16-pack startup and actual F3+T reload at 6 GiB on NeoForge 21.1.265. Both checks reached 2,541 registrations, completed parsing and 60 seconds of continuous fresh stable samples without diagnostic GC. Sampled heap / working set / private commit peaks were 5.75 / 7.06 / 7.23 GiB at startup and 5.93 / 7.61 / 7.78 GiB at reload. Native F2 before reload shows both DC01 cars with interiors and open doors; both native floor/doorway caches remain unchanged after reload. Wider rendering/passenger checks and lower heaps remain pending. The older default v0.1.1 artifact is retained separately. See [6 GiB evidence](../../evidence/neoforge-v020-6gb-acceptance.json).
