# Explicit observer stop requests

The observer now checks its own `output/stop-request`. File presence requests a
stop; contents have no language or JSON-format requirement. Exact bytes are
preserved in an exclusively created `stop-request-captured.bin`. An exclusively
created receipt records the SHA-256, byte count and independent UTC/monotonic
observation time. The summary additionally hashes that receipt. The request is
retained; an existing capture/receipt is never overwritten.

Requests are checked before sampling, after sample accounting, and before
declaring startup/reload success. Waiting polls the control path every 0.25 s
against the original absolute sampling deadline. It creates no game observations
or catch-up samples. Only FileNotFoundError means no request; other control I/O
errors propagate. A request received during a blocking call is handled when that
call returns; polling is not a wall-clock response guarantee. Existing bounded
auxiliary cleanup still runs before the summary is written.

An observed request sets `status=stopped`, `passed=false`, and exit code 1. Normal
finally cleanup closes the process handle and drains/closes the auxiliary worker.
The actual sampling end and monotonic elapsed time are retained. Existing errors,
source-freeze checks, route/reload evidence and missing-cleanup gates remain.
No requested duration is substituted for the actual window. This controls only
the observer, never game input or JVM lifetime.

The root task explicitly confirmed the two incomplete old observer attempts as
unaccepted before edits. Already completed startup evidence keeps its original
frozen source and result. A running Python process does not acquire this protocol
merely because the file on disk changes; a new observer attempt must load it.

## Recorded validation

Every execution directory retains the actual child argv/PID, UTC start/end,
exit code, raw stdout/stderr and exact input copies/hashes.

- `targeted-01`: seven initial deterministic controls pass.
- `regression-01`: the intermediate source runs 103 existing/new controls; 97
  pass and six existing short real-time auxiliary tests fail. Original failures,
  source and receipts remain unchanged. This is not a full-suite pass.
- `targeted-final-02`: all ten final deterministic controls pass, including
  read/stat errors, actual receipt-write failure with raw/bin preservation and
  cleanup, and a request arriving inside reload evaluation before success.
- `head-realtime-control-01`: one control of the six failing tests against the
  frozen original HEAD observer/test passes all six with their original windows.
- `final-realtime-pair-01`: one paired run against the final source passes the
  same six unchanged real-time controls. These later runs cannot precisely
  attribute the initial failures to system load; they do not rewrite that result.

An independent read-only review confirmed error propagation, success-boundary
ordering, cleanup and preserved failure/source gates in the final source.
No source, production threshold or test timing window was changed to force the
real-time cases to pass. No additional repeat-to-green loop was performed.

Final observer SHA-256:
`2da073a006bbfcf7f15ccb3d9d2686d8db3430bf495b962c7667125de456810e`.
This batch supplies tool-engineering controls only and starts no Minecraft client.
