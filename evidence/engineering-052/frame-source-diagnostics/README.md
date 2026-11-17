# Frame diagnostic failures and cleanup

These are diagnostic outcomes, not performance acceptance. The two actual
Windows logman attempts retained their actual command/exit and raw streams.
Attempt 01 rejected the `-ets`/`-rf` combination. Attempt 02 returned access
denied after creating its unique session. The separately saved cleanup checked
its recorded GUID/handle, stopped only that session and confirmed status 4201.
No privileges, permissions or unrelated sessions were changed.

Offline PresentMon 2.6.0 returned zero without a CSV. This cannot establish
frame availability or identify the exact denied provider. Raw ETL stays in the
ignored cache; its original inventory records its bytes. No ETL is copied here.
The original inventories also describe their original scope, not this selected
copy. The outer SHA256.json binds the selected files.

Twenty current controls passed: offline frame contracts, synthetic ETW behavior,
independent ETL-replay tamper rejection, actual ordinary-child wait receipts,
and partial-start cleanup. Synthetic records are not Windows ETW evidence.
Current post-fix sources are reference snapshots. Original intents retain the
source hashes observed at each diagnostic; these copies are not asserted to be
pre-frozen capture sources.

A qualified independent frame source, known positive rendering control,
observer-off calibration and actual A/A and A/B trials remain outstanding.
