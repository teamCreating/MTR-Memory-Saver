# Support and artifact identity

Minecraft **1.21.1**, Java **21**, client only. The authoritative build targets and
fingerprints are in [config/targets.json](../config/targets.json).

| Target preset | MTR binary | NeoForge | 0.4.x status |
| --- | --- | --- | --- |
| `official-nf248` (default) | Official 4.1.0-beta.2 | 21.1.248 exactly | Development candidate |
| `official-nf265` | Same official binary | 21.1.265 exactly | Development candidate |
| `v6-nf248` | Audited custom Performance v6 | 21.1.248 exactly | Development candidate |
| `v6-nf265` | Same custom v6 binary | 21.1.265 exactly | Development candidate |

The historical 0.3.x reports include particular full-pack runtime trials. Those
passes identify their exact older JARs; they are not 0.4.x runtime passes. The new
reports distinguish bootstrap/build, headless algorithm tests and game/GPU checks.
Fabric 0.1.1 is a historical implementation, excluded from the stable 0.4.x presets.

Only the official MTR dependency has a verified public download URL in the matrix.
For v6, supply the exact custom JAR with `-PmtrJar=<path>`; a game instance or marker
is not required. Both supplied and downloaded files are checked every build.

No public 0.4.x release has been published from this local repository. `gradlew
releaseBundle` creates a local ZIP containing the JAR, build identity, license and
installation guide. CI stores build artifacts when the workflow is run in a hosted
repository.
