# 0.4.2 engineering evidence

`benchmark/` retains three alternating paired source-lookup runs, exact controls,
raw JFR/GC logs, measured windows and standalone JFR summaries. The input archives
are supplied fixtures, fingerprinted in the report; copyrighted pack content is not
copied here. Adjust archive paths to local copies with the same hashes to rerun.
The streaming exports can be regenerated from committed JFR files and the exporter
source; their hashes are recorded by each analysis JSON.

The native-model jobs/results compare three actual MTR parses, packed emission,
bounds and mirrored/unmirrored merge. Native-reference JUnit outputs are recorded
per build target. They do not apply Mixins.

The client loader results/logs are actual isolated development-client runs using
the current compiled main classes, official/v6 MTR binaries and NeoForge 21.1.248.
They validate client Mixin factory/accessor/executor publication, a fast hit,
injected read failure/retry and balanced tickets/permits. They use an empty model,
base MTR resources and no world/external packs; they do not certify gameplay or
full-pack performance. The client startup logs identify the runtime dependencies,
JVM arguments and graphics environment.

The v6 mismatch log/crash records the discovered 0.4.0/0.4.1 dependency-metadata
defect. The corrected 0.4.2 target uses the binary's actual custom version string.
No historical pass was rewritten into a new-candidate pass.

`v6-gpu.json` and its log record 100 synthetic GPU ownership cycles in the real
render-thread GL context after title-screen resource loading. They check distinct
consumer GPU models, own-model close, sibling survival, early consumer close,
staging/source ownership and rejection of mutation after build. The cycle test is
not an extended gameplay session or a measurement of driver VRAM retention.

The final build/check report identifies current delivery JARs and matching build
manifests. Exact future loader versions, repeated full-pack reloads and long-session
retained/GPU behavior remain outside these checks.
