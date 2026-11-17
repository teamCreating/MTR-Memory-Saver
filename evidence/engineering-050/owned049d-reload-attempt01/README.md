# Owned049d first reload: unobserved, stopped, unaccepted

This is a minimal, byte-exact closure of the terminated first reload observation of PID **45784**, created 2026-11-17 03:15:53.538301 UTC. It preserves the failed attempt, not a mod-crash diagnosis or a successful reload. The original cache evidence and runtime sources were not modified. No observer, native-log reader, game input or UI capture was started for this seal.

## Actual boundary

The input API reported F3+t success from **03:19:56.912Z to 03:19:58.130Z**. Its original receipt was selected by recorder confirmation, using record `00000044`: the native before snapshot was 0.901768 seconds old and the publication receipt had closed 0.055952 seconds before input. Original UI receipt bytes match the submitted receipt; the input ledger, its selected before payload/receipt and raw hashes are preserved.

The consumer observed **03:19:31.536436Z–03:27:08.611972Z**, 457.074028 seconds, **92/92 verified samples**. Every OS process sample reports running. Native game time advances from 1770511 to 1779598 and every sample retains completed epoch 1. The complete final log remains **27,396 bytes**, SHA-256 `1c8a412683ecb7f7833401e442ca8be138e647615ab4e8c470140c9a5f490d15`, byte-identical to the input-before log. It contains only the startup ResourceManager reload/registration and the native journal contains only epoch 1 HEAD/RETURN. No epoch 2 or new ResourceManager bytes appear before stop.

The preserved summary has `status="stopped"`, `passed=false`, `error=null`, zero verified reloads and longest run zero. Its retained reload fails with:

- `Reload event offset is outside new, distinct log evidence.`
- `The input has no verified full resource/registration log completion.`
- `Input did not cause the immediately following unique native epoch.`

The sole summary failure category is `retained_neutral_reload_attempt_unverified`. Native diagnostic attribution passes, with no unreviewed native diagnostic, and no consumer/native-log source drift or completion-read error was recorded. These facts do not establish why the injected input had no observed effect. In particular, API success or a selected confirmation is not proof that Minecraft handled the key chord.

Both readers received explicit stop requests. The consumer's 228 original stop bytes equal its captured bytes; SHA-256 and stop-receipt fingerprint match the summary. Recorder's separate request has its own request timestamp. Its full 895-row hash journal contains 446 captures and 446 published records, no ineligible/capture-failed entry, and a final `stopped` event with `reason="stop_request"`. Its session-end reports `status="stopped"`, the matching journal SHA and `process_handle_closed=true`. This is orderly reader closure; it does not stop or certify final exit of the game JVM.

Root reported actual tool-terminal results consumer session **85049 exit 1** and recorder session **86808 exit 0**, plus two WGC capture timeouts. No original tool receipt was supplied in the selected on-disk inputs. `parent-reported-results.json` labels that provenance explicitly; it is not a reconstructed raw receipt. Consumer exit 1 is consistent with its unaccepted stopped summary, not evidence of a mod crash. The small UI directory preserves the controller, five original API receipts and four before snapshots; receipt success does not grant screenshot or key-delivery effects.

## Minimal closure and export checkpoint

`capture-01/read-receipts.json` records each source path, original byte SHA/length/file identity/mtime, and actual UTC copy interval. Sources were required to retain identity/size/mtime during the copy. The closure includes:

- Consumer complete samples/summary, stop originals/receipt, final log/epoch/diagnostic/input exports and exact frozen consumer dependencies.
- Recorder context/plan/launch, full journal, input ledger, its sole input-attempt directory, **only record 00000044** and the four unique raw blobs it references. The other 445 record payloads are deliberately not copied. Their journal entries remain original; their individual payloads are outside this minimal export's verification scope.
- Original native-log context/anchor/configuration/plan/launch and referenced blobs for **recorder capture 44** and **consumer completion capture 93**. No redundant intermediate native-log capture receipts are required for this failure boundary.
- Pinned original diagnostic proof files, small UI source/receipts, and a read-timed collector execution/export checkpoint.

The collector checkpoint records successful `JFR.dump` and `jfr summary` commands, both exit 0, for `diagnostic-01.jfr`; its original summary reports three chunks, start 03:15:54 UTC and duration 1279 seconds. Original dump/summary stdout and stderr plus the export request are preserved. The exporter manifest and root's supplied fingerprint both give SHA-256 **`dbbc078206c95ed4f52edde51b6d193fcf347fe525bac0263c6ee88e3bf9c936`**. **The JFR binary is not copied into Git or independently rehashed/replayed by this verifier.** This is a manifest-bound readable-export fact, not a portable JFR archive, per-event coverage proof or a performance result.

Collector `execution.json` is explicitly a checkpoint at its recorded copy time. Its `status="observing"` is not treated as a current liveness or complete-exit fact. The still-growing `native-snapshots.jsonl` was not read or copied. No later prepared049e state, route session, graphics behavior, twenty-reload pass or game exit is attributed to this attempt.

## Independent replay

`sha256-index.json` covers this directory's payloads except itself and bytecode caches. `verify_sealed.py` imports the preserved recorder/consumer/helper copies, verifies the complete journal and selected input closure, reconstructs the final log, and replays the failed reload and diagnostic classification exactly against the saved summary. It also checks the stop receipts and the exporter-manifest/stdout consistency. It does not read current runtime sources, current logs, the game process or the omitted JFR binary.

Use a fresh output filename from the repository root:

```powershell
.\.venv\Scripts\python.exe -X utf8 evidence/engineering-050/owned049d-reload-attempt01/verify_sealed.py .cache/owned049d-failed-reload-recheck.json
```

The actual independent subprocess receipt/result is stored outside this seal in `../owned049d-reload-attempt01-verification`. Passing that integrity/replay check means the failure boundary was preserved; it does not pass the failed reload itself.
