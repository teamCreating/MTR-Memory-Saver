# Same-launch native log across Log4J2 rollover

This batch repairs the native-log input used by the recorder, reload observer and both sides of `client_experiment`. It reads the released rolling stream as original bytes: date ascending, same-date index descending (`fileIndex=min`), then the owned prefix of `latest.log`. No original log was edited, removed, filtered or normalized. `debug.log` is not a substitute. No game input, launch, restart or stop was performed by these scripts.

The final targeted engineering execution ran **60 tests, exit 0**, with all 11 source/config/test fingerprints unchanged. The read-only check of the existing PID 18796 reconstructed **30,411 bytes** from the original 6,598-byte gzip (28,764 decoded) and a 1,647-byte active prefix. Its beginning equals the independently preserved 27,952-byte startup02 prefix. Replaying the earlier frozen diagnostic code and five pinned proof dependencies produces exactly the earlier startup summary's diagnostics. The official default-rail diagnostic and account/network error remain in the raw log and result.

## Released configuration, separately bound per target

`release-proof-02` is the authoritative capture of actual marker, plan, launch, version profile, three deduplicated dependency JARs, XML/class members, and original `javap -c -p` stdout/stderr with execution metadata. NF248 selects FML 4.0.43; NF265 selects FML 4.0.45. Both actual releases select Log4J core 2.22.1 and the same logging XML. `config/native-log-reader.json` pins each supported combination separately. An unreviewed dependency/profile fails rather than inheriting the observed contract.

The production `forgeclient` handler invokes `CommonLaunchHandler.overwriteLoggingConfiguration`: it obtains `log4j2.xml` from module `fml_loader` and reconfigures Log4J. This is based on that released code, not classpath order or an assets XML guess. The File appender is `RollingRandomAccessFile`, `logs/latest.log`, `logs/%d{yyyy-MM-dd}-%i.log.gz`, TimeBased and OnStartup policies, maximum 99, `fileIndex=min`, default minimum 1. The date trigger runs on the first append after the boundary. The released min strategy moves older same-date `i` to `i+1`, so index 1 is newest. The released rename action also supports copy/delete and copy/truncate fallbacks; content-verified reindexing can therefore change or reuse a file identity.

The first exploratory `release-proof` is retained separately. Its role-based output paths collided when the second loader was added. `preliminary-limitations.json` explicitly excludes those overwritten transcripts from authoritative acceptance. The second capture uses the exact JAR SHA as its namespace.

## Reader and evidence contract

Each reader freezes the actual plan/launch bytes, exact dependency and XML fingerprints, complete process identity supplied by the verified native process handle, reader/config hashes, and anchor origin in `native-log/context.json`. Every successful capture has an immutable receipt, namespace metadata before and after, original gzip/active bytes, raw/decoded lengths and SHA-256, gzip CRC32/ISIZE, logical offsets and file identities. Producer references pin both the context and exact receipt. Recorder selection reconstructs the original before prefix from these segments and checks its identity and capture interval; observer completion freezes the same logical stream. Baseline and candidate trials use this same reader.

Attaching after rollover requires an explicit independently captured prefix from that exact launched JVM. Both live recorder and observer accept `--log-prefix-witness`; for the still-existing owned049c instance it is:

```
evidence/engineering-050/neutral103-startup/capture-01/observation/native-log-at-completion.log
```

The context preserves the witness source and SHA; `anchor.bin` preserves its exact bytes. A fresh owned trial without archives may establish its first complete unique startup header as the anchor, recording that different origin explicitly. The header must match the reviewed logger/message syntax and contain the instance path bytes. This path check is a byte substring check, not a complete `--gameDir` token/argv parser. It is not independently sufficient to establish launch identity: this actual attachment also requires the explicit previously sealed prefix, frozen plan/launch and native process identity. Native row timestamps are not parsed using Chinese or English month names.

Previously observed logical prefixes and retired bytes must survive. Retired raw bytes may move only in the reviewed same-date min reindex direction, with the verified old identity/hash retained in the receipt. A replacement active file must have a matching new retired publication. Duplicate payloads/identities, foreign or repeated startup headers, same-date sequence holes, changed/deleted observed segments, truncation, invalid UTF-8, malformed/concatenated/trailing gzip or CRC failure are rejected. Calendar dates with no archive are not automatically gaps: the logger need not emit every day. This is a consistency proof for the preserved anchor and observed publications; it cannot prove that an entirely unobserved archive was never externally removed before attachment. The actual two-segment check retains the full witnessed startup archive and all available active bytes.

Namespace/rename/compression changes have at most eight capture attempts separated by 0.25 seconds. The compression intermediate is recognized from the released file pattern. These limits bound publication retries, not total I/O or compression time. A long compression or abandoned intermediate fails closed; a partial/empty gzip appearing without a visible intermediate can fail CRC/completeness immediately. Genuine integrity and permission failures are not retried to a later pass. Fresh startup without a complete log is explicitly unavailable. Exhaustion writes a failure receipt. A completion-read failure cannot be accepted using the last trusted prefix: that prefix is retained only with an explicit failed marker.

## Preserved validation and limits

- `actual-inputs`: original gzip, earlier 330-byte active prefix, startup witness and actual plan/launch with owned-read metadata. These are historical prefixes, not a statement of current `latest.log` size.
- `engineering-run-01`: all 176 executed tests and original failure output. 174 passed; the recorder truncation test still expected the old exception type, and the pre-existing real-time 0.3-second shutdown fixture returned failure. The temporary fixture summary was not preserved, so its exact run-specific cause is not inferred. Neither production timing thresholds nor that real-time test were relaxed or repeatedly rerun to obtain a pass.
- `engineering-run-02-targeted`: 58 targeted tests, exit 0, intermediate frozen inputs.
- `engineering-run-03-final`: final 60 targeted tests, exit 0. Includes actual preserved gzip, earlier witness, midnight rollover, min reindex including copy/truncate identities, calendar gaps, foreign startup, sequence gap, corruption, retired mutation/removal, duplicate payload, unexplained replacement, rotation during owned read, bounded transitions, source pins and stop/lifecycle integrations.
- `actual-read-01`: actual native identity, raw snapshot/epoch/diagnostic JSONL, source copies, logical log and complete segment/context/receipt evidence. Capture ran read-only from 2026-11-16 17:16:27.322514 to 17:16:28.016575 UTC (2026-11-17 UTC+08:00). It closed only its own process handle.
- `sealed-dependencies`: byte-exact post-capture copies of previously committed startup sources, summary/index and five diagnostic proof files. Copy provenance is explicit; these are not a new live capture. The original files and historical failed attempts remain unchanged.

An independent sibling agent also read the helper/config and recomputed the authoritative release JAR/XML hashes. Its read-only review found no release-profile or ordering blocker for this known attachment and reported the header/transition limits above. This review did not change runtime source or repeat tests.

This establishes the reader repair and read-only reconstruction/diagnostic replay. It grants no 20-reload, vehicle appearance, route, performance or complete game-exit acceptance. Startup02 remains its original limited minute of observation; the now longer diagnostic input does not extend that old observer run.

## Sealed-only verification

`sha256-index.json` covers every payload in this directory except itself and bytecode caches. The verifier imports only frozen source copies, reconstructs original segments using both the frozen reader and independent stdlib gzip, verifies prior startup index/proof pins, replays frozen diagnostics, checks the exact release/class/javap evidence, and checks original test receipts. It does not read a live instance, current source or process. Results and the actual subprocess receipt are outside this index in `../native-log-stream-verification`.

From the repository root, choose a fresh output filename:

```powershell
.\.venv\Scripts\python.exe -X utf8 evidence/engineering-050/native-log-stream/verify_sealed.py --output .cache/native-log-stream-recheck.json
```
