"""Freeze the completed first route window without changing the live observer."""
import collections
import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import shutil

OUTPUT = pathlib.Path(__file__).resolve().parent
ROOT = OUTPUT.parents[2]
SOURCE = ROOT / "evidence/engineering-046/route-attempt-03"
OBSERVATION = SOURCE / "observation"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def complete_lines(path):
    return [line for line in path.read_bytes().splitlines(keepends=True) if line.endswith(b"\n")]


if (OUTPUT / "assessment.json").exists():
    raise SystemExit("Do not overwrite an immutable route checkpoint.")
execution = json.loads((SOURCE / "execution.json").read_text(encoding="utf-8"))
policy_bytes = (OBSERVATION / "route-window-policy.json").read_bytes()
policy = json.loads(policy_bytes)
source_bytes = (OBSERVATION / "observer-source.py").read_bytes()
assert sha(source_bytes) == execution["source_sha256"]
assert source_bytes == (ROOT / "tools/observe_packaged_client.py").read_bytes()
window_end = policy["windows"][0]["end_seconds"]
lines = complete_lines(OBSERVATION / "samples.jsonl")
prefix = []
rows = []
for line in lines:
    row = json.loads(line)
    prefix.append(line)
    rows.append(row)
    if row["elapsed_seconds"] >= window_end:
        break
assert rows[-1]["elapsed_seconds"] >= window_end, "First frozen window is still running."
arguments = execution["observer_command"]
interval = float(arguments[arguments.index("--interval") + 1])
freshness = float(arguments[arguments.index("--freshness-seconds") + 1])
spec = importlib.util.spec_from_file_location("frozen_route_observer", OBSERVATION / "observer-source.py")
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
route = observer.RouteWindows(policy["duration_seconds"], policy["window_count"],
    policy["minimum_window_progress_displacement"], interval, freshness)
assert route.policy() == policy
for row in rows:
    recomputed = route.add(row["elapsed_seconds"], row["observation"])
    expected = dict(row["route_window"])
    assert expected.pop("policy_sha256") == sha(policy_bytes)
    assert expected == recomputed, "Raw route-window evidence differs from independent replay."
first = route.summary()["windows"][0]
selected = [row for row in rows if row["route_window"]["index"] == 0]
vehicles = [vehicle for row in selected for vehicle in row["observation"]["state"].get("vehicles", [])
            if "railProgress" in vehicle]
progresses = [vehicle["railProgress"] for vehicle in vehicles]
door_values = [vehicle["door_value"] for vehicle in vehicles if "door_value" in vehicle]
times = [row["observation"]["state"]["game_time"] for row in selected]
auxiliary_lines = [line for line in complete_lines(OBSERVATION / "auxiliary-events.jsonl")
                   if json.loads(line)["elapsed_seconds"] <= window_end]
auxiliary = [json.loads(line) for line in auxiliary_lines]
report = {
    "timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(), "utc_offset": "+08:00",
    "scope": "Completed first 2400-second window of the still-running official NF248 route attempt 03",
    "pid": execution["pid"], "observer_pid": execution["observer_pid"], "source_sha256": sha(source_bytes),
    "route_policy_sha256": sha(policy_bytes), "first_window": first,
    "raw_prefix_samples": len(rows), "first_window_samples": len(selected),
    "verified_first_window_samples": sum(row["observation"]["verified"] is True for row in selected),
    "boundary_witness_elapsed_seconds": rows[-1]["elapsed_seconds"],
    "native_epoch_sequences": sorted({row["observation"]["state"]["resource_epochs"]["last_completed_sequence"] for row in selected}),
    "sampled_progress_range": [min(progresses), max(progresses)],
    "sampled_door_value_range": [min(door_values), max(door_values)] if door_values else None,
    "game_time_advance": times[-1] - times[0],
    "auxiliary_phase_counts_before_window_boundary": dict(collections.Counter(event["phase"] for event in auxiliary)),
    "complete_two_hour_route_proven": False, "actual_visual_or_boarding_proven": False,
    "limits": "Only the first sampled window is complete. Door values and route motion are native state, not visual geometry, door animation, boarding or uninterrupted continuity. The complete three-window/JFR/GPU/NMT and native-diagnostic audit remains pending. No game input, instance modification or process stop was performed."
}
for name, data in (("samples-prefix.jsonl", b"".join(prefix)), ("auxiliary-prefix.jsonl", b"".join(auxiliary_lines)),
                   ("observer-source.py", source_bytes), ("route-window-policy.json", policy_bytes)):
    (OUTPUT / name).write_bytes(data)
shutil.copyfile(SOURCE / "execution.json", OUTPUT / "execution-at-checkpoint.json")
(OUTPUT / "assessment.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
