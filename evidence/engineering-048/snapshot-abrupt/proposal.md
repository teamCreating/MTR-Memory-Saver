# Proposed owned-channel snapshot lifetime

The confirmed limitation warrants a focused crash-cleanup improvement. Do not
add a shared-temp sweep or imply that old 0.4.6 residues were automatically
recovered. This proposal has not modified product code.

1. Create and open each randomized snapshot in one filesystem operation using
   `FileChannel.open(CREATE_NEW, READ, WRITE, DELETE_ON_CLOSE)`. Avoid
   `createTempFile` followed by reopening: abrupt termination between those two
   operations can retain a file before delete-on-close ownership is established.
   Resolve only the configured/test-owned temporary directory. A filename
   collision may generate another name; unrelated I/O failures must propagate.
2. Keep this single channel owned by `Snapshot` throughout write, finish,
   workspace waiting, rewind, restoration and close. The length limit, shared
   text-budget accounting and caller InputStream ownership remain unchanged.
   Release the small reservation before awaiting the complete restoration
   reservation as today.
3. Finish flushes all buffered UTF-16 bytes without closing the owner channel.
   Rewind the same channel to position zero and restore through it; do not
   reopen the path. Use either direct channel reads/writes or explicitly
   non-owning views. Handle partial writes correctly and retain cancellation,
   exact decoded-length checks and independent Unicode oracles.
4. `Snapshot.close` closes its one owner channel on success and on every caught
   exception. Windows then deletes the file when its last compatible handle
   closes, including abrupt process death. Preserve original failures and
   suppressed close failures; do not translate a real failure into successful
   empty text or claim cleanup merely because a path cannot be read.
5. Keep existing pre-0.4.7 residues untouched. Snapshot names do not prove that
   another process is dead or that this process owns its files. Other holders
   granting delete sharing may legitimately defer removal until their handles
   close; this is distinct from an abandoned file with no owner.

Validation must cover both official packaged targets after the candidate
version changes. The current fault filesystem injects `newOutputStream`,
`newInputStream` and `delete` failures; adapt it to forward and fault actual
channel write/read/close operations rather than retaining tests that no longer
exercise the implementation. Preserve write failure, restoration failure,
cleanup failure, same-key retry and suppression coverage. The old Windows
delete-lock audit also needs a changed expectation: a reader denying delete
sharing should be unable to open a delete-on-close snapshot in the first place.

Required concrete checks include creation failure without abandoned files,
short/failed writes, final flush/read/close failures, exact UTF-16 boundary and
supplementary-character restoration, normal cleanup, concurrent large reads,
waiting-generation retirement and caller stream ownership. Rerun the exact
large OBJ audit at 3 GiB with both CompactStrings modes. Reuse the abrupt child
protocol but expect no new residue and preserve another-owner sentinel; include
termination during writing and while waiting for the full workspace claim.
Then rebuild and rerun packaged resource/lifecycle fault checks and fresh game
startup/reload checks against the new artifact. The JDK-only control in this
directory cannot substitute for those actual product tests.
