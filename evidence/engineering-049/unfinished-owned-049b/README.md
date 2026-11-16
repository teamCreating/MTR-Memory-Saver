# Unfinished diagnostic run 049b

This is a **retrospective unfinished-run observation**, not an exit receipt or a
record of a stopping action. The original diagnostic client was PID 63044,
Minecraft 1.21.1 / official MTR 4.1.0-beta.2 / NeoForge 21.1.248, with Memory Saver
0.4.7 and neutral observer 1.0.3 at a 3072 MiB maximum heap. Its original launch,
plan and collector receipt are retained byte-for-byte.

The collector's last retained capture is
`2026-11-16T22:23:18.16857+08:00`; the native snapshot itself was observed at
`2026-11-16T14:23:17.566868600Z`. The original `execution.json` still says
`status=observing`, with no terminal time or exit code and no JFR export. Its
empty `capture_errors` list is an unfinished receipt, not certification of an
error-free complete run. `acceptance.jfr` is an empty file, whose exact hash and
zero-byte size are preserved.

The fresh, read-only CIM query records the target PID and corresponding Python
collector absent at its actual observation time. It retains the exact command,
helper PID, execution boundaries, exit status and raw stdout/stderr. That absence
does not reveal why or exactly when either process ended. Accordingly:

- `exit_code=null`, `exit_time=null`, `termination_cause=unknown`;
- `normal_exit_verified=false`, `interruption_action_observed=false`;
- no final game shutdown, readable JFR, consecutive reload, endurance, gameplay
  or performance pass follows from this archive.

`sealed-01/` preserves all original collector files, the complete retained native
snapshot JSONL, logs and native streams, both plan/launch copies, final published
snapshot, settings/profile context, empty JFR, GC log, and installed companion and
observer JARs. Their hashes match the original plan and their separately pinned
build manifests. All 44 companion and 25 observer manifest inputs, plus the three
recorded collector sources, resolve to exact bytes and are copied with explicit
source resolutions. Original files are checked before and after each copy.

The final published snapshot is paused at `PauseScreen`, with 1,092 declarations,
1,091 distinct IDs, settled native work, one completed startup epoch and zero
reported observation errors at that observation. It is an endpoint observation;
it does not prove behavior after the last retained sample or a completed reload.

No source world, resource archive, MTR JAR, JDK/runtime or library inventory was
freshly rehashed in this task. Their original plan declarations are retained
without promoting them to new verification. No game directory, process, world or
source file was changed by the archive helper. The separate 049c run was not read
or operated.

The archive's `SHA256SUMS.json` covers every sealed payload except itself. A
separate sealed-only verifier recomputes the entire payload set, plan/launch
binding, actual CIM result, snapshot identity/endpoint, both JAR manifests, all 69
build inputs and original collector source hashes. It cannot manufacture missing
exit evidence. Use a fresh output path to repeat that integrity check:

```powershell
.venv/Scripts/python.exe -X utf8 evidence/engineering-049/unfinished-owned-049b/verify_sealed.py `
    sealed-01 verification-02.json
```

`seal_unfinished.py` is the actual preservation source, not a reusable game
launcher. Re-executing it against changed original paths cannot recreate this
historical observation. Keep its original receipt, source snapshot and hashes.
