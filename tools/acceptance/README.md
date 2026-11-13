# Standalone acceptance tools

All tools are owned by this repository. Java audits compile against the selected,
fingerprinted MTR target and Gradle-provided game dependencies. They require no
launcher-private Python API, patched client or prepared-instance marker.

`gradlew test` runs the native packed-mesh, display-retention and JSON-reader
reference audits as JUnit checks, alongside the Java-only failure/churn tests.
Native mesh checks compare 1,400,028 emitted/stored vertices in 27 cases, including
translation, mirror, snapshot, nested merge, finite/NaN boundaries, colors and
interaction bounds. Display checks compare actual native part-cache consumers.
They operate without Mixins and do not allocate GPU models.

For explicit real-model jobs:

```powershell
./gradlew.bat auditModels -PauditJobs='<jobs.json>' -PauditOutput='<fresh result.json>'
```

The JSON array contains `key`, `archive` (path to a supplied pack ZIP), `model`
(entry path), `sha256` (entry bytes) and `texture` (resource identifier). Every
entry is fingerprinted before native parsing. Include the exact MTR/artifact
manifest when archiving a result. The test output by itself is a geometry/parser
audit, not runtime Mixin or GL validation.

For paired source lookup measurements:

```powershell
python tools/benchmark_sources.py --java-home '<Java 21 JDK>' `
  --baseline '<0.4.0 JAR>' --candidate '<current JAR>' `
  --jobs '<jobs.json>' --output '<new report directory>' --heap 3g --pairs 3
```

This workload uses real resource bytes and the actual delivered text/digest
implementations, replacing a parsed model with its digest to isolate source lookup.
Baseline queries retrieve text/digest before looking up that result; candidate
queries use provider/path scheduling first. Identical result hashes are required.
Reports record exact archive/entry/JAR/driver/runner hashes, equal heap and query
controls, alternating run order, live-thread allocation counters, JVM collection
counters and sampled heap. Each process produces raw JFR and GC logs. The sample
interval can miss peaks, and live-thread counters exclude already terminated
threads. Explicit GC is outside the timed windows. A tiny synthetic warm-up does
not fully warm every large-file path, so preserve all trials and report dispersion.

`tools/analyze_performance_jfr.py` compiles the streaming JFR exporter using an
explicit JDK and shaded-Gson MTR JAR. Its windows are explicit ISO timestamps. It
preserves allocation-sample, frame-interval and GC-pause distinctions and is covered
by regression tests; it has no game-instance import. Run its `--help` for arguments.

## Optional client probes

`gradlew probeJar` builds a separate observation JAR. It is excluded from the mod
and release bundle. Enable it only in an isolated client with
`-Dmtr.memory.acceptance=true`, and include its hash/overhead in the run manifest.
The common probe records `mtrtest.ClientFrame` and `mtrtest.ServerTick` JFR events.
Frame intervals include render-loop pacing and are not GPU presentation times;
server event spans are not complete MSPT.

The common loader probe runs only when `loader-lifecycle-request.json` is present
in the isolated game directory and native parsers are quiescent. It writes a fresh
`loader-lifecycle-result.json`, checking actual factory/accessor/executor Mixins,
publication, path fast hits, read failure/retry and balanced native tickets. Its
empty model does not validate rendered geometry or GPU models. For an automated
development-client smoke run, place that request in `build/run/<target>/`, then
use `gradlew runClient -PacceptanceProbe=true`; this enables the separate probe,
sets a 3 GiB heap and exits the isolated client after recording its result.
NeoForge's JUnit launch target is hard-wired to the dedicated-server side and is
unsuitable for certifying these client Mixins.

On a v6 preset the probe also includes the migrated GPU ownership audit. After
entering an unpaused world, create `v6-compatibility-request.json` in that isolated
game directory with a run ID/control reference. It writes a fresh
`v6-compatibility-result.json`; remove/archive a prior result before a new run.
This is an explicit probe request, not a prerequisite of ordinary builds or play.
For automated v6 development runs, `-PacceptanceProbe=true` allows the GPU audit at
the title screen after the resource-loading overlay closes and runs 100 synthetic
cycles. This still uses a real GL render-thread context; a world/route and long
session are separate validation. When both probe requests are present, the loader
probe waits for the GPU result before requesting client exit.
The checks cover staging release, source retention, independent consumer GPU
models, early consumer close and cross-owner disposal. Compilation alone is not
a probe pass. See [the full protocol](../../docs/ACCEPTANCE.md).

The migrated Java/JFR tools originate in this project's parent history. Their
namespace and entry points were adapted here; original historical evidence remains
unchanged. New reports identify current sources and binaries separately.
