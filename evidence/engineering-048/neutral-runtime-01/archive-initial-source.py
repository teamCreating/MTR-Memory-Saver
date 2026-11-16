"""Seal the completed, first real native-observer client; retain narrow scope."""
import collections
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTPUT = pathlib.Path(__file__).resolve().parent
CAPTURE = ROOT / ".cache/acceptance/capture-neutral-048"
INSTANCE = ROOT / ".cache/acceptance/official-nf248-neutral-048"


def digest(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(name, data):
    (OUTPUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if (OUTPUT / "assessment.json").exists():
    raise SystemExit("Preserve the existing sealed assessment")
execution = read(CAPTURE / "execution.json")
assert execution["status"] == "exited" and execution["exit_code"] == 0
assert not execution["capture_errors"]
for name, expected in execution["files"].items():
    assert digest(CAPTURE / name) == expected, name
shutil.copytree(CAPTURE, OUTPUT / "capture")
plan = read(CAPTURE / "packaged-client-plan.json")
for mod in plan["mods"]:
    assert digest(INSTANCE / "mods" / mod["filename"]) == mod["sha256"]
for pack in plan["packs"]:
    assert digest(INSTANCE / "resourcepacks" / pack["filename"]) == pack["sha256"]
    assert digest(pathlib.Path(pack["source"])) == pack["sha256"]
shutil.copytree(INSTANCE / "screenshots", OUTPUT / "screenshots")
shutil.copyfile(INSTANCE / "acceptance.jfr", OUTPUT / "recording.jfr")
shutil.copyfile(INSTANCE / "acceptance-gc.log", OUTPUT / "final-gc.log")
java = pathlib.Path(plan["java"])
commands = []
for label, command in [
    ("jfr-summary", [str(java.with_name("jfr.exe")), "summary", str(OUTPUT / "recording.jfr")]),
    ("jfr-events", [str(java.with_name("jfr.exe")), "print", "--json", "--events", "mtrtest.ClientFrame,mtrtest.ServerTick", str(OUTPUT / "recording.jfr")])]:
    with (OUTPUT / (label + ".json" if label == "jfr-events" else label + ".log")).open("wb") as stdout:
        result = subprocess.run(command, stdout=stdout, stderr=subprocess.PIPE, timeout=60)
    (OUTPUT / (label + ".stderr.log")).write_bytes(result.stderr)
    commands.append({"command": command, "returncode": result.returncode})
    assert result.returncode == 0
write("jfr-execution.json", commands)
events = read(OUTPUT / "jfr-events.json")["recording"]["events"]
counts = collections.Counter(event["type"] for event in events)
frames = [event for event in events if event["type"] == "mtrtest.ClientFrame"]
assert frames and counts["mtrtest.ServerTick"] > 0
world_frames = [event for event in frames if event["values"]["inWorld"] and not event["values"]["paused"]]
assert world_frames
rows = [json.loads(line) for line in (CAPTURE / "native-snapshots.jsonl").read_text().splitlines()]
snapshots = [row["snapshot"] for row in rows]
assert all(s["process"]["pid"] == execution["pid"] for s in snapshots)
assert len({s["process"]["start_instant"] for s in snapshots}) == 1
assert all(s["observation_errors"] == 0 for s in snapshots)
world = [s for s in snapshots if s["in_world"] and not s["paused"] and s["native_settled"]]
assert world and all(s["registered_count"] == 1091 and s["registered_declarations"] == 1092 for s in world)
assert all(s["resource_epochs"]["completed"] == 1 for s in world)
last = world[-1]
log = (CAPTURE / "logs/latest.log").read_text(encoding="utf-8")
assert "All dimensions are saved" in log
assert "Loaded vehicles" in log
write("assessment.json", {
    "timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
    "scope": "Actual official NF248 0.4.6 / neutral observer 1.0.0 functional observation only",
    "pid": execution["pid"], "process_created": snapshots[0]["process"]["start_instant"],
    "normal_saved_exit": True, "exit_code": execution["exit_code"],
    "unchanged_current_packs": len(plan["packs"]), "bound_mods": plan["mods"],
    "native_snapshot_count": len(snapshots), "unpaused_settled_world_snapshots": len(world),
    "observed_registration": {"distinct_ids": 1091, "declarations": 1092},
    "native_observation_errors": 0, "actual_native_epochs": last["resource_epochs"],
    "jfr_event_counts": dict(counts), "unpaused_in_world_frame_events": len(world_frames),
    "caches": [{"id": r["resource_id"], "entries": [{"floors": len(e["floors"]), "doorways": len(e["doorways"])} for e in r["entries"]]} for r in last["cache_state"]["resources"]],
    "native_invalid_model_review": "../native-invalid-model/startup-prefix/attribution.json",
    "scope_passed": True, "full_gameplay_accepted": False, "performance_accepted": False,
    "successful_real_reloads": 0,
    "limits": ["The initial stock-platform F2 screenshots contain no train; geometry, displays, boarding and floor traversal remain unverified.",
               "Two computer-use state captures timed out. Slash, T and Escape inputs produced no observed screen transition; no F3+T pass is inferred.",
               "The old 1.0.0 observer is superseded by the Windows atomic-publication repair. This run did not reproduce the held-reader error, and does not validate the later observer.",
               "Background engineering work, diagnostic hook, JFR and thread dump make this unsuitable as a controlled benchmark."]})
write("sha256.json", {str(p.relative_to(OUTPUT)): digest(p) for p in OUTPUT.rglob("*") if p.is_file() and p.name != "sha256.json"})
print(json.dumps(read(OUTPUT / "assessment.json"), indent=2))
