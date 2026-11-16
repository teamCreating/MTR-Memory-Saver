# Official experiment tooling review

The [final assessment](review-final/assessment.json) passes **55 synthetic
experiment tests**, actual JDK 21 parsing of the two existing official observer
event-schema JFRs, and rejection of two truncated copies. The recordings contain
manually emitted standalone schema events, not gameplay. Their original bytes
and all nine reviewed tool/config/document/runner source files are unchanged
during the final execution. Commands, stdout/stderr, source snapshots and hashes
are retained under `review-final/`.

The review finishes the interrupted integration's raw execution receipts, actual
JVM identity binding and independent sealed-JFR parsing. Qualification captures
cannot be copied into scheduled trials; a qualifier's PID/creation identity
cannot be reused with differently formatted time zones. Missing GC durations or
full-GC pause evidence remains unavailable and prevents qualification.

An additional negative control reproduced an actual analysis gap: distinct JVMs
whose windows all overlapped could still pass the instrumented statistical
gates. Analysis now enforces the scheduled chronological order, non-overlap, and
containment by the raw trial/experiment receipts. Exact raw inventories retain
all captures and failed exports. Qualification freezes source identities before
capture and rechecks source, prepared inputs and host afterward, so a mid-run
edit cannot qualify observations under new source fingerprints.

Native snapshot reads now use the same Windows reader as the observer, and that
helper participates in source identity. The reader's compatible native publisher
and new observer binaries are validated separately by the route-recovery work;
these experiment tests do not establish native-publisher or client acceptance.

`review-attempt01/` preserves the earlier successful tooling run before routing
experiment snapshot reads through the shared reader and before that helper's
final documentation/dependency changes. `run_review.py` reproduces the final
checks with an explicit JDK and a new output directory.

The four current actual-client qualification groups, all 48 scheduled JVM trials
and observer-off calibration remain unexecuted by this review. No Minecraft
client was started, no production file was modified, and no v6 verification was
performed. Uninstrumented whole-client performance remains unaccepted.
