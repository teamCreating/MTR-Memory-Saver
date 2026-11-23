# Development build

Install a Java 21 JDK and select it with `JAVA_HOME`. The checked-in Gradle 8.14.3
wrapper verifies the distribution checksum. On Windows use PowerShell 7 and
`./gradlew.bat`; on Linux/macOS use `./gradlew`.

```powershell
./gradlew.bat build
./gradlew.bat build -Ptarget=official-nf265
./gradlew.bat build -Ptarget=v6-nf248 -PmtrJar='<exact custom MTR JAR>'
./gradlew.bat build -Ptarget=v6-nf265 -PmtrJar='<exact custom MTR JAR>'
./gradlew.bat releaseBundle
```

`config/targets.json` determines the official/v6 source directory, exact MTR SHA-256,
exact NeoForge version, metadata and Mixin set. The default is `official-nf265`.
`releaseTargets` selects the targets built and published by CI; 0.4.8 selects
only `official-nf265`. Historical presets remain explicit build options.
`gradle.properties` contains the sole current version, which must stay `0.x.x`.
The ModDevGradle plugin generates development game dependencies in its own cache;
it does not read a vehicle-test-instance marker or any launcher-private Python API.

For official MTR, the build downloads and verifies the pinned public release on
first use. For offline use, supply that exact JAR with `-PmtrJar=<path>`. v6 has no
configured public source and always needs an explicit audited JAR. Gradle itself
also needs cached dependencies when run offline (`--offline`).

The optional Python entry point `python tools/build_vehicle_memory_mod.py --target
official-nf265` forwards to Gradle. Its historical instance/feature path requires
`--legacy` and is not a stable release build.

## Outputs and verification

`build/libs/` contains the target-named JAR and `.build.json` identity manifest.
`releaseBundle` puts an installable ZIP in `build/releases/`. JAR entries have stable
timestamps and order. A clean build of the same inputs should produce the same JAR
SHA-256. Manifests identify source/resource bytes, MTR dependency and exact target;
updating a dependency requires a matrix change and fresh validation.

```powershell
./gradlew.bat test
python -m pip install -r requirements-test.txt
python -m minecraft_testkit verify
python -m minecraft_testkit test
```

The [Python test kit](tests/README.md) organizes regressions, verified samples and
the historical script catalog; [Minecraft MCP](docs/MINECRAFT_MCP.md) is a future
extension plan. Unit tests run without a game instance. Runtime acceptance is
separate: it must
identify its input packs, world, target binaries, heap and process, exercise actual
Mixin application and verify completed reload epochs. Historical instance helpers
remain available under `tools/legacy/` for reproducing earlier reports.

The native reference audits and paired benchmark are documented in
[tools/acceptance/README.md](tools/acceptance/README.md). `probeJar` creates a
separate optional client observation tool; ordinary bundles exclude it.

## Artwork and resources

`src/main/resources/` provides pack format 34 metadata, locale descriptions and the
512-pixel icon. The generated loader/Mixin/target metadata comes from the matrix.
Optional `requirements-artwork.txt` supplies Pillow for `tools/render_pack_icon.py`;
normal builds use the committed PNG and need no artwork/Python dependencies.

See [SUPPORT.md](docs/SUPPORT.md), [INSTALL.md](docs/INSTALL.md), the
[engineering review](docs/ENGINEERING_REVIEW.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Supplied/downloaded MTR bytes are checked and cached under a SHA-named JAR in
`.cache/dependencies/` before compilation/testing. Supplied filenames remain
unchanged. This gives a stable dependency identity and avoids Windows launcher
argument-file failures for non-ASCII supplied artifact names. The build also checks
the audited JAR's actual loader metadata version against the selected matrix.
