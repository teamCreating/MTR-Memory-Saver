"""Independently bind the route failure, Windows event identity and repaired observer tests."""
import ast
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

OUT = pathlib.Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import observe_packaged_client as observer


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def class_ast(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return ast.dump(next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == name))


route = ROOT / "evidence/engineering-046/route-attempt-03/observation"
summary = read(route / "summary.json")
rows = [json.loads(line) for line in (route / "samples.jsonl").read_text(encoding="utf-8").splitlines()]
assert sha(route / "samples.jsonl") == summary["samples_sha256"]
assert class_ast(route / "observer-source.py", "RouteWindows") == class_ast(ROOT / "tools/observe_packaged_client.py", "RouteWindows")
policy = summary["policy"]
windows = observer.RouteWindows(policy["duration"], policy["route_windows"]["window_count"],
    policy["route_windows"]["minimum_window_progress_displacement"], policy["interval"], policy["freshness_seconds"])
for row in rows:
    windows.add(row["elapsed_seconds"], row.get("observation", {"verified": False}))
assert windows.summary() == summary["route_window_evidence"]

namespace = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
event = ET.parse(OUT / "event-66377.xml").getroot()
values = [item.text for item in event.findall("e:EventData/e:Data", namespace)]
pid, exception = int(values[8], 16), int(values[6], 16)
created = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(microseconds=int(values[9], 16) // 10)
assert pid == summary["process_identity"]["pid"] == 34668
assert created == dt.datetime.fromisoformat(summary["process_created"])
assert pathlib.Path(values[10]).resolve() == pathlib.Path(summary["process_identity"]["executable"]).resolve()
assert exception == rows[-1]["process"]["exit_code"] == 1653
assert values[3] == "textinputframework.dll"

capture = read(OUT / "capture.json")
complete = [item for item in capture["chunks"] if item["readable_complete_chunk"]]
prefix_end = max(item["header"]["start_nanos"] + item["header"]["duration_nanos"] for item in complete) / 1e9
end = dt.datetime.fromtimestamp(prefix_end, dt.timezone.utc)

builds = []
for target in ("official-nf248", "official-nf265"):
    directory = OUT / target
    manifest = read(directory / ("mtr-native-observer-" + target + "-1.0.1.build.json"))
    artifact = directory / manifest["artifact"]
    assert sha(artifact) == manifest["sha256"]
    sources = {}
    for name, expected in manifest["inputs"].items():
        source = ROOT / name
        assert sha(source) == expected, name
        destination = OUT / "source-inputs" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        sources[name] = sha(destination)
    junit = [ET.parse(path).getroot() for path in (directory / "junit").glob("*.xml")]
    tests = {key: sum(int(suite.get(key, "0")) for suite in junit) for key in ("tests", "failures", "errors", "skipped")}
    assert tests == {"tests": 18, "failures": 0, "errors": 0, "skipped": 0}
    with zipfile.ZipFile(artifact) as jar:
        classes = [name for name in jar.namelist() if name.endswith(".class")]
        assert all(name.startswith(("dev/abenli/neutralprobe/", "dev/abenli/probeio/")) for name in classes)
        assert len([name for name in classes if name.startswith("dev/abenli/probeio/")]) == 3
    builds.append({"target": target, "artifact": artifact.relative_to(OUT).as_posix(), "sha256": sha(artifact),
                   "junit": tests, "class_count": len(classes), "source_inputs_verified": sources})

for name in ("tools/windows_snapshot_io.py", "tools/test_windows_snapshot_io.py", "tools/observe_packaged_client.py", "tools/test_observe_packaged_client.py"):
    source, destination = ROOT / name, OUT / "source-inputs" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
for directory in (ROOT / "tools/probes/neutral/test", ROOT / "tools/probes/io/test"):
    for source in directory.rglob("*.java"):
        destination = OUT / "source-inputs" / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

assessment = {
    "timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(), "utc_offset": "+08:00",
    "route_attempt_03": {"status": "failed", "full_route_accepted": False,
        "actual_observation_seconds": summary["elapsed_seconds"], "requested_seconds": policy["duration"],
        "samples": summary["sample_count"], "verified_samples": summary["verified_sample_count"],
        "terminal_process_sample": rows[-1], "independently_replayed_windows": windows.summary(),
        "available_auxiliary_samples": summary["auxiliary_available_samples"],
        "attempted_auxiliary_samples": summary["auxiliary_attempted_samples"]},
    "windows_failure": {"event_record": "event-66377.xml", "wer_record": "Report.wer", "pid": pid,
        "process_created": created.isoformat(), "process_executable": values[10], "identity_verified": True,
        "exception_decimal": exception, "exception_hex": "0x" + values[6],
        "faulting_module": values[3], "module_version": values[4], "module_path": values[11],
        "attribution": "Windows native text-input module crash location and exact process identity are confirmed. The triggering action and underlying defect are not established without a native stack/minidump; this does not prove or disprove a Memory Saver defect."},
    "jfr": {"raw_chunks_preserved": len(capture["chunks"]), "readable_complete_chunks": len(complete),
        "readable_prefix_end": end.isoformat(), "route_seconds_inside_readable_prefix": (end-dt.datetime.fromisoformat(summary["started"])).total_seconds(),
        "locked_tail_preserved": [item["path"] for item in capture["chunks"] if not item["readable_complete_chunk"]],
        "tail_modified": False, "full_route_jfr_available": False},
    "snapshot_publication": {"old_observer_error_time": "2026-11-15T06:54:40.517+08:00",
        "python_tests": 4, "observer_tests": 61, "old_movefileex_negative_control": "sharing-probe.json",
        "correction": "Shared-delete readers and ReplaceFileW publishers preserve one complete file version on Windows; native publication failures remain visible. First publication and other OSes require atomic rename.",
        "scope": "Only probe tooling changes. Actual published game snapshots with observer 1.0.1 need separate fresh runtime verification. The old access-denied event precedes the native crash by about 38 minutes and does not establish its cause."},
    "builds": builds,
    "limits": ["No game process launched, stopped or mutated by this recovery.",
               "Route duration/coverage gates and historical failures were not relaxed.",
               "The first 40-minute sampled route window passed; its final seven minutes are not covered by the readable JFR prefix.",
               "Product source/JARs and v6 runtime remain outside this change."]}
save(OUT / "assessment.json", assessment)
files = []
for path in sorted(OUT.rglob("*")):
    if path.is_file() and path.name != "sha256.json" and "binary" not in path.parts and "__pycache__" not in path.parts:
        files.append({"path": path.relative_to(OUT).as_posix(), "sha256": sha(path), "bytes": path.stat().st_size})
save(OUT / "sha256.json", files)
print(json.dumps({"assessment": str(OUT / "assessment.json"), "indexed_files": len(files), "builds": [{"target": b["target"], "junit": b["junit"]} for b in builds]}, indent=2))
