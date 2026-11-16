"""Bind the immutable startup prefix to its real client, inputs and native evidence."""

from __future__ import annotations

import datetime as dt
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[3]
folder = Path(__file__).resolve().parent
prefix = folder / "capture-01"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--process-receipt", type=Path, help="Previously captured actual Win32 identity receipt; never substitutes a live query silently.")
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(exist_ok=False)
instance = root / ".cache/acceptance/official-nf248-owned-049"


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def instant(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(relative, data):
    path = output / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


inputs = {}


def copy(source, relative):
    source = Path(source)
    expected = sha(source)
    assert str(source) not in inputs or inputs[str(source)] == expected
    inputs[str(source)] = expected
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert sha(target) == expected
    return target


report = {"started": stamp(), "status": "reviewing", "pid": 58468,
          "scope": "Official 0.4.7 native startup and photographed selected side body only"}
write("execution.json", report)
try:
    frozen = read(prefix / "freeze.json")
    for relative, receipt in frozen["files"].items():
        assert sha(prefix / relative) == receipt["sha256"]
        assert (prefix / relative).stat().st_size == receipt["bytes"]
        assert receipt["source_size_before"] == receipt["source_size_after"] == receipt["bytes"]
    plan, launch = read(prefix / "packaged-client-plan.json"), read(prefix / "packaged-client-launch.json")
    assert plan["artifact"]["version"] == "0.4.7" and plan["artifact"]["target"] == "official-nf248"
    assert launch["pid"] == 58468 and launch["plan_sha256"] == sha(prefix / "packaged-client-plan.json")
    snapshot = read(prefix / "game-probe/native-observer.json")
    assert snapshot["pid"] == 58468 and snapshot["registered_count"] == 1091 and snapshot["registered_declarations"] == 1092
    assert snapshot["native_pending"] == 0 and snapshot["native_settled"] and snapshot["observation_errors"] == 0
    assert snapshot["resource_epochs"] == {"started": 1, "completed": 1, "in_flight": 0, "max_nesting": 1, "last_completed_sequence": 1}
    process_command = ["pwsh", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter 'ProcessId=58468' | Select-Object ProcessId,ExecutablePath,CommandLine,@{Name='CreatedUtc';Expression={$_.CreationDate.ToUniversalTime().ToString('o')}} | ConvertTo-Json -Depth 4"]
    if args.process_receipt is None:
        process_receipt = {"argv": process_command, "started": stamp()}
        observed = subprocess.run(process_command, capture_output=True, check=True)
        process_receipt.update(ended=stamp(), exit_code=observed.returncode)
        (output / "process.stdout.json").write_bytes(observed.stdout)
        (output / "process.stderr.log").write_bytes(observed.stderr)
        write("process-execution.json", process_receipt)
        process_raw = json.loads(observed.stdout)
    else:
        original = args.process_receipt.resolve(strict=True)
        for name in ("process-execution.json", "process.stdout.json", "process.stderr.log"):
            copy(original / name, name)
        process_receipt = read(output / "process-execution.json")
        assert process_receipt["argv"] == process_command and process_receipt["exit_code"] == 0
        process_raw = read(output / "process.stdout.json")
        report["explicit_historical_process_receipt"] = str(original)
    process = {"pid": process_raw["ProcessId"], "created": process_raw["CreatedUtc"],
               "executable": process_raw["ExecutablePath"], "command_line": process_raw["CommandLine"]}
    assert process["pid"] == launch["pid"] and Path(process["executable"]) == Path(plan["java"])
    assert abs((instant(process["created"]) - instant(snapshot["process"]["start_instant"])).total_seconds()) < .002
    write("process.json", process)
    sources = ["tools/client_experiment_analysis.py", "tools/native_diagnostic_review.py", "tools/windows_snapshot_io.py",
               "tools/packaged_client.py", "config/native-diagnostic-review.json"]
    for relative in sources:
        copy(root / relative, "sources/" + relative)
    assert sha(output / "sources/tools/packaged_client.py") == launch["launcher_tool_sha256"]
    bindings = {"mods": [], "packs": []}
    for item in plan["mods"]:
        path = instance / "mods" / item["filename"]
        expected = sha(path)
        assert expected == item["sha256"]
        inputs[str(path)] = expected
        bindings["mods"].append({**item, "bytes": path.stat().st_size, "actual_sha256": expected})
        if item["role"] in {"observer", "companion"}:
            copy(path, "installed-tools/" + path.name)
    assert {p.name for p in (instance / "mods").glob("*.jar")} == {item["filename"] for item in plan["mods"]}
    for item in plan["packs"]:
        source, installed = Path(item["source"]), instance / "resourcepacks" / item["filename"]
        source_sha, installed_sha = sha(source), sha(installed)
        assert source_sha == installed_sha == item["sha256"]
        inputs[str(source)], inputs[str(installed)] = source_sha, installed_sha
        bindings["packs"].append({**item, "source_sha256": source_sha, "installed_sha256": installed_sha})
    write("installed-bindings.json", bindings)
    observer = next(item for item in plan["mods"] if item["role"] == "observer")
    with zipfile.ZipFile(output / "installed-tools" / observer["filename"]) as jar:
        metadata = json.loads(jar.read("mtr-native-observer-target.json"))
        write("observer-target.json", metadata)
        write("observer-class-hashes.json", {n: hashlib.sha256(jar.read(n)).hexdigest() for n in jar.namelist() if n.endswith(".class")})
    sys.path.insert(0, str(output / "sources/tools"))
    from client_experiment_analysis import client_log_completeness, native_diagnostics
    from native_diagnostic_review import review_diagnostics, validate_review
    review = read(output / "sources/config/native-diagnostic-review.json")
    for proof in review["proofs"]:
        copied = copy(root / proof["path"], "proofs/" + proof["path"])
        assert sha(copied) == proof["sha256"]
    validate_review(review, metadata, root=output / "proofs")
    log = (prefix / "logs/latest.log").read_bytes()
    witness = {**frozen["files"]["logs/latest.log"], "started": frozen["files"]["logs/latest.log"]["read_started"],
               "ended": frozen["files"]["logs/latest.log"]["read_ended"]}
    completeness = client_log_completeness(log, [{"client_log_witness": witness}], instance)
    write("log-prefix-completeness.json", completeness)
    assert completeness["passed"], completeness
    events = [json.loads(line) for line in (prefix / "game-probe/native-invalid-model.jsonl").read_bytes().splitlines()]
    epochs = [json.loads(line) for line in (prefix / "game-probe/native-resource-epochs.jsonl").read_bytes().splitlines()]
    diagnostic = review_diagnostics(native_diagnostics(log.decode("utf-8")), log.decode("utf-8"), events, epochs, process,
                                    metadata, review, {"start": plan["timestamp"], "end": frozen["ended"]}, snapshot)
    write("native-diagnostic-review.json", diagnostic)
    assert diagnostic["native_attribution"]["passed"] and not diagnostic["unreviewed_native"], diagnostic
    collector = root / ".cache/acceptance/capture-owned-049"
    collector_report = read(copy(collector / "execution.json", "collector-execution-prefix.json"))
    assert collector_report["pid"] == 58468
    for name, expected in collector_report["sources"].items():
        candidate = root / "tools" / name
        assert sha(candidate) == expected
        copy(candidate, "collector-sources/" + name)
    started = stamp()
    size_before = (collector / "native-snapshots.jsonl").stat().st_size
    raw = (collector / "native-snapshots.jsonl").read_bytes()
    ended = stamp()
    size_after = (collector / "native-snapshots.jsonl").stat().st_size
    (output / "collector-read.jsonl.raw").write_bytes(raw)
    complete = raw[:raw.rfind(b"\n") + 1].splitlines(keepends=True)
    kept = [line for line in complete if instant(json.loads(line)["captured_at"]) <= instant(frozen["ended"])]
    prefix_raw = b"".join(kept)
    assert prefix_raw == (prefix / "native-snapshots-prefix.jsonl").read_bytes()
    write("collector-read-receipt.json", {"started": started, "ended": ended, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
          "source_size_before": size_before, "source_size_after": size_after, "complete_lines": len(complete), "retained_prefix_lines": len(kept),
          "unparsed_trailing_bytes": len(raw) - raw.rfind(b"\n") - 1, "prefix_cutoff": frozen["ended"]})
    rows = [json.loads(line) for line in kept]
    states = [row["snapshot"] for row in rows]
    assert all(s["pid"] == 58468 and s["observation_errors"] == 0 and s["resource_epochs"]["completed"] == 1 for s in states)
    assert all(instant(a["timestamp"]) < instant(b["timestamp"]) for a, b in zip(states, states[1:]))
    eligible = lambda s: s["in_world"] and not s["paused"] and s["screen"] is None and s["native_pending"] == 0 and s["native_settled"] and s["registered_count"] == 1091 and s["registered_declarations"] == 1092
    stability = None
    for i, row in enumerate(rows):
        if not eligible(row["snapshot"]):
            continue
        selected = []
        for candidate in rows[i:]:
            selected.append(candidate)
            if not eligible(candidate["snapshot"]):
                break
            elapsed = (instant(candidate["snapshot"]["timestamp"]) - instant(row["snapshot"]["timestamp"])).total_seconds()
            if elapsed >= 60:
                gaps = [(instant(b["snapshot"]["timestamp"]) - instant(a["snapshot"]["timestamp"])).total_seconds() for a, b in zip(selected, selected[1:])]
                if max(gaps) <= 2:
                    stability = {"start": row["snapshot"]["timestamp"], "end": candidate["snapshot"]["timestamp"], "seconds": elapsed,
                                 "samples": len(selected), "maximum_gap_seconds": max(gaps),
                                 "maximum_capture_delay_seconds": max((instant(r["captured_at"]) - instant(r["snapshot"]["timestamp"])).total_seconds() for r in selected)}
                    break
        if stability:
            break
    assert stability is not None
    write("startup-stability.json", stability)
    errors_in_stability = [error for error in collector_report["capture_errors"]
                           if instant(stability["start"]) <= instant(error["at"]) <= instant(stability["end"])]
    write("collector-errors-and-scope.json", {"all_captured_errors": collector_report["capture_errors"],
          "errors_inside_accepted_stability_window": errors_in_stability,
          "whole_collector_error_free": not collector_report["capture_errors"],
          "scope": "Accept only the completed initial sixty-second native startup window, not error-free whole-run collection"})
    assert not errors_in_stability
    image_time = instant("2026-11-16T19:25:21+08:00")
    near = sorted(rows, key=lambda r: abs((instant(r["snapshot"]["timestamp"]) - image_time).total_seconds()))[:2]
    for row in near:
        s = row["snapshot"]
        # Body context is distinct from the earlier screen-null stability window.
        # Retain the actual adjacent ChatScreen -> null transition rather than
        # treating a one-second published pre-image snapshot as the F2 UI state.
        assert s["in_world"] and not s["paused"] and s["native_settled"] and s["native_pending"] == 0
        assert s["registered_count"] == 1091 and s["registered_declarations"] == 1092 and s["observation_errors"] == 0
        vehicle = s["train_state"]["vehicles"][0]
        assert vehicle["speed"] == 0 and vehicle["door_value"] == 1 and vehicle["rail_progress"] == 160
        assert abs((instant(s["timestamp"]) - image_time).total_seconds()) < 1
        assert vehicle["car_resources"] == [r["resource_id"] for r in snapshot["cache_state"]["resources"]]
    assert any(row["snapshot"]["screen"] is None for row in near)
    write("image-nearby-snapshots.json", near)
    caches = [{"id": r["resource_id"], "entries": [{"floors": len(e["floors"]), "doorways": len(e["doorways"])} for e in r["entries"]]} for r in snapshot["cache_state"]["resources"]]
    assert [r["entries"] for r in caches] == [[{"floors": 5, "doorways": 10}], [{"floors": 6, "doorways": 10}]]
    assert all(sha(Path(path)) == expected for path, expected in inputs.items())
    report.update(ended=stamp(), status="verified", input_fingerprints=inputs)
    write("execution.json", report)
    write("assessment.json", {"timestamp": stamp(), "scope": report["scope"], "scoped_native_startup_passed": True,
          "artifact": plan["artifact"]["artifact"], "artifact_sha256": plan["artifact"]["sha256"], "pid": 58468,
          "native_snapshot_prefix_count": len(states), "first_snapshot": states[0]["timestamp"], "last_snapshot": states[-1]["timestamp"],
          "startup_stability": stability, "native_counts": {"distinct_ids": 1091, "declarations": 1092}, "native_pending": 0,
          "observer_errors": 0, "native_epochs": snapshot["resource_epochs"], "native_diagnostic_attribution_passed": True,
          "all_collector_errors_retained": collector_report["capture_errors"], "whole_collector_error_free": not collector_report["capture_errors"],
          "other_raw_errors_retained": diagnostic["other_errors_requiring_contextual_review"], "caches": caches,
          "verified_original_and_installed_packs": len(bindings["packs"]), "bound_mods": len(bindings["mods"]),
          "image": {"path": "capture-01/screenshots/2026-11-16_19.25.21.png", "sha256": frozen["files"]["screenshots/2026-11-16_19.25.21.png"]["sha256"],
                    "scope": "Independently reviewed selected DC01 two-car side bodies/windows/visible open doors/junction only"},
          "limits": ["Frozen startup prefix; no final save/exit acceptance is derived", "Only selected photographed side view",
                     "No passenger/boarding, cab/consist-wide geometry, 20-reload, two-hour route or controlled performance acceptance",
                     "No product permit/workspace counters are supplied by the neutral observer"]})
    copy(Path(__file__), "assess-prefix-script.py")
    print(json.dumps({"status": report["status"], "startup_stability": stability, "snapshot_prefix_count": len(states)}))
except BaseException as error:
    report.update(ended=stamp(), status="failed", error=repr(error))
    write("execution.json", report)
    raise
