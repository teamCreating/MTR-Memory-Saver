# Packaged 0.4.8 component checks and binary rejection

| Case | JVM PID | JVM exit | Actual result |
| --- | ---: | ---: | --- |
| NF248 smoke capture03 / smoke02 instance | 39660 | 0 | 24 lifecycle + 18 strict-resource checks, all true |
| NF265 smoke | 54748 | 0 | 24 lifecycle + 18 strict-resource checks, all true |
| NF248 intentionally mismatched MTR | 60744 | 1 | fingerprint fatal before native resource registration |
| NF265 intentionally mismatched MTR | 41096 | 1 | fingerprint fatal before native resource registration |

Both smoke plans use the actual packaged 0.4.8 companion, matching acceptance probe and official MTR 4.1.0-beta.2, 3072 MiB heap, base resources, no selected world and no external resource packs. Their request/result IDs correspond byte-for-byte, audit result copies match the instance originals, and all 42 fields are actual booleans true. Original logs also record the native snapshot capability path (107 attempts/captures, zero String fallbacks) and the completed base registration. This scope is packaged component correctness, including deliberate native/parser/resource fault injection and cleanup. Full original ERROR/WARN output is retained: this is not an error-free gameplay claim or a diagnostic whitelist for a full catalogue.

The mismatches retain the correct companion, no probe, and a deliberately different installed MTR SHA (`b4a1...` versus audited `ff2b...`). The fatal is in **launch.stderr.log**, including BinaryFingerprint.require, before any ResourceManager reload or memory-sharing registration. Seeing a mod in the loader inventory alone does not mean its native hooks completed registration. No lifecycle result exists for either rejection control.

## Original attempts remain distinct

- `nf248-smoke-capture`: original execution remains `launching`, with no PID, launch record or recorded traceback. Parent reports a missing launcher Python module and no actual launch. Only the incomplete disk boundary is independently available; the cause is explicitly parent-reported.
- `nf248-smoke-capture02`: actual JVM44444 exits0, but its lifecycle result is absent. Original logs/plan/launch/collector execution remain; it is **not accepted** and is not substituted for capture03.

The four completed collectors' `execution.exit_code` values come from their owned `process.wait()` and denote JVM exits. Frozen collector source does not forward those values as Python wrapper exits. `parent-reported-tool-results.json` explicitly labels the actual wrapper terminal results (62013/48261/63994/91696 all0) as parent-reported tool history because no original terminal receipt was saved. No synthetic raw receipt is created.

## Minimal immutable closure

Copies retain the original five completed capture directories, initial incomplete execution, original inputs and nine frozen Python/two config sources, all audit stdout/stderr/result metadata, instance markers/options and available request/results. `copy-receipts.json` binds every original path, read time, before/after file metadata, size and SHA. No original was modified.

Four product/probe manifests are copied. Their exact JARs and corresponding build/probe source inputs already exist under the tracked `../streamed-blockbench-input/runs/06` and `07` seal; `run-bindings.json` pins those repository-relative portable references rather than duplicating them. The verifier rechecks all 122 manifest input fingerprints against those frozen sources or generated/resource entries in the exact JAR. Nothing is read from live Java source or current build output.

Installed mod and on-exit JFR bytes were independently hashed read-only while the specified executions were already terminal. `external-binary-references.json` records those read-time observations; large MTR and JFR binaries are **not copied into this seal**. The saved four JFR summary commands actually have exit0/empty stderr and readable durations51/52/8/8 seconds, with matching on-exit JFR SHA. Two smoke summaries each show only1 ClientFrame/0 ServerTick: these are readable component-check exit recordings, not performance, route, whole-gameplay or whole-history coverage. The incomplete earlier capture02 JFR hash is retained without awarding a readable-summary or pass claim.

Recheck from repository root (stdlib only, no archived tool imports or original-instance reads):

```powershell
.\.venv\Scripts\python.exe -X utf8 evidence/engineering-051/packaged-client-checks/verify_sealed.py
```

`sha256-index.json` covers the exact local payload inventory. The sibling verification directory holds actual isolated verifier/catalog receipts. Existing production tools, running051a client/collector/readers, previous seals and source pins were untouched. Twenty reloads and the revised remaining release gates are separate evidence.
