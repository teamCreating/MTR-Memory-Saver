# Reload waiter fail-fast repair

`tools/wait_reload_ready.py` is a separate read-only progress helper. The original 90e waiter and 810 evaluator remain byte-identical (`legacy-preservation.json`), as do all failed-run inputs. No game, live reader, input ledger, release Java or producer source was changed by this batch.

The old waiter could keep waiting for an eligible recorder publication after a real RETURN even though an OOM made that publication ineligible. The new helper first verifies a closed post-RETURN published **or ineligible** capture, reconstructs its original logical native log from hash-pinned segments and runs the frozen producer's diagnostic attribution/review. Unreviewed native errors or failed attribution terminate with `diagnostics_failed` before the eligible-publication gate. It never treats an ineligible capture as successful reload evidence.

Only after that diagnostic gate does it reuse frozen producer input-ledger and full reload evaluation. Ready requires an existing verified consumer baseline strictly before the first input, every retained reload verified with the exact count and consecutive run, current process identity and source pins, a fresh eligible post-RETURN publication, latest verified sample, pending/in-flight zero, settled native state, and both measured trailing consumer and native spans at least 60 seconds. A broken sample cadence resets the trailing run; no interval is credited. It checks the deadline again after assessment before granting ready. Its acquired process handle is closed even if native API or initial clock setup throws.

All locations are explicit; a fresh output must stay outside recorder, consumer and game-instance directories:

```powershell
.\.venv\Scripts\python.exe -u -X utf8 tools/wait_reload_ready.py `
  --recorder <actual-recorder-directory> `
  --consumer <actual-consumer-directory> `
  --output <fresh-independent-directory> `
  --expected-sequence <completed-native-sequence>
```

Defaults are deadline 420 seconds, consumer cadence 5 seconds, native freshness 15 seconds, and both stable spans 60 seconds. Heartbeats occur about every 35 seconds while waiting. Deadline is bounded to 420 seconds; freshness cannot exceed the recorder's frozen criterion; stable duration cannot be shortened below 60 seconds. Exit 0 means interim ready, 1 means deadline, 2 means a runtime/evidence/diagnostic failure; invalid preflight arguments also exit nonzero. `result.json`, raw stdout/stderr, execution metadata and the helper source are retained in the fresh output. This helper never replaces a normally finalized consumer summary or sealed acceptance.

## Actual offline validation

- `test-run-01`: 9 tests, actual exit 1; six fixture errors occurred because a historical journal prefix included later records deliberately absent from the old minimal seal. The test fixture now retains the journal exactly through its selected historical record. Original source, stderr and exit remain preserved.
- `test-run-02`: 12 tests, actual exit 0 after that fixture correction and additional controls.
- `test-run-03`: 15 tests, actual exit 0 after deadline, process-handle ownership and output-directory controls.
- `test-run-04`: final 16 tests, actual exit 0 on Windows 10 / project Python 3.14, **zero skips**. Source bytes before and after execution match. This includes real OOM/ineligible precedence, historical three-input success, before-first-input baseline, 59.999-second negative control, source/raw corruption, stale/ineligible state, pending RETURN, partial append versus malformed complete input, cadence, deadline crossing during assessment and API/clock failure handle closure.

The live helper relies on the qualified Windows process identity API. Three full historical input-ledger controls are explicitly Windows-only because the immutable Windows producer itself uses host `Path` semantics for captured absolute Windows source keys. On non-Windows CI those three controls are skipped, rather than altering the original producer or ledger to claim a cross-platform replay. The real OOM fail-fast control and the other source/raw/deadline controls remain enabled there. Manifest basename parsing in the **new** helper accepts both recorded Windows and POSIX separators. No Linux execution is claimed by these local receipts.

`real-oom-replay-final.json` performs one additional offline inspection using final source SHA `2ce1525514d71f0c18c4de274832491d7635cf86f46fb13f62816cba09aa66f1`, frozen recorder source, original sealed record 2482 and its owned raw/log prefix. It returns `diagnostics_failed` for the actual epoch-5 RETURN and unreviewed lines 365/366/395/396, with no eligible publication or ready grant. The earlier replay with the prior tool source is retained separately. These reads do not query the live JVM or create a reader. The earlier 049d run remains overall unaccepted; its historical three verified prefixes apply only to their own ranges.

`invocation-note.json` records one earlier wrong-working-directory launcher error as agent-reported tool history, not a fabricated raw receipt. The numbered test runs contain actual subprocess receipts. `sha256-index.json` covers this directory's payloads. A separate verification directory records catalog registration and independent payload/source byte checks; archived Python is reference-only and is not executed by the catalog.
