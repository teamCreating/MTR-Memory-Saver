# Historical official 0.4.7 startup seal completion

Completed on 2026-11-16 (UTC+08:00). This audit reads only the retained historical
`../full-load-startup/` payloads. It does not read or control a current instance.
The original 251 payloads remain byte-identical, including the failed assessments,
actual snapshot-reader sharing error, freeze receipts and exact historical source
bindings.

The existing independent `verify_sealed.py` executed twice, with actual commands,
start/end times, raw stdout/stderr and exit code 0 retained in `run-01/`:

- `core.execution.json` verifies the frozen prefix, native startup minute, process
  identity, exact build inputs, installed artifact bindings, diagnostic replay and
  selected image. Its new result is `../full-load-startup/verification-result.json`.
- The new `../full-load-startup/sha256-index.json` then covers all 252 payloads,
  including that result, and excludes only itself.
- `indexed.execution.json` independently invokes the same sealed-only verifier
  against the complete index. `run-01/verification-result-indexed.json` records
  successful verification of all 252 payloads. This output stays outside the
  indexed directory to avoid a self-referential hash.

The first result consequently reports no outer index: it was created before the
index existed. The second result supplies the explicit complete index check.
`run-01/original-inventory.json` and `assessment.json` retain the pre/post byte
preservation and final hashes. The source of each executed script is preserved.

Accepted scope remains historical PID 58468, official NeoForge 21.1.248,
Memory Saver 0.4.7 and neutral observer 1.0.2: 60 samples over 60.727157 seconds
of initial settled native startup and the photographed selected DC01 side body.
The collector's later sharing error remains visible and whole-run collection is
not error-free. No final-exit, full-run, reload, gameplay, endurance or performance
acceptance is added.
