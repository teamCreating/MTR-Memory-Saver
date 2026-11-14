# Native observer engineering evidence

Scope: official MTR 4.1.0-beta.2, Minecraft 1.21.1, Java 21, exact NeoForge
21.1.248 and 21.1.265. No game was launched or changed by these builds/audits.

Each target's `final/` contains the exact observer JAR/build manifest, the 14-test
JUnit reports and a standalone JFR with one manually emitted frame and one tick
event. The JFR JSON/summary validate schema readability, not native callbacks,
real frames, loading latency or client coverage. `assessment.json` independently
checks the final JARs, all 21 manifest inputs, class namespace/reference isolation,
embedded native target/capability metadata and archived JUnit/JFR records. Run
`audit.ps1 -RepositoryRoot <repository>` after rebuilding both neutral targets.

The first NF248 build is retained in `attempt-01/`; it precedes the final tick
lifecycle cleanup and persistent JFR export. It is an intermediate engineering
artifact, not the JAR to install in comparison trials. The final tested runtime
sources are tracked under `tools/probes/neutral/java/`. The 13-test stage before
completion timestamps is preserved with its source snapshot in
`pre-timestamp-correction/`; it is not the final installable observer.

Each successful reproducibility recording forces the native JAR tasks to rerun
with the product `modVersion` property set to 0.3.0. Its SHA-256 equals the final
JAR built under the default 0.4.6 property, proving both reproducibility and
independence from that property. This did not build or run the old product. The
first NF248 re-run failed the existing development-version validation and
produced no rebuilt artifact. Its log/receipt are preserved; successful retries
pass the property as an explicit quoted PowerShell string.

No actual Mixin/client qualification, baseline current-pack qualification,
complete native reload, real JFR frame window, full A/B or observer-off calibration
pass is claimed here. The separate current route run uses its previously installed
probes and is not a runtime qualification of these neutral JARs.

JDK-exported JSON retains its original trailing spaces and indexed bytes. A local
Git whitespace attribute applies only to those raw `frame-events.json` captures;
source/configuration/documentation whitespace checks remain enabled.
