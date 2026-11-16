# Official beta.2 coverage audit

Scope: Memory Saver 0.4.6 with official MTR 4.1.0-beta.2, Minecraft 1.21.1,
Java 21 and the two explicit NeoForge targets. New v6 validation is paused.
Updated: 2026-11-16T14:05:09.075618+08:00 (UTC+08:00).

Latest runtime evidence: a fresh official NF248 0.4.6 client with native observer
1.0.0 loaded all sixteen packs, produced 603 native snapshots (601 unpaused and
settled in-world), 33,446 actual frame events and 12,607 server-tick events, and
saved normally with exit code 0. Both DC01 native caches were observed (5/6 floors,
10 doorways each). Its screenshots do not show a train, and no full reload or
performance acceptance follows. The later observer publication/diagnostic repairs
need their own runtime verification. See [sealed runtime evidence](../evidence/engineering-048/neutral-runtime-01/assessment.json).

## Established evidence

- Both official targets now pass 66 core Java tests each. Five new snapshot-I/O
  cases cover output write/close, restoration read, deletion and suppressed
  cleanup failure, including failed-cache retry and real memory settlement.
  Both unchanged packaged readers also pass an actual Windows deletion-lock
  audit: failed deletion remains an error with a retained file; memory settles,
  and the independent fixture deletes the file after confirmed handle release.
  This does not establish automatic recovery after abrupt JVM termination.
  The archived standalone Python suite passes 100 tests, including background auxiliary-query ownership,
  interrupted thread startup and process-scoped GPU counters. Actual execution,
  source snapshots and logs are archived; the previous 91-test stage is retained.
- Both packaged official clients pass 24 base-resource loader/fault checks,
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
  real reloads and the longest verified reload sequence are both zero. A native F2
  screenshot exports successfully but shows no train, so visual interaction and
  F3+T remain separate gaps. A manual qualification is requested from the user.
- A new UI recovery confirms the live target window but both fresh screenshot
  requests time out. No keyboard/mouse input or visual/reload pass follows.
- Route attempt 03 failed when its Java process exited with code 1653. Windows
  Application Error and WER bind that exact process/start time to a crash in
  textinputframework.dll; the triggering cause is not established. All thirteen
  JFR chunks are preserved, twelve readable; the last remains incomplete. The
  first 2400-second sampled window passes, but the complete two-hour session and
  JFR coverage fail. [Recovery and raw evidence](../evidence/engineering-048/route-recovery/assessment.json).
- Real Windows tests exposed a separate observer publication conflict: shared
  delete access alone does not permit MoveFileEx replacement over an open target.
  The probe-only publisher now uses ReplaceFileW, preserving the old reader's
  bytes and reporting actual failures. Two targets pass eighteen tests each at
  observer 1.0.1; this repair changes no product class or native game state.

## Remaining gates

| Priority | Coverage | Current boundary and required observation |
| --- | --- | --- |
| P1 | Full catalogue interaction | The 0.4.6 NF248 16-pack/669-entry catalogue has registered 1092 declarations/1091 distinct IDs and settled. Observe geometry, displays, doors, floors, boarding and native diagnostics in the actual scene. Current largest referenced Blockbench input is 13,141,932 bytes; the old 65 MB Blockbench asset is unreferenced. |
| P1 | Twenty consecutive full-pack reloads | Successful actual F3+T reloads are 0/20. Three input receipts lack a corresponding new epoch and full ResourceManager reload log. Require an external input receipt, native HEAD/RETURN pair, complete reload log and settled fresh snapshot for every accepted reload. |
| P1 | Two-hour unpaused route | All three attempts failed. Attempt 03's first 2400-second sampled window passes, but the process crashes and JFR coverage is incomplete. Retain strict sampling/availability gates for a fresh complete route; do not promote the partial window. |
| P1 | Controlled full-client performance | Current control/protocol engineering is ready for qualification. First apply the same final neutral observer in actual clients and qualify baseline/candidate independently in plain/profile modes. The frozen comparison requires 48 independent JVM trials plus separate observer-off calibration. No new performance trial has run. Source allocation results alone do not settle loading latency, Full-GC pauses or frame regressions. |
| P1 | Native Invalid model attribution | A new actual NF248 startup traces its one occurrence to the official default RailResource constructor's empty model/texture arguments and unchanged returned fallback. This accounts for that run's diagnostic, not future logs or rail rendering. The common observer and experiment consumer are being extended to require per-run call/return evidence; other errors remain blocking. |
| P2 | NeoForge 21.1.265 full-pack runtime | Build, 66 tests, actual packaged startup, all 42 fault/resource checks and wrong-binary rejection pass. Full-pack/world and representative interaction checks on this loader remain to be observed. |
| P2 | Repeated official registration ordering | Static analysis establishes synchronous official reload entry points; the initial 0.4.6 full registration is paired on the render thread with nesting one. Collect the same evidence through 20 actual full ResourceManager reloads. |
| P2 | Snapshot failure boundaries | Injected snapshot write/close/read/delete and actual Windows deletion-lock tests pass. Real disk-full, abrupt JVM exit and stale-file recovery remain separate coverage; explicit fixture cleanup is not automatic product cleanup. |

Both current release ZIPs have been refreshed and audited against their unchanged
tested JARs, manifests and support bytes. Later acceptance results require a fresh
support/evidence audit before expanding runtime claims.

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
