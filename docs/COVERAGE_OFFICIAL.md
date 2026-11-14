# Official beta.2 coverage audit

Scope: Memory Saver 0.4.5 with official MTR 4.1.0-beta.2, Minecraft 1.21.1,
Java 21 and the two explicit NeoForge targets. New v6 validation is paused.
Updated: 2026-11-15T04:17:00+08:00 (UTC+08:00).

## Established evidence

- Both official targets build and pass 43 Java tests each; the standalone Python
  suite includes the process-exit and packaged-observer regression checks.
- Both packaged official clients pass 24 base-resource loader/fault checks,
  including malformed/missing/oversized inputs, same-path correction and retry,
  native-parser retirement, replacement publication and ownership cleanup.
- The actual same-version wrong-binary NF248 client exits with code 1 before
  resource registration through MixinInitialisationError. The 0.4.4 warning-only
  failure remains immutable negative evidence.
- Static official call-chain analysis finds synchronous reload RETURN injection,
  not an asynchronous registration completion callback. Actual first full-pack
  HEAD/RETURN records are paired on the render thread with nesting one.
- Historical source-work comparisons do not establish full-client improvement.
  The 48-run source protocol remains inconclusive because A/A timing equivalence
  did not pass its preregistered band.

## Remaining gates

| Priority | Coverage | Current boundary and required observation |
| --- | --- | --- |
| P1 | Large valid text and full catalogue | The actual isolated 16-pack run registers 1092 declarations/1091 distinct IDs and settles module work, but the default 100,663,296-code-unit limit rejects a valid 102,035,449-code-unit OBJ. Repair and repeat full loading, native diagnostics, geometry/display/door/floor/boarding checks. Current largest referenced Blockbench input is 13,141,932 bytes; the old 65 MB Blockbench asset is not referenced by current vehicles. |
| P1 | Repeated reload and long gameplay | The exact current candidate has no 20 consecutive full-pack reload or two-hour unpaused route result. Observe cache retention, stale publication, native ownership and comparable heap/OS/native/GPU measurements through defined windows. |
| P1 | Controlled full-client performance | Freeze baseline, current candidate, controls and budgets; collect counterbalanced pairs, A/A and instrumentation controls with raw JFR/GC/frame/OS evidence. Source allocation results alone do not settle loading latency, Full-GC pauses or frame regressions. |
| P2 | NeoForge 21.1.265 full-pack runtime | Build, 43 tests, actual packaged startup and all 24 fault checks pass. Full-pack/world checks and wrong-binary rejection on this loader remain to be observed. |
| P2 | Repeated official registration ordering | Static analysis establishes synchronous official reload entry points; the first actual full reload is paired on the render thread. Collect the same evidence through 20 actual full ResourceManager reloads. No generation-token repair is justified by the old callback hypothesis. |
| P2 | Final exact-artifact delivery audit | After repairs, revalidate changed binaries, evidence hashes, support statements and release ZIP contents. Older 0.3.x/0.4.x passes cannot certify a changed candidate. |

The malformed-model fallback and admission-generation races have already been
repaired and tested; they are not outstanding defects. Full-pack behavior and
registration-callback ordering above remain unverified, rather than proven failures.
The current default large-text rejection is an observed acceptance failure. The
failed full-pack run's surviving JFR chunks are preserved; its final open chunk
is incomplete, and it is not controlled performance evidence. Window screenshot
capture timed out twice, so visual interaction results are not claimed.

Evidence: [verification plan](../evidence/engineering-045/verification-plan.json),
[packaged fault result](../evidence/engineering-045/packaged-faults-nf248/loader-lifecycle-result.json),
[wrong-binary assessment](../evidence/engineering-045/packaged-mismatch-nf248/assessment.json),
and [failed full load](../evidence/engineering-045/packaged-full-load-before-text-fix-nf248/failed-full-load-assessment.json).
