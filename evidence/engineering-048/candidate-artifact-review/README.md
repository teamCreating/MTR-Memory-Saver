# Independent 0.4.7 candidate artifact review

Reviewed on 2026-11-16 at 14:36:19 UTC+08:00. This is a read-only artifact and
source-identity review of the official MTR 4.1.0-beta.2 candidates. It does not
launch Gradle, Minecraft or performance trials, and does not constitute gameplay,
full-reload, endurance or performance acceptance. MTR v6 remains outside scope.

## Findings

Both candidates match the exact bytes exercised by the snapshot-owned-channel
engineering tests. Each JAR has 67 file members and 58 Java 21 classes. There are
no added or removed members. The only changed classes relative to the exact
engineering-046 0.4.6 references are `SegmentedResourceText.class` and
`SegmentedResourceText$Snapshot.class`. All other 56 class payloads are identical,
including native compatibility guards, fingerprinting, mixin hooks, packed
vertices, parsing/cache algorithms, generation admission and workspace budgeting.
All 58 candidate classes are also identical between the two loader targets.

The other three changed members are `META-INF/MANIFEST.MF`,
`META-INF/neoforge.mods.toml` and `mtr-memory-target.json`. Their exact byte changes
are limited to `0.4.6` becoming `0.4.7`. The official MTR hash, exact NeoForge
requirements, resource files, mixin configuration and license are unchanged.

| Target | Reference 0.4.6 SHA-256 | Candidate 0.4.7 SHA-256 |
| --- | --- | --- |
| official-nf248 | `dd47f6ae4daa4139b9ada9196d757db634a79ebdd7fa5f06083719d764285997` | `e8b5b40230d0f44c541c12b32c8a30d4c2ea056b8a972335ae10166496837a99` |
| official-nf265 | `fbcb608fd5b2452f650c656bc930934ac4e4880addae4d24846faa5df5d9f63e` | `12162be2d0e75962e58d33dec6951e0a82b1455ef1466f9b94c3dce1c4d36a02` |

All 44 declared build inputs per target match current files. Only
`SegmentedResourceText.java`, `build.gradle` and the two generated version-bearing
resources differ from the reference source fingerprints. No other declared Java
source changes. `build.gradle` has accumulated optional observation-tool work;
the byte comparison confirms it introduced no other product class changes.
Sixty-one original files, including both pairs of JARs/manifests and all declared
current source inputs, were stable before and after capture.

## Effective version and build evidence

The captured `gradle.properties` still defaults to `modVersion=0.4.6`.
`build.gradle` obtains the effective version from the Gradle project property,
tracks it as a task input, and writes it into the artifact and build manifest.
The actual repeat-build receipts in
`run-01/inputs/evidence/engineering-048/snapshot-owned-channel/build-replay/execution.json`
record `-PmodVersion=0.4.7`, `--rerun-tasks`, actual process IDs and timestamps,
exit code zero, and the exact candidate hashes above for both targets. Both
commands ran `test jar buildManifest verifyRelease`, reported 73 tests with no
failures, errors or skips, and reproduced each original candidate manifest
byte-for-byte. These are new recorded executions; the older initial console logs
do not contain argv/timestamp receipts and have not been retroactively assigned
those facts.

The product build manifest enumerates main source/resources, `targets.json` and
`build.gradle`. It does not enumerate `gradle.properties`, `LICENSE`, the JDK or
every dependency/build-environment file. This review separately captures the
properties and license, verifies the actual license payload, and binds exact
whole-JAR bytes. It does not claim the declared-input list is an exhaustive
build-environment attestation. The later default-version change, if any, is a
separate source change and must retain its own build verification.

## Reproducible evidence

`audit.py` and `review-spec.json` define the explicit reviewed scope and pinned
identities. The actual invocation, exit code and console output are preserved in
`run-01.execution.json` and its adjacent logs. `run-01/assessment.json` includes
every member's old/new length and SHA-256, all declared-input comparisons, source
fingerprints before/after, and fourteen in-memory negative controls. The controls
reject extra/missing members, a changed class outside scope, unrelated edits to
each metadata member, and a missing expected class change. These controls alter
only copied dictionaries; original JARs are never changed.

`run-01/inputs/` contains the exact inspected bytes. `run-01/SHA256SUMS.json`
indexes all 64 payload files. `verify_sealed.py` independently recomputes the
sealed inventory, source fingerprints and every archived ZIP member digest,
without loading `audit.py` or the original workspace artifacts. Its result is
`sealed-verification.json`.

To replay the original audit against only sealed inputs, use a fresh output
directory and the sealed specification. From this evidence directory:

```powershell
python ./run-01/audit.py --root ./run-01/inputs --spec ./run-01/review-spec.json --output ./fresh-replay
```

The replay command intentionally refuses an existing output directory. Original
workspace paths in old build receipts remain historical data. Copying those
receipts does not repeat the recorded builds.
