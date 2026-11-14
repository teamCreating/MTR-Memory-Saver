# Support and artifact identity

Updated: 2026-11-15T05:46:47.7460681+08:00 (UTC+08:00).

Minecraft **1.21.1**, Java **21**, client only. The authoritative build targets and
fingerprints are in [config/targets.json](../config/targets.json).

| Target preset | MTR binary | NeoForge | 0.4.x status |
| --- | --- | --- | --- |
| `official-nf248` (default) | Official 4.1.0-beta.2 | 21.1.248 exactly | 0.4.6 build, 61 tests, 42 packaged fault/resource checks, wrong-binary rejection and initial full-pack registration/settlement passed; interaction pending |
| `official-nf265` | Same official binary | 21.1.265 exactly | 0.4.6 build, 61 tests, 42 packaged fault/resource checks and wrong-binary rejection passed; full-pack acceptance pending |
| `v6-nf248` | Audited custom Performance v6 | 21.1.248 exactly | Historical 0.4.2 client smoke/GPU cycles; new validation paused |
| `v6-nf265` | Same custom v6 binary | 21.1.265 exactly | Historical development candidate; new validation paused |

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
