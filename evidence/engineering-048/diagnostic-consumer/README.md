# Live native diagnostic qualification

[Final tooling evidence](final/assessment.json) passes **104 tests**: 7
multi-case native-attribution controls, 57 experiment controls and 40 launcher
controls. Both exact official neutral-observer **1.0.2** artifacts pass their
actual JAR/manifest/capability and frozen-review validation. All 13 captured
source/configuration/document/runner inputs are unchanged during the final run.
Raw commands, stdout/stderr, source snapshots and SHA indexes are retained.

The explicit review can classify only a **live** observed official default-rail
fallback. It requires paired native epochs and diagnostic calls, process and
thread identities, UTC and monotonic boundaries, invocation depth, exact native
method descriptors and caller locations, empty raw factory arguments, the
observed fallback type and matching final native counters. The full raw log must
contain exactly the matching native messages. Known entries remain visible;
other errors remain unreviewed. A missing or malformed trace or final snapshot
cannot reuse a saved successful assessment or hide the original log errors.

The shared observer records this in both comparison arms. The frozen review SHA
is part of each qualification identity and is independently rechecked from
copied raw evidence. Older observer schemas remain readable by the general
launcher but cannot qualify the new performance protocol.

An initial interactive run under system Python could not import
`minecraft_launcher_lib`; the final run uses the project's existing `.venv`,
which provides that dependency. No dependency was installed and no test was
skipped. An initial ad-hoc metadata check also expected duplicate diagnostics
fields in the build manifest; the validator now checks the actual contract:
embedded schema/path, matching declared capabilities and exact artifact hash.

These checks do not start a Minecraft client, establish actual 1.0.2 Mixin
application, prove that the known fallback renders harmlessly, or establish
whole-client performance. A separate short 1.0.2 runtime capture and the complete
current-candidate qualification/trial/calibration gates remain separate.
