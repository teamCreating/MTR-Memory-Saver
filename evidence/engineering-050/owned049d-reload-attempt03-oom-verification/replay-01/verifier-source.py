"""Replay the final OOM failure and three separately bounded historical prefixes."""
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


def check(value, message):
    if not value:
        raise ValueError(message)


def compact(records, observations):
    values = []
    for record in records:
        native = record.get("native_epoch", {})
        settled = next((row["raw_state"] for row in observations if row.get("state_sha256") == native.get("settled_state_sha256")), {})
        values.append({"event_id": record["event"]["event_id"], "input_issued_at": record["event"]["input"]["issued_at"],
            "verified": record["verified"], "failures": record["failures"], "sequence": record.get("sequence"),
            "head": native.get("start", {}).get("timestamp"), "returned": native.get("returned", {}).get("timestamp"),
            "return_monotonic_nanos": native.get("returned", {}).get("monotonic_nanos"),
            "settled": native.get("settled_timestamp"), "settled_state_sha256": native.get("settled_state_sha256"),
            "settled_capture_started_monotonic_nanos": settled.get("capture_started_monotonic_nanos"),
            "declared_vehicle_count": record.get("declared_vehicle_count")})
    return values


def verify():
    index = read(HERE / "sha256-index.json")["files"]
    actual = {p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file() and p.name != "sha256-index.json" and "__pycache__" not in p.parts}
    check(actual == set(index), "Payload inventory differs.")
    for name, expected in index.items():
        raw = (HERE / name).read_bytes()
        check(len(raw) == expected["bytes"] and sha(raw) == expected["sha256"], "Payload changed: " + name)
    base = HERE / "capture-01"
    for receipt in read(base / "read-receipts.json")["reads"]:
        raw = (base / receipt["destination"]).read_bytes()
        check(len(raw) == receipt["bytes"] and sha(raw) == receipt["sha256"], "Timed original copy differs.")
    obs, rec = base / "observer", base / "recorder"
    context, summary = read(rec / "session-start.json"), read(obs / "summary.json")
    for original, expected in context["source_sha256"].items():
        check(sha((rec / "sources" / Path(original).name).read_bytes()) == expected, "Frozen recorder source differs.")
    sys.path.insert(0, str(rec / "sources"))
    import reload_before_recorder as recorder
    import observe_packaged_client as observer
    import native_log_stream as logs
    import native_diagnostic_review as diagnostics
    observer.NEUTRAL_CONTRACT_FILE = rec / "sources/native-observer-consumer.json"
    check(sha((obs / "observer-source.py").read_bytes()) == summary["source_sha256"] == summary["current_source_sha256"], "Consumer source pin differs.")
    for field in ("native_log_source_sha256", "neutral_source_sha256"):
        for original, expected in summary[field].items():
            check(sha((obs / Path(original).name).read_bytes()) == expected, "Consumer dependency pin differs.")
    check(not summary["source_changed_during_observation"] and not summary["neutral_sources_changed"] and not summary["native_log_sources_changed"], "Source drift was recorded.")
    journal_raw = (rec / "journal.jsonl").read_bytes()
    journal = recorder.verify_journal(journal_raw)
    end = read(rec / "session-end.json")
    check(end["status"] == "stopped" and end["process_handle_closed"] and end["journal_sha256"] == sha(journal_raw), "Recorder stopped boundary differs.")
    check(journal[-1]["event"]["kind"] == "stopped" and journal[-1]["event"]["reason"] == "stop_request", "Recorder did not stop by request.")
    inputs = recorder.input_events(rec)
    check(len(inputs) == 4 and all(row["record_status"] == "selected" and row["input"]["succeeded"] is True for row in inputs), "The four original inputs were changed or omitted.")
    check((rec / "inputs.jsonl").read_bytes() == (obs / "external-input-events-at-completion.jsonl").read_bytes(), "Consumer ledger export differs.")
    for number, event in enumerate(inputs, 1):
        check(sha((base / "ui" / f"reload-{number:03d}.json").read_bytes()) == event["external_receipt_sha256"], "UI/input receipt differs.")
    binding = read(base / "history-bindings.json")
    retained = {int(p.name) for p in (rec / "records").iterdir()}
    check(retained == set(binding["retained_record_numbers"]) and len(retained) == 8, "Recorder record scope expanded or lost a dependency.")
    for number in retained:
        for row in recorder.json_lines((rec / "records" / f"{number:08d}" / "raw-evidence.jsonl").read_bytes()):
            raw = (rec / row["path"]).read_bytes()
            check(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "Retained raw capture differs.")
        folder = rec / "records" / f"{number:08d}"
        if (folder / "before.json").exists():
            before_raw, receipt_raw = (folder / "before.json").read_bytes(), (folder / "receipt.json").read_bytes()
            before, receipt = json.loads(before_raw), json.loads(receipt_raw)
            published = [row["event"] for row in journal if row["event"]["kind"] == "published" and row["event"]["record_id"] == before["event_id"]]
            check(len(published) == 1 and published[0]["receipt_sha256"] == sha(receipt_raw) and receipt["payload_sha256"] == sha(before_raw), "Historical publication/body receipt differs.")
    stop_bytes = (obs / "stop-request-captured.bin").read_bytes()
    stop_receipt = read(obs / "stop-request-receipt.json")
    check(stop_bytes == (obs / "stop-request").read_bytes() and sha(stop_bytes) == stop_receipt["sha256"] == summary["stop_request"]["sha256"], "Captured stop request differs.")
    check(len(stop_bytes) == stop_receipt["bytes"] and summary["auxiliary_shutdown"]["worker_stopped"] and not summary["auxiliary_shutdown"]["uncompleted_request_ids"], "Stop length or auxiliary close differs.")
    check(sha((obs / "stop-request-receipt.json").read_bytes()) == summary["stop_request"]["receipt_sha256"], "Consumer stop receipt differs.")
    reference = summary["native_log_stream"]
    check(sha((obs / "native-log" / reference["receipt"]).read_bytes()) == reference["receipt_sha256"], "Completion log receipt pin differs.")
    log = logs.verify_capture(obs / "native-log", obs / "native-log" / reference["receipt"])
    check(log == (obs / "native-log-at-completion.log").read_bytes() and sha(log) == summary["log_sha256_at_completion"], "Final complete log differs.")
    samples = recorder.json_lines((obs / "samples.jsonl").read_bytes())
    observations = [row["observation"] for row in samples if row.get("observation", {}).get("verified")]
    check(len(samples) == summary["sample_count"] and len(observations) == summary["verified_sample_count"], "Sample counts differ.")
    check(all(row["process"]["running"] for row in samples), "A game process exit was recorded.")
    baseline = observations[0]["state"]["resource_epochs"]["last_completed_sequence"]
    epochs = recorder.json_lines((obs / "native-epoch-events-at-completion.jsonl").read_bytes())
    native_diagnostics = recorder.json_lines((obs / "native-diagnostic-events-at-completion.jsonl").read_bytes())
    check(len(epochs) == 10 and {row["sequence"] for row in epochs} == set(range(1, 6)), "Startup and four full epoch pairs were not preserved.")
    launch, plan = read(rec / "packaged-client-launch.json"), read(rec / "packaged-client-plan.json")
    metadata, review = read(obs / "observer-target.json"), read(obs / "native-diagnostic-review.json")
    diagnostics.validate_review(review, metadata, root=base / "proof-root")
    def replay(raw_log, events, raw_epochs, raw_diagnostics, eligible, finish):
        return observer.neutral_reload_evidence(raw_log, events, raw_epochs, raw_diagnostics, eligible, baseline,
            launch, context["process"], context["expected_registration"]["distinct_ids"], context["expected_registration"]["declarations"],
            metadata, review, plan["timestamp"], finish)
    results, diagnostic_result = replay(log, inputs, epochs, native_diagnostics, observations, summary["ended"])
    check(results == summary["reload_evidence"] and diagnostic_result == summary["native_diagnostics"], "Final whole-prefix failed replay differs.")
    check(summary["status"] == "stopped" and summary["passed"] is False and summary["verified_reload_count"] == summary["longest_verified_reload_run"] == 0 and all(not row["verified"] for row in results), "The final failed session was promoted.")
    oom = [row for row in diagnostic_result["unreviewed_native"] if "java.lang.OutOfMemoryError" in row["text"]]
    check(len(oom) == 2, "The two original heap-space exceptions were lost.")
    last_number = binding["last_ineligible_record_number"]
    last = next(row["event"] for row in reversed(journal) if row["event"]["kind"] == "ineligible")
    check(int(last["record_id"].rsplit(":", 1)[1]) == last_number, "Last ineligible identity differs.")
    raw_map = {row["name"]: (rec / row["path"]).read_bytes() for row in recorder.json_lines((rec / "records" / f"{last_number:08d}" / "raw-evidence.jsonl").read_bytes())}
    last_log = logs.verify_capture(rec / "native-log", rec / "native-log" / binding["last_ineligible_log_receipt"])
    check(last_log == raw_map["client-log-prefix.log"] and log.startswith(last_log), "Last ineligible complete raw log differs.")
    errors = recorder.before_errors(json.loads(raw_map["native-snapshot.json"]), context["process"], last["capture_completed_at"],
        context["expected_registration"], metadata, last_log.decode("utf-8"), recorder.json_lines(raw_map["epochs-after.jsonl"]),
        recorder.json_lines(raw_map["diagnostics-after.jsonl"]), review, plan)
    check("; ".join(errors) == last["error"], "Last ineligible diagnostic reason does not replay.")
    historical = []
    for item in binding["histories"]:
        saved = read(base / item["result"])
        prefixes = {}
        for spec in item["exact_prefixes"]:
            raw = (base / spec["final_payload"]).read_bytes()[spec["offset"]:spec["offset"] + spec["bytes"]]
            check(len(raw) == spec["bytes"] and sha(raw) == spec["sha256"], "A historical owned prefix was changed.")
            prefixes[spec["final_payload"]] = raw
        recorder.verify_journal(prefixes["recorder/journal.jsonl"])
        historical_inputs = recorder.json_lines(prefixes["recorder/inputs.jsonl"])
        historical_samples = recorder.json_lines(prefixes["observer/samples.jsonl"])
        historical_observations = [row["observation"] for row in historical_samples if row.get("observation", {}).get("verified")]
        record = read(rec / "records" / f"{item['record_number']:08d}" / "before.json")
        ref = record["native_log_stream"]
        historical_log = logs.verify_capture(rec / "native-log", rec / "native-log" / ref["receipt"])
        check(log.startswith(historical_log) and sha(historical_log) == record["log_prefix_sha256"], "Historical logical prefix is not exact.")
        historical_results, historical_diagnostics = replay(historical_log, historical_inputs,
            recorder.json_lines((rec / record["raw_files"]["epochs-after.jsonl"]).read_bytes()),
            recorder.json_lines((rec / record["raw_files"]["diagnostics-after.jsonl"]).read_bytes()), historical_observations, saved["latest_sample_timestamp"])
        check(compact(historical_results, historical_observations) == saved["reloads"], "Historical per-prefix reload replay differs.")
        check(sum(row["verified"] for row in historical_results) == item["verified_count"] == saved["verified_reload_count"] and historical_diagnostics["native_attribution"]["passed"] and not historical_diagnostics["unreviewed_native"], "Historical pass scope differs.")
        check(sha((base / "operators/evaluate_once.py").read_bytes()) == saved["program_sha256"], "Historical evaluator source pin differs.")
        historical.append({"verified_count": item["verified_count"], "samples": len(historical_samples), "log_bytes": len(historical_log), "replay_exact": True})
    deadline = read(base / "waiter/deadline-four/execution.json")
    check(deadline["status"] == "deadline_elapsed" and deadline["returned_exit_code"] == 1 and deadline["latest_result"] is None, "The failed waiter boundary was changed.")
    check(sha((base / "operators/wait_ready.py").read_bytes()) == deadline["source_sha256"] == sha((base / "waiter/deadline-four/wait-source.py").read_bytes()), "Original waiter source was changed.")
    change = read(base / "ui/controller-change-v2.json")
    check(sha((base / "ui/controller-source.js").read_bytes()) == change["old_source_sha256"] and sha((base / "ui/controller-source-v2.js").read_bytes()) == change["new_source_sha256"], "Actor v1/v2 correction record differs.")
    for mod in read(base / "installed-fingerprints.json"):
        expected = next(row for row in plan["mods"] if row["filename"] == mod["filename"])
        check(mod["actual_sha256"] == expected["sha256"] and mod["binary_copied"] is False, "Installed artifact fingerprint manifest differs.")
    export = read(base / "collector-checkpoint/execution.json")["exports"][-1]
    check(export["status"] == "readable" and all(row["exit_code"] == 0 for row in export["commands"]) and export["recording"].endswith("diagnostic-02.jfr"), "The post-OOM JFR export did not complete.")
    return {"verified_at": dt.datetime.now(dt.timezone.utc).isoformat(), "passed": True, "payloads": len(index),
        "index_sha256": sha((HERE / "sha256-index.json").read_bytes()), "inputs": len(inputs), "epoch_rows": len(epochs),
        "samples": len(samples), "verified_samples": len(observations), "journal_rows": len(journal),
        "retained_recorder_records": sorted(retained), "final_verified_reload_count": 0, "historical_prefix_replays": historical,
        "final_whole_prefix_replay_exact": True, "final_log_bytes": len(log), "oom_exception_lines": [row["line"] for row in oom],
        "last_ineligible_errors": errors, "original_waiter_deadline_preserved": True, "post_oom_jfr_manifest_sha256": export["sha256"],
        "jfr_binary_copied_or_rehashed": False,
        "scope": "Sealed failure integrity/replay only. The final four-input session is unaccepted; historical three-prefix results do not grant whole-session, route, performance, JFR coverage or game-exit acceptance."}


if __name__ == "__main__":
    result = verify()
    with Path(sys.argv[1]).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result))
