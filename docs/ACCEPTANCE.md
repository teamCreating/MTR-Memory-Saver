# Acceptance and performance procedure

Use the [optimization and comparison workflow](OPTIMIZATION.md) to preregister
hypotheses, controls and budgets and interpret paired evidence. Its source runner
automates plan/run/analysis with A/A and instrumentation controls; client phases
below still require their actual isolated workload and packaged binaries.

0.4.2 records NF248 official/v6 development-client Mixin smoke checks and 100 v6
synthetic GPU ownership cycles. Full-pack performance, packaged-release/world
acceptance and long-session validation remain unrecorded. A build or headless
test is not a substitute for those checks. Historical 0.3.x trials retain their
original identities.

0.4.4 adds actual official-nf248 packaged-client fault checks: missing, truncated,
wrong-root and oversized input, correction/retry, and native-parser retirement.
The optional observation JAR pauses the real submission after the native ticket
starts, allowing verification that canceled running work retains its ownership
until actual exit. This fault hook is excluded from product releases. It does not
replace the full-pack/world/reload/long-session procedure below. New v6 validation
is paused; current runs target official MTR 4.1.0-beta.2.

## Reproducible headless checks

Run `gradlew test` and the standalone Python tests for each preset. Exercise both
official and v6 ABIs. Lifecycle tests include 1,000 generations, read/parse failure,
failure retry, canceled queue entries, interrupted admission, timeout and native
work that ignores interruption. At quiescence, require zero pending futures,
outstanding tasks, queued descriptors, native task tickets and active read permits.
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
3. Complete at least 20 consecutive full-pack reloads and a two-hour route session.
   Separate reload/warm-up/steady-state windows. Require all parse/permit counters
   to settle and no monotonically growing completed source cache. Compare heap at
   the same quiescent points; forced GC is a diagnostic, not normal play timing.
4. Trigger a missing input, truncated/invalid model, oversized text, a reader
   failure, cancellation and reload during a blocked/slow parse. Require a visible
   failure/diagnostic, terminal future, retry after correction and balanced counts.
5. For v6, run the optional GPU probe inside the rendering client. Check closed
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
