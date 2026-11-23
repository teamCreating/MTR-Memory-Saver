# Concurrent workload and outlier sensitivity

The user reported substantial concurrent tasks on this computer after the
practical comparison was sealed. Shared CPU, storage and memory pressure can
affect wall-clock loading. The recorded increases therefore have inconclusive
causal attribution to the candidate. The earlier numerical comparisons remain
observations of this host during those runs.

The original startup samples contain client working set, private memory, page
fault counts and native state. They lack a startup-aligned host CPU, disk and
other-process workload series. The Spark captures begin after loading.
These records cannot identify a specific externally contaminated loading trial.

| Mode and retained data | Loading change | Steady private-memory change |
| --- | --- | --- |
| Plain, both pairs | +9.840% | -0.282% |
| Plain, pair 1 only | +9.401% | -0.296% |
| Plain, pair 2 only | +10.279% | -0.268% |
| Profile, both pairs | +13.034% | -0.053% |
| Profile, pair 3 only | +11.757% | -0.065% |
| Profile, pair 4 only | +14.311% | -0.042% |

Removing either pair does not bring the remaining measurements within the
existing loading or private-memory targets. A one-pair sensitivity case has one
replicate and cannot estimate measurement noise. Removing both pairs leaves no
estimate. The AA plain control's loading difference was +5.793%.

The new configurable screen uses Tukey fences, inclusive quartiles and 1.5 times
the interquartile range. Groups use the same instrumentation mode and treatment.
Baseline and candidate groups receive the same rule. If either arm is flagged,
both arms of that pair are excluded from the sensitivity comparison across its
reported metrics. Full results, flagged identities, fences, excluded pairs and
retained counts are always reported. Individual frame or GC spikes inside a
trial are retained by this screen.

The default minimum of six measurements per group is an engineering choice
introduced for this tool. It is configurable and is not a statistical guarantee
or an additional release gate. A zero IQR is reported as unresolved. This
post hoc rule can flag unusual durations without proving external interference.
The current data has two measurements per group, so automatic screening records
insufficient replicates, excludes zero pairs and supplies leave-one-pair-out
sensitivity instead. The six-replicate default and 1.5 multiplier should be
declared before collecting a future comparison that will use this rule.

The tool reads the qualified assessment and schedule without editing them.
It validates finite positive inputs and pair membership, groups treatments
separately and binds its inputs with SHA-256.

```powershell
.venv/Scripts/python.exe tools/client_outlier_analysis.py --assessment evidence/engineering-054/practical-spark/assessment.json --output .cache/outlier-analysis.json
```

[assessment.json](assessment.json) preserves the full and screened comparisons,
all single-pair omissions and input fingerprints.
The implementation is in [client_outlier_analysis.py](../../../tools/client_outlier_analysis.py)
and the explicit choices are in [client-outlier-analysis.json](../../../config/client-outlier-analysis.json).

Performance acceptance remains unestablished, including the private-memory
benefit. This analysis grants no release acceptance. It records timing
uncertainty under the reported workloads and the sensitivity of the available
paired observations.
