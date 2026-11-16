# Owned snapshot channel repair — candidate 0.4.7

This evidence validates a focused reader repair against official MTR
4.1.0-beta.2 / Minecraft 1.21.1 on NeoForge 21.1.248 and 21.1.265. The two
candidate JARs are frozen beside their build manifests:

| Target | Candidate SHA-256 |
| --- | --- |
| official-nf248 | `e8b5b40230d0f44c541c12b32c8a30d4c2ea056b8a972335ae10166496837a99` |
| official-nf265 | `12162be2d0e75962e58d33dec6951e0a82b1455ef1466f9b94c3dce1c4d36a02` |

The previous 0.4.6 implementation separately opened, closed and deleted its
UTF-16 spill file. A halted JVM could therefore leave a file after its handle
closed but before Java cleanup. `Snapshot` now atomically creates a randomized
path with `CREATE_NEW`, `READ`, `WRITE` and `DELETE_ON_CLOSE`, and retains that
single owned channel through writing, full-budget waiting, rewind and
restoration. Windows removes the file when the process releases its final
handle. The implementation retains a bounded 8 KiB I/O buffer, handles short
and zero-progress transfers with retirement checks, preserves owner-only POSIX
creation permissions when supported, and never overwrites a colliding owner.
There is no sweep of prior files or fallback to a weaker ownership mode.

The focused fault provider now targets actual channel operations. Each target
passes 73 tests, including create/write/read/rewind/close failures, primary and
suppressed errors, odd seven-byte transfers, transient zero progress,
persistent zero-progress retirement, actual odd truncation, collision-owner
preservation and unsupported ownership options. Original caller-stream
ownership and all existing text, admission, workspace and generation tests
remain covered. `targeted-nf248.log` predates the added persistent-zero test;
it is an intermediate run, not the final source validation.

`full-nf248.log` and `full-nf265.log` are the initial full-run logs. They do not
contain structured argv or exact execution timestamps, so these were not
reconstructed afterward. `build-replay/execution.json` records fresh actual
Gradle invocations, start/end times, process IDs, exits and final JUnit totals.
These explicitly use `-PmodVersion=0.4.7` and `--rerun-tasks`. Both reproduce the
already-tested candidate JAR and build-manifest bytes exactly. Frozen manifest
inputs and final test/audit sources are under `inputs/`.

The packaged abrupt-exit checks use five fresh, small JVMs per candidate:
normal read, halt during writing, normal restart, halt during full-budget
waiting, and normal restart. Before allowing either halt, the parent records
the running child PID, loaded reader/admission code source and an independent
shared-delete read of the actual UTF-16 bytes. The writing case has 65,536 of
90,008 bytes on disk with 9,007 source bytes still unread. The waiting case has
all 90,008 bytes on disk and one full-budget waiter while only the competing
120,000-byte workspace share remains held. Both cases exit exactly 74 through
`Runtime.halt`, with no caller-finally or shutdown-hook receipt. All four
candidate snapshots disappear. Normal restart controls preserve the exact
other-owner sentinel and leave no additional files.

`old-reader-control/` runs the same current harness against the frozen 0.4.6
NF248 JAR. Both writing and waiting cases retain their files with matching
pre/post bytes, and later normal reads leave these residues untouched. Its
`passed: true` means that the expected old failure was reproduced;
`product_cleanup_after_halt` is explicitly false. The earlier two-target
0.4.6 baseline remains separately preserved in `../snapshot-abrupt/`.

`large-text/` contains four actual 3 GiB JVM runs: both targets with default
Compact Strings and with `-XX:-CompactStrings`. Every run reads the same
102,035,449-byte OBJ entry from the frozen HXD3D/YW25T pack. The independent
source-byte hash, decoded character count and candidate output match exactly;
the UTF-8 SHA-256 is
`e43f1b6b3d1819044094218e5d38c317be4d4a6800582cae0cfdff9f662041bc`.
Eight additional Unicode/malformed forced-spill controls per run match native
IOUtils. The final admission/workspace use and snapshot inventory are empty.
Actual class-load logs bind the reader, admission and workspace to the exact
candidate JAR used by each run.

`assessment.json` records the mechanical cross-checks, original/replayed
JUnit totals, binary comparison and evidence boundaries. `sha256.json` indexes
all sealed evidence payloads, including audit classes and JARs, except itself
and `__pycache__`. The seal verifies archived source copies, manifest inputs,
recorded process receipts, raw results and existing-owner bytes; it does not
rewrite original execution records.

These are reader-level tests on the actual Windows filesystem and exact
packaged artifacts. They do not establish power-loss behavior, actual
filesystem-full behavior, game lifecycle/resource-reload behavior, visual
correctness, the two-hour route, or whole-client performance. Fresh gameplay
and full acceptance for these candidate bytes are separate. V6 remains paused.
