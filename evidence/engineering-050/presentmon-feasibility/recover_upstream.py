"""Read the failed wrapper's current helper/session/target state without another capture."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from datetime import datetime, timezone
import pilot
from native_etw import query_session

BASE = Path(__file__).resolve().parent
OUT = BASE / "upstream-recovery-01"
OUT.mkdir(exist_ok=False)
start = json.loads((BASE / "upstream-capture-02/capture-start.json").read_text(encoding="utf-8"))
intent = json.loads((BASE / "upstream-capture-02/capture-intent.json").read_text(encoding="utf-8"))
session = start["session_name"]
assert start["argv"][start["argv"].index("--session_name") + 1] == session
assert session.startswith("mtr-present-feasibility-")
helper = pilot.ps(f"$pmHelper=@(Get-CimInstance Win32_Process -Filter 'ProcessId = {start['helper_pid']}' -ErrorAction Stop | "
    "Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine); "
    "@{observed_at=[DateTimeOffset]::UtcNow.ToString('o'); processes=$pmHelper} | ConvertTo-Json -Depth 5", OUT, "helper-current")
pilot.write(OUT / "helper-current.json", helper)
query = query_session(session)
pilot.write(OUT / "native-session-current.json", query)
if query["status"] == 0:
    # The unique name was absent before the pinned Popen created this session.
    # Never target another session or any process/service.
    absent = json.loads((BASE / "upstream-capture-02/unique-session-before.execution.json").read_text(encoding="utf-8"))
    assert absent["exit_code"] != 0 and not helper["processes"]
    pilot.execute(["logman", "stop", session, "-ets"], OUT, "only-owned-orphan-session-cleanup")
pilot.execute(["logman", "query", session, "-ets"], OUT, "unique-session-current")
after = query_session(session)
pilot.write(OUT / "native-session-after.json", after)
args = SimpleNamespace(instance=pilot.ROOT / ".cache/acceptance/official-nf248-owned-049c", pid=18796,
                       created="2026-11-16T15:31:22.677Z")
target = pilot.inspect_target(args, OUT, "target-current")
assert target["processes"] == intent["target_before"]["processes"]
services = pilot.ps("@{observed_at=[DateTimeOffset]::UtcNow.ToString('o'); "
    "frameview_service=@(Get-Service -Name FvSvc | Select-Object Name,Status,DisplayName)} | ConvertTo-Json -Depth 4",
    OUT, "service-current")
pilot.write(OUT / "service-current.json", services)
for source in (Path(__file__), BASE / "pilot.py", BASE / "native_etw.py"):
    shutil.copy2(source, OUT / (source.stem + "-source.py"))
pilot.write(OUT / "assessment.json", {"observed_at": datetime.now(timezone.utc).isoformat(),
    "scope": "retrospective_cleanup_observation_only", "original_helper_pid": start["helper_pid"],
    "helper_currently_absent": not helper["processes"], "unique_session_absent": after["status"] != 0,
    "session_query_status": after["status"], "original_helper_exit_code": None,
    "target_identity_unchanged_at_actual_later_read": True,
    "limits": "Missing original wait receipt is not reconstructed. No third capture, game input, permission or service change."})
print(json.dumps({"helper_absent": not helper["processes"], "session_status": after["status"], "target_identity_unchanged": True}))
