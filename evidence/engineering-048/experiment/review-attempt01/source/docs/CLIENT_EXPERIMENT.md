# Official whole-client experiment

This protocol applies only to the exact official MTR 4.1.0-beta.2 binary and one
explicit NeoForge target at a time. It does not use the source lookup benchmark as
whole-client evidence. The default policy in
[client-experiment.json](../config/client-experiment.json) freezes six pairs in
each A/A or A/B and plain or profile stratum: **48 independently created JVMs**.
The four prerequisite qualification runs are separate from those 48 trials.
No full-client qualification or performance pass is established by implementing
or unit-testing these tools.

## Controls and qualification

Prepare four never-launched templates using
[packaged_client.py](../tools/packaged_client.py): baseline/plain,
baseline/profile, candidate/plain and candidate/profile. Both arms must use the
same exact official MTR, loader, JDK runtime bytes, libraries and loader metadata,
configuration and default configuration inventories, ordered resource archives,
native catalogue, options, world snapshot, local profile, camera and route,
Xms/Xmx, collector, scheduler settings and injection environment. The same loader
must use **identical neutral observer JAR bytes in all four groups**. Companion
artifact identity is the treatment; its source provenance remains frozen.

The baseline may use the explicitly selected `official-030-nf248` or
`official-030-nf265` legacy identity adapter. Its original JAR bytes are preserved.
A known artifact SHA or historical load is not qualification for current packs,
world, JVM or instrumentation. Missing baseline qualification fails planning;
there is no replacement treatment, automatic relaxation or source-only fallback.

Pass a scenario JSON to `packaged_client.py prepare --performance --controls`.
Its complete schema is:

```json
{
  "schema": 1,
  "scenario_name": "Name of the actual measured scene",
  "expected_registration": {"declarations": 12, "distinct_ids": 11},
  "world_name": "Actual direct-child world name",
  "camera": {
    "dimension": "minecraft:overworld",
    "player": {"x": 0, "y": 64, "z": 0, "yaw": 0, "pitch": 0},
    "maximum_position_error": 0.1,
    "maximum_angle_error": 0.1
  },
  "route": {
    "description": "Actual fixed route and observation point",
    "route_ids": [10],
    "vehicle_ids": []
  },
  "cache_policy": "fresh_jvm_warm_os_cache",
  "observation": {
    "require_world": true,
    "require_unpaused": true,
    "require_train": true,
    "minimum_train_displacement": 1
  },
  "machine_context": {
    "hardware": "Actual CPU, RAM and GPU context",
    "windows": "Actual Windows version and build",
    "power_mode": "Actual power mode and relevant tuning",
    "background_workload": "Actual scheduler/background workload controls"
  },
  "warmup": {
    "duration_seconds": 60,
    "description": "Actual native and scene warm-up procedure"
  }
}
```

These numbers and identities illustrate the schema; replace them with the real
catalogue, world and observed scene. Camera position and wrapped angles are
checked against the declared tolerances. Required train observations must match
the frozen route IDs and, when supplied, vehicle IDs. Positive displacement
requires at least two measurements of the same train's native rail progress in
the steady window. This does not certify vehicle geometry or boarding. Hardware,
Windows, GPU driver identities and active Windows power scheme are also read and
frozen independently; the declarations are not execution evidence.

Preparation example, using a **stopped isolated source client**:

```powershell
.venv/Scripts/python.exe tools/packaged_client.py prepare `
  --source <stopped-source> --instance <fresh-baseline-plain-template> `
  --companion <exact-baseline.jar> --legacy-baseline official-030-nf248 `
  --observer <exact-neutral-observer.jar> --catalogue <official-native-catalogue.json> `
  --world <world-name> --username <local-profile-name> --performance `
  --controls <scenario.json> --heap-mib 3072 --initial-heap-mib 512 `
  --jvm-arg=-XX:+UseG1GC
```

Use `--jfr` only for the profile template. Use the exact candidate companion and
omit the legacy selector for candidate templates. Any optional NMT or scheduler
controls must match all groups. Qualification and trial collection never control
game input or attach to an existing game. Every run copies a never-launched
template into a new directory, preserving its initial world and options.

Execute each group separately with its matching role and mode:

```powershell
.venv/Scripts/python.exe tools/client_experiment.py qualify `
  --prepared-plan <baseline-plain-template>/packaged-client-plan.json `
  --role baseline --instrumentation plain --output <new-qualification-attempt>
```

The generated report is `<new-qualification-attempt>/trial/qualification.json`.
Repeat for the other three groups. The qualification key contains role, mode,
exact companion SHA, comparison-controls SHA, neutral observer SHA, target and
policy SHA. All four are independently re-audited from raw evidence during
planning. A profile run cannot lend qualification to plain, nor candidate to
baseline. A changed policy, source, pack, world, runtime or observer needs current
qualification again.
Qualification process identities are frozen from their independently audited raw
PID and process-creation records. Scheduled trials cannot reuse any of those four
JVMs, even if timestamps are reformatted with another UTC offset.

## Planning and execution

```powershell
.venv/Scripts/python.exe tools/client_experiment.py plan `
  --baseline-plain <baseline-plain-template>/packaged-client-plan.json `
  --baseline-profile <baseline-profile-template>/packaged-client-plan.json `
  --candidate-plain <candidate-plain-template>/packaged-client-plan.json `
  --candidate-profile <candidate-profile-template>/packaged-client-plan.json `
  --qualification <baseline-plain-qualification.json> `
  --qualification <baseline-profile-qualification.json> `
  --qualification <candidate-plain-qualification.json> `
  --qualification <candidate-profile-qualification.json> `
  --environment-notes <actual-power-and-background-context> --output <new-experiment>
```

`plan` never starts a client. It first saves `attempt.json`, including failures,
and only writes `plan.json` after all strict checks pass. A failed or existing
attempt directory is never overwritten. The seeded schedule balances A/B and B/A,
A/A labels and plain/profile ordering. Both A/A arms use the baseline artifact.

`run --plan <new-experiment>/plan.json` verifies current frozen inputs and
qualification before each trial. Each trial owns its actual `Popen` process and
checks the real Windows executable, command, PID and creation time. Loading runs
from **actual process creation to the first settled snapshot following actual
native reload RETURN**. A RETURN with pending work does not complete loading.
World/camera/route readiness is recorded separately as scene loading; it does not
extend the native loading metric. The default 60-second warm-up starts at the
first qualified scene observation and precedes a 180-second steady measurement window.
Native work, world, pause state, camera, route, snapshot freshness and advancing
samples must stay valid throughout post-load observation. Unexpected reloads,
gaps, malformed observations and missing metrics fail the trial.
The complete raw client log is also scanned independently. Missing/unreadable
logs, unreviewed native MTR errors, `Invalid model`, resource/model read, decode
or parse failures, OOM, Mixin startup failures and FATAL messages prevent
qualification. Other ERROR messages remain in a separate contextual-review list;
an authlib user-properties HTTP 401 does not become a native Memory Saver failure.
Native registration counts cannot establish that `transparent.png` is harmless.
There is no automatic native-diagnostic allowlist; such messages remain pending
attribution.
The template must contain no prior logs. The actual ModLauncher startup header
must identify this trial's game directory, and every observed log prefix's byte
count and SHA must match the final raw file. Missing post-load prefixes,
truncation, rotation or rewriting prevents qualification; a final logfile alone
does not prove complete history.
Raw start and finish receipts bind each capture directory, scheduled identity and
qualification key to actual process creation, launch/capture, measurement and
cleanup times. The prepared game directory must be this exact attempt's
`instance/` directory. Copied qualification evidence and edited execution-time
summaries cannot become scheduled performance replicates.
The independent analyzer also requires actual run windows to follow the scheduled
order without overlap; unique PIDs alone do not establish independent sequential
trials. Every window must fit the enclosing trial and experiment receipts.

Plain and profile both sample independent native heap and OS private/working-set
memory. The OS startup peak is the actual process-start working-set peak; the heap
peak is a **sampled lower bound**, not a continuous maximum. Profile additionally
retains full-history JFR and GC logs. The collector exports and validates the
recording before terminating only its owned copied client. This cleanup exit is
recorded separately and is not advertised as a normal game shutdown. Process
cleanup failure prevents another trial from starting. No directory is reused or
reset, and no ordinary world is overwritten.
The owned process must remain alive through the declared steady endpoint;
sampling-boundary gaps cannot shorten the experiment. The actual endpoint is
recorded before cleanup. Profile dumping waits until two seconds after that
frozen endpoint so conservative whole-second JFR metadata can cover the window.
Every profile failure or interruption also attempts a partial dump and verifies
its readability before termination. Export failure preserves the actual live
process and handle, records its exact PID/instance in `preserved-process.json`
and halts further trials. Each export attempt retains its own raw JFR and command
receipts; a zero helper exit without a readable file is insufficient. Native
loading is a sampled first-captured-settled anchor: the report preserves both
native snapshot time and external capture time/delay and the polling interval.
It does not claim a continuous exact native completion timestamp.

## Independent decisions and remaining calibration

`analyze --plan <plan.json> --output <new-analysis.json>` checks frozen source and
input hashes, raw file inventories, actual process/launch records, raw sample and
native epoch JSONL and independently parsed JFR data. It recomputes every trial
result; saved summaries cannot replace raw evidence. JFR whole-second metadata is
used conservatively, and frame events must continuously cover the complete steady
window. Missing startup/history, orphan/duplicate GC IDs or GC events crossing a
measurement boundary prevent acceptance. The explicit G1 collector permits JDK
21 `G1Full` identification. Plain frame and GC metrics remain **unavailable**.
JFR summary/print receipts preserve the exact input SHA before and after parsing
and the output SHA. Canonical recordings and export copies must match those
bytes. Audit independently reparses the sealed binary using the frozen JDK tool;
old parsed JSON cannot validate a replaced or corrupt recording. A `G1Full`
collection requires a complete matching observed pause, and GC/pause durations
are mandatory. Missing pause evidence stays unavailable and fails qualification.

All 48 scheduled trials remain in the failure denominator. Missing, failed,
duplicate, reordered or reused-process trials invalidate the experiment. There is
no outlier removal, additional sample replicates or unrecorded retry substitution.
Raw inventories must exactly include all captures and failed export attempts;
omitted, added or duplicated inventory members invalidate the audit. Qualification
source fingerprints include the Windows snapshot reader used by
the observer, so changed capture behavior requires fresh qualification. Source,
prepared-input and host identities are checked again at qualification completion;
a mid-run edit cannot acquire a new fingerprint over observations made by old code.
The analysis uses paired median deltas and exact binomial sign-test intervals.
Zero reference values are handled by predeclared absolute budgets, never invented
percentage ratios. A/A equivalence and added JFR/GC instrumentation equivalence
must pass their frozen budgets before instrumented comparison acceptance.

**Neutral observer overhead remains an explicit outstanding gate.** These 48
trials share the same observer and measure the additional JFR/GC logging cost;
they do not measure observer frame-event allocation or registry/cache traversal
overhead. The policy requires independent probe-off calibration before an
uninstrumented whole-client claim. Even when every instrumented statistical gate
passes, the report has `instrumented_comparison_status=pass`, overall
`status=inconclusive`, `performance_accepted=false` and a pending
`neutral_probe_off_calibration` gate. Probe-off calibration is not implemented by
this protocol; it needs independent external process/native-log anchors and must
leave unavailable neutral metrics unavailable.

Fresh JVM/world copies still use uncontrolled warm OS file cache. Sequential host
measurements may remain correlated. This experiment does not certify visual
correctness, doors, floors, boarding, twenty reloads or a two-hour route. Source
microbenchmark results do not supply any of these missing qualifications.

Validate the tools without launching a game:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tools -p test_client_experiment.py -v
```

Successful planning or one qualified group exits zero. Unqualified evidence,
invalid experiments and incomplete uninstrumented performance acceptance exit
two; inspect the preserved report for the specific gate. Interrupted attempts
remain preserved and cannot be relabeled as complete runs.
