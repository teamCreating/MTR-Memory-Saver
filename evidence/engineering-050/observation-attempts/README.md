# Incomplete official 0.4.7 observation attempts

Captured on 2026-11-16 (UTC+08:00), retaining earlier attempts from that day. The
three terminal tool attempts refer to official NeoForge 21.1.248, Memory Saver
0.4.7, neutral observer 1.0.3 and launched game PID 18796. They award **no completed
startup, reload, gameplay, endurance, performance or process-exit acceptance**.

- `capture-01/attempts/startup/` preserves 201 complete original sample lines and
  the exact consumer/helper/configuration sources. There is no `summary.json`.
  The parent reports interrupting tool session 3751 with Ctrl-C, followed by a
  final empty poll returning exit code 1. That information is explicitly labeled
  **parent-reported tool history** in `parent-reported-tool-results.json`, not an
  original persisted receipt or independent proof of the exit cause/time.
- `capture-01/attempts/reload-recorder/` preserves the complete initialization
  journal and its source copies. Its final hash-chained event is
  `initialization_failed`, recording the actual 20-second CIM subprocess timeout.
  No ready session, sealed before publication or input attempt exists here.
- `capture-01/attempts/reload-observation/` preserves the actual
  `preflight_failed` / `passed=false` summary and empty sample file. It records
  the same 20-second process-identity query timeout. The parent-reported tool exit
  code is kept separately from these on-disk observations.

`capture-01/instance/` freezes the actual plan/launch and copied installed
companion/observer JARs. All three installed mod hashes match the frozen plan;
the large official MTR JAR is fingerprinted without another binary copy. The
observer's embedded metadata is exactly version 1.0.3, and the frozen product
manifest is version 0.4.7. Pack identity declarations remain in the plan; this
checkpoint does not recopy or rehash the sixteen packs.

`capture-01/collector-checkpoint/` is a prefix of the still-running runtime
collector: status `observing`, 503 complete retained snapshot records, and no
ended/exit-code field. Its three declared source hashes match copied source
bytes. `instance-checkpoint/` separately retains a later shared-handle native
snapshot, append-only callback/log prefixes and exact per-file read boundaries.
The later snapshot has PID 18796 and zero observation errors. These later reads
do not complete or repair any earlier attempt. They are not a simultaneous
transaction across all files.

Fresh `startup-attempt02` and `reload-recorder-attempt02` directories are excluded.
The capture does not send game input, change source/runtime settings, start a
client, request JFR export, or stop the game/collector. `assessment.json` records
read start/completion, exact bytes/hashes and source size frontiers. Terminal
attempt source bytes are checked again after the capture and remain unchanged.

The SHA inventory covers every payload here except the index itself. Independent
verification results belong in the sibling `observation-attempts-verification/`
directory so they cannot become self-referential indexed outputs.
