# Packaged official 0.4.7 lifecycle validation

Four independent, sequential ordinary Minecraft 1.21.1 JVMs ran on
2026-11-16 (UTC+08:00) with the exact owned-channel candidates, Java 21.0.11,
a 3072 MiB maximum heap and a 512 MiB initial heap. These use base resources,
no user world or authored pack, and no scheduler override. New v6 validation
remains paused.

| Target | Fault client | Same-version wrong-binary client |
| --- | --- | --- |
| official-nf248 / NeoForge 21.1.248 | PID 51108; exit 0; 24 lifecycle + 18 resource checks | PID 57720; exit 1; rejected before vehicle registration |
| official-nf265 / NeoForge 21.1.265 | PID 27604; exit 0; 24 lifecycle + 18 resource checks | PID 53920; exit 1; rejected before vehicle registration |

Both fault clients exercise the packaged factory/accessor Mixins, missing,
truncated, wrong-root and oversized inputs, same-key correction/retry, actual
resource open/read/close failures, legal empty text, native malformed-UTF-8
replacement and missing-cache retirement. A probe holds a real native parser
across retirement: its ticket and permit remain owned until actual exit, the new
generation publishes independently, and late completion cannot repopulate the
retired facade. All 42 checks pass on each target; used/waiting text workspace
ends at zero. Both normally closed JFR files pass actual `jfr summary` execution
with one readable chunk each (47 and 39 seconds). Their duration covers these
short fault clients, not an endurance session.

Both mismatched MTR files keep every JAR member and metadata byte unchanged; only
the ZIP comment changes. Final independent file comparison rechecks that exact
byte boundary. With no probe installed, both clients exit with code 1 through
`MixinInitialisationError`, preserve the fingerprint cause and show no vehicle
registration line. These are binary guard checks, not missing-model tests.

The candidate hashes remain:

- NF248: `e8b5b40230d0f44c541c12b32c8a30d4c2ea056b8a972335ae10166496837a99`.
- NF265: `12162be2d0e75962e58d33dec6951e0a82b1455ef1466f9b94c3dce1c4d36a02`.

The independently reviewed product JARs contain no probe classes. Their exact
artifacts/manifests, separate probe identities and frozen source inputs are in
`artifacts/` and `sources/`. `prepare/` contains actual preparation/build commands,
exit codes and ZIP-comment controls; `prepared/` preserves each original plan.
`runtime/` contains actual owned process identity/creation time, launch/exit chain,
live process observations, unmodified logs, results and JFRs. Final installed
mod/source hashes match the plans and runtime sources for all four cases.

## Preserved evidence-runner failure

The first NF248 JVM passed its checks and exited normally, but the original
post-exit runner attempted to decode a native console stream as UTF-8 and failed.
`runtime/official-nf248-faults/execution.json` retains `passed=false`, the original
`UnicodeDecodeError` and original console bytes. `sources/run_matrix.py` preserves
that runner. The later runner matches fixed ASCII diagnostic bytes directly,
without assuming a console language/encoding or rewriting logs; its separate
source is `sources/run_matrix-byte-log.py`.

The [independent final assessment](final-assessment.json) validates the completed
first JVM from its actual result, owned exit, source/input fingerprints and fresh
JFR summary. It records the original runner failure separately. The preliminary
`assessment.json` retains its earlier assessor fingerprint and result; no old
receipt was overwritten. The other three actual runs finish with runner
`passed=true`.

`assess.py` reads only sealed receipts/artifacts; it never starts Minecraft or a
JVM. It binds the candidate hashes to `review-spec.json`, checks all four process
chains, policies, fault/resource outcomes, ownership settlement, readable JFR
identities and fatal mismatches. Twelve copied-actual-receipt negative controls
reject another process, candidate/runner identity, unowned exit, failed lifecycle,
leaked workspace, missing oversize, transplanted time, unrelated failed runner,
wrong JFR and invalid binary controls. Original files are unchanged by them.

Replay from this directory with a fresh output:

```powershell
python ./assess.py --root . --output ./fresh-assessment.json
```

`SHA256SUMS.json` records the complete captured payload inventory and
`sealed-verification.json` independently rehashes it. The two inventory/verifier
outputs are excluded from their own fingerprint cycle.

Full-pack geometry, selector behavior, displays, doors, floors/boarding, twenty
consecutive full ResourceManager reloads, the two-hour route and controlled
performance remain separate acceptance gates. Expected injected fault errors,
the base-resource `transparent.png Invalid model` diagnostic and account/service
messages remain in the original logs. This audit does not classify them as a
whole-client visual or performance pass. No product class changed during this
packaged matrix.
