# Revised 0.4.8: native OBJ and MTL streams

The earlier 0.4.8 candidate failed the seventh full-pack reload. Its entire failed
run remains in [streamed051a-reload-oom](../streamed051a-reload-oom/README.md), with
zero final accepted reloads; the six successful historical prefixes are separate.

This revision is source commit `a63214910038ee11ed377cd7dfeb6158729eb1d7`.
The official NF248 product SHA is
`943b3d455fa3ce9d3ede74bc1a2071ece7bf70b09d9b7f829027347b53a9b588`;
NF265 is `134770acd53ec81325993604e8441d213d9ea1be990adb3bc2877b0cb7cc17dd`.
Both are unpublished 0.4.8 candidates. Original candidate files are preserved.

Native provider capability now admits OBJ descriptors before capture. The owned
snapshot supplies a bounded UTF-8 ReaderInputStream to the original OBJ/MTL
InputStream parsers. This deliberately retains OBJ US-ASCII decoding and MTL's
default-charset decoding after UTF-8 encoding, including replacement. Native mesh
construction, material parsing, path/texture resolution and flip behavior remain
the reference. Unknown providers retain their original factory; a declined
capability retains its String contract. OBJ path reuse does not alias different
material dependencies by an OBJ-only content digest. Snapshots close before
publication; retired running work holds its ticket until real exit.

Each official target passed 105 Java tests without failures or skips, release
verification, probe build/manifests and the Blockbench and OBJ 64 MiB allocation
controls. The OBJ control streams 40 MiB of generated comment lines through the
native parser, checks native output and digest, and observes cleanup. Explicit
fixture limits exceed the production policy for that small heap. The matching
full-String control actually exited 1 at String.join with Java heap OOM. It is an
expected negative result, not a successful product run. Native model allocations,
long parser lines and whole-client heap use are not bounded by this control.

The first targeted run preserved 45/46 passing controls. Its material reference
fixture omitted native path resolution; corrected native resolver comparison and
explicit material dependencies passed 6/6, followed by both complete 105-test runs.
The original failure source and XML remain. Runner copies are post-run references,
not pre-frozen terminal receipts; Java/build input pre/post fingerprints are saved.

Packaged JVMs 57308/NF248 and 62672/NF265 each passed 24 lifecycle, 18 strict
resource and 27 OBJ checks and exited 0. Checks include actual native mesh
publication, streaming OBJ/MTL, epoch reread, path hits, flip separation, source
close/read/size and malformed-OBJ failure/retry, unknown/declined contracts and
retirement ownership. Mismatched-binary JVMs 44564/NF248 and 67416/NF265 exited 1
at the fingerprint guard before resource registration. Collector wrapper exit and
owned JVM exit are distinct; execution.json records the actual JVM wait.

All four on-exit JFRs were independently summarized with actual exit 0 and hashed;
their command arguments, raw output and identity are retained. JFR, MTR, SDK world
and dependency binaries are not copied. Source archives include unselected v6
files as references; this does not constitute new v6 validation.

This evidence does not grant twenty-reload, performance or release acceptance.
The new full-pack run is separate. Release scope is the user's items 1/2/5/6;
interaction regression and the two-hour route are excluded from this release gate.

`verify.py` uses only files in this evidence directory. The SHA index protects
payload bytes; source/manifests, native probes and negative outcomes are rechecked.
