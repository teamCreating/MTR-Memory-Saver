# Native observer 1.0.2 diagnostic contract

Engineering verification on 2026-11-16 (UTC+08:00), official MTR 4.1.0-beta.2 only.

The same independent observer can now record real invalid-model callsites for
both experiment treatments. Its native logger hook preserves raw model/texture
arguments, thread, actual stack descriptors and bytecode indices, JVM identity,
and the active native reload ID. Its final native return hook records the
unchanged loader class. A separate call tracker pairs only matching
thread/depth/epoch/arguments; failed or mismatched calls remain incomplete.
Calls outside an observed reload have a null epoch rather than inheriting the
last completed one. Original logs and model behavior are unchanged.

`game-probe/native-invalid-model.jsonl` has schema 1, one installation receipt,
and paired `before_native_invalid_log` / `native_fallback_return` events.
Snapshots expose started/completed/in-flight/error totals, together with observed
`window_active` and `mouse_grabbed` values. The latter call the exact native
Minecraft query methods and do not alter focus or synthesize input.

The observer retains 1.0.1's shared atomic snapshot publisher. Exact official
runtime/binary guards remain fatal, and installation beside the earlier
standalone model diagnostic is rejected to prevent duplicate providers. It does
not link either current or historical Memory Saver classes, request caches,
bake models, wait for parsing, cancel native callbacks or replace results.

| Target | Final SHA-256 | Tests |
| --- | --- | --- |
| official-nf248 | `1f5a3f9721bd7199cd952f4926afa8cf40996cf76fdc9484a9372f45d1664167` | 24 pass |
| official-nf265 | `6cc023b0024ad3884cae73d7fa7381328758a88a17ba3624d7c8e5abbd3917d6` | 24 pass |

[Verification](verification.json) checks all 28 classes and 25 build inputs per
target. The 24 checks include 20 native-observer tests and four shared publisher
tests. Forced rebuilds under quoted `-PmodVersion=0.3.0` reproduce the final JAR
bytes exactly, while each rerun also passes all 24 checks. Each final directory
contains the JAR/manifest, copied and verified build inputs, original JUnit/logs,
and readable manually emitted frame/tick JFR schema examples. These examples are
not gameplay frame measurements.

The earlier `official-nf248` directory preserves an intermediate build before
the two focus fields and their ABI check. Its source snapshot and 23-test result
remain separate from the final target directories. The verifier's first ad-hoc
run expected only the 20 neutral tests and rejected the additional four shared
publisher tests; the corrected total is 24, with no test removed or changed.

The experiment consumer separately requires complete per-run native epochs,
diagnostic events, full raw log counts, exact identities, and the frozen reviewed
default-rail contract. This feature supplies evidence for that check, not a
message allowlist or a claim that all Invalid model errors are harmless.
Functional visuals, boarding, all reload cycles, long-session acceptance,
baseline/candidate qualification and observer-off calibration remain separate
runtime gates. This build evidence does not assert they have passed.
