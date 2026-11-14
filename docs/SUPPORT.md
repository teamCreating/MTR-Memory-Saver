# Support and artifact identity

Minecraft **1.21.1**, Java **21**, client only. The authoritative build targets and
fingerprints are in [config/targets.json](../config/targets.json).

| Target preset | MTR binary | NeoForge | 0.4.x status |
| --- | --- | --- | --- |
| `official-nf248` (default) | Official 4.1.0-beta.2 | 21.1.248 exactly | 0.4.5 packaged loader/fault checks passed; full-pack test found a default text-limit rejection |
| `official-nf265` | Same official binary | 21.1.265 exactly | 0.4.5 build, 43 tests and packaged loader/fault checks passed; full-pack acceptance pending |
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
a failed full-pack gate. Zero module failures cannot override the native decode
diagnostic. Evidence is under `evidence/engineering-045/`; the source repository's
`docs/COVERAGE_OFFICIAL.md` lists the remaining work.

The custom v6 binary declares `4.1.0-beta.2-mc1.21.1-performance-v6`, distinct from
the official binary's metadata version. The 0.4.0/0.4.1 v6 presets incorrectly used
the official version in their strict dependency range and must not be installed.
0.4.2 corrects the range and verifies version metadata alongside the fingerprint.

The 21.1.248 checks use an isolated development client and the current compiled
main classes. They are not a full-pack/world performance comparison or packaged
release certification. Raw reports/logs are under `evidence/engineering-042/`.

Only the official MTR dependency has a verified public download URL in the matrix.
For v6, supply the exact custom JAR with `-PmtrJar=<path>`; a game instance or marker
is not required. Both supplied and downloaded files are checked every build.

No public 0.4.x release has been published from this local repository. `gradlew
releaseBundle` creates a local ZIP containing the JAR, build identity, license and
installation guide. CI stores build artifacts when the workflow is run in a hosted
repository.
