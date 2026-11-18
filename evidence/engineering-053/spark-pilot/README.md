# Local Spark operation and diagnostic pilots

NF248 PID 74984, created 2026-11-18T04:34:24.160750+00:00, used the revised
0.4.8 943b… candidate, neutral observer 1.0.3 and audited spark 1.10.124.
It loaded the complete 16 packs with Xms512M/Xmx3072M, explicit G1, full-history
JFR and disabled implicit Spark background profiling. This is a diagnostic
pilot, not one of the four qualifications or 48 scheduled A/A/A/B trials.

The native startup epoch 1 and one actual F3+T reload epoch 2 both returned;
epoch 2 ran 2026-11-18T04:45:27.671843300Z–04:56:59.147986800Z. Input attempts
were CUA operations, but no complete strict input-receipt closure was made for
this pilot; it is not appended to the earlier sealed 20-reload cohort.
The initial native snapshot showed a stationary train, while later samples
observed the declared route 1634058583976595067 and changing rail progress.
F2 images were visually inspected locally; WGC capture remained unavailable.

The 4 ms all-thread Java profile was started at 12:43:25 +08:00 and manually
stopped with local save at 13:00:36. It produced the first raw Spark file.
Frequent ThreadDump safepoints, world-statistics timeouts and substantial
background host CPU load make this unsuitable for a performance-gain claim.
The SDK metadata duration includes export timing and is not asserted to be
continuous CPU sample coverage. A 100 ms, 30-second all-thread Java profile
then actually stopped and saved locally by its timeout callback. Neither was
uploaded to a Spark viewer. These observations do not qualify overhead.

The environment skill reader's first outputs incorrectly interpreted signed
negative player counts and omitted engine semantics; those initial outputs are
retained under pilot/profile-4ms-analysis and are not used as corrected metrics.
The new offline adapter instead invokes the exact Spark JAR's own public
generated protobuf decoder and exports typed getters. Its first attempt did
not handle an opaque ByteString and failed; original actual exit/stderr/class
remain in cache. Adding an explicit Base64 representation fixed both actual
profile exports. Current source, compile/self-test/actual execution receipts
and six strict flat-tree/time-window analyzer tests are retained here.

All six actual official-decoder thread analyses completed. Sample self weights
include waiting states and are not measured CPU time. Small negative residuals
from the 4 ms sample tree are retained in the reports; none occurred in the
100 ms reports. Unavailable world-statistics sentinels remain negative.
The high-frequency render profile mainly sampled ReadAdmission parking and
texture upload paths; the short low-frequency profile included MTR draw calls.
No baseline comparison or benefit percentage follows from those rankings.

Both profiles were saved before normal Alt+F4. The actual owned JVM wait and
collector exited zero (collector exit0 is parent-tool-reported; execution.json
is the actual JVM wait receipt). The 62,017,654-byte JFR was independently summarized
with actual exit0 and unchanged before/after fingerprint. Product/observer/
Spark/MTR installed JAR hashes all matched the original plan after shutdown.

This selected seal is not a complete raw replay closure: raw Spark/JFR files,
full decoded machine/configuration data, third-party JARs, worlds, resource
packs, dependencies and screenshots stay in ignored cache. Their explicit
fingerprints do not stand in for a published raw replay. A/A, A/B, observer-off,
instrumentation acceptance and release remain pending. The earlier failed
qualification had no explicit G1 option and was rejected before any trial JVM;
it remains a failed preparation attempt, not a completed performance sample.
