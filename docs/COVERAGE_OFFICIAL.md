# Official beta.2 coverage audit

Scope: Memory Saver 0.4.7 candidate and separately identified historical 0.4.6
evidence with official MTR 4.1.0-beta.2, Minecraft 1.21.1,
Java 21 and the two explicit NeoForge targets. New v6 validation is paused.
Updated: 2026-11-17 (UTC+08:00).

The default candidate is now **0.4.7**. Both official targets pass 73 Java tests,
four actual abrupt-exit cleanup checks across writing and workspace waiting, and
four 3 GiB large-OBJ checks across targets and CompactStrings modes. The exact
0.4.6 negative controls retain spill files under the same abrupt-exit harness.
[Owned-channel evidence](../evidence/engineering-048/snapshot-owned-channel/README.md)
and [independent artifact audit](../evidence/engineering-048/candidate-artifact-review/README.md)
bind the new JARs. Only the reader and its Snapshot class change; the other 56
classes are byte-identical. Both exact 0.4.7 packaged official clients now pass
24 lifecycle and 18 real-resource fault checks each, exit normally, and preserve
readable JFRs. Both same-version wrong-binary clients fail fatally before vehicle
registration. [Packaged 0.4.7 evidence](../evidence/engineering-048/packaged-owned-channel/README.md)
binds all four independent JVMs; full-pack interaction, reload endurance, route
duration and controlled performance are still pending.

A fresh official NF248 **0.4.7 / neutral observer 1.0.3** startup now has an
independently sealed settled window: 13/13 valid samples over 60.0146004 seconds
of external observation at a five-second cadence, 1,092 declarations / 1,091
distinct IDs and zero native pending work or observer errors. The native sample
timestamps span 59.7471383 seconds; the external interval is not relabeled as a
continuous sixty-second native trace. All sixteen plan-listed source/installed
archive pairs and the installed artifacts match their fingerprints. DC01's
existing caches contain 5/6 floor regions and ten doorways each. The exact live
default-rail diagnostic is attributed; the account-property error remains visible.
This establishes the stated startup scope, without a visual, boarding, reload,
route, performance or final-exit pass. See the [sealed startup and independent
replay](../evidence/engineering-050/neutral103-startup/README.md).

A later 0.4.6 NF248 run with neutral observer 1.0.2 completed one actual F3+T
ResourceManager reload and exited normally with a readable JFR. Its explicitly
captured before state is more than 15 seconds before input, so the strict accepted
streak remains **0/20**. The input-method issue is resolved; manual input is no
longer requested. Screenshots show the station/empty siding rather than a train.
The earlier unsuccessful inputs and route failures below retain their identities.

Earlier sealed runtime evidence: a fresh official NF248 0.4.6 client with native observer
1.0.0 loaded all sixteen packs, produced 603 native snapshots (601 unpaused and
settled in-world), 33,446 actual frame events and 12,607 server-tick events, and
saved normally with exit code 0. Both DC01 native caches were observed (5/6 floors,
10 doorways each). Its screenshots do not show a train, and no full reload or
performance acceptance follows. The later observer publication/diagnostic repairs
need their own runtime verification. See [sealed runtime evidence](../evidence/engineering-048/neutral-runtime-01/assessment.json).

## Established evidence

- Both official 0.4.7 targets now pass 73 tests each, actual abrupt-exit deletion
  at two reader phases and exact 3 GiB large-input checks in both string modes.
  The independent audit binds each candidate and its unchanged remaining classes.
- Both current 0.4.7 official packaged clients pass all 24 lifecycle and 18
  actual-resource checks, including correction/retry, blocked native-parser
  retirement, replacement publication, balanced tickets/permits and zero used or
  waiting text workspace. Each exits normally with a readable JFR. Both exact
  same-version binary negative controls change only the MTR ZIP comment, install
  no probe, and exit with code 1 through the fatal fingerprint guard before vehicle
  registration. The first NF248 evidence runner's post-exit log-decoding failure
  remains preserved; an independent raw-byte assessment verifies the completed
  JVM's checks and JFR without rewriting that original failed receipt.
- The historical 0.4.6 official targets pass 66 core Java tests each. Five new snapshot-I/O
  cases cover output write/close, restoration read, deletion and suppressed
  cleanup failure, including failed-cache retry and real memory settlement.
  Both unchanged packaged readers also pass an actual Windows deletion-lock
  audit: failed deletion remains an error with a retained file; memory settles,
  and the independent fixture deletes the file after confirmed handle release.
  This does not establish automatic recovery after abrupt JVM termination.
  The archived standalone Python suite passes 100 tests, including background auxiliary-query ownership,
  interrupted thread startup and process-scoped GPU counters. Actual execution,
  source snapshots and logs are archived; the previous 91-test stage is retained.
- Both historical 0.4.6 packaged official clients pass 24 base-resource loader/fault checks,
  including malformed/missing/oversized inputs, same-path correction and retry,
  native-parser retirement, replacement publication and ownership cleanup. Each
  also passes 18 real-resource checks covering actual open/read/close/size failure,
  correction/retry, successful empty text, replacement decoding and missing-cache
  retirement. Both actual JVMs exit normally and their complete JFRs are readable.
- Both exact 0.4.6 same-version wrong-binary clients exit with code 1 before
  registration through MixinInitialisationError, preserving the fingerprint
  cause, with no probe installed. The 0.4.4 warning-only failure and the 0.4.5
  NF248 rejection pass retain their historical artifact identities.
- Default text admission is repaired using shared weighted workspace and owned
  UTF-16 snapshots. The actual 102,035,449-unit OBJ passes the exact packaged
  NF248 reader at 3 GiB with CompactStrings enabled and disabled, preserving raw
  and reencoded hashes and clearing all workspace/files. This is text evidence,
  and does not establish native OBJ geometry or full-pack acceptance.
- The actual 0.4.6 NF248 sixteen-pack load reaches 1092 native vehicle declarations
  and 1091 distinct ID strings. Native and module work and text workspace settle,
  with no renewed large-OBJ decode rejection. Visual geometry, displays, doors,
  floors and boarding remain unverified. The 0.4.5 large-text rejection remains
  historical failed-load evidence under its original artifact identity.
- Static official call-chain analysis finds synchronous reload RETURN injection,
  not an asynchronous registration completion callback. Actual first full-pack
  HEAD/RETURN records are paired on the render thread with nesting one.
- Current-input launcher controls, an independent native observer and the
  whole-client comparison protocol are implemented. The launcher passes 39 tests;
  the observer passes 14 isolated tests per official target, archive/ABI checks
  and companion-version-independent reproducibility. Its synthetic JFR schema
  check is not an actual client Mixin or frame acceptance result. All four
  baseline/candidate and plain/profile qualifications remain missing; no new
  whole-client performance trial has run.
- Historical source-work comparisons do not establish full-client improvement.
  The 48-run source protocol remains inconclusive because A/A timing equivalence
  did not pass its preregistered band.

## Preserved incomplete and failed observations

- The first large-text audit compilation failed during annotation-processor
  discovery. Its command and error log remain alongside the successful second
  attempt; the first attempt produced no source-equivalence pass.
- The initial 0.4.6 startup observer failed its observation gate. Only two of four
  requested GPU samples were available, and two window screenshot captures timed
  out. Registration and settlement evidence remains usable within that boundary.
- Route attempt 01 is interrupted with `passed=false`: 287 samples cover
  1432.8089 seconds of the requested 7200 seconds, with 19 repeated-state failures
  and one unavailable GPU query out of 23. Auxiliary-query delays exposed a
  catch-up sampling defect. The repaired observer skips missed sampling slots.
  Attempt 02 is also interrupted with `passed=false`: 56 samples over 349.2593
  seconds include one 20.8426-second gap beyond the frozen 20-second limit.
  All its GPU/NMT requests were available; serial auxiliary calls still blocked
  sampling. Both partial JFRs end before their final observer samples.
- Three native F3+T API receipts report successful input delivery, but none is
  followed by a new native epoch or full ResourceManager reload log. Successful
  strict reloads and the longest verified sequence remain zero after those inputs. A native F2
  screenshot exports successfully but shows no train, so visual interaction and
  F3+T evidence remain separate gates. The later English-input recovery completed
  a real reload, with a stale-before limitation; manual input is no longer needed.
- A new UI recovery confirms the live target window but both fresh screenshot
  requests time out. No keyboard/mouse input or visual/reload pass follows.
- Route attempt 03 failed when its Java process exited with code 1653. Windows
  Application Error and WER bind that exact process/start time to a crash in
  textinputframework.dll; the triggering cause is not established. All thirteen
  JFR chunks are preserved, twelve readable; the last remains incomplete. The
  first 2400-second sampled window passes, but the complete two-hour session and
  JFR coverage fail. [Recovery and raw evidence](../evidence/engineering-048/route-recovery/assessment.json).
- Historical observer 1.0.1 used ReplaceFileW after MoveFileEx rejected an open
  target. Actual 1.0.2 client collection and concurrent-open controls later
  exposed missing-path/sharing windows. Observer 1.0.3 uses one FileRenameInfoEx
  POSIX replacement; both targets pass 27 tests, including concurrent readers,
  without changing any product class. Its fresh runtime startup is scoped above;
  the earlier failures remain preserved in the [publisher repair evidence](../evidence/engineering-049/publisher-race/README.md).

## Remaining gates

| Priority | Coverage | Current boundary and required observation |
| --- | --- | --- |
| P1 | Full catalogue interaction | The current 0.4.7 NF248 sixteen-pack startup has a sealed settled minute, 1092 declarations/1091 distinct IDs and the observed DC01 caches. Observe geometry, displays, doors, floors and boarding in the actual scene; registration and cache regions do not establish these interactions. Current largest referenced Blockbench input is 13,141,932 bytes; the old 65 MB Blockbench asset is unreferenced. |
| P1 | Twenty consecutive full-pack reloads | Strict accepted reloads remain 0/20. One actual 0.4.6 F3+T reload completed after input-method recovery, but its before snapshot exceeds 15 seconds; earlier no-epoch inputs remain preserved. Require an external input receipt, native HEAD/RETURN pair, complete reload log and settled fresh snapshot for every accepted reload. |
| P1 | Two-hour unpaused route | All three attempts failed. Attempt 03's first 2400-second sampled window passes, but the process crashes and JFR coverage is incomplete. Retain strict sampling/availability gates for a fresh complete route; do not promote the partial window. |
| P1 | Controlled full-client performance | Current control/protocol engineering is ready for qualification. First apply the same final neutral observer in actual clients and qualify baseline/candidate independently in plain/profile modes. The frozen comparison requires 48 independent JVM trials plus separate observer-off calibration. No new performance trial has run. Source allocation results alone do not settle loading latency, Full-GC pauses or frame regressions. |
| P1 | Native Invalid model attribution | A new actual NF248 startup traces its one occurrence to the official default RailResource constructor's empty model/texture arguments and unchanged returned fallback. This accounts for that run's diagnostic, not future logs or rail rendering. The final observer 1.0.2 and experiment consumer require per-run call/return evidence; other errors remain blocking. |
| P2 | NeoForge 21.1.265 full-pack runtime | 0.4.7 build, 73 tests, actual abrupt-exit/large-input audits, 42 packaged checks and fatal same-version wrong-binary rejection pass. Full-pack/world checks remain pending. |
| P2 | Repeated official registration ordering | Static analysis establishes synchronous official reload entry points; the initial 0.4.6 full registration is paired on the render thread with nesting one. Collect the same evidence through 20 actual full ResourceManager reloads. |
| P2 | Snapshot failure boundaries | 0.4.7 actual abrupt exits delete this owner's snapshot during writing and budget waiting, while other-owner sentinels remain unchanged. Real disk-full and power loss remain untested. There is deliberately no broad stale-file sweep. |

The previous 0.4.6 release ZIPs remain intact. Both 0.4.7 delivery bundles have a
[version-bound support/evidence audit](../evidence/engineering-049/release/README.md);
their packaged-client checks and the stated NF248 startup scope are complete.
The remaining gameplay, endurance and performance gates above are unchanged.

The malformed-model fallback and admission-generation races have already been
repaired and tested. Full-pack interaction and repeated reload ordering remain
unverified. The 0.4.5 default large-text rejection was an observed acceptance
failure. Its surviving JFR chunks are preserved; its final open chunk is incomplete,
and it is not controlled performance evidence. The incomplete 0.4.6 startup and
route observations likewise cannot establish visual or long-session acceptance.

Evidence: [historical verification plan](../evidence/engineering-046/verification-plan.json),
[current verification progress](../evidence/engineering-047/verification-progress.json),
[neutral observer assessment](../evidence/engineering-047/neutral-observer/assessment.json),
[controlled client protocol](CLIENT_EXPERIMENT.md),
[snapshot-I/O assessment](../evidence/engineering-047/snapshot-io/assessment.json),
[route attempt 03 start](../evidence/engineering-047/route-attempt-03-start/execution-start.json),
[route attempt 03 first window](../evidence/engineering-047/route-attempt-03-first-window/assessment.json),
[packaged fault result](../evidence/engineering-046/packaged-faults-nf248/loader-lifecycle-result.json),
[NF265 wrong-binary assessment](../evidence/engineering-046/packaged-mismatch-nf265/assessment.json),
[large-text assessment](../evidence/engineering-046/text-workspace/attempt-02/assessment.json),
[initial 0.4.6 full-load assessment](../evidence/engineering-046/full-load-initial-nf248/assessment.json),
[interrupted route assessment](../evidence/engineering-046/route-attempt-01/assessment.json),
[reload input assessment](../evidence/engineering-046/reload-input-attempts/assessment.json),
and [historical failed 0.4.5 full load](../evidence/engineering-045/packaged-full-load-before-text-fix-nf248/failed-full-load-assessment.json).
