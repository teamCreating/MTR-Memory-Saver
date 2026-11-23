# Local spark diagnostics

The current Windows/Minecraft 1.21.1 NeoForge diagnostic uses spark 1.10.124,
Modrinth version `v5qtqRQi`, SHA-256
`647e8a81afbe414dba1df4ba15fd06c5d32d4cb544e68828405e8e074c2e16db`.
The downloaded bytes also match the release metadata's SHA-512. The third-party
JAR stays in the ignored test cache and is not part of the Memory Saver release.

Pass it explicitly through `packaged_client.py prepare --measurement-mod`.
Freeze an explicit G1 collector and `-Dspark.backgroundProfiler=false` in every
group. New measurement mods require new prepared instances and qualification.
The separate independent observer and existing performance budgets remain in
effect. Installing spark is not qualification or evidence of a performance gain.

Client commands use `/sparkc`. The Windows Java engine has safepoint sampling
bias. The first 4 ms all-thread pilot caused frequent costly ThreadDump safepoints
and is retained as a diagnostic/overhead attempt, not a comparison result. A
second pilot verified automatic local saving with:

```text
/sparkc profiler start --thread * --interval 100 --force-java-sampler --timeout 30 --save-to-file
```

The exact JAR's `SamplerModule` bytecode confirms the start command propagates
the local-save flag to its completion callback. The 30-second pilot actually
stopped automatically and wrote a second `.sparkprofile` under `config/spark`.
This only verifies operation; 100 ms overhead has not passed a paired calibration.
Do not omit the timeout for a new diagnostic whose render thread may block.
An already-running sampler can be stopped with
`/sparkc profiler stop --save-to-file`. Neither command uploads the profile.

## Offline decoding

`tools/SparkProfileExport.java` uses the selected spark JAR's **public generated
protobuf decoder**. It does not initialize Minecraft, inspect private fields, or
reconstruct signed protobuf integers. JSON is exported through generated public
getters; opaque byte fields retain explicit Base64 encoding. Compile it with
JDK 17 or newer, then supply the audited JAR on the Java classpath:

```powershell
javac --release 17 -encoding UTF-8 -d <new-output> tools/SparkProfileExport.java
java -cp <new-output> SparkProfileExport --self-test
java -cp '<new-output>;<audited-spark.jar>' SparkProfileExport <local.sparkprofile>
```

Redirect output to a new local file and retain actual commands, exit codes and
input/output hashes. Spark metadata `interval` is in **microseconds**, unlike
the command's millisecond argument. Negative world counts are unavailable
sentinels. Metadata export end time is not asserted to be the exact last stack
sample time. Raw metadata can include machine/configuration data; it remains
local unless separately reviewed for publication.

```powershell
python tools/spark_profile_analysis.py <export.json> --thread 'Render thread'
```

The analyzer requires an exact thread match, explicit roots, valid acyclic flat
child references, and weights aligned to `timeWindows` in their original order.
It retains negative self-weight residual diagnostics while clamping those
residuals to zero for the displayed self ranking. It does not silently select
another thread or infer missing fields. Root/child sample weights are neither
measured CPU elapsed time nor displayed/JFR frame durations. World statistics
also need native-log freshness review: the loading pilot recorded timeouts.

Actual A/A, A/B, observer-off and instrumentation controls remain separate gates
in [CLIENT_EXPERIMENT.md](CLIENT_EXPERIMENT.md). These pilots do not pass them.

Primary references: [spark commands](https://spark.lucko.me/docs/Command-Usage),
[configuration](https://spark.lucko.me/docs/Configuration),
[engine requirements](https://spark.lucko.me/docs/misc/Using-async-profiler),
[sampler schema](https://github.com/lucko/spark/blob/master/spark-common/src/main/proto/spark/spark_sampler.proto).
