"""Seal the completed second neutral-observer runtime without changing the instance."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def time(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def inventory(path):
    return {p.relative_to(path).as_posix(): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    capture = root / ".cache/acceptance/capture-neutral-048b"
    instance = root / ".cache/acceptance/official-nf248-neutral-048b"
    prefix = root / "evidence/engineering-048/neutral-runtime-02-review/capture-02"
    observed = {}
    report = {"started": stamp(), "status": "sealing", "argv": sys.argv,
              "scope": "Completed diagnostic run: official NF248 / Memory Saver 0.4.6 / neutral observer 1.0.2",
              "commands": [], "input_fingerprints_before": observed}

    def write(name, value):
        (out / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def remember(path):
        key = str(path.resolve())
        actual = sha(path)
        assert key not in observed or observed[key] == actual, f"Input changed during archive: {path}"
        observed[key] = actual
        return actual

    def copy_file(source, destination):
        expected = remember(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        assert sha(destination) == expected, source

    def copy_tree(source, destination):
        for file in sorted(source.rglob("*")):
            if file.is_file():
                copy_file(file, destination / file.relative_to(source))
        assert inventory(source) == inventory(destination), source

    def command(label, argv, compressed=False):
        receipt = {"argv": argv, "started": stamp(), "executable_sha256": remember(Path(argv[0]))}
        report["commands"].append(receipt)
        write("archive-execution.json", report)
        completed = subprocess.run(argv, capture_output=True, timeout=60)
        destination = out / (label + (".json.gz" if compressed else ".stdout.log"))
        if compressed:
            with destination.open("wb") as raw:
                with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as archive:
                    archive.write(completed.stdout)
        else:
            destination.write_bytes(completed.stdout)
        (out / (label + ".stderr.log")).write_bytes(completed.stderr)
        receipt.update(ended=stamp(), exit_code=completed.returncode,
                       stdout_file=destination.name, stdout_sha256=sha(destination),
                       uncompressed_stdout_sha256=hashlib.sha256(completed.stdout).hexdigest())
        write("archive-execution.json", report)
        assert completed.returncode == 0, receipt
        return completed.stdout

    try:
        execution = read(capture / "execution.json")
        assert execution["status"] == "exited" and execution["exit_code"] == 0
        assert not execution["capture_errors"]
        for name, expected in execution["files"].items():
            assert remember(capture / name) == expected, name
        copy_tree(capture, out / "capture")
        copy_tree(prefix, out / "prefix")
        prefix_index = read(prefix.parent / "sha256.json")
        assert prefix_index["schema"] == 1
        prefix_files = prefix_index["files"]
        for path in prefix.rglob("*"):
            if path.is_file():
                relative = path.relative_to(prefix.parent).as_posix()
                indexed = prefix_files[relative]
                assert sha(path) == indexed["sha256"] and path.stat().st_size == indexed["bytes"], relative
        copy_file(prefix.parent / "sha256.json", out / "prefix-parent-sha256.json")
        plan, launch = read(capture / "packaged-client-plan.json"), read(capture / "packaged-client-launch.json")
        process = read(prefix / "process.json")
        assert execution["pid"] == launch["pid"] == process["pid"]
        assert sha(capture / "packaged-client-plan.json") == launch["plan_sha256"]
        assert (capture / "packaged-client-plan.json").read_bytes() == (prefix / "packaged-client-plan.json").read_bytes()
        assert (capture / "packaged-client-launch.json").read_bytes() == (prefix / "packaged-client-launch.json").read_bytes()
        assert Path(process["executable"]) == Path(plan["java"])
        for name, expected in execution["sources"].items():
            candidates = [prefix / "sources/tools" / name, root / "tools" / name]
            matches = [path for path in candidates if path.is_file() and sha(path) == expected]
            assert matches, f"Missing exact launched capture source: {name}"
            copy_file(matches[0], out / "capture-sources" / name)
        for name in ["logs", "game-probe", "screenshots"]:
            copy_tree(instance / name, out / "instance-final" / name)
        for name in ["launch.stdout.log", "launch.stderr.log", "acceptance-gc.log", "options.txt",
                     "packaged-client-plan.json", "packaged-client-launch.json", "command_history.txt",
                     "vehicle-test-instance.json"]:
            copy_file(instance / name, out / "instance-final" / name)
        for name in ["logs/latest.log", "game-probe/native-observer.json", "game-probe/native-resource-epochs.jsonl",
                     "game-probe/native-invalid-model.jsonl", "launch.stdout.log", "launch.stderr.log", "acceptance-gc.log"]:
            assert (capture / name).read_bytes() == (instance / name).read_bytes(), name
        bindings = {"mods": [], "packs": []}
        for mod in plan["mods"]:
            path = instance / "mods" / mod["filename"]
            actual = remember(path)
            assert actual == mod["sha256"], path
            bindings["mods"].append({**mod, "current_sha256": actual, "bytes": path.stat().st_size})
            if mod["role"] in {"companion", "observer"}:
                copy_file(path, out / "installed-tools" / path.name)
        for pack in plan["packs"]:
            source, installed = Path(pack["source"]), instance / "resourcepacks" / pack["filename"]
            assert remember(source) == remember(installed) == pack["sha256"], pack["filename"]
            bindings["packs"].append({"filename": pack["filename"], "source": str(source),
                                     "sha256": pack["sha256"], "bytes": installed.stat().st_size})
        write("installed-bindings.json", bindings)
        sys.path.insert(0, str(out / "prefix/sources/tools"))
        from client_experiment_analysis import client_log_completeness, native_diagnostics
        from native_diagnostic_review import review_diagnostics, validate_review
        metadata = read(out / "prefix/observer-target.json")
        review = read(out / "prefix/sources/config/native-diagnostic-review.json")
        for proof in review["proofs"]:
            assert remember(root / proof["path"]) == proof["sha256"]
            copy_file(root / proof["path"], out / "proofs" / proof["path"])
        validate_review(review, metadata, root=out / "proofs")
        native_mod = next(mod for mod in plan["mods"] if mod["role"] == "observer")
        with zipfile.ZipFile(out / "installed-tools" / native_mod["filename"]) as jar:
            assert json.loads(jar.read("mtr-native-observer-target.json")) == metadata
        log_bytes = (out / "capture/logs/latest.log").read_bytes()
        old_log = (out / "prefix/logs/latest.log").read_bytes()
        assert log_bytes.startswith(old_log)
        old_capture = read(out / "prefix/capture.json")
        completeness = client_log_completeness(old_log, [{"client_log_witness": old_capture["stream_captures"]["logs/latest.log"]}], Path(plan["instance"]))
        assert completeness["passed"], completeness
        for name in ["native-invalid-model.jsonl", "native-resource-epochs.jsonl"]:
            assert (out / "capture/game-probe" / name).read_bytes().startswith((out / "prefix/game-probe" / name).read_bytes())
        events = [json.loads(line) for line in (out / "capture/game-probe/native-invalid-model.jsonl").read_bytes().splitlines()]
        epochs = [json.loads(line) for line in (out / "capture/game-probe/native-resource-epochs.jsonl").read_bytes().splitlines()]
        final = read(out / "capture/game-probe/native-observer.json")
        window = {"start": plan["timestamp"], "end": execution["ended"]}
        write("run-window.json", window)
        diagnostics = review_diagnostics(native_diagnostics(log_bytes.decode("utf-8")), log_bytes.decode("utf-8"),
                                         events, epochs, process, metadata, review, window, final)
        write("diagnostic-review.json", diagnostics)
        assert diagnostics["native_attribution"]["passed"], diagnostics
        rows = [json.loads(line) for line in (out / "capture/native-snapshots.jsonl").read_bytes().splitlines()]
        snapshots = [row["snapshot"] for row in rows]
        assert snapshots and snapshots[-1] == final
        assert all(s["process"]["pid"] == process["pid"] for s in snapshots)
        assert len({s["process"]["start_instant"] for s in snapshots}) == 1
        assert all(abs((time(s["process"]["start_instant"]) - time(process["created"])).total_seconds()) < 0.002 for s in snapshots)
        assert all(s["observation_errors"] == 0 for s in snapshots)
        assert all(time(a["timestamp"]) < time(b["timestamp"]) for a, b in zip(snapshots, snapshots[1:]))
        world = [s for s in snapshots if s["in_world"] and not s["paused"] and s["native_settled"]]
        assert world
        registrations = sorted({(s["registered_count"], s["registered_declarations"]) for s in world})
        log = log_bytes.decode("utf-8")
        assert "All dimensions are saved" in log and "Stopping!" in log
        declared = [int(n) for n in re.findall(r"Loaded (\d+) vehicles", log)]
        assert len(declared) == final["resource_epochs"]["completed"]
        assert set(declared) == {final["registered_declarations"]}
        before = read(out / "capture/reload-before-english.json")
        receipt = read(out / "capture/reload-receipt-english.json")
        before_age = (time(receipt["issued_at"]) - time(before["timestamp"])).total_seconds()
        assert before_age > 15
        write("reload-review.json", {
            "input_attempts": [read(out / "capture/reload-receipt-ime-active.json"), receipt],
            "preserved_before_files": ["capture/reload-before.json", "capture/reload-before-english.json"],
            "english_before_age_at_input_seconds": before_age,
            "maximum_strict_before_age_seconds": 15,
            "observed_new_native_epochs_after_startup": final["resource_epochs"]["completed"] - 1,
            "strict_accepted_reloads": 0,
            "reason": "The IME-active input has no new native epoch; the later native reload is visible, but its before record exceeds the required 15-second age. Preserve both attempts without retroactive approval."})
        recordings = []
        for path in sorted(instance.glob("*.jfr")):
            destination = out / "recordings" / path.name
            copy_file(path, destination)
            recordings.append({"name": path.name, "sha256": sha(destination), "bytes": destination.stat().st_size})
            command(path.stem + "-summary", [str(Path(plan["java"]).with_name("jfr.exe")), "summary", str(destination)])
        for exported in execution["exports"]:
            assert exported["status"] == "readable"
            assert sha(out / "recordings" / Path(exported["recording"]).name) == exported["sha256"]
        printed = command("acceptance-events", [str(Path(plan["java"]).with_name("jfr.exe")), "print", "--json", "--events",
                          metadata["frame_event"] + "," + metadata["server_tick_event"], str(out / "recordings/acceptance.jfr")], compressed=True)
        jfr_events = json.loads(printed)["recording"]["events"]
        counts = collections.Counter(event["type"] for event in jfr_events)
        assert counts[metadata["frame_event"]] > 0 and counts[metadata["server_tick_event"]] > 0
        frames = [e for e in jfr_events if e["type"] == metadata["frame_event"]]
        world_frames = [e for e in frames if e["values"]["inWorld"] and not e["values"]["paused"]]
        after = {name: sha(Path(name)) for name in observed}
        assert after == observed, "Original inputs changed during archive"
        report.update(status="sealed", ended=stamp(), input_fingerprints_after=after)
        write("archive-execution.json", report)
        assessment = {
            "timestamp": stamp(), "scope": report["scope"], "scope_passed": True,
            "pid": process["pid"], "process_created": process["created"],
            "normal_saved_exit": True, "exit_code": execution["exit_code"],
            "native_snapshot_count": len(snapshots), "distinct_snapshot_timestamps": len({s["timestamp"] for s in snapshots}),
            "first_snapshot": snapshots[0]["timestamp"], "last_snapshot": snapshots[-1]["timestamp"],
            "unpaused_settled_world_snapshots": len(world), "registrations": registrations,
            "native_observation_errors": 0, "native_epochs": final["resource_epochs"],
            "diagnostic_trace_events": len(events), "reviewed_native_log_lines": len(diagnostics["reviewed_native"]),
            "native_diagnostic_attribution_passed": diagnostics["native_attribution"]["passed"],
            "other_raw_errors": diagnostics["other_errors_requiring_contextual_review"],
            "prefix_complete_and_final_extends_prefix": completeness["passed"],
            "final_player": (final.get("world") or {}).get("player"),
            "caches": [{"id": item["resource_id"], "entries": [{"floors": len(e["floors"]), "doorways": len(e["doorways"])} for e in item["entries"]]} for item in final["cache_state"]["resources"]],
            "verified_source_and_installed_packs": len(bindings["packs"]), "bound_mods": bindings["mods"],
            "recordings": recordings, "jfr_event_counts": dict(counts),
            "unpaused_in_world_frame_events": len(world_frames),
            "jfr_first_event": jfr_events[0]["values"]["startTime"], "jfr_last_event": jfr_events[-1]["values"]["startTime"],
            "screenshots": inventory(out / "instance-final/screenshots"),
            "strict_accepted_reloads": 0, "observed_native_reloads_after_startup": final["resource_epochs"]["completed"] - 1,
            "full_gameplay_accepted": False, "performance_accepted": False, "whole_route_accepted": False,
            "limits": [
                "The three screenshot files show a platform/empty track view and do not establish train rendering, geometry, displays or boarding.",
                "The later F3+T has an actual second native epoch, but its before record is over 15 seconds old and earns no strict reload credit.",
                "This diagnostic run used Memory Saver 0.4.6; it does not validate candidate 0.4.7 runtime behavior.",
                "Background engineering, UI debugging, teleport commands and instrumented collection exclude controlled performance and route/endurance acceptance.",
                "Official MTR and resource packs are hash-bound in place; their large existing byte copies are not duplicated into this archive.",
                "Capture starts with available published snapshots after loading; snapshot absence during native work is not replaced by fabricated observations."]}
        write("assessment.json", assessment)
        copy_file(Path(__file__).resolve(), out / "archive.py")
        write("sha256.json", inventory(out))
        print(json.dumps({"scope_passed": True, "output": str(out), "native_snapshot_count": len(snapshots),
                          "native_epochs": final["resource_epochs"], "jfr_event_counts": dict(counts),
                          "recordings": recordings, "strict_accepted_reloads": 0}))
        return 0
    except BaseException as error:
        report.update(status="failed", ended=stamp(), error=repr(error))
        write("archive-execution.json", report)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
