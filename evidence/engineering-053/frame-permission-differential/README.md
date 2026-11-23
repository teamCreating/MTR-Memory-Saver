# Frame permission differential (2026-11-18 +08:00)

The normal-token per-provider test enabled five graphics providers; only
Kernel-Process returned access denied. All six unique owned sessions were
confirmed absent after identity-checked cleanup. This isolates the permission
failure; it does not prove completed frame availability.

The first owned WGL control (PID 56592) completed 24833 successful swap calls.
Its renderer reported Intel HD Graphics P530. The 25-second graphics-only raw
trace started/stopped successfully with zero reported session loss. Tracerpt
timed out after 45 seconds, leaving a partial XML, so that diagnostic did not
complete. Get-WinEvent target header counts separately found 3262 DxgKrnl
Present_Info and 3262 PresentHistoryDetailed_Start events. Header counts and
swap-call markers are not completed PresentMon frames.

Offline PresentMon returned zero without CSV for the original target filter,
without PID filtering, and without PID filtering plus explicit v1 metrics.
The second control (PID 69816) completed 25491 swap calls; the upstream native
25-second live capture also returned zero without any CSV. No driver or schema
cause is inferred from these failures. The WGC screenshot timed out; no pixels
were visually verified. Context and API success are technical observations.

Current replay code now explicitly requests v1 metrics to match its strict
TimeInQPC/MsBetweenPresents parser. Twenty related tests pass. Reference source
copies are post-fix snapshots, not pre-frozen capture sources. Original receipts
retain the actual commands used in earlier attempts.

The selected copy is not a full ETL replay closure. Raw ETL, partial XML, class
files and swap-marker streams remain in ignored cache with fingerprints listed
in raw-files-not-copied.json. No third-party binary is redistributed. Hashes
bind selected bytes, not measurement validity. Administrator differential was
requested separately and remains pending; this seal asserts no admin result.

Independent present qualification, observer-off calibration, A/A, A/B and
instrumentation overhead acceptance remain outstanding. No performance benefit,
release acceptance, tag or published release is asserted here.
