# Independent failed-attempt seal verification

The standalone sealed-only reviewer in `independent-seal-review-20261116-a/`
ran successfully on 2026-11-16 (UTC+08:00). Its actual verifier invocation,
timestamps, exit code 0 and original stdout/stderr are preserved under
`execution-20261116T155030029610Z/`. The review reads only the frozen sibling
`observation-attempts/` payloads; it does not inspect current game data or run
the consumer against a live process.

All 43 payload hashes and the complete inventory agree before and after review.
The reviewer verifies all 38 copy receipts, frozen plan/launch, both copied
companion/observer JAR identities, recorder canonical journal chain, actual
failed status/empty reload sample file, 201 interrupted startup records without
a summary, and 503 collector checkpoint records without an exit. The native
checkpoint retains PID 18796, matching observer 1.0.3 metadata and zero
observation errors.

The MTR binary is not copied into the seal, so this external review checks its
recorded fingerprint's agreement with the frozen plan; it does not independently
rehash that runtime binary. The exception encodes a configured 20-second timeout;
the recorder journal timestamps actually span 120.875254 seconds. Parent-reported
tool exit history remains distinct from original persisted receipts and does not
prove an exit cause or time.

No attempt02 content is consumed. Successful evidence verification grants no
startup, reload, gameplay, endurance, performance or process-exit acceptance.
The initial optional-directory listing failure is preserved in
`exploration-failure-reported.json`; it is explicitly a reported exploration
failure, separate from the successful verifier execution.
