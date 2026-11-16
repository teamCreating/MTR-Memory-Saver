# Packaged snapshot behavior after abrupt JVM exit

Both exact official Memory Saver 0.4.6 artifacts reproduce retained snapshot
files after abrupt JVM termination. Each target ran five fresh owned JVMs:
normal completion, abrupt halt, normal restart, a second abrupt halt, and a
second normal restart. The two halts occur only after an independent parent has
observed real nonzero UTF-16 snapshot bytes and verified the child PID and the
reader/admission code sources against the exact packaged JAR.

Each halt exits with code 74 and skips the caller's finally block and the
registered shutdown hook. Each leaves one snapshot with exactly the observed
pre-halt length and hash. Later reads succeed and remove their own snapshot,
but leave earlier residues unchanged. A preexisting other-owner sentinel also
remains unchanged. All files are retained inside each audit's dedicated
`owned-tmp` directory; no shared temporary directory is scanned or cleaned.
This is a demonstrated crash-cleanup limitation, not a surviving JVM admission
counter leak. The audit's `passed:true` means these observations and controls
match; `product_cleanup_after_halt:false` remains explicit.

The JDK-only candidate-design control successfully creates one read/write
`FileChannel` with `CREATE_NEW` and `DELETE_ON_CLOSE`, writes and rewinds 70,000
bytes, and restores the exact text through the same channel. An independent
shared-delete reader verifies the exact UTF-16 bytes before the child halts with
code 75. The shutdown hook does not run and the snapshot path disappears when
Windows closes the child's handle. This establishes feasibility on this actual
Windows/JDK, not acceptance of a changed product.

The initial control used an ordinary Python reader and received access denied:
readers of a file opened for delete-on-close must allow delete sharing. That
failed attempt and its actual owned-child cleanup are preserved separately.
The successful new control uses the already tested shared-delete reader.

Real filesystem disk-full behavior remains untested. Read-only inspection found
VHD commands installed but the process is not elevated. Filling any existing
volume or changing user quotas is inappropriate. A future actual Windows test
should use a deliberately prepared, size-capped disposable virtual volume,
with verified image/disk identity and free-space bounds before filling it. No
VHD, partition, quota, system setting or existing filesystem was changed here.

See [the proposed product change](proposal.md). Product source remains untouched.
Per-target `execution.json` records all commands, exact inputs, class hashes,
processes, exits and file inventories. The retained receipts distinguish every
failed and successful attempt; `sha256.json` indexes this evidence.
