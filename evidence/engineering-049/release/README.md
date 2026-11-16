# Official 0.4.7 candidate delivery audit

Both official target bundles were built sequentially on 2026-11-16 (UTC+08:00)
after the separate full-pack client reached native settlement. The build executes
`releaseBundle -x test` with Java 21.0.11 and the effective default version from
`gradle.properties`. No game client was launched by this delivery audit. Original
0.4.6 bundles remain unchanged.

| Target | Candidate JAR SHA-256 | Local bundle SHA-256 |
| --- | --- | --- |
| official-nf248 | `e8b5b40230d0f44c541c12b32c8a30d4c2ea056b8a972335ae10166496837a99` | `571d3ce58a6bb0b1dba2289935eef78a5e5b8f690a1b76c5df4fa30d45354db4` |
| official-nf265 | `12162be2d0e75962e58d33dec6951e0a82b1455ef1466f9b94c3dce1c4d36a02` | `17d3f3d5beecd073b26388f3dc72116290a9ced8a8b6d9aa9bce4ac1c481b79d` |

The JARs remain byte-identical to the independently reviewed owned-channel and
packaged-client candidates. Each current build manifest verifies all 44 declared
source/resource inputs. The changed `build.gradle` fingerprint belongs to delivery
engineering; it changes no product class or runtime resource. Both Gradle commands
exit zero and run `verifyRelease`; the existing exact-JAR 73-test and packaged
evidence is retained without rerunning Java tests for document packaging.

Each bundle has exactly eight file members: the JAR, its build JSON, license,
README, installation guide, self-contained support document, version-bound
validation JSON and target matrix. All members equal their actual build sources;
ZIP CRCs and all eight local Markdown links per bundle pass. There is no acceptance
probe inside the product or delivery bundle.

## Corrected delivery documentation

The repository's complete `docs/SUPPORT.md` links detailed engineering evidence.
Copying it into a small install bundle would produce missing local links. The
bundle now uses `docs/templates/delivery-support.md`, filled from `targets.json`,
the effective version and the actual JAR digest. It links only included files and
retains the development-candidate label.

`config/delivery-evidence.json` selects evidence by version and target, pins the
artifact and assessment hashes, and points to the already reviewed packaged
assessment. `bundleSupport` rejects a changed JAR/assessment, duplicate version
records, wrong target, missing/failed cases or invalid recorded outcomes. Counts,
exit results and scope are copied from the accepted actual cases, not hardcoded
into future releases. A later version without a bound record emits `unavailable`
and makes no inherited runtime claim. The bundle's `docs/VALIDATION.json` preserves
the first NF248 runner's original post-exit decoding limitation through its copied
case record. Raw engineering receipts remain in the source repository.

## Preserved records and independent replay

`execution.json` records actual commands, child PIDs, start/end/exit receipts,
tool/JDK/source hashes and sequential target execution. Target directories contain
raw logs, full copied ZIPs, the actual eight-member sources and assessments.
`inputs/` preserves every declared build input for each target; `source/` freezes
delivery configuration, templates, license and original packaged assessment.

`SHA256SUMS.json` pins the complete captured payload set. `verify_sealed.py` rehashes
the inventory, checks exact product/evidence/source identities, parses the ZIPs
and validates their links independently of Gradle and `build_and_audit.py`. Its
twelve copied-member negative controls reject missing support, broken navigation,
promotion of a candidate, changed product bytes, another version's evidence and
replaced actual outcomes. Original bundle bytes are never altered.

The [sealed verification](sealed-verification.json) and target assessments record
the results. This is local delivery correctness. It establishes no new full-pack
interaction, twenty-reload endurance, two-hour route or controlled-performance
pass, and publishes nothing outside the local repository. New v6 validation remains
paused.
