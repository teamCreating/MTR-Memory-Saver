# Official NF248 whole-client preparation

This directory preserves preparation, not an executed performance experiment.
Four real `packaged_client.py prepare --performance` commands completed with code
0 between 2026-11-16 21:36 and 21:42 (UTC+08:00). Each template remains unlaunched.
The original receipts, stdout/stderr, plan copies and controls are retained.

The two treatments are the unchanged official NF248 v0.3.0 baseline and official
NF248 0.4.7 candidate. All four groups contain identical neutral observer 1.0.3
bytes, SHA-256 `1a4e69a81e8baaeaf30e76b7647a371a39411ab7687934da83742c0fdce8487d`.
Candidate SHA-256 is
`e8b5b40230d0f44c541c12b32c8a30d4c2ea056b8a972335ae10166496837a99`.
The sixteen native catalogue packs, saved world, profile, options, runtime and
initial 512 MiB / maximum 3072 MiB heap are comparison controls. Profile groups
add JFR/GC logging; plain groups retain the same observer without that addition.

`assessment.json` records the original preparation checks. The later
`independent-audit-*.json` reports recheck current template bytes against the
original command receipts, frozen plans/descriptors and source-world inventory,
using the existing strict descriptor verifier. An audit does not create or
substitute for a qualification report. Failed audit receipts remain preserved.

`environment.json`, `machine-context.json`, `power-context.json` and scenario
background-process counts describe their timestamped observations. They do not
establish current or identical future background load. The first friendly-name
CIM query failed and is retained; the separate actual `powercfg` query identified
the Balanced scheme. No user process or power setting was changed. New
qualification and trial execution read/recheck actual host identity independently;
all load/noise, failures and interruptions must remain in the evidence.

The scenario requires an unpaused station-A camera at the declared pose, a train
on route `1634058583976595067`, and actual displacement of the same train during
the measurement window. A stopped train with route ID 0 does not satisfy this
scenario. These declarations do not prove that the client reaches that scene.

## Next execution

Run commands from the independent `vehicle-memory` repository root with the
project virtual environment. Keep prepared instances immutable: qualification
copies each template to a new owned instance. Avoid competing heavy builds,
hashing or game clients during observations. Do not change the frozen budgets
to obtain a favorable result. If a source, control or observer changes, preserve
the old preparation and create a separate preparation/qualification attempt.

First perform four separate actual qualifications, with fresh output directories:

```powershell
$perfPreparation = Join-Path (Get-Location) 'evidence/engineering-049/performance-preparation'
$perfAttempt = Join-Path (Get-Location) '.cache/acceptance/performance-049-qualifications-01'
foreach ($perfRole in 'baseline', 'candidate') {
    foreach ($perfMode in 'plain', 'profile') {
        $perfGroup = "${perfRole}_${perfMode}"
        $perfDescriptor = Get-Content -Raw -LiteralPath (Join-Path $perfPreparation 'descriptors.json') | ConvertFrom-Json
        $perfPlan = $perfDescriptor.$perfGroup.prepared_plan.path
        .venv/Scripts/python.exe -X utf8 tools/client_experiment.py qualify `
            --prepared-plan $perfPlan --role $perfRole --instrumentation $perfMode `
            --output (Join-Path $perfAttempt $perfGroup)
        if ($LASTEXITCODE -ne 0) { throw "Qualification failed: $perfGroup; preserve this attempt." }
    }
}
```

Each successful report is `<qualification-directory>/trial/qualification.json`.
Then use the four original template plans and all four actual reports to create
a new experiment, following [CLIENT_EXPERIMENT.md](../../../docs/CLIENT_EXPERIMENT.md).
`plan` performs no game launch and rejects missing/incompatible qualifications:

```powershell
$perfDescriptors = Get-Content -Raw -LiteralPath (Join-Path $perfPreparation 'descriptors.json') | ConvertFrom-Json
$perfExperiment = Join-Path (Get-Location) '.cache/acceptance/performance-049-experiment-01'
.venv/Scripts/python.exe -X utf8 tools/client_experiment.py plan `
    --baseline-plain $perfDescriptors.baseline_plain.prepared_plan.path `
    --baseline-profile $perfDescriptors.baseline_profile.prepared_plan.path `
    --candidate-plain $perfDescriptors.candidate_plain.prepared_plan.path `
    --candidate-profile $perfDescriptors.candidate_profile.prepared_plan.path `
    --qualification (Join-Path $perfAttempt 'baseline_plain/trial/qualification.json') `
    --qualification (Join-Path $perfAttempt 'baseline_profile/trial/qualification.json') `
    --qualification (Join-Path $perfAttempt 'candidate_plain/trial/qualification.json') `
    --qualification (Join-Path $perfAttempt 'candidate_profile/trial/qualification.json') `
    --environment-notes '<actual contemporaneous power/background observations and limitations>' `
    --output $perfExperiment
```

Only after planning passes, run all 48 scheduled fresh JVMs and the independent
analysis. The default policy freezes six pairs per A/A or A/B and plain/profile
stratum, 60 seconds of scene warm-up and 180 seconds of steady measurement per
JVM. Four qualification JVMs are additional; they cannot become trial replicates.

```powershell
.venv/Scripts/python.exe -X utf8 tools/client_experiment.py run --plan (Join-Path $perfExperiment 'plan.json')
.venv/Scripts/python.exe -X utf8 tools/client_experiment.py analyze `
    --plan (Join-Path $perfExperiment 'plan.json') --output (Join-Path $perfExperiment 'analysis.json')
```

Actual qualifications, the 48-trial plan/run/analysis and observer-off calibration
remain pending. The implemented protocol does not provide observer-off
calibration, so even an accepted instrumented comparison cannot establish an
uninstrumented performance claim. Full-pack startup, twenty consecutive reloads,
visual/passenger correctness, GPU lifetime and two-hour route acceptance retain
their separate gates. NF265 requires its own full-client experiment. V6 remains
paused.
