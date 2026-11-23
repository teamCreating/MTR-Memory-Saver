# 0.4.8 practical Spark verification

All twelve selected NF248 observations passed independent evidence replay.
Performance acceptance failed. The plain pairs missed the required 10% reduction
in steady private memory and exceeded the allowed 5% increase in loading time.
The 0.4.8 release remains held.

| Comparison | Private memory | Resource loading | Steady heap |
| --- | --- | --- | --- |
| Plain AB | -0.296% | +9.401% | +4.662% |
| Plain BA | -0.268% | +10.279% | +1.550% |
| Profile and Spark AB | -0.065% | +11.757% | -0.548% |
| Profile and Spark BA | -0.042% | +14.311% | -0.680% |

Values are paired percent changes from baseline to candidate. Plain median
private memory changed by -0.282%, about -12.93 MiB, and loading by +9.840%.
The AA plain control changed private memory by -0.415%, loading by +5.793%
and heap by +4.807%. The observed private-memory differences are smaller than
this AA control's difference.

The frozen comparison uses official MTR 4.1.0-beta.2 on Minecraft 1.21.1,
NeoForge 21.1.248, all sixteen native catalogue packs, G1, Xms512M and
Xmx3072M. Baseline companion SHA-256 starts b9c95bbe and candidate starts
943b3d45. Each instrumented observation has sixty seconds of warmup and
180 seconds of steady measurement. The profile mode includes JFR and Spark
1.10.124 with a 100 ms Java sampler over all threads for 300 seconds.
The two probe-off controls install only MTR and the candidate.

Four actual Spark profiles were saved locally and independently decoded with
the pinned Spark JAR's public protobuf getters. Their timestamps, JVM uptime,
instance arguments, installed artifact identities and required Render/Server
threads pass the sampler audit. Render-thread self weights include FPS limiting,
texture upload and MTR draw calls. Server-thread weights are dominated by
parking between ticks. Java execution sample weights include waiting and carry
safepoint bias. These weights do not quantify CPU elapsed time or displayed FPS.

Both profile pairs meet the existing frame and GC comparison bounds. Native
render-loop p99 changed by -5.548% and +1.154%. Steady GC pauses changed by
-2.083 ms and -7.739 ms. All four steady profile windows have zero Full GC.
JFR-plus-Spark steady private-memory overhead is +1.29% for baseline and +1.52%
for candidate, within the configured equivalence bounds. Observer-plus-idle-Spark
private memory changes by -0.31% against probe-off. The probe-off control lacks
live heap, frame and route observations. Its loading anchor uses the native log
and its 300-second warmup differs from the instrumented scene preparation.

The original run has five failed attempts, comprising one scene timeout and
four failed Spark window-coordination attempts. One successful original plain
candidate was superseded when its whole AB pair was rerun. Eighteen attempt
captures are retained. The selected twelve use distinct JVM creation identities,
have no overlapping execution windows and preserve AB/BA order inside each pair.
Recovery pairs were executed later than the original pairs. This practical
selection does not complete the separately configured 48-trial statistical
protocol or establish a confidence interval.

Every selected JVM was terminated by the existing collector after measurement
and reports exit 1. These observations establish completed sampling and process
cleanup. Normal save-and-close remains untested in this round. NF265 performance
and independent displayed-frame qualification also remain outside these results.

The earlier independent inventory bug rejected every trial because it required
trial-summary.json to hash itself. Commit 07c137f makes collection and verification
exclude the root receipt consistently while retaining nested evidence and
tamper rejection. Its 348 Python tests and CI passed before final replay.
No product binary was changed for the recovery.

[assessment.json](assessment.json) records the independent replay, exact paired
metrics, identities and windows. [decision.json](decision.json) applies the frozen
budgets to each pair. Equivalence uses absolute percent change. The probe-off
bound applies to steady private memory. [captures.json](captures.json) indexes
the ZIP payloads and their original per-file hashes. Every archived payload was
read back and verified against those hashes.

The archives preserve original samples, observations, native log segments,
phase receipts, Spark publication and analysis results, and producer inventories.
Source snapshots in source/ retain the recovery derivation and sampler tools.
[local-recordings.json](local-recordings.json) fingerprints the original JFR,
Spark binaries and full decoded machine/configuration exports retained in the
ignored local cache. Full binary replay requires those local recordings and
the pinned dependency JARs. The published selection is not a self-contained
binary replay bundle. SHA256.json binds every selected file in this directory.
