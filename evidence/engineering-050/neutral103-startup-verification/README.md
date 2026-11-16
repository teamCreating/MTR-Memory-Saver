# Sealed-only startup verification

`run-01/` preserves the actual successful invocation of `verify_startup.py`,
including exact argv, start/end UTC timestamps, exit code 0, raw stdout/stderr and
executed verifier/runner source copies. It reads only the sibling frozen
`neutral103-startup/` tree. It does not query or control the live game and does
not rerun or modify the original consumer result.

The independent calculation verifies all 99 indexed payloads, 94 read receipts,
13 valid raw sample records, original source fingerprints, retained process
identity/Windows command-line parsing, native callbacks/counters, existing cache
regions, 44/25 exact artifact build inputs and the recorded sixteen archive pairs.
The original frozen diagnostic implementation and five pinned proof files replay
to a result exactly equal to `summary.native_diagnostics`.

The observer interval is **60.0146004 seconds**. Actual first-to-last sampled
monotonic span is **60.000258 seconds**. Native UTC observations span
**59.7471383 seconds**, with native monotonic span **59.7472558 seconds**; this is
not represented as a full sixty seconds of native timestamps. Maximum native
snapshot age is **1.0831475 seconds** and maximum sampling gap is **5.0522572
seconds**. All thirteen observations remain unpaused, screen-null and settled,
with zero native pending/in-flight work and observation errors, and 1,092 native
declarations / 1,091 distinct IDs.

The verifier preserves the limitations in its result. Per-sample original native
JSON byte hashes cannot be reconstructed from parsed `raw_state` formatting;
the original complete samples-file SHA is verified. Runtime archive/MTR hashes
are the separately preserved read receipts and are not reread by this sealed-only
process. Original process identity comes from the retained consumer CIM result
and matching native observations. No later UI state, empty-track F2 image,
twenty reloads, route, boarding, rendered train appearance, complete game exit or
controlled performance pass is inferred.
