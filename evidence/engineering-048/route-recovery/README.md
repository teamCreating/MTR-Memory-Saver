# Official route failure and snapshot publication repair

The third two-hour route attempt **failed after 2710 seconds**. The first
40-minute sampled-state window passed; neither the complete route nor its full
JFR was accepted. [Assessment](assessment.json) independently replays the same
frozen route-window algorithm and binds the Windows crash to the observed JVM.

Windows Application Error event 66377 identifies the exact Java PID 34668,
creation FILETIME, executable and exception `0x675` / `1653`. The faulting module
is `textinputframework.dll`; Windows Error Reporting corroborates the crash.
This identifies the native crash location, not its trigger or whether a product
defect contributed. No source game process, world, setting or system component
was changed by this recovery.

All thirteen residual JFR chunks are preserved byte-for-byte. The JDK reads
twelve complete chunks through 07:20:11 UTC+08:00, about 32 minutes 36 seconds
inside this route window. The final chunk remains in locked-stream state and
was not edited. Exact raw files, per-chunk JDK output and the reproducible
readable-prefix assembly are recorded in [capture.json](capture.json).

An independent observation defect is repaired. Windows `MoveFileExW` replacement
fails against an open target even when the reader allows delete sharing. The
initial proposed reader-only fix failed its real filesystem test; the original
failure is retained. Shared-delete readers plus `ReplaceFileW` publication pass,
and a reader held across replacement still returns the old complete payload.
The native sharing probe also preserves failing overwrite and successful
rename-away/delete controls. Native access failures remain visible.

Both optional probes now use the shared `AtomicSnapshot` publisher; the native
observer is version 1.0.1. The companion product is unchanged. Both official
targets pass 18 Java tests, including four actual publisher cases. Four Python
Windows sharing tests and 61 observation tests pass. Each target's exact JAR,
manifest, JUnit XML and source inputs are retained. Fresh actual game validation
of these new probe bytes remains a separate step.

The first NF248 build command named a nonexistent manifest task and failed
before building. Its log is retained alongside the successful corrected
`verifyNeutralProbe probeJar` executions. Earlier/final Python logs also remain
separate. [sha256.json](sha256.json) indexes the evidence; generated JUnit binary
runtime directories are not part of that index or this record.
