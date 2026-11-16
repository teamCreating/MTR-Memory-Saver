"""Independently verify the sealed prior diagnostic run; never read a live JVM."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def instant(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sealed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sealed, output = args.sealed.resolve(), args.output.resolve()
    assert not output.exists() and not output.is_relative_to(sealed)
    index = read(sealed / "sha256.json")
    actual = {p.relative_to(sealed).as_posix(): sha(p) for p in sealed.rglob("*")
              if p.is_file() and p != sealed / "sha256.json"}
    assert actual == index, "Sealed payload inventory differs"
    assessment = read(sealed / "assessment.json")
    archive = read(sealed / "archive-execution.json")
    capture = read(sealed / "capture/execution.json")
    assert archive["status"] == "sealed" and archive["input_fingerprints_before"] == archive["input_fingerprints_after"]
    assert capture["status"] == "exited" and capture["exit_code"] == 0 and not capture["capture_errors"]
    for relative, expected in capture["files"].items():
        assert sha(sealed / "capture" / relative) == expected, relative
    prefix_index = read(sealed / "prefix-parent-sha256.json")
    assert prefix_index["schema"] == 1
    prefix_files = [p for p in (sealed / "prefix").rglob("*") if p.is_file()]
    for path in prefix_files:
        entry = prefix_index["files"]["capture-02/" + path.relative_to(sealed / "prefix").as_posix()]
        assert sha(path) == entry["sha256"] and path.stat().st_size == entry["bytes"], path
    plan, launch = read(sealed / "capture/packaged-client-plan.json"), read(sealed / "capture/packaged-client-launch.json")
    process = read(sealed / "prefix/process.json")
    assert capture["pid"] == launch["pid"] == process["pid"] == assessment["pid"]
    assert sha(sealed / "capture/packaged-client-plan.json") == launch["plan_sha256"]
    assert plan["artifact"]["version"] == "0.4.6"
    assert plan["artifact"]["target"] == "official-nf248"
    log = (sealed / "capture/logs/latest.log").read_bytes()
    assert log.startswith((sealed / "prefix/logs/latest.log").read_bytes())
    assert b"All dimensions are saved" in log and b"Stopping!" in log
    sys.path.insert(0, str(sealed / "prefix/sources/tools"))
    from client_experiment_analysis import client_log_completeness, native_diagnostics
    from native_diagnostic_review import review_diagnostics, validate_review
    metadata = read(sealed / "prefix/observer-target.json")
    review = read(sealed / "prefix/sources/config/native-diagnostic-review.json")
    validate_review(review, metadata, root=sealed / "proofs")
    old_capture = read(sealed / "prefix/capture.json")
    prefix_review = client_log_completeness((sealed / "prefix/logs/latest.log").read_bytes(),
                                          [{"client_log_witness": old_capture["stream_captures"]["logs/latest.log"]}],
                                          Path(plan["instance"]))
    assert prefix_review["passed"]
    events = [json.loads(line) for line in (sealed / "capture/game-probe/native-invalid-model.jsonl").read_bytes().splitlines()]
    epochs = [json.loads(line) for line in (sealed / "capture/game-probe/native-resource-epochs.jsonl").read_bytes().splitlines()]
    final = read(sealed / "capture/game-probe/native-observer.json")
    text = log.decode("utf-8")
    replay = review_diagnostics(native_diagnostics(text), text, events, epochs, process, metadata,
                                review, read(sealed / "run-window.json"), final)
    assert replay == read(sealed / "diagnostic-review.json")
    assert replay["native_attribution"]["passed"] and not replay["unreviewed_native"]
    rows = [json.loads(line)["snapshot"] for line in (sealed / "capture/native-snapshots.jsonl").read_bytes().splitlines()]
    assert len(rows) == assessment["native_snapshot_count"] and rows[-1] == final
    assert all(row["process"]["pid"] == process["pid"] and row["observation_errors"] == 0 for row in rows)
    assert all(instant(a["timestamp"]) < instant(b["timestamp"]) for a, b in zip(rows, rows[1:]))
    world = [row for row in rows if row["in_world"] and not row["paused"] and row["native_settled"]]
    assert len(world) == assessment["unpaused_settled_world_snapshots"]
    assert sorted({(row["registered_count"], row["registered_declarations"]) for row in world}) == [tuple(v) for v in assessment["registrations"]]
    reload_review = read(sealed / "reload-review.json")
    before = read(sealed / "capture/reload-before-english.json")
    receipt = read(sealed / "capture/reload-receipt-english.json")
    age = (instant(receipt["issued_at"]) - instant(before["timestamp"])).total_seconds()
    assert age == reload_review["english_before_age_at_input_seconds"] and age > 15
    assert reload_review["strict_accepted_reloads"] == assessment["strict_accepted_reloads"] == 0
    assert final["resource_epochs"] == assessment["native_epochs"]
    assert not any(assessment[name] for name in ("full_gameplay_accepted", "performance_accepted", "whole_route_accepted"))
    for recording in assessment["recordings"]:
        path = sealed / "recordings" / recording["name"]
        assert sha(path) == recording["sha256"] and path.stat().st_size == recording["bytes"]
    printed = gzip.decompress((sealed / "acceptance-events.json.gz").read_bytes())
    export = next(c for c in archive["commands"] if c["stdout_file"] == "acceptance-events.json.gz")
    assert hashlib.sha256(printed).hexdigest() == export["uncompressed_stdout_sha256"]
    jfr_events = json.loads(printed)["recording"]["events"]
    counts = dict(collections.Counter(event["type"] for event in jfr_events))
    assert counts == assessment["jfr_event_counts"]
    assert len([e for e in jfr_events if e["type"] == metadata["frame_event"] and e["values"]["inWorld"] and not e["values"]["paused"]]) == assessment["unpaused_in_world_frame_events"]
    event_times = [e["values"]["startTime"] for e in jfr_events]
    report = {"timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "passed": True,
              "scope": assessment["scope"], "sealed_payloads_verified": len(actual),
              "prefix_payloads_verified": len(prefix_files), "frozen_diagnostic_replay_equal": True,
              "native_snapshot_count": len(rows), "unpaused_settled_world_snapshots": len(world),
              "jfr_event_counts": counts,
              "jfr_min_event_time": min(event_times, key=instant), "jfr_max_event_time": max(event_times, key=instant),
              "english_before_age_seconds": age, "strict_accepted_reloads": 0,
              "original_sealed_index_sha256": sha(sealed / "sha256.json"),
              "verifier_sha256": sha(Path(__file__))}
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
