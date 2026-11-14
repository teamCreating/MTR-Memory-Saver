# Source experiment — 2026-11-14 (UTC+08:00)

**Overall decision: inconclusive.** All 48 scheduled JVM trials complete with
matching independent warm-up/measurement answers and exact 3 GiB effective heaps.
The primary allocation endpoint and elapsed-time regression guardrail pass, but
neither timing A/A stratum establishes equivalence inside the frozen ±15% band.
Do not promote this experiment to full-client performance acceptance.

The [frozen plan](plan.json), [complete execution](execution.json) and
[analysis](analysis.json) retain all observations. A separate
[reanalysis](reanalysis.json) checks raw evidence hashes and produces byte-identical
analysis. Each trial directory contains its raw JSON and process log; the 24
profile trials also retain their JFR recording. Input jobs and policy are in
[the preparation directory](../source-protocol-20261114-inputs/).

## Design and identities

Baseline: official-nf248 **0.4.0**, SHA-256
`2da554aaa25daf4438cd994d916f858cd8becb1f8432bd73b63867bc1050eb2f`.
Candidate: official-nf248 **0.4.2**, SHA-256
`70ed09564bd41a09cf08f468d73474bad3bdc2cd287ed4dca389c8f74c73a885`.
These are existing artifacts; this change does not replace the mod or change its
version. Both embed the same official MTR/NeoForge target except companion version.

Java 21.0.11+10, G1, 512 MiB initial heap, exactly 3,221,225,472-byte maximum heap.
Six independent pair blocks, each containing A/B and same-baseline A/A with both
plain and JFR/GC-log modes. Orders are seeded and counterbalanced. Each fresh JVM
performs one full real-input warm-up epoch followed by one measured epoch, with
two queries per input in each epoch. This smaller workload was declared before
running and differs from both the default policy workload and the historical
0.4.2 experiment. No budgets or counts were changed after observing results.

The four historical real inputs contain 65,255,687, 20,693,961, 1,827,339 and 11,684
UTF-8 bytes. Baseline performs eight measured digests; candidate performs four.
Expected ordered answer hashes are derived directly from input bytes in Python,
independently of both Java digest implementations.

## Observations

Plain mode retains allocation/heap observation but excludes JFR and GC logging.
Intervals below are conservative two-sided 95% median intervals from six pairs;
they are pointwise, not simultaneous coverage for all metrics.

| A/B plain endpoint | Baseline median | Candidate median | Median paired change | Interval for paired change |
| --- | ---: | ---: | ---: | ---: |
| Live-thread allocated bytes | 608,668,484 | 228,983,192 | −62.3803% | [−62.3810%, −62.3783%] |
| Elapsed milliseconds | 4,956.043 | 1,478.717 | −71.3122% | [−73.1666%, −67.1779%] |

| A/A endpoint | Median paired change | Interval | Gate |
| --- | ---: | ---: | --- |
| Plain elapsed time | −4.0068% | [−35.8728%, +48.1922%] | Inconclusive against ±15% |
| Profile elapsed time | +4.7945% | [−8.1040%, +22.5473%] | Inconclusive against ±15% |
| Plain allocation | −0.0019% | [−0.0203%, +0.0207%] | Pass against ±5% |
| Profile allocation | +0.0021% | [−0.0039%, +0.0130%] | Pass against ±5% |

The timing noise is retained. A/A's largest favorable/unfavorable observations
are not discarded or explained away. All primary/guardrail observations remain
available even though the overall decision is inconclusive.

Added JFR/GC logging has median paired elapsed changes of +0.2923% for baseline
and +2.1080% for candidate, with intervals [−11.8003%, +2.1880%] and
[−11.0965%, +20.4629%]. These intervals do not isolate a precise instrumentation
cost from temporal noise and do not prove that instrumentation is free.

Windows Balanced power mode was observed. Codex and an idle Gradle daemon were
present, with light document editing during measurements. No game/build/audit
workload was intentionally run concurrently. Background services, temperature
and CPU frequency were not controlled; they remain possible confounders rather
than proven explanations for particular samples. Repeated archive hash checks
and real-input warm-up make this a warm-file-cache workload, not cold disk I/O.

## Validation and next decision

The first scheduled baseline/profile recording was replayed through the JFR
exporter/analyzer using exact separate warm-up and measured windows. See
[windows](jfr-windows.json), [analysis](jfr-analysis.json) and
[exported events](jfr-export.json). It reports no game frames/ticks, as expected
for a source harness. This one recording validates the analysis path; it is not
a multi-run GC performance conclusion. Phase-crossing spans are separately
reported rather than charged wholly to an adjacent phase.

The overall workflow passes 27 Python tests and the modified Java driver compiles
with the 24-test official-nf248 Gradle suite. Negative controls cover shared wrong
answers, failed/missing/duplicate/reordered trials, nonfinite metrics, heap/workload
drift, A/A drift, timing regression, changed raw logs/plans and failure preservation.

The next timing experiment should be newly preregistered, with a longer measured
window and better recorded/control of host activity, and replicated in another
session. The current allocation evidence supports the source-work mechanism but
does not certify whole-game loading, Full-GC pauses, GPU ownership or frame latency.
The full-pack/native reload/long-route gates in
[the workflow](../../docs/OPTIMIZATION.md) remain separate. No production instance,
resource pack, world or delivered JAR was changed.
