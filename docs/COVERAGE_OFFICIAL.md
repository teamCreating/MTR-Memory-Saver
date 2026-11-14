# Official beta.2 coverage audit

Scope: Memory Saver 0.4.4 with official MTR 4.1.0-beta.2, Minecraft 1.21.1,
Java 21 and the two explicit NeoForge targets. New v6 validation is paused.
Audit time: 2026-11-15T03:47:07+08:00 (UTC+08:00).

## Established evidence

- Both official targets build and pass 43 Java tests each; 33 Python tests pass.
- The packaged official-nf248 client passes 24 base-resource loader/fault checks,
  including malformed/missing/oversized inputs, same-path correction and retry,
  native-parser retirement, replacement publication and ownership cleanup.
- Historical source-work comparisons do not establish full-client improvement.
  The 48-run source protocol remains inconclusive because A/A timing equivalence
  did not pass its preregistered band.

## Remaining gates

| Priority | Coverage | Current boundary and required observation |
| --- | --- | --- |
| P1 | Explicit incompatible-binary startup rejection | The actual same-version ZIP-comment negative control reaches BinaryFingerprint.require, but Mixin catches the plugin exception, warns and continues startup. The probe then fails factory_mixin_applied. The documented requirement that startup itself fails before hooks install is not met. Preserve this failure and repair/retest the integration. |
| P1 | Latest full resource catalogue | The isolated 16-pack, 669-entry native-catalogue instance is prepared with frozen pack order, world and artifact hashes, but has not launched. Establish completed registration/parsing, valid largest authored inputs, settled counters and representative geometry/display/door/floor/boarding behavior. Catalogue entries are not a count of distinct parsed models. |
| P1 | Repeated reload and long gameplay | The exact current candidate has no 20 consecutive full-pack reload or two-hour unpaused route result. Observe cache retention, stale publication, native ownership and comparable heap/OS/native/GPU measurements through defined windows. |
| P1 | Controlled full-client performance | Freeze baseline, current candidate, controls and budgets; collect counterbalanced pairs, A/A and instrumentation controls with raw JFR/GC/frame/OS evidence. Source allocation results alone do not settle loading latency, Full-GC pauses or frame regressions. |
| P2 | NeoForge 21.1.265 runtime | Build/headless checks pass; actual packaged startup, native faults, recovery and required Mixin application remain unobserved for this loader. |
| P2 | Registration completion across reloads | finishRegistration currently operates on the current epoch. Establish whether the actual official registration callback can overlap a replacement reload before treating this as a defect or choosing a generation-bound implementation. Existing parser-retirement tests do not establish that caller ordering. |
| P2 | Final exact-artifact delivery audit | After repairs, revalidate changed binaries, evidence hashes, support statements and release ZIP contents. Older 0.3.x/0.4.x passes cannot certify a changed candidate. |

The malformed-model fallback and admission-generation races have already been
repaired and tested; they are not outstanding defects. Full-pack behavior and
registration-callback ordering above remain unverified, rather than proven failures.
The wrong-binary startup result is an observed acceptance failure.

Evidence: [verification plan](../evidence/engineering-044/verification-plan.json),
[packaged fault result](../evidence/engineering-044/packaged-faults-nf248/loader-lifecycle-result.json),
and [wrong-binary assessment](../evidence/engineering-044/packaged-mismatch-nf248/assessment.json).
