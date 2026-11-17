"""Replay this one failed attempt using only its preserved minimal closure."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify():
    index = read(HERE / "sha256-index.json")["files"]
    actual = {p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file() and p.name != "sha256-index.json" and "__pycache__" not in p.parts}
    check(actual == set(index), "Sealed payload inventory differs.")
    for name, expected in index.items():
        raw = (HERE / name).read_bytes()
        check(len(raw) == expected["bytes"] and sha(raw) == expected["sha256"], "Payload changed: " + name)
    base = HERE / "capture-01"
    for receipt in read(base / "read-receipts.json")["reads"]:
        raw = (base / receipt["destination"]).read_bytes()
        check(len(raw) == receipt["bytes"] and sha(raw) == receipt["sha256"], "Read-timed original copy differs.")
    obs, rec = base / "observer", base / "recorder"
    sys.path.insert(0, str(rec / "sources"))
    import reload_before_recorder as recorder
    import observe_packaged_client as observer
    import native_diagnostic_review as diagnostic
    import native_log_stream as logs
    summary, context = read(obs / "summary.json"), read(rec / "session-start.json")
    check(summary["status"] == "stopped" and summary["passed"] is False and summary["error"] is None, "Terminal observation scope differs.")
    check(not summary["source_changed_during_observation"] and not summary["native_log_sources_changed"] and not summary["neutral_sources_changed"], "Observation recorded changed sources.")
    check(sha((obs / "observer-source.py").read_bytes()) == summary["source_sha256"] == summary["current_source_sha256"], "Observer source pin differs.")
    for field in ("native_log_source_sha256", "neutral_source_sha256"):
        for source, expected in summary[field].items():
            check(sha((obs / Path(source).name).read_bytes()) == expected, "Frozen consumer dependency differs.")
    check(sha((obs / "windows_snapshot_io.py").read_bytes()) == summary["snapshot_io_source_sha256"], "Snapshot reader pin differs.")
    journal_raw = (rec / "journal.jsonl").read_bytes()
    journal = recorder.verify_journal(journal_raw)
    end = read(rec / "session-end.json")
    check(sha(journal_raw) == end["journal_sha256"] and end["status"] == "stopped" and end["process_handle_closed"], "Recorder did not preserve its stopped boundary.")
    check(journal[-1]["event"]["kind"] == "stopped" and journal[-1]["event"]["reason"] == "stop_request", "Recorder terminal journal differs.")
    check({p.name for p in (rec / "records").iterdir()} == {"00000044"}, "Unselected recorder payloads were copied.")
    inputs = recorder.input_events(rec)
    check(len(inputs) == 1 and inputs[0]["record_status"] == "selected" and inputs[0]["input"]["succeeded"] is True, "Original selected input differs.")
    check((rec / "inputs.jsonl").read_bytes() == (obs / "external-input-events-at-completion.jsonl").read_bytes(), "Consumer input export differs.")
    captured = (obs / "stop-request-captured.bin").read_bytes()
    stop_receipt = read(obs / "stop-request-receipt.json")
    check(captured == (obs / "stop-request").read_bytes(), "Stop-request captured bytes differ.")
    check(sha(captured) == stop_receipt["sha256"] == summary["stop_request"]["sha256"] and len(captured) == stop_receipt["bytes"], "Stop-request byte/length pin differs.")
    check(sha((obs / "stop-request-receipt.json").read_bytes()) == summary["stop_request"]["receipt_sha256"], "Stop receipt pin differs.")
    check(summary["auxiliary_shutdown"]["worker_stopped"] and not summary["auxiliary_shutdown"]["uncompleted_request_ids"], "Auxiliary close was incomplete.")
    log_root = obs / "native-log"
    reference = summary["native_log_stream"]
    check(sha((log_root / reference["receipt"]).read_bytes()) == reference["receipt_sha256"], "Final native-log receipt pin differs.")
    log = logs.verify_capture(log_root, log_root / reference["receipt"])
    check(log == (obs / "native-log-at-completion.log").read_bytes(), "Final log does not reconstruct from original bytes.")
    check(len(log) == inputs[0]["log_offset"] and sha(log) == inputs[0]["log_prefix_sha256"] == summary["log_sha256_at_completion"], "Input-to-stop unchanged log frontier differs.")
    samples = [json.loads(line) for line in (obs / "samples.jsonl").read_bytes().splitlines()]
    observations = [sample["observation"] for sample in samples]
    check(len(samples) == summary["sample_count"] == summary["verified_sample_count"] and all(item["verified"] for item in observations), "Sample verification/count differs.")
    check(all(sample["process"]["running"] for sample in samples), "A sampled process exit was recorded.")
    pid = summary["process_identity"]["pid"]
    check(pid == context["process"]["pid"] == read(rec / "packaged-client-launch.json")["pid"], "Process binding differs.")
    epochs = recorder.json_lines((obs / "native-epoch-events-at-completion.jsonl").read_bytes())
    check(len(epochs) == 2 and {event["sequence"] for event in epochs} == {summary["baseline_completed_epoch_sequence"]}, "There was a post-baseline native epoch.")
    metadata, review = read(obs / "observer-target.json"), read(obs / "native-diagnostic-review.json")
    diagnostic.validate_review(review, metadata, root=base / "proof-root")
    result, attribution = observer.neutral_reload_evidence(log, inputs, epochs,
        recorder.json_lines((obs / "native-diagnostic-events-at-completion.jsonl").read_bytes()), observations,
        summary["baseline_completed_epoch_sequence"], read(rec / "packaged-client-launch.json"), context["process"],
        context["expected_registration"]["distinct_ids"], context["expected_registration"]["declarations"], metadata, review,
        read(rec / "packaged-client-plan.json")["timestamp"], summary["ended"])
    check(result == summary["reload_evidence"] and attribution == summary["native_diagnostics"], "Frozen failed-reload/diagnostic replay differs.")
    check(not result[0]["verified"] and summary["verified_reload_count"] == summary["longest_verified_reload_run"] == 0, "An unobserved reload was promoted.")
    execution = read(base / "collector-checkpoint/execution.json")
    export = execution["exports"][0]
    check(export["status"] == "readable" and all(command["exit_code"] == 0 for command in export["commands"]), "Exporter did not record successful dump/summary.")
    check(export["sha256"] == read(HERE / "parent-reported-results.json")["jfr_expected_sha256"], "Exporter/parent JFR manifest fingerprints disagree.")
    check(b'Dumped recording "acceptance"' in (base / "collector-checkpoint/export-01-dump.stdout.log").read_bytes(), "Original dump output differs.")
    jfr_summary = (base / "collector-checkpoint/export-01-summary.stdout.log").read_text(encoding="utf-8")
    check("Duration:" in jfr_summary and "mtrtest.ClientFrame" in jfr_summary and "mtrtest.ServerTick" in jfr_summary, "Original JFR summary is missing.")
    return {"verified_at": dt.datetime.now(dt.timezone.utc).isoformat(), "passed": True,
        "payloads": len(index), "index_sha256": sha((HERE / "sha256-index.json").read_bytes()), "pid": pid,
        "samples": len(samples), "journal_rows": len(journal), "copied_recorder_records": ["00000044"],
        "log_bytes": len(log), "log_unchanged_after_input": True, "verified_reloads": 0,
        "failed_reload_replay_exact": True, "diagnostic_replay_exact": True, "stop_receipt_verified": True,
        "jfr_exporter_manifest_sha256": export["sha256"], "jfr_binary_copied_or_rehashed_by_this_verifier": False,
        "scope": "Sealed-only failure-boundary verification. Passing this verifier does not pass the failed reload, input delivery, route, performance, full JFR replay or game exit."}


if __name__ == "__main__":
    result = verify()
    path = Path(sys.argv[1])
    with path.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(json.dumps(result))
