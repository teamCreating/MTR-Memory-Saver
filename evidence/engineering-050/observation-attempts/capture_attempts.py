"""Preserve three terminal tool attempts and a read-only current collector prefix."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "capture-01"
ACCEPTANCE = REPO / ".cache/acceptance"
INSTANCE = ACCEPTANCE / "official-nf248-owned-049c"
COLLECTOR = ACCEPTANCE / "capture-owned-049c"
ATTEMPTS = {
    "startup": ACCEPTANCE / "owned-049c-startup",
    "reload-recorder": ACCEPTANCE / "owned-049c-reload-recorder",
    "reload-observation": ACCEPTANCE / "owned-049c-reload-observation",
}
sys.path.insert(0, str(REPO / "tools"))
import windows_snapshot_io


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")


def complete_jsonl(raw):
    end = raw.rfind(b"\n")+1
    return [json.loads(line) for line in raw[:end].splitlines() if line.strip()], len(raw)-end


def copy_file(source, target, *, append_prefix=False, snapshot=False):
    started = now()
    before = source.stat()
    if snapshot:
        raw = windows_snapshot_io.read_snapshot_bytes(source)
        handle_size_before = handle_size_after = None
    else:
        with source.open("rb") as stream:
            handle_size_before = os.fstat(stream.fileno()).st_size
            raw = stream.read(handle_size_before) if append_prefix else stream.read()
            handle_size_after = os.fstat(stream.fileno()).st_size
    completed = now()
    after = source.stat()
    if not append_prefix and not snapshot:
        assert before.st_size == after.st_size == len(raw)
        assert before.st_mtime_ns == after.st_mtime_ns, "Terminal input changed during capture: "+str(source)
    if append_prefix:
        assert len(raw) == handle_size_before and handle_size_after >= handle_size_before
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return raw, {"source": str(source), "target": target.relative_to(OUTPUT).as_posix(),
                 "started_at": started, "read_completed_at": completed, "bytes": len(raw), "sha256": sha(raw),
                 "source_path_size_before": before.st_size, "source_path_size_after": after.st_size,
                 "source_handle_size_before": handle_size_before, "source_handle_size_after": handle_size_after,
                 "append_prefix": append_prefix, "shared_snapshot_reader": snapshot}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    started, receipts = now(), []
    initial_names = {}
    for label, source in ATTEMPTS.items():
        initial_names[label] = [p.relative_to(source).as_posix() for p in sorted(source.rglob("*")) if p.is_file()]
        for relative in initial_names[label]:
            _, receipt = copy_file(source / relative, OUTPUT / "attempts" / label / relative)
            receipts.append(receipt)
        assert initial_names[label] == [p.relative_to(source).as_posix() for p in sorted(source.rglob("*")) if p.is_file()]
    for name in ("packaged-client-plan.json", "packaged-client-launch.json"):
        _, receipt = copy_file(INSTANCE / name, OUTPUT / "instance" / name)
        receipts.append(receipt)
    plan = json.loads((OUTPUT / "instance/packaged-client-plan.json").read_bytes())
    launch = json.loads((OUTPUT / "instance/packaged-client-launch.json").read_bytes())
    assert launch["plan_sha256"] == sha((OUTPUT / "instance/packaged-client-plan.json").read_bytes())
    assert Path(plan["instance"]).resolve() == INSTANCE.resolve() and launch["pid"] == 18796
    installed = []
    for mod in plan["mods"]:
        source = INSTANCE / "mods" / mod["filename"]
        if mod["role"] in {"observer", "companion"}:
            raw, receipt = copy_file(source, OUTPUT / "instance/mods" / mod["filename"])
            receipts.append(receipt)
            actual = sha(raw)
        else:
            before = source.stat()
            with source.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            after = source.stat()
            assert before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
        assert actual == mod["sha256"], "Installed mod differs from frozen plan"
        installed.append({**mod, "actual_sha256": actual, "copied": mod["role"] in {"observer", "companion"}})
    observer = next(item for item in installed if item["role"] == "observer")
    with zipfile.ZipFile(OUTPUT / "instance/mods" / observer["filename"]) as jar:
        metadata = json.loads(jar.read("mtr-native-observer-target.json"))
    assert metadata["observer_version"] == "1.0.3"
    assert plan["artifact"]["version"] == "0.4.7"
    write(OUTPUT / "instance/installed-bindings.json", {"mods": installed, "observer_metadata": metadata,
        "product_manifest_from_plan": plan["artifact"], "packs": "Plan declarations only; packs were neither recopied nor rehashed by this audit."})
    # These files belong to the launcher/collector, not to either fresh attempt02.
    for name in ("execution.json", "native-snapshots.jsonl", "packaged-client-plan.json", "packaged-client-launch.json"):
        _, receipt = copy_file(COLLECTOR / name, OUTPUT / "collector-checkpoint" / name,
                               append_prefix=name == "native-snapshots.jsonl")
        receipts.append(receipt)
    collector = json.loads((OUTPUT / "collector-checkpoint/execution.json").read_bytes())
    for name, expected in collector["sources"].items():
        raw, receipt = copy_file(REPO / "tools" / name, OUTPUT / "collector-checkpoint/sources" / name)
        receipts.append(receipt)
        assert sha(raw) == expected
    for name in (metadata["snapshot_path"], metadata["epochs_path"], metadata["diagnostics_path"], "logs/latest.log"):
        _, receipt = copy_file(INSTANCE / name, OUTPUT / "instance-checkpoint" / name,
                               snapshot=name == metadata["snapshot_path"], append_prefix=name != metadata["snapshot_path"])
        receipts.append(receipt)
    snapshot = json.loads((OUTPUT / "instance-checkpoint" / metadata["snapshot_path"]).read_bytes())
    assert snapshot["pid"] == launch["pid"] and snapshot["target"] == metadata
    assert collector["pid"] == launch["pid"]
    assert "ended" not in collector and "exit_code" not in collector
    startup = OUTPUT / "attempts/startup"
    assert not (startup / "summary.json").exists()
    samples, partial_sample_bytes = complete_jsonl((startup / "samples.jsonl").read_bytes())
    recorder_rows, recorder_partial = complete_jsonl((OUTPUT / "attempts/reload-recorder/journal.jsonl").read_bytes())
    assert recorder_partial == 0 and recorder_rows[-1]["event"]["kind"] == "initialization_failed"
    assert "TimeoutExpired" in recorder_rows[-1]["event"]["error"] and ", 20)" in recorder_rows[-1]["event"]["error"]
    reload_summary = json.loads((OUTPUT / "attempts/reload-observation/summary.json").read_bytes())
    assert reload_summary["status"] == "preflight_failed" and not reload_summary["passed"]
    assert "timed out after 20 seconds" in reload_summary["error"]
    assert (OUTPUT / "attempts/reload-observation/samples.jsonl").stat().st_size == 0
    collector_samples, partial_collector_bytes = complete_jsonl((OUTPUT / "collector-checkpoint/native-snapshots.jsonl").read_bytes())
    report = {"recorded_at": now(), "origin": "Parent agent messages in the current chat; not an independently preserved tool receipt or process-exit observation.",
              "startup": {"reported_session_id": 3751, "reported_input": {"chars": "\u0003"},
                          "reported_initial_input_result": "Session remained running; final empty poll returned exit_code 1.",
                          "final_tool_response_as_reported": {"chunk_id": "c23302", "wall_time_seconds": 0.0000232,
                              "exit_code": 1, "original_token_count": 0, "output": ""},
                          "actual_exit_timestamp": None, "independent_exit_cause_proven": False,
                          "reported_cadence_seconds": 1},
              "reload_recorder": {"reported_exit_code": 1, "raw_tool_receipt_available": False},
              "reload_observation": {"reported_exit_code": 1, "raw_tool_receipt_available": False}}
    write(OUTPUT / "parent-reported-tool-results.json", report)
    assessment = {"started_at": started, "ended_at": now(), "evidence_capture_completed": True,
                  "client_pid_from_frozen_launch_and_native_snapshot": launch["pid"],
                  "startup": {"summary_present": False, "retained_complete_sample_lines": len(samples),
                              "trailing_partial_bytes": partial_sample_bytes, "accepted": False,
                              "status": "Interrupted terminal attempt; reported tool exit 1; no complete result."},
                  "reload_recorder": {"terminal_journal_event": recorder_rows[-1]["event"], "accepted": False},
                  "reload_observation": {"status": reload_summary["status"], "accepted": False},
                  "collector_checkpoint": {"status_as_captured": collector["status"], "retained_complete_snapshot_lines": len(collector_samples),
                                           "trailing_partial_bytes": partial_collector_bytes,
                                           "process_exit_proven": False, "checkpoint_only": True},
                  "instance_checkpoint": {"timestamp": snapshot["timestamp"], "observation_errors": snapshot.get("observation_errors"),
                                          "later_checkpoint_not_an_attempt_completion": True},
                  "scope": "Preserve failed/interrupted observer attempts and identities only. Fresh attempt02 excluded. No startup/reload/gameplay/performance/exit acceptance.",
                  "read_receipts": receipts}
    write(OUTPUT / "assessment.json", assessment)
    for label, source in ATTEMPTS.items():
        for relative in initial_names[label]:
            assert sha((source / relative).read_bytes()) == sha((OUTPUT / "attempts" / label / relative).read_bytes())
    print(json.dumps({"evidence_capture_completed": True, "pid": launch["pid"], "startup_samples_retained": len(samples),
                      "collector_samples_checkpoint": len(collector_samples), "raw_read_receipts": len(receipts),
                      "instance_observation_errors_at_checkpoint": snapshot.get("observation_errors")}))


if __name__ == "__main__":
    main()
