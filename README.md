# MTR Memory Saver

MTR Memory Saver shares resource/model inputs and stores parsed vertex data losslessly
for **Minecraft 1.21.1 / NeoForge**. The current **0.4.x** line is a development
candidate with explicit official-MTR and Performance-v6 targets. Its support matrix
is closed to exact binaries and loader releases.

The historical sixteen-pack 0.3.x trials prove specific memory/loading results.
They do not automatically qualify newer artifacts. See the [support matrix](docs/SUPPORT.md)
and [critical engineering review](docs/ENGINEERING_REVIEW.md) for scope and remaining risks.

## Build

Use a Java 21 JDK. No Minecraft test instance, marker file, Python launcher library,
or copied patched-client JAR is required for a development build.

```powershell
./gradlew.bat build
./gradlew.bat build -Ptarget=official-nf265
./gradlew.bat build -Ptarget=v6-nf248 -PmtrJar='<audited Performance-v6 JAR>'
./gradlew.bat releaseBundle
```

The default is `official-nf248`. Gradle resolves the game/NeoForge toolchain and the
hash-pinned official MTR dependency. Custom v6 must be supplied explicitly. All
releases remain `0.x.x`; `gradle.properties` is the version authority.

JARs and their identity manifests are produced in `build/libs/`. Release ZIPs in
`build/releases/` include the JAR, manifest, license and installation guide. No
public download has been published from this local repository. The included CI
workflow builds official target bundles and makes them available as workflow artifacts
when used in a hosted repository.

See [BUILDING.md](BUILDING.md) for reproducibility and offline/custom inputs,
[installation](docs/INSTALL.md) for deployment/rollback, and [LICENSE](LICENSE).

## Maintain and verify

Stable code is in `src/main/java/`. Only release-specific ABI/lifecycle files belong
in `src/targets/official/java/` or `src/targets/v6/java/`; a preset compiles exactly
one target directory. Feature flags do not assemble a production release.
`src/experiments/`, `src/legacy/` and `tools/legacy/` are historical references and
are excluded from stable builds.

`gradlew test` runs headless regression tests. Build manifests record the selected
target, MTR hash, exact loader, version, source/resource hashes and artifact hash.
Reproducible JAR ordering/timestamps permit meaningful rebuild comparisons.
The Mixin compatibility plugin checks the loaded MTR bytes before installing hooks.

Version 0.4.1 adds bounded descriptor scheduling, provider/path fast hits,
generation retirement, terminal parse failure and guarded text admission. See the
[runtime contract](docs/RUNTIME_DESIGN.md) and [acceptance procedure](docs/ACCEPTANCE.md).

Version 0.4.3 binds admission waiters to their original generation across model,
text and vehicle-JSON caches, cancels retired read waiters promptly and validates
configured limits explicitly. Current validation focuses on official MTR
4.1.0-beta.2; new v6 validation is paused. Candidate-specific runtime evidence is
required before extending the historical support claims.

Version 0.4.4 propagates malformed Blockbench input failures through the native
parser and shared-future cleanup instead of caching successful empty fallbacks.
Valid inputs retain the original schema and model algorithm.

Historical guides and measurements are indexed in [HISTORY.md](docs/HISTORY.md)
and [TECHNICAL.md](TECHNICAL.md). New candidate tests and performance reports have
separate artifact identities. GPU lifetime and gameplay require runtime acceptance;
a successful compile or class-file comparison is not such acceptance.

The independent [acceptance tools](tools/acceptance/README.md) cover native reference
audits, paired real-input source lookup, JFR analysis and optional client probes.

The [optimization and comparison workflow](docs/OPTIMIZATION.md) supplies a frozen
experiment plan, balanced A/B and A/A runs, JFR overhead controls, preserved failures
and independent paired analysis. Policies live outside the mod in
`config/source-experiment.json`; source results do not certify full-client performance.

![Pack icon](src/main/resources/pack.png)
