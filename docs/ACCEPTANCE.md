# Acceptance and performance procedure

Updated: 2026-11-15T06:21:31.898993+08:00 (UTC+08:00).

Use the [optimization and comparison workflow](OPTIMIZATION.md) to preregister
hypotheses, controls and budgets and interpret paired evidence. Its source runner
automates plan/run/analysis with A/A and instrumentation controls; client phases
below still require their actual isolated workload and packaged binaries.

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
propagates real provider read failures. Both official 0.4.6 artifacts pass 61 Java
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

Current real F3+T reload acceptance is 0/20. Three successful input API receipts
produced no new native epoch or complete ResourceManager reload log. Route attempt
01 was interrupted with `passed=false` after 287 samples over 1432.8089 seconds,
with 19 repeated-state failures and one unavailable GPU query out of 23. The
catch-up defect is repaired, but attempt 02 still fails one 20.8426-second gap:
serial GPU/NMT queries block its sampling loop. Preserve both attempts and their
partial JFRs; do not relax the frozen 20-second limit. Bounded background auxiliary
observation now passes regressions, preserving request/terminal events and the
actual sampling cutoff; a fresh two-hour run remains pending. Native F2 export succeeds,
but that screenshot contains no train. A manual F3+T qualification is requested.
See the [current verification plan](../evidence/engineering-046/verification-plan.json).

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
2. Warm up an identical world/route, then collect at least three paired baseline
   and candidate runs in alternating order with the same heap (start at 3 GiB).
   Capture JFR and unified GC logs, loading/reload wall time, allocation samples,
   Full-GC count/pause sum and frame-interval p50/p95/p99/max. Keep raw recordings.
   Include an uninstrumented timing control to quantify probe/JFR overhead.
   Freeze `maxsize=0` in the recording configuration to retain the complete window;
   JDK 21 otherwise applies an implicit 250 MiB limit and discards older chunks.
   Preserve `JFR.check verbose=true`, dump while the process is still alive and
   verify the dump with `jfr summary` before saving and closing the client.
3. Complete at least 20 consecutive full-pack reloads and a two-hour route session.
   Separate reload/warm-up/steady-state windows. Require all parse/permit counters
   to settle and no monotonically growing completed source cache. Compare heap at
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
