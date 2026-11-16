# Native Invalid model runtime attribution

Recorded 2026-11-16 (UTC+08:00). Official MTR 4.1.0-beta.2 only; no v6 verification.

The first isolated NF248 / Memory Saver 0.4.6 / sixteen-pack startup now has a real
caller trace. Its single `transparent.png Invalid model` occurrence comes from
`CustomResourceLoader.reload` constructing the built-in `RailResource` with empty
model and texture strings. The native unsupported-format branch emits the log,
then returns its usual `BlockbenchModelLoader`. This is an actual observation of
that invocation, not an inference from the texture filename.

- [Captured prefix and attribution](startup-prefix/attribution.json) binds the raw
  log, three trace events, exact prepared/launch receipts and independent native
  observer process identity. PID 51876 started at 2026-11-16T05:40:37.224Z; the
  traced error occurred at 05:41:12Z. It is a live startup prefix, not final client
  acceptance. Later activity is outside this snapshot.
- [Original probe reproduction](early-rebuild/comparison.json) recompiles all four
  original diagnostic classes from [preserved source](early-probe-source/) with
  the actual runtime dependencies. Every class matches the launched JAR exactly.
  That early JAR is `95aa3ac2d140ead4bca42a7625c497fdceeca7cc09acd72dc960065fae5ebea4`.
- [Final build](build-nf248/mtr-model-trace-official-nf248-1.0.0.build.json) uses
  `TAIL` instead of `RETURN` for the unchanged native fallback return, avoiding
  possible matches on another mod's injected early return. The before-log hook
  is unchanged. Its JAR is
  `626a663f70d4fe6c4a61f22a2104f845f4ccf346e155e251f12e957a17d25f03`.
  Three JUnit checks validate the exact bytecode hook, target rejection and absence
  of lazy factory/product calls. Six Python rejection tests cover trace gaps,
  mismatched process/target/arguments, observation failures and unmatched log lines.
- [Saved rail styles](saved-rail-styles/assessment.json) verifies all twelve
  persisted fixture rails against the prepared world hashes. All are TRAIN with
  exact `default`, and the captured config has `defaultRail3D=true`. The previously
  identified `default_1`/`default_2` boundary is absent from these saved rails.
  The audited native branch maps exact default to `default_3d` or
  `default_3d_siding`; active rendering remains separate evidence.

The diagnostic is an optional separate build, with exact official binary/loader
guards and no product dependency. It does not cancel the native method, replace
models, suppress logs, request caches, or alter parser state. Build with Java 21:

```powershell
./gradlew.bat -I tools/diagnostics/native-model-trace.gradle modelTraceManifest -Ptarget=official-nf248
```

The prior static inventory has 4,503 authored model consumers and 1,560 distinct
raw model references (974 OBJ, 586 Blockbench). A complete geometry corpus audit
is feasible but separate: the older parent harness uses obsolete package/API
bindings and must be adapted to current official sources; resource provider
priority, model/textures, generated groups, displays and interaction boxes must
be bound before treating parser comparisons as meaningful. This diagnostic did
not execute that corpus or establish native fallback cost, overall visual
harmlessness, a companion-free baseline, performance gains or full gameplay.

Historical untraced errors retain their original limits. The next neutral
observer may integrate the same observational hook for per-run qualification;
these separate-diagnostic measurements are not neutral performance evidence.
