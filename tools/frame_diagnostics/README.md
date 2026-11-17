# Frame source diagnostics

This package diagnoses one explicitly selected process. It does not qualify a
performance measurement, launch a game, elevate privileges, change permissions,
or run a capture on import. The target JSON must contain the actual Windows
handle query's PID, creation time, executable and command line.

`python -m tools.frame_diagnostics plan --help` describes the explicit inputs.
`capture` creates a unique, previously absent ETW session for 20–30 seconds,
with a 128 MiB raw-file cap. The wrapper stops only its session after checking
the GUID and trace handle. Windows 10 rejects scheduled `-rf` with direct
`-ets`, so this uses wrapper cleanup rather than claiming an independent timed
session expiry. A wrapper crash requires checking the saved session identity.
Partial start failures also require cleanup: logman can create a session before
a provider enable returns access denied.

Raw telemetry stays under the ignored `.cache`. Execution records preserve the
actual wait result before post-exit hashes; helper exit zero without a CSV is
not a frame measurement. Offline inspection checks raw bytes, process identity,
sampling boundaries, QPC semantics and provider headers. `inspect --replay-output`
redecodes the original ETL with the pinned decoders and compares derivations.
Without this independent replay, saved CSV data cannot establish availability.
Synthetic tests establish validation behavior, not Windows provider availability.

The pinned modern-provider subset is **not qualified for measurement**. Native
render-loop JFR durations, present intervals and OS CPU counters retain separate
meanings. A known positive rendering control, full-window loss checks and
observer-off calibration remain required before performance claims.

On 2026-11-18 +08:00, the first real diagnostic rejected `-ets`/`-rf` without
creating a session. After correcting that incompatibility, logman returned
access denied after partially creating the unique session. Its recorded GUID
and handle were checked and the session was stopped; a subsequent query returned
4201 (absent). Offline PresentMon exited zero and produced no CSV. The exact
denied provider and the earlier PresentMon failures' causes remain unclassified.

References: [Microsoft logman trace options](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/logman-create-trace),
[PresentMon v2.6.0 trace implementation](https://github.com/GameTechDev/PresentMon/blob/v2.6.0/PresentData/PresentMonTraceSession.cpp).
