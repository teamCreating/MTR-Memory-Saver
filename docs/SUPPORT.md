# Support and artifact identity

Updated: 2026-11-17 (UTC+08:00).

Minecraft **1.21.1**, Java **21**, client only. The authoritative build targets and
fingerprints are in [config/targets.json](../config/targets.json).

| Target preset | MTR binary | NeoForge | 0.4.x status |
| --- | --- | --- | --- |
| `official-nf248` (default) | Official 4.1.0-beta.2 | 21.1.248 exactly | 0.4.7 build, 73 tests, abrupt-exit, 3 GiB source audits, 42 packaged checks, fatal wrong-binary rejection and scoped sixteen-pack startup passed; interaction/endurance/performance pending |
| `official-nf265` | Same official binary | 21.1.265 exactly | 0.4.7 build, 73 tests, abrupt-exit, 3 GiB source audits, 42 packaged checks and fatal wrong-binary rejection passed; full-pack acceptance pending |
| `v6-nf248` | Audited custom Performance v6 | 21.1.248 exactly | Historical 0.4.2 client smoke/GPU cycles; new validation paused |
| `v6-nf265` | Same custom v6 binary | 21.1.265 exactly | Historical development candidate; new validation paused |

The default candidate is now **0.4.7**. Both official targets pass 73 Java tests,
four actual abrupt-exit cleanup checks across writing and workspace waiting, and
four 3 GiB large-OBJ checks across targets and CompactStrings modes. The exact
0.4.6 negative controls retain spill files under the same abrupt-exit harness.
[Owned-channel evidence](../evidence/engineering-048/snapshot-owned-channel/README.md)
and [independent artifact audit](../evidence/engineering-048/candidate-artifact-review/README.md)
bind the new JARs. Only the reader and its Snapshot class change; the other 56
classes are byte-identical. Both exact 0.4.7 packaged official clients now pass
24 lifecycle and 18 real-resource fault checks each, exit normally, and preserve
readable JFRs. Both same-version wrong-binary clients fail fatally before vehicle
registration. [Packaged 0.4.7 evidence](../evidence/engineering-048/packaged-owned-channel/README.md)
binds all four independent JVMs; full-pack interaction, reload endurance, route
duration and controlled performance are still pending.

Current NF248 runtime coverage includes the [independently sealed 0.4.7 startup
with observer 1.0.3](../evidence/engineering-050/neutral103-startup/README.md):
13/13 valid samples, a 60.0146004-second external interval, all sixteen archive
pairs, 1092 declarations/1091 distinct IDs and zero native pending work/observer
errors. Native timestamps span 59.7471383 seconds. Existing cache regions are
observed, but visual, passenger, complete-exit, reload and performance acceptance
remain separate. The probe-only publisher repair changes no product class.

A later 0.4.6 NF248 run with neutral observer 1.0.2 completed one actual F3+T
ResourceManager reload and exited normally with a readable JFR. Its explicitly
captured before state is more than 15 seconds before input, so the strict accepted
streak remains **0/20**. The input-method issue is resolved; manual input is no
longer requested. Screenshots show the station/empty siding rather than a train.
The earlier unsuccessful inputs and route failures below retain their identities.

The historical 0.3.x reports include particular full-pack runtime trials. Those
passes identify their exact older JARs; they are not 0.4.x runtime passes. The new
reports distinguish bootstrap/build, headless algorithm tests and game/GPU checks.
Fabric 0.1.1 is a historical implementation, excluded from the stable 0.4.x presets.

The 0.4.4 official-nf248 check loads the packaged companion in an ordinary SDK
client. It checks malformed/missing/oversized inputs and a paused native parser
across retirement, including failure retry and balanced cleanup. Evidence is under
`evidence/engineering-044/`; full resource-pack/world and performance validation
are still separate gates. Current verification focuses on official beta.2.

The 0.4.4 same-version wrong-binary failure is preserved: Mixin logs its plugin
exception and continues startup with the companion configuration skipped. 0.4.5
uses the framework's standard fatal initialization error. Its actual mismatched
NF248 client exits with code 1 before resource registration; matching binaries on
both official loaders pass all 24 packaged fault checks.

The actual 0.4.5 full sixteen-pack test reaches 1092 vehicle declarations and 1091
distinct ID strings, with settled module counters, but rejects a valid 102,035,449
code-unit OBJ input against the default 100,663,296 limit at a 3 GiB heap. This is
a historical failed full-pack gate. Zero module failures cannot override the native decode
diagnostic. Evidence is under `evidence/engineering-045/`; the source repository's
`docs/COVERAGE_OFFICIAL.md` lists the remaining work.

0.4.6 replaces the fixed per-reader default with a shared heap-derived text
workspace and owned UTF-16 snapshots. The actual large OBJ passes exact packaged
NF248 source-byte checks at 3 GiB, including disabled CompactStrings. Existing
resource open/read/close/size failures now propagate through the official provider;
successful empty text and native missing-resource behavior remain distinct.
Both official packaged clients pass 24 lifecycle plus 18 actual resource checks
and exit normally. The new NF265 same-version mismatch exits with code 1 before
registration. The actual 0.4.6 NF248 sixteen-pack load registers 1092 declarations
and 1091 distinct ID strings, with native/module work and text workspace settled
and no renewed large-OBJ decode rejection. Its visual geometry, displays, doors,
floors and boarding remain unverified. The exact 0.4.6 NF248 mismatched client also
exits with code 1 before registration, with the original fingerprint cause intact.
The copied MTR entries are byte-identical; only the ZIP comment changes.

The initial startup observer failed its observation gate with two of four GPU
samples available. Route attempt 01 was interrupted with `passed=false` after
287 samples over 1432.8089 seconds, including 19 repeated states and one unavailable
GPU query out of 23. Attempt 02 removes repeated-state samples but still fails one
20.8426-second gap against its frozen 20-second limit. Both attempts remain failed
observations. Three F3+T input API receipts
produced no new native epoch or full ResourceManager reload log; accepted real
reloads remain 0/20. These preserved incomplete results do not establish a two-hour
route, boarding, complete GPU coverage or controlled full-client performance.
The game exported a native F2 screenshot, but no train is visible in that view;
it does not establish vehicle interaction. Standalone tool test executions and
raw observations are under `evidence/engineering-046/`. The source repository's
`docs/COVERAGE_OFFICIAL.md` records the current gates.

The five additional core checks cover snapshot output write/close, restoration
read, deletion and suppressed cleanup failures. Actual Windows deletion-lock
audits also pass on both unchanged packaged readers. A retained file on failed
deletion is reported honestly; explicit fixture cleanup does not establish
automatic recovery after an abrupt JVM exit or a full disk.

Route attempt 03 failed after the exact Java process crashed in Windows
textinputframework.dll (exit 1653). Its partial first window is preserved; the
two-hour session and final JFR coverage do not pass. A new NF248 diagnostic run
with native observer 1.0.0 provides actual native/frame/tick data and a normal
saved exit. Its one `transparent.png Invalid model` message is traced to the
official empty default-rail constructor, without certifying rail rendering or
excusing future errors. Probe-only Windows snapshot publication is repaired;
observer 1.0.2 has since produced per-call native evidence through the real reload.
Each later qualification must bind its own diagnostic trace and raw errors.
Independent launcher/observer/comparison engineering does not establish runtime
qualification. Both versions still need separate current plain/profile
qualifications, followed by the frozen 48-trial whole-client comparison and
observer-off calibration. No new performance trial has run.

The custom v6 binary declares `4.1.0-beta.2-mc1.21.1-performance-v6`, distinct from
the official binary's metadata version. The 0.4.0/0.4.1 v6 presets incorrectly used
the official version in their strict dependency range and must not be installed.
0.4.2 corrects the range and verifies version metadata alongside the fingerprint.

The historical 0.4.2 NF248 checks use an isolated development client and its
compiled main classes. Those reports do not certify a packaged release or
full-pack/world performance. Raw reports/logs are under `evidence/engineering-042/`;
the exact 0.4.6 packaged checks are identified separately above.

Only the official MTR dependency has a verified public download URL in the matrix.
For v6, supply the exact custom JAR with `-PmtrJar=<path>`; a game instance or marker
is not required. Both supplied and downloaded files are checked every build.

No public 0.4.x release has been published from this local repository. `gradlew
releaseBundle` creates a local ZIP containing the JAR, build identity, license and
installation guide. CI stores build artifacts when the workflow is run in a hosted
repository.
