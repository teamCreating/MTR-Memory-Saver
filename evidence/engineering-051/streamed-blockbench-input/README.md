# Streamed Blockbench input candidate 0.4.8

Sealed at 2026-11-17T20:19:54+08:00. These are engineering results; no packaged-client or full-pack acceptance is awarded here.

The old 0.4.7 fourth-reload failure is preserved in `../../engineering-050/owned049d-reload-attempt03-oom/`. Both OOM stacks fail at the module's complete `String.join` input materialization. That stack locates an allocation; it does not prove a generation leak.

The candidate adds an explicit snapshot capability only at five audited native default `ResourceProvider` arguments. The exact MTR SHA is `ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa`; ASM tests check their method-reference producer and downstream call descriptors. Unknown providers still call their actual `get`; native DEBUG still uses its original String/local-file path. Snapshot capture decodes with strict length/cancellation checks into one `CREATE_NEW/READ/WRITE/DELETE_ON_CLOSE` UTF-16 channel, hashes equivalent UTF-8 bytes, and feeds the existing shaded Gson/Blockbench parser through a bounded Reader. No full module-owned input String is created on that capability path. This does not bound the native Gson DOM or model heap.

`Prepared` owns the snapshot through parsing. Success and content aliases close it before publication/subscription. Cancellation, retirement, timeout, parse and close errors retain the original outcome and independent suppressed failures without cause cycles. Source-close failures cannot transfer a snapshot. Failed facades include the dynamic resource ID. Capability counters bind to the wrapper's creation epoch so late old work cannot inflate a new epoch's stream count; the log explicitly scopes these counts to native snapshot capability attempts.

## Final checked artifacts

| Target | Product SHA-256 | Product manifest | Probe SHA-256 | Probe manifest |
|---|---|---|---|---|
| NF248 | `34c0b27780f7a3d4d5f29845f98a655f22cae0b1eeca1a4a95ab86b60921b0c1` | `runs/06/mtr-memory-saver-official-nf248-0.4.8.build.json` | `ad5e9cccf272559c62dcf35f9fbe237e2bd1c6f896cb06bfb692e604d5e4c79a` | `runs/06/mtr-memory-saver-official-nf248-0.4.8-acceptance-probe.build.json` |
| NF265 | `89720d30c76b4f5dfc6a71a398bb67c3138cf4f8f4e0afd0dbb062753552e735` | `runs/07/mtr-memory-saver-official-nf265-0.4.8.build.json` | `ad5e9cccf272559c62dcf35f9fbe237e2bd1c6f896cb06bfb692e604d5e4c79a` | `runs/07/mtr-memory-saver-official-nf265-0.4.8-acceptance-probe.build.json` |

Runs 06 and 07 each execute `test verifyRelease probeJar probeManifest streamingBlockbenchInputAudit`: exit 0, **99 tests / 0 failures / 0 errors / 0 skipped**. Their original command receipts, raw stdout/stderr, JUnit XML, byte-exact source snapshots, source fingerprints, product/probe JARs and identity manifests are retained. Source hashes still match at sealing. The runner executes the targets sequentially and stops on failure. Only official NF248/NF265 were validated; v6 validation stays paused.

## Preserved controls and failure

- Run 01: early targeted 59/59; it is not the final source validation.
- Run 02: intermediate 92/92 and successful stream fixture, before late-failure handling/counters. Its `source-snapshot-status.json` names the subsequently changed test source that was not copied; no replacement is presented as the earlier file.
- Run 03: one actual exit-1 complete-String control. The same generated 40 MiB whitespace plus `{}` input under a 64 MiB heap fails at `SegmentedResourceText.read:47 / String.join`. The snapshot path succeeds with the same digest and native serialized schema, and settles all ownership. Explicit fixture size/workspace limits differ from production defaults. This isolates input copying; it is not a 3 GiB game claim.
- Run 04: 99 tests / 1 failure, preserved unchanged. The new race test incorrectly asserted `current.pending > 0` after `beginReload` had replaced the current epoch with an empty one. The correction only asserts current pending 0 and retirement still blocked, retaining the not-yet-canceled old future, both closed owners, released permits/tickets and original Cancellation/suppressed-error checks. Product logic did not change for this correction. `artifact-eligibility.json` documents that this failed build's copied old manifest does not match its newer JAR; neither is accepted as a final pair.
- Runs 06/07: final corrected source, both 99/99 plus successful snapshot fixture. The retained Log4j missing-provider stderr line belongs to the standalone audit, not a Minecraft run.

`archive-map.json` maps compact run directories to the original ignored paths. `SHA256SUMS.json` covers every payload except itself. The actual final-build and sealing scripts are included. Later runtime smoke, wrong-binary, twenty-reload and performance evidence must remain separate. Interaction coverage and a two-hour route are outside the revised 0.4.8 release scope.
