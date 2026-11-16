# Standalone acceptance tools

All tools are owned by this repository. Java audits compile against the selected,
fingerprinted MTR target and Gradle-provided game dependencies. They require no
launcher-private Python API, patched client or prepared-instance marker.

For snapshot crash-cleanup checks, run `snapshot_abrupt_audit.py` with explicit
`--java`, `--artifact`, `--mtr`, a fresh `--output`, and `--expect-cleanup removed`.
It starts only small audit-owned JVMs with a dedicated temporary directory and
halts them after independently observing incomplete writing or full-budget
waiting. Normal controls, exact loaded artifact identity, actual exit codes and
another-owner sentinel are retained. Use `--expect-cleanup retained` to record
the older reader's known residue behavior; audit success then does not mean
product crash-cleanup acceptance. The historical `snapshot_windows_audit.py`
checks the pre-owned-channel deletion-lock behavior; an owned delete-on-close
snapshot instead denies opening an incompatible reader that lacks delete sharing.

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
python tools/benchmark_sources.py plan --java-home '<Java 21 JDK>' `
  --baseline '<0.4.0 JAR>' --candidate '<current JAR>' `
  --jobs '<jobs.json>' --output '<new report directory>' `
  --policy config/source-experiment.json `
  --environment-notes '<power mode, background workload and limitations>'
python tools/benchmark_sources.py run --plan '<report directory>/plan.json'
python tools/benchmark_sources.py analyze --plan '<report directory>/plan.json' `
  --output '<fresh analysis.json>'
```

This workload uses real resource bytes and the actual delivered text/digest
implementations, replacing a parsed model with its digest to isolate source lookup.
Baseline queries retrieve text/digest before looking up that result; candidate
queries use provider/path scheduling first. Identical result hashes are required.
Plans freeze archive/entry/JAR/JDK/tool hashes, equal heap, real-input warm-up and
query counts, all trial orders and decision budgets before timing. The default
six blocks contain 48 JVM trials covering A/B and same-baseline A/A, each in plain
and profile modes. Profile mode adds JFR and GC logs; both retain allocation and
heap observations. Raw failures/timeouts are preserved and block acceptance.
Independent expected answer hashes detect shared incorrect results. Exact paired
median intervals prevent small samples or noisy A/A results from qualifying.
See [the complete workflow](../../docs/OPTIMIZATION.md) for policy fields, limits,
CLI migration and client-level comparison. Historical reports remain unchanged.

`tools/analyze_performance_jfr.py` compiles the streaming JFR exporter using an
explicit JDK and shaded-Gson MTR JAR. Its windows are explicit ISO timestamps. It
preserves allocation-sample, frame-interval and GC-pause distinctions and is covered
by regression tests; it has no game-instance import. Run its `--help` for arguments.

## Optional client probes

`tools/packaged_client.py` prepares a fresh ordinary NeoForge instance from an
explicit stopped SDK test client, then launches the actual companion JAR through
the public `minecraft-launcher-lib` command API. It does not add development
classes to the client classpath. Install optional launcher requirements from
`requirements-client.txt`. Preparation verifies embedded/build/target identities,
records world and ordered archive hashes, and creates a separate launch plan.
Launching refuses changed settings, mods, packs or world bytes.

```powershell
python tools/packaged_client.py prepare --source '<stopped SDK instance>' `
  --instance '<fresh instance>' --companion '<official candidate JAR>' `
  --probe '<matching acceptance probe JAR>' --username '<SDK profile>' --smoke
python tools/packaged_client.py launch --instance '<prepared instance>'
```

Add `--faults` to request malformed-model failure/retry checks. A separate
`--expect-binary-rejection` preparation changes only the copied MTR ZIP comment,
preserving its version/classes while changing its whole-JAR fingerprint. That
negative run must be rejected by the actual runtime guard. For full-pack/world
work, omit `--smoke`, supply `--catalogue '<catalog.json>'` and `--world '<saved
SDK world>'`, and record `--jfr` when profiling. The runner observes the selected
official target; no v6 client is created.

`launch --wait-seconds 60` preserves the actual child's exit code, including
nonzero guard rejection. An observation timeout records that the process remains
live and leaves it running. `prepare --nmt summary` explicitly freezes optional
native memory tracking before launch; keep this and JFR identical in paired arms.

`tools/observe_packaged_client.py` validates the launched process handle, start
time, arguments and frozen inputs. It saves its running source, raw JSONL samples
and the native log. `startup` requires stable registration and ownership cleanup;
`route --duration 7200` requires fresh explicitly unpaused world/vehicle state
through the real duration, with vehicle and game-time progression. Optional GPU
counter paths are selected from the local OS, rather than assuming their language.
Requested NMT/GPU observations that are unavailable cannot pass.

For the current catalogue, `--expected-count 1091 --expected-declarations 1092`
separates distinct ID strings from the native declaration-list count. For 20 full
reloads, use `reloads --require-reloads 20 --reload-events '<input receipts.jsonl>'`.
The external input actor calls `capture_reload_before` before actual F3+T and
`confirm_reload_input` with the actual input provider's issued/confirmed timestamps.
The observer performs no game input. Every successful input must match a distinct
full ResourceManager reload, native method boundaries and subsequent settled
ownership. Merely polling or invoking the creator's native reload cannot pass.

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

The 0.4.6 fault probe also records `strict_resource_checks` and
`strict_resource_observations`. Require both the original lifecycle checks and
these real-resource checks to pass. Its scoped native Resource fixtures exercise
open/read/close/decoded-size failure, same-key correction/retry, legal empty text,
UTF-8 replacement and native missing-resource cache retirement. They are absent
from the product JAR. Workspace use and waiting claims must both settle to zero.

`LargeTextWorkspaceAudit` is an independent Java main under `tools/acceptance/java/`.
Compile it with `-proc:none` against the exact packaged candidate, Commons IO and
audited MTR JAR, then pass archive, entry and a fresh JSON output. Run at 3 GiB with
default JVM settings and `-XX:-CompactStrings`. It compares source bytes/UTF-16
length and UTF-8 reencoding hashes plus forced-snapshot native-decoder controls;
its result does not certify OBJ geometry or full-client memory.

The packaged observer uses one bounded background worker for GPU/NMT queries,
preserving requested/started/completed events and raw results in
`auxiliary-events.jsonl`. Main sampling does not wait for those queries and skips
missed deadlines instead of rereading one snapshot. Shutdown is bounded, and
incomplete/missing results or unconfirmed worker exit prevent acceptance. Actual
long gaps and unchanged snapshots still fail. GPU wildcard instance queries are scoped
to the launched PID, preserving the caller's counter names. Missing/invalid values
or nonzero query exits remain unavailable, with raw query output retained.

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
