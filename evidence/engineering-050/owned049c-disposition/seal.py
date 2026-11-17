"""One scoped preservation of old 049c; no runtime or original-file changes."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
INSTANCE = ROOT / ".cache/acceptance/official-nf248-owned-049c"
COLLECTOR = ROOT / ".cache/acceptance/capture-owned-049c"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def info(path):
    stat = path.stat()
    return {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "file_id": [stat.st_dev, stat.st_ino]}


def save(name, value):
    path = BASE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


reads = []
for folder, source, names in (
    ("instance", INSTANCE, ("launch.stdout.log", "launch.stderr.log", "acceptance-gc.log", "packaged-client-plan.json",
      "packaged-client-launch.json", "vehicle-test-instance.json", "options.txt", "usercache.json", "usernamecache.json",
      "logs/latest.log", "logs/debug.log", "logs/2026-11-16-1.log.gz", "game-probe/native-observer.json",
      "game-probe/native-resource-epochs.jsonl", "game-probe/native-invalid-model.jsonl")),
    ("collector", COLLECTOR, ("execution.json", "packaged-client-plan.json", "packaged-client-launch.json",
      "export-01-dump.stdout.log", "export-01-dump.stderr.log", "export-01-summary.stdout.log",
      "export-01-summary.stderr.log", "export-request-01"))):
    for relative in names:
        original, destination = source / relative, BASE / folder / relative
        started, before, digest = now(), info(original), sha(original)
        destination.parent.mkdir(parents=True, exist_ok=True)
        assert not destination.exists(), "Never overwrite a payload"
        shutil.copy2(original, destination)
        after = info(original)
        assert before == after and sha(original) == sha(destination) == digest
        reads.append({"source": str(original), "payload": destination.relative_to(BASE).as_posix(), "started": started,
                      "completed": now(), "before": before, "after": after, "sha256": digest, "copy_verified": True})

references = []
source = COLLECTOR / "native-snapshots.jsonl"
started, before = now(), info(source)
with source.open("rb") as stream:
    stream.seek(max(0, before["bytes"]-131072))
    window = stream.read()
assert window.endswith(b"\n"), "Do not hide an incomplete terminal line"
tail = b"".join(window.splitlines(keepends=True)[-3:])
assert len(tail.splitlines()) == 3
destination = BASE / "collector/native-snapshots-tail.jsonl"
with destination.open("xb") as stream:
    stream.write(tail)
digest = sha(source)
after = info(source)
assert before == after
with source.open("rb") as stream:
    stream.seek(before["bytes"]-len(tail))
    assert stream.read(len(tail)) == destination.read_bytes() == tail
assert info(source) == after
references.append({"path": str(source), "portable_payload": False, "bytes": before["bytes"], "sha256": digest,
                   "read_started": started, "read_completed": now(), "before": before, "after": after,
                   "portable_extract": {"payload": destination.relative_to(BASE).as_posix(), "start_offset": before["bytes"]-len(tail),
                                        "end_offset_exclusive": before["bytes"], "bytes": len(tail), "sha256": sha(destination), "complete_lines": 3}})
for relative in ("acceptance.jfr", "diagnostic-01.jfr"):
    path = INSTANCE / relative
    started, before, digest = now(), info(path), sha(path)
    assert info(path) == before
    references.append({"path": str(path), "portable_payload": False, "bytes": before["bytes"], "sha256": digest,
                       "read_started": started, "read_completed": now(), "before": before, "after": info(path)})
save("nonportable-references.json", references)
save("copy-read-receipts.json", reads)

script = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); " \
    "$oldProcess=@(Get-CimInstance Win32_Process -Filter 'ProcessId = 18796' -ErrorAction Stop | " \
    "Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine); " \
    "$oldCollector=@(Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" -ErrorAction Stop | " \
    "Where-Object {$_.CommandLine -match 'capture_diagnostic_client.py' -and $_.CommandLine -match 'capture-owned-049c'} | " \
    "Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine); " \
    "@{observed_at=[DateTimeOffset]::UtcNow.ToString('o'); pid=18796; matching_processes=$oldProcess; matching_collectors=$oldCollector} | ConvertTo-Json -Depth 5"
command = ["pwsh", "-NoProfile", "-Command", script]
query = {"started": now(), "argv": command, "owner_pid": os.getpid(), "scope": "old049c_identity_only_no_system_log_search"}
child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
query["helper_pid"] = child.pid
stdout, stderr = child.communicate(timeout=30)
query.update(completed=now(), exit_code=child.returncode, stdout_sha256=hashlib.sha256(stdout).hexdigest(), stderr_sha256=hashlib.sha256(stderr).hexdigest())
(BASE / "query.stdout.log").write_bytes(stdout)
(BASE / "query.stderr.log").write_bytes(stderr)
save("query.execution.json", query)
assert child.returncode == 0
current = json.loads(stdout.decode("utf-8-sig"))
assert not current["matching_processes"] and not current["matching_collectors"]
save("query.json", current)

record = json.loads((BASE / "collector/execution.json").read_bytes())
last = json.loads(tail.splitlines()[-1])
published = json.loads((BASE / "instance/game-probe/native-observer.json").read_bytes())
assert published == last["snapshot"] and published["pid"] == record["pid"] == 18796
assert record["status"] == "observing" and "exit_code" not in record and "ended" not in record
assert references[2]["sha256"] == record["exports"][0]["sha256"]
assert (BASE / "collector/packaged-client-plan.json").read_bytes() == (BASE / "instance/packaged-client-plan.json").read_bytes()
assert (BASE / "collector/packaged-client-launch.json").read_bytes() == (BASE / "instance/packaged-client-launch.json").read_bytes()
save("assessment.json", {"scope": "old049c_retrospective_unknown_disposition", "observed_at": current["observed_at"],
    "pid": 18796, "pid_and_collector_absent_at_query": True, "original_collector_status": record["status"],
    "last_native_observed": published["observed_at"], "last_captured_at": last["captured_at"],
    "last_state": {key: published[key] for key in ("paused", "screen", "resource_epochs", "observation_errors")},
    "exit_code": None, "exit_time": None, "termination_cause": "unknown", "normal_exit_verified": False,
    "original_acceptance_jfr_bytes": references[1]["bytes"], "early_export_sha_matches_original_receipt": True,
    "early_export_ended": record["exports"][0]["ended"], "integrity_checks_passed": True,
    "limits": ["Only the final three original collector records are portable; the complete snapshot stream and both JFR paths are nonportable references.",
        "The early JFR dump/summary receipts do not cover final termination; no later exit status is reconstructed.",
        "Separately discovered JVM repository chunks and recovery are outside this scope; this does not inventory all system JFR data.",
        "No new system-log search, game input, process stop, runtime/world/pack/source mutation, or inspection of 049d was performed."]})
files = {path.relative_to(BASE).as_posix(): {"bytes": path.stat().st_size, "sha256": sha(path)}
         for path in sorted(BASE.rglob("*")) if path.is_file() and "__pycache__" not in path.parts}
save("sha256-index.json", {"schema": 1, "created_at": now(), "files": files})
for relative, expected in files.items():
    path = BASE / relative
    assert path.stat().st_size == expected["bytes"] and sha(path) == expected["sha256"]
print(json.dumps({"payloads_verified": len(files), "portable_bytes": sum(item["bytes"] for item in files.values()), "exit_code": None}))
