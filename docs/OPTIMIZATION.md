# Optimization and controlled comparison

Use this procedure for each optimization. A completed build, a smaller heap limit,
and a faster source benchmark answer different questions. Record them separately.
The executable source experiment is `tools/benchmark_sources.py`; the complete
client gates remain in [ACCEPTANCE.md](ACCEPTANCE.md). No current source experiment
certifies a packaged client, full resource-pack reload or long route session.

The [first complete 48-trial run](../evidence/source-protocol-20261114/README.md)
demonstrates this decision process: allocation and elapsed guardrail pass, while
A/A timing equivalence remains inconclusive. Its plan and failures/noise remain
preserved without changing the acceptance budgets.

## Development loop

1. **Define the problem and unit.** State the observed failure or cost, exact
   artifact/loader/MTR/pack identities, affected phase and relevant units. Distinguish
   allocated bytes, retained heap, admitted cache weight, OS working set, private
   commitment and GPU allocation. Preserve the original failure and raw evidence.
2. **Diagnose separately.** Use JFR, GC logs, cache counters and, where needed, native
   memory diagnostics to locate repeated work and retaining owners. Diagnostic
   forced GC, heap dumps and detailed profiling have overhead; they do not belong
   in ordinary timing windows. A large allocation sample is not a retained-size
   measurement. Do not infer native memory by subtracting unrelated peak values.
3. **Specify a falsifiable hypothesis.** Identify the expected mechanism, one primary
   endpoint and acceptable regression budgets before measuring. Use an unchanged
   artifact as baseline. Change one mechanism per candidate when causal attribution
   matters; a bundled version comparison establishes only the bundle's effect.
4. **Freeze the experiment.** Save exact artifacts, input hashes/order, JDK and JVM
   flags, warm-up/workload, seed/order, repetition count, metric definitions and
   budgets. Record power mode and background/thermal limitations. Keep heap size
   and scheduler equal. Heap reduction and scheduler tuning are later experiments.
5. **Establish correctness independently.** Run native-reference geometry/text
   audits, failure/retry/retirement tests and negative controls. Make the historical
   defect fail the check. Shared output from two implementations is insufficient:
   both may be wrong. A correctness failure blocks performance acceptance.
6. **Measure the declared experiment.** Start a fresh JVM for every replicate. Use
   blocked, counterbalanced A/B order, A/A noise controls and matched instrumentation
   controls. Keep all failures, OOMs, timeouts and slow runs. If inputs change, stop
   that experiment and retain it as invalid; make a new plan for another attempt.
7. **Decide without moving the threshold.** Report every paired delta and its
   uncertainty. Require A/A equivalence inside the frozen tolerance, primary
   benefit, and all regression budgets. Missing data is invalid; insufficient
   precision is inconclusive. An inconclusive result does not authorize lowering
   the budget, extending only the favorable arm or repeatedly testing until pass.
8. **Validate the actual client.** Test packaged binaries with the full input set,
   startup, native reload, the fixed route, native caches and GPU ownership. Repeat
   reloads and long sessions according to the separate acceptance procedure.
   Smoke, microbenchmark and full-client results retain their own identities.
9. **Deliver or reject.** Archive the plan, failures, raw recordings, report and
   decision. Record the mechanism and remaining limits in `walkthrough.md` with an
   explicit UTC offset. Update support only for observed artifact/fixture pairs;
   retain the baseline and rollback instructions. A rejected optimization remains
   useful evidence and must not disappear from the history.

## Executable source experiment

The command now has three stages. The old single-command CLI is replaced so the
complete plan exists before any timed workload. Python 3.11+ and Java 21 are needed.

```powershell
python tools/benchmark_sources.py plan `
  --java-home '<Java 21 JDK>' `
  --baseline '<baseline JAR>' --candidate '<candidate JAR>' `
  --jobs '<jobs.json>' --policy config/source-experiment.json `
  --environment-notes '<observed power mode, background activity and limitations>' `
  --output '<new experiment directory>'

python tools/benchmark_sources.py run --plan '<experiment directory>/plan.json'

python tools/benchmark_sources.py analyze --plan '<experiment directory>/plan.json' `
  --output '<new analysis.json>'
```

Input jobs are a nonempty array of `archive`, `model` and `sha256`. Relative archive
paths resolve against the jobs file's directory. Duplicate ZIP members, changed
entry hashes and invalid UTF-8 are rejected. UTF-8 replacement and arbitrary UTF-16
semantics belong to the independent codec tests. Every valid input byte string is
hashed independently with Python; the ordered digest sequence determines the
expected warm-up and measurement answers. Neither measured Java implementation
supplies the expected answer.

The policy is configuration, not product behavior. Its default declares allocation
as primary (at least 10% median reduction), an elapsed-time guardrail (at most 5%
median increase), six independent pairs, 95% confidence and A/A tolerances of 15%
for elapsed time and 5% for allocation. These are starting research budgets, not
universal user performance promises. Set appropriate values in a new policy before
planning. `--pairs` supports a pilot without reducing `minimum_pairs`; a three-pair
pilot cannot inherit a six-pair acceptance threshold.

Each pair block contains eight fresh JVMs:

| Comparison | Arm A | Arm B | Instrumentation |
| --- | --- | --- | --- |
| A/B | Baseline artifact and baseline lookup | Candidate artifact and candidate lookup | Plain and profile, separately |
| A/A | Baseline artifact and baseline lookup | Identical baseline artifact and lookup | Plain and profile, separately |

The seed determines block order and first arm. Subsequent blocks alternate arm and
instrumentation order within each stratum, giving exact balance with an even pair
count. Analysis never pools profile timing with plain timing. A/A checks whether
order/noise can masquerade as a useful change. Profile/plain pairs estimate the
added overhead of JFR and unified GC logging for each implementation; this estimate
also contains normal time-order noise.

Both plain and profile modes retain a ten-millisecond heap sampler and live-thread
allocation counters. Plain therefore means **without JFR/GC logging**, not zero
observer overhead. Every process warms up on the same real workload, clears
application caches and performs explicit GC before the timed window. The warm-up
and measured windows are saved separately. Fixed warm-up does not prove complete
JIT convergence. OS file caching remains uncontrolled/warm, especially after input
hash verification; these trials cannot claim cold disk performance.

This harness invokes the measured JAR's text cache, segmented reader and digest.
It models baseline source lookup as text/digest before content lookup, and candidate
lookup with the candidate JAR's `GenerationWorkCache` before text/digest. The same
driver and scheduler classes are on both process classpaths; baseline mode does
not use the scheduler for lookup. A digest substitutes for parsed geometry. This
is a reconstructed **source-work comparison**, not invocation of either full
production MTR loader. Baseline/candidate versions may also differ in their text
cache, so this version comparison is not a single-feature ablation.

Plan creation verifies matching embedded target metadata except companion version.
The plan fingerprints both artifacts, archive bytes, entries, driver/runner/analyzer,
Java launchers, runtime modules and VM implementation. Each trial verifies frozen
inputs and compiled harness bytes before launch; the final check runs again after
all trials. Effective heap, workload counts, digest count, warm-up/answer hashes,
instrumentation and observation windows are independently checked by analysis.
Known environment variables that inject JVM flags are rejected.

`execution.json` is checkpointed before and after each trial, including nonzero
exits/timeouts and raw files. The same execution directory cannot be resumed or
overwritten. An interrupted experiment remains incomplete; start a new directory
instead of mixing a later machine state into the existing schedule. Reanalysis
checks the frozen plan hash and raw JSON/log/JFR hashes before making a decision.
SHA-256 provides reproducibility and accidental-change detection, not a signature
against someone rewriting the whole evidence set. Keep the original committed
evidence and record paths when moving an experiment; raw references are absolute.

## Statistics and decision

The independent experimental unit is one pair of fresh JVMs. Repeated queries,
epochs, heap samples and frames are not additional independent replicates. The
report retains individual baseline/candidate values, absolute paired differences,
relative paired differences and medians. A relative delta is `100 * (B/A - 1)`;
zero baselines retain absolute deltas and have undefined percentages.

Median intervals invert the exact binomial sign test, without a normality
assumption or a bootstrap-generated appearance of precision. At 95%, six pairs
give the conservative interval from the smallest to largest observed difference;
three pairs cannot provide finite two-sided bounds and remain inconclusive. Even
six pairs may be far too few for a narrow A/A tolerance. Intervals are pointwise,
not a simultaneous confidence statement about all metrics. Sequential measurements
can remain correlated despite fresh JVMs and counterbalancing. Replication across
sessions/machines is required before generalizing beyond this fixture.

The primary interval must lie entirely beyond the declared reduction. Each
guardrail interval must lie entirely below its allowed regression. A/A intervals
must lie entirely inside both sides of their equivalence bounds. Failure to detect
a difference is not proof of equivalence. A clear budget violation fails; an
interval crossing a boundary is inconclusive. No outliers are discarded.

| Observation | Correct interpretation |
| --- | --- |
| Live-thread allocated bytes | Allocation traffic of threads still observable at the endpoint; terminated threads can be missed |
| Sampled heap peak | Maximum sampled heap; short peaks may be missed |
| Post-release full-GC heap | Diagnostic whole-VM heap after explicit cleanup/GC, outside the timed window; not a proof of leak freedom |
| JVM GC count/collection milliseconds | Collection counter deltas, not exact stop-the-world pause distributions or specifically Full GC |
| JFR pause spans | Whole, bounded observation events; avoid nested-pause double counting and phase-crossing attribution |
| Frame intervals | Render-loop pacing including VSync/FPS cap; not GPU presentation time |

The source report deliberately has no frame, full-pack loading, native parsing,
GPU or long-session acceptance field. Those outcomes require their actual workload.

## Full-client counterpart

Use the same predeclared structure for each exact official/v6 and NF248/NF265 target,
but collect real startup/reload/route evidence with the client probes and JFR tools.
The source runner does not launch or control a Minecraft world.

| Stage | Controls and evidence needed |
| --- | --- |
| Frozen client | Exact packaged mod/MTR/probe hashes, Java/JVM flags, pack hashes/order, disposable world snapshot, settings, route/camera, hardware/power |
| Startup | Process-start to completed native registration/parsing; samplers running before loading, final zero pending/tickets/permits |
| Reload | Request to completion of a **new** resource epoch; start/end snapshots, native F3+T and settled counters |
| Steady route | Same warm-up, route, camera, duration, VSync/cap and view distance; separate frame/GC windows |
| Instrumentation control | Matching isolated baseline/candidate runs without probe/JFR; independently establish completion timing |
| Correctness | Exact native geometry/cache comparisons, rendered bodies/doors, passenger paths, failure cleanup and actual GPU ownership |
| Durability | At least 20 consecutive full-pack reloads and two-hour route; compare matched quiescent points and retaining owners |

Do not reuse naturally advancing mutable worlds across arms; restore independent
copies of the same snapshot. Do not combine targets or treat changed pack catalogs
as identical workloads. Failures must remain in the scheduled-run denominator,
including inability to start at a chosen heap. Lower-heap exploration follows a
successful same-heap comparison and cannot replace it. Full-pack Full-GC pause
costs from the historical evidence remain unresolved until measured here.
