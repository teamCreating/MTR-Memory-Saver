# Acceptance and performance procedure

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

The fresh 0.4.7 NF248 / observer 1.0.3 run now passes a separately
[sealed startup observation](../evidence/engineering-050/neutral103-startup/README.md):
13/13 independent samples at five-second cadence cover 60.0146004 seconds of
external observation, with all sixteen archive pairs verified, 1092 declarations,
1091 distinct IDs and no native pending work or observer errors. Its native
timestamps span 59.7471383 seconds. This startup window does not qualify the later
paused/UI portions, a complete exit, interactions, twenty reloads or performance.
Use the default five-second cadence when requiring every observed native state
to advance; the one-second failed attempt and identity-query failures remain
[preserved separately](../evidence/engineering-050/observation-attempts/README.md).

A later 0.4.6 NF248 run with neutral observer 1.0.2 completed one actual F3+T
ResourceManager reload and exited normally with a readable JFR. Its explicitly
captured before state is more than 15 seconds before input, so the strict accepted
streak remains **0/20**. The input-method issue is resolved; manual input is no
longer requested. Screenshots show the station/empty siding rather than a train.
The earlier unsuccessful inputs and route failures below retain their identities.

Use the [optimization and comparison workflow](OPTIMIZATION.md) to preregister
hypotheses, controls and budgets and interpret paired evidence. Its source runner
automates plan/run/analysis with A/A and instrumentation controls. The
[whole-client protocol](CLIENT_EXPERIMENT.md) separately freezes actual packaged
client inputs and prerequisite qualification; source evidence cannot replace it.

0.4.2 records NF248 official/v6 development-client Mixin smoke checks and 100 v6
synthetic GPU ownership cycles. Those historical reports do not record full-pack
performance, packaged-release/world acceptance or long-session validation. A build
or headless test does not substitute for those checks. Historical 0.3.x trials
retain their original identities.

0.4.4 adds actual official-nf248 packaged-client fault checks: missing, truncated,
wrong-root and oversized input, correction/retry, and native-parser retirement.
The optional observation JAR pauses the real submission after the native ticket
starts, allowing verification that canceled running work retains its ownership
until actual exit. This fault hook is excluded from product releases. It does not
replace the full-pack/world/reload/long-session procedure below. New v6 validation
is paused; current runs target official MTR 4.1.0-beta.2.

The [official coverage audit](COVERAGE_OFFICIAL.md) preserves the historical 0.4.5
NF248 wrong-binary rejection and its failed full-pack load: the old default text
limit rejected a valid authored OBJ despite settled module counters. 0.4.6 repairs
the policy with shared weighted text workspace and immutable snapshots and
propagates real provider read failures. Both official 0.4.6 artifacts pass 66 Java
tests and 42 packaged fault/resource checks each; the actual large OBJ passes exact
NF248 source checks with CompactStrings enabled and disabled. The 0.4.6 NF265
wrong-binary startup is fatal before registration. The exact 0.4.6 NF248 mismatch
also exits with code 1 before registration through the same fatal guard.

The initial 0.4.6 NF248 sixteen-pack registration reaches 1092 declarations and
1091 distinct ID strings, and native/module work and text workspace settle without
the old large-OBJ decode rejection. Geometry, displays, doors, floors and boarding
still need visual and interaction evidence. The initial startup observer failed
its gate with only two of four requested GPU samples available; screenshot capture
timed out twice. These failures remain alongside the registration evidence.

Earlier input attempts preserve three successful input API receipts that
produced no new native epoch or complete ResourceManager reload log. Route attempt
01 was interrupted with `passed=false` after 287 samples over 1432.8089 seconds,
with 19 repeated-state failures and one unavailable GPU query out of 23. The
catch-up defect is repaired, but attempt 02 still fails one 20.8426-second gap:
serial GPU/NMT queries block its sampling loop. Preserve both attempts and their
partial JFRs; do not relax the frozen 20-second limit. Bounded background auxiliary
observation now passes regressions, preserving request/terminal events and the
actual sampling cutoff. Route attempt 03 also fails: the exact Java process
crashes in Windows textinputframework.dll with exit code 1653. Twelve of thirteen
preserved JFR chunks are readable; the final chunk is incomplete. Its first
forty-minute sampled window does not establish two-hour acceptance. Native F2 export succeeds,
but that screenshot contains no train. The later input-method recovery above
provides functional reload evidence without satisfying the strict before gate.
The new official NF248 diagnostic client traces its one `transparent.png Invalid
model` occurrence to the official empty default-rail constructor. Future client
qualification must bind its own live diagnostic evidence; this does not certify
rail rendering. A new native observer 1.0.0 run provides actual native snapshots,
frame/tick events and a normal saved exit, with no geometry/reload/performance
pass inferred. See the [runtime record](../evidence/engineering-048/neutral-runtime-01/assessment.json),
[route recovery](../evidence/engineering-048/route-recovery/assessment.json), and the
[current progress](../evidence/engineering-047/verification-progress.json) and
[historical verification plan](../evidence/engineering-046/verification-plan.json).

## Reproducible headless checks

Run `gradlew test` and the standalone Python tests for each active official preset.
New v6 ABI validation is paused. Lifecycle tests include 1,000 generations, read/parse failure,
failure retry, canceled queue entries, interrupted admission, timeout and native
work that ignores interruption. At quiescence, require zero pending futures,
outstanding tasks, queued descriptors, native task tickets and active read permits.
Also require zero used text workspace and zero waiting workspace claims.
During canceled work that still runs, the ticket and permit must remain positive.

Core audits and microbenchmarks belong in `tools/acceptance/`; their runners accept
explicit archives/dependencies and write fresh, fingerprinted reports. Paired runs
must use equal heap/JVM settings, exact file bytes and order, warm-up/repetition
counts and instrumentation. Report elapsed time, allocation traffic, GC and sampled
heap separately. Text/source-lookup microbenchmarks exclude native parsing, model
construction, GPU work and frames; no gameplay claim follows from their results.

## Actual client acceptance

Use an isolated client directory (`gradlew runClient` uses `build/run/<target>`).
Record a run manifest before starting: candidate and all mod JAR SHA-256 values,
pack archive hashes/order, Java version/arguments, loader, world snapshot hash,
camera/train/route, render distance, VSync/FPS cap, scheduler settings and machine.
Reject a paired comparison when any control other than the candidate differs.
Do not reuse a mutable world or modify ordinary user instances for testing.

1. Confirm the exact runtime binary guard and every required Mixin applied. Start
   once with the expected MTR artifact and once with a same-version mismatched
   binary in the isolated client; the second must fail before hooks install.
2. Follow [CLIENT_EXPERIMENT.md](CLIENT_EXPERIMENT.md) for the official whole-client
   comparison. Qualify the exact baseline and candidate independently in both
   plain and profile modes with identical neutral observer bytes and frozen
   controls. Then run the declared six pairs in each A/A or A/B and plain or
   profile stratum: 48 fresh JVM trials at the same heap. Preserve complete raw
   logs, native snapshots, process/OS evidence and profile JFR/GC/frame records.
   Plain/profile controls measure the JFR/GC increment; a separate observer-off
   calibration is required before claims about ordinary uninstrumented play.
   Missing qualification or unreviewed native diagnostics prevents a valid plan.
   Freeze `maxsize=0` in the recording configuration to retain the complete window;
   JDK 21 otherwise applies an implicit 250 MiB limit and discards older chunks.
   Preserve `JFR.check verbose=true`, dump while the process is still alive and
   verify the dump with `jfr summary` before saving and closing the client.
3. Complete at least 20 consecutive full-pack reloads and a two-hour route session.
   Separate reload/warm-up/steady-state windows. Require all parse/permit counters
   to settle when supported; require native pending/settled evidence on both arms.
   Unsupported companion counters remain unavailable. Require no monotonically
   growing completed source cache. Compare heap at
   the same quiescent points; forced GC is a diagnostic, not normal play timing.
   For packaged clients use `tools/observe_packaged_client.py`: distinct native
   epochs alone are insufficient. Each reload must match a confirmed external
   F3+T receipt, the full ResourceManager log, a native HEAD/RETURN pair and a
   fresh settled snapshot before the next reload. Keep declaration-list and
   distinct-ID counts separate. Native decode/parse errors prevent acceptance
   even when module counters report zero failures.
   The route observer requires displacement of the same vehicle in each frozen
   observation window. A changed vehicle ID or one early movement cannot certify
   the complete session. Audit raw traces for repeated route travel, legitimate
   station dwell, departures, doors and game-time advancement; trajectory
   eligibility alone does not establish those interaction checks. Check the JFR
   recording's actual first/last event and coverage against the requested window.
4. Trigger a missing input, truncated/invalid model, oversized text, a reader
   failure, cancellation and reload during a blocked/slow parse. Require a visible
   failure/diagnostic, terminal future, retry after correction and balanced counts.
5. V6 validation remains paused at the user's request. After validation explicitly
   resumes, run its optional GPU probe inside the rendering client. Check closed
   facades are not repopulated, distinct consumers build distinct GPU models,
   closing one consumer preserves another, staging is released only by its proper
   owner, and repeated close/build rejection remain valid. Also inspect trains,
   displays, doors, floors/doorways, interaction and resource reload in the scene.

Acceptance fails on an unresolved future, stale replacement-generation entry,
unbalanced task ticket, GPU double-close/cross-owner disposal, geometry mismatch or
uncaught crash. Performance regressions must be reported independently from
correctness and memory gains. Set comparison budgets in the run manifest before
collecting data; do not choose them after seeing measurements. The historical
10–11 Full GCs/~13.5 seconds of reload pause time remain unresolved performance
evidence until a controlled newer comparison measures an improvement.

Record each result with candidate/input/control hashes, exact observation window,
raw evidence references, passed/failed checks and missing coverage. Update the
support matrix only for the exact artifact/loader/fixture actually exercised.
