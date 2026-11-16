# Probe snapshot publication repair — observer 1.0.3

The Windows 10 publisher renames the completed temporary file once through
`FileRenameInfoEx` with `REPLACE_IF_EXISTS | POSIX_SEMANTICS`. It owns and closes
the source DELETE handle, preserves a prior failure if close also fails, and
exposes actual API errors. Readers must grant read/write/delete sharing. Failed
snapshot reads are not retried. The helper is excluded from the product JAR.

The actual client failure and old sources remain in `failed-runtime/`,
`old-sources/` and `before.json`. The original independent Windows fixture's
1,500 ReplaceFileW publications exposed missing-path/sharing attempts; its exact
per-reader counters remain in `independent-win32/`. Its initial POSIX feasibility
run retained 1,500 publications and 49,906 successful requests without failures.
`reproduce_publication.py` provides the raw API reproducer without game/JVM access.

The fresh `sealed-01/` build receipts preserve actual argv, PID, JDK hash, UTC
start/end, exit code, stdout/stderr, JUnit XML and JFR per official target. Both
targets pass 27 tests, including seven actual publication cases: first/replacement
publication, an old delete-sharing handle, denied source/destination handles,
Unicode, concurrent opens and a missing-parent error. Each runs 1,000 Java
publications against four native readers: NF248 records 768,317 complete reads
and NF265 1,293,774, both without failures. The fresh separate Python fixture
records 1,500 publications and 79,954 complete requests without failures. These
are engineering checks, not performance benchmarks.

`nf248-first-failed/` preserves the incorrect initial test assumption that POSIX
replacement bypasses a reader withholding delete sharing. Actual error 32
correctly rejects publication. The final test requires that failure and unchanged
destination, then separately succeeds after the restrictive reader closes. The
implementation was not relaxed. Earlier NF248 build logs lack complete structured
receipts; the fresh builds supply actual receipts instead of reconstructing them.

`sealed-01/artifact-review.json` compares both exact 1.0.2 references with 1.0.3.
Of 28 classes, 25 remain byte-identical. `AtomicSnapshot` and `WindowsApi` contain
the API repair; `Windows` differs only at two source-line bytes, with identical
member/instruction disassembly. Original/candidate javap dumps remain. Three
metadata files change the observer version. Both targets' 25 declared inputs
match frozen copies. Six captured old sources and 113 recorded product inputs/JARs
remain unchanged. The first seal assessor's too-narrow two-class expectation and
actual failure remain separate from the final three-class comparison.

The fresh 1.0.3 client's application, reloads, gameplay, endurance and controlled
performance remain separate acceptance work. This batch starts no Minecraft
client and changes neither product JAR.
