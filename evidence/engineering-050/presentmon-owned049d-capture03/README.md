# Owned 049d PresentMon availability probe 03

One authorized official PresentMon 2.6.0 capture requested 25 seconds for exact Java PID 45784, creation 2026-11-17T03:15:53.5383010Z, after the first independently verified reload. **Data-source availability remains false: no CSV was created.** No calibration or performance acceptance is granted.

The owned helper PID 69616 started at 2026-11-17T10:27:36.204992Z and exited at 10:28:02.011032Z. Its actual Popen wait returned 0 without timeout. `capture-exit.json` was saved before optional post-exit metadata; `capture.execution.json` retains owned-handle process times. Target identity is identical before and after. The helper printed Started/Stopped recording; stderr contains the generic non-elevated-process warning. These facts do not identify the reason for the absent CSV.

The unique session was observed running. A query at 10:27:44.073489Z reported zero EventsLost, LogBuffersLost and RealTimeBuffersLost, with BuffersWritten 70. These are query-point session counters, not target-present counts or a full-window no-loss guarantee. The exact session query after exit returned 4201 (not found); no timeout cleanup was executed. Global listing receipts retain their actual results and do not certify that every other session was unchanged.

There is no empirical CSV header, row count, PID/QPC range, missing-value audit or verified nonzero target data row. The original command did not request v1/v2 metrics; no assumed legacy schema or synthetic zero rows are substituted. External present timings cannot replace native render-loop, process CPU, GC, heap or OS memory metrics. Previous failures remain unchanged, including the missing exit code from the earlier upstream attempt.

`relocation-receipt.json` maps all 46 original capture files from the former nested `presentmon-feasibility/owned049d-capture-03` directory to this sibling directory. Before moving, both exact absolute paths and repository containment were checked, the target was absent, and existing ancestors plus the source tree had no reparse points. A single PowerShell `Move-Item -LiteralPath` moved the directory; every original file retained its byte count and SHA256. Embedded original absolute paths and argv are intentionally preserved. No raw payload was rewritten.

`historical-payload-verification.json` independently verifies all 147 index-defined historical payloads (5,831,275 bytes), the old index byte-for-byte against HEAD, and removal of the new capture subdirectory from that namespace. Three preexisting unindexed Python bytecode files remain untouched in the old physical directory. Their origin is not attributed to this probe; the entire physical directory is not claimed to be fully indexed.

`assessment.json` records the observed result. `sha256-index.json` binds every file in this directory except itself. The prior signed-binary help and release-download evidence remain in the unchanged sibling historical seal.
