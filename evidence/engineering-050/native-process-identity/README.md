# Same-handle native Windows process identity

The observer no longer starts `pwsh` or queries CIM to identify a process. It
opens the same query/read handle as before and reads actual PID, creation time,
executable path and command line through that handle. The existing independent
launch comparison still requires the exact argument vector. No observed field
is filled from the launch plan, and there is no CIM/launch-data fallback.

The query is qualified only on **Windows 10.0.19045, native AMD64 Python and
target processes**. `RtlGetVersion` and both `IsWow64Process2` observations enforce
that boundary. Unknown OS/build/architecture, a missing export, access failure,
non-success NTSTATUS or invalid data rejects identity. No token, ACL, privilege,
game process or Windows setting is modified.

## Choice and lifetime

Class 60 returns an inline `UNICODE_STRING` and its UTF-16 bytes in one kernel
query. This avoids class 0 plus PEB/RTL_USER_PROCESS_PARAMETERS pointer chasing,
multiple ReadProcessMemory snapshots and additional remote-layout assumptions.
Neither route is treated as a portable, stable command-line ABI. Class 60 is
chosen because the exact local OS/bitness and complete argv are actually tested;
other targets require separate qualification.

`QueryFullProcessImageNameW` obtains the image name. `GetProcessId` and
`GetProcessTimes` anchor identity to the handle, with liveness/creation checks
before and after capture. A nonzero recorded exit time also rejects actual exit
code 259, which otherwise shares the STILL_ACTIVE value. The observer retains
that exit-time check during subsequent samples.

Command size discovery has bounded, progressing buffer growth, not error
retries. The parser validates header/returned size, even UTF-16 lengths, maximum
length, alignment and complete inline pointer bounds before dereferencing. Empty
or embedded-null command lines cannot qualify. Unicode code units are preserved;
the existing Windows argument parser and exact launch comparison are retained.
Initialization failures close the owned handle, including unavailable APIs,
native errors and identity/argv mismatches.

## Evidence and controls

- `feasibility-01` preserves the first owned-child rejection before any native
  identity query: the virtual-environment Python redirector's Popen PID differs
  from the physical interpreter PID printed by the child. The original script,
  report and actual child-ready bytes remain. It awards no native-query pass.
- `feasibility-02` uses the direct base interpreter binary, matching the direct
  executable launch under test. It verifies complete Unicode/emoji, empty,
  quoted, spaced, trailing-backslash and 20,000-character arguments. Wrong PID,
  creation time, executable and argv are rejected. A real exit between size/data
  queries yields NTSTATUS `0xc000010a` and is rejected. No descendant/PID-search
  workaround is used.
- `native-tests-01` preserves a command-selection failure: all 11 native tests
  pass, but two requested integration class names do not exist. The raw errors
  and source snapshots remain; this invocation is not called successful.
- `native-tests-final-02` runs the corrected selectors and passes all **16 tests,
  zero skips**, with actual command/launcher PID/UTC/exit receipts and immutable
  input copies. Actual child source, child-reported argv, full native identity,
  memory sample and exit rejection are retained under `owned-child/`. The real
  successful identity test disallows subprocess.run, so a shell/CIM call cannot
  silently supply the result.

Controls include Win32 failures and missing exports, wrong identity/argv,
changed creation or exit during capture, unsupported OS and cross-bitness,
long/growing/non-progressing/oversized buffers, NTSTATUS errors, truncated/odd/
null/unaligned/out-of-bounds Unicode, image buffer growth and all constructor
failure cleanup. The observer freezes/copies the new helper and rejects later
hash drift; neutral source records, recorder source_files and experiment SOURCES
all include it. Integration controls preserve those source-change gates.

`native-tests-byte-preserved-03` repeats the same 16 controls after preserving
all unchanged original test-file line endings; all 16 pass with zero skips.
Runtime sources are identical to the already reviewed/tested hashes.

Independent read-only review found no remaining blocker in the final helper,
same-handle lifetime, exit-time check, buffer checks or fingerprint coverage.
`windows_snapshot_io.py` remains byte-identical. Product JARs, game state, original
evidence and the stop protocol are unchanged. These records establish tool
engineering; actual reload/endurance/performance acceptance is separate.

References: [QueryFullProcessImageNameW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-queryfullprocessimagenamew),
[NtQueryInformationProcess](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntqueryinformationprocess).
