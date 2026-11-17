"""Replay the failed seventh reload and six separately bounded prior prefixes.

Reads only this seal and the named tracked original 0.4.8 artifact/source seal.
No original instance, process API, JFR, growing collector or game input is used.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]


def read(path):
    return json.loads(path.read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check(value, message):
    if not value:
        raise ValueError(message)


def name(value):
    return PurePosixPath(str(value).replace("\\", "/")).name


def verify():
    index = read(HERE / "sha256-index.json")["files"]
    actual = {p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file() and p.name != "sha256-index.json"}
    check(actual == set(index), "Payload inventory differs")
    for path, expected in index.items():
        raw = (HERE / path).read_bytes()
        check(len(raw) == expected["bytes"] and sha(raw) == expected["sha256"], "Payload changed: " + path)
    base = HERE / "capture-01"
    for receipt in read(base / "read-receipts.json")["reads"]:
        raw = (base / receipt["destination"]).read_bytes()
        check(len(raw) == receipt["bytes"] and sha(raw) == receipt["sha256"] and receipt["before_mtime_ns"] == receipt["after_mtime_ns"], "Original read-time copy differs")
    rec, obs = base / "recorder", base / "observer"
    summary, context, binding = read(obs / "summary.json"), read(rec / "session-start.json"), read(base / "closure-bindings.json")
    sys.path.insert(0, str(base / "operators"))
    import wait_reload_ready as core
    core.ROOT = base / "proof-root"
    check(sha((base / "operators/wait_reload_ready.py").read_bytes()) == read(base / "waiters/001/execution.json")["source_sha256"], "Original waiter source differs")
    with core.FrozenProducer(rec, obs) as producer:
        journal_raw = (rec / "journal.jsonl").read_bytes()
        journal = producer.rec.verify_journal(journal_raw)
        end = read(rec / "session-end.json")
        check(end["status"] == "stopped" and end["process_handle_closed"] and end["journal_sha256"] == sha(journal_raw), "Recorder close boundary differs")
        check(journal[-1]["event"]["kind"] == "stopped" and journal[-1]["event"]["reason"] == "stop_request", "Recorder did not stop by request")
        inputs = producer.rec.input_events(rec)
        check(len(inputs) == 7 and all(row["record_status"] == "selected" and row["input"]["succeeded"] is True for row in inputs), "Seven original inputs were lost or changed")
        check((rec / "inputs.jsonl").read_bytes() == (obs / "external-input-events-at-completion.jsonl").read_bytes(), "Consumer input export differs")
        for number, event in enumerate(inputs, 1):
            check(sha((base / "ui" / f"reload-{number:03d}.json").read_bytes()) == event["external_receipt_sha256"], "Original UI/input receipt differs")
        retained = {int(p.name) for p in (rec / "records").iterdir()}
        check(retained == set(binding["retained_record_numbers"]) and len(retained) == 14, "Minimal record closure differs")
        for number in retained:
            folder = rec / "records" / f"{number:08d}"
            for row in producer.rec.json_lines((folder / "raw-evidence.jsonl").read_bytes()):
                raw = producer.rec.owned_path(rec, row["path"]).read_bytes()
                check(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "Raw record/blob differs")
            if (folder / "before.json").exists():
                body, publication = (folder / "before.json").read_bytes(), (folder / "receipt.json").read_bytes()
                record = json.loads(body)
                events = [row["event"] for row in journal if row["event"]["kind"] == "published" and row["event"]["record_id"] == record["event_id"]]
                check(len(events) == 1 and events[0]["receipt_sha256"] == sha(publication) and json.loads(publication)["payload_sha256"] == sha(body), "Closed publication/body differs")
                ref = record["native_log_stream"]
                check(sha((rec / "native-log" / ref["receipt"]).read_bytes()) == ref["receipt_sha256"], "Record native-log receipt differs")
                data = producer.logs.verify_capture(rec / "native-log", rec / "native-log" / ref["receipt"])
                check(data == (rec / record["raw_files"]["client-log-prefix.log"]).read_bytes(), "Record logical prefix differs")
        for field in ("native_log_source_sha256", "neutral_source_sha256"):
            for original, expected in summary[field].items():
                check(sha((obs / name(original)).read_bytes()) == expected, "Consumer dependency changed")
        check(summary["source_sha256"] == summary["current_source_sha256"] == sha((obs / "observer-source.py").read_bytes()), "Consumer source pin changed")
        check(not summary["source_changed_during_observation"] and not summary["neutral_sources_changed"] and not summary["native_log_sources_changed"], "Source drift was recorded")
        stop = (obs / "stop-request-captured.bin").read_bytes()
        stop_receipt = read(obs / "stop-request-receipt.json")
        check(stop == (obs / "stop-request").read_bytes() and sha(stop) == stop_receipt["sha256"] == summary["stop_request"]["sha256"], "Normal stop receipt differs")
        check(sha((obs / "stop-request-receipt.json").read_bytes()) == summary["stop_request"]["receipt_sha256"], "Stop receipt body differs")
        check(summary["auxiliary_shutdown"]["worker_stopped"] and not summary["auxiliary_shutdown"]["uncompleted_request_ids"], "Auxiliary close is incomplete")
        check(sha((obs / "auxiliary-events.jsonl").read_bytes()) == summary["auxiliary_events_sha256"], "Auxiliary journal changed")
        reference = summary["native_log_stream"]
        check(sha((obs / "native-log" / reference["receipt"]).read_bytes()) == reference["receipt_sha256"], "Completion log receipt differs")
        log = producer.logs.verify_capture(obs / "native-log", obs / "native-log" / reference["receipt"])
        check(log == (obs / "native-log-at-completion.log").read_bytes() and sha(log) == summary["log_sha256_at_completion"], "Final logical native log differs")
        raw_samples = (obs / "samples.jsonl").read_bytes()
        samples = producer.rec.json_lines(raw_samples)
        observations = [row["observation"] for row in samples if row.get("observation", {}).get("verified")]
        check(sha(raw_samples) == summary["samples_sha256"] and len(samples) == summary["sample_count"] == 1392 and len(observations) == summary["verified_sample_count"] == 1168, "Full sample inventory differs")
        check(all(row["process"]["running"] for row in samples), "Main consumer recorded a process exit")
        baseline = observations[0]["state"]["resource_epochs"]["last_completed_sequence"]
        first_verified = next(row for row in samples if row.get("observation", {}).get("verified"))
        check(baseline == summary["baseline_completed_epoch_sequence"] == 1 and producer.observer.instant(first_verified["timestamp"]) < producer.observer.instant(inputs[0]["input"]["issued_at"]), "Original baseline/input order differs")
        epochs = producer.rec.json_lines((obs / "native-epoch-events-at-completion.jsonl").read_bytes())
        diagnostics = producer.rec.json_lines((obs / "native-diagnostic-events-at-completion.jsonl").read_bytes())
        def replay(raw_log, events, raw_epochs, raw_diagnostics, eligible, finish):
            return producer.observer.neutral_reload_evidence(raw_log, events, raw_epochs, raw_diagnostics, eligible, baseline,
                producer.launch, context["process"], context["expected_registration"]["distinct_ids"], context["expected_registration"]["declarations"],
                producer.metadata, producer.review, producer.plan["timestamp"], finish)
        results, reviewed = replay(log, inputs, epochs, diagnostics, observations, summary["ended"])
        check(results == summary["reload_evidence"] and reviewed == summary["native_diagnostics"], "Final complete-prefix strict replay differs")
        check(summary["status"] == "stopped" and summary["passed"] is False and summary["verified_reload_count"] == summary["longest_verified_reload_run"] == 0 and all(not row["verified"] for row in results), "Failed full session was promoted")
        heads8 = [row for row in epochs if row["sequence"] == 8 and row["phase"] == "start"]
        returns8 = [row for row in epochs if row["sequence"] == 8 and row["phase"] == "return"]
        recovery = [row for row in epochs if row["sequence"] == 9]
        check(len(heads8) == 1 and not returns8 and [row["phase"] for row in recovery] == ["start", "return"], "Failed epoch/recovery pair differs")
        last = core.closed_capture(producer, journal, [])
        check(last["kind"] == "ineligible" and int(last["record_id"].rsplit(":", 1)[1]) == binding["last_ineligible_record_number"], "Last ineligible boundary differs")
        errors = producer.rec.before_errors(last["snapshot"], context["process"], last["completed_at"], context["expected_registration"], producer.metadata, last["log"].decode("utf-8"), last["epochs"], last["events"], producer.review, producer.plan)
        last_event = next(row["event"] for row in reversed(journal) if row["event"]["kind"] == "ineligible")
        check("; ".join(errors) == last_event["error"], "Final ineligible reason differs")
        raw = last["snapshot"]
        check(raw["registered_count"] == 422 and raw["registered_declarations"] == 423, "Fallback registration scope differs")
        check(raw["resource_epochs"]["started"] == 9 and raw["resource_epochs"]["completed"] == 8 and raw["resource_epochs"]["in_flight"] == 1, "Unfinished epoch state differs")
        historical = []
        for item in binding["histories"]:
            saved, execution = read(base / item["result"]), read(base / item["execution"])
            prefix = {}
            for spec in item["prefixes"]:
                value = (base / spec["payload"]).read_bytes()[:spec["bytes"]]
                check(sha(value) == spec["sha256"], "Historical exact prefix differs")
                prefix[spec["payload"]] = value
            producer.rec.verify_journal(prefix["recorder/journal.jsonl"])
            historical_inputs = producer.rec.json_lines(prefix["recorder/inputs.jsonl"])
            historical_samples = producer.rec.json_lines(prefix["observer/samples.jsonl"])
            eligible = [row["observation"] for row in historical_samples if row.get("observation", {}).get("verified")]
            record = read(rec / "records" / f"{item['record_number']:08d}" / "before.json")
            ref = record["native_log_stream"]
            historical_log = producer.logs.verify_capture(rec / "native-log", rec / "native-log" / ref["receipt"])
            check(log.startswith(historical_log) and sha(historical_log) == saved["log_sha256"], "Historical owned logical prefix differs")
            local_epochs = producer.rec.json_lines((rec / record["raw_files"]["epochs-after.jsonl"]).read_bytes())
            local_diagnostics = producer.rec.json_lines((rec / record["raw_files"]["diagnostics-after.jsonl"]).read_bytes())
            actual_records, actual_review = replay(historical_log, historical_inputs, local_epochs, local_diagnostics, eligible, historical_samples[-1]["timestamp"])
            compact = [{"event_id": row["event"]["event_id"], "sequence": row.get("sequence"), "verified": row["verified"], "failures": row["failures"]} for row in actual_records]
            check(compact == saved["reloads"] and len(actual_records) == item["number"] and all(row["verified"] for row in actual_records), "Historical per-prefix strict replay differs")
            check(actual_review["native_attribution"]["passed"] and not actual_review["unreviewed_native"], "Historical diagnostics failed")
            initial_review = producer.diagnostics.review_diagnostics(producer.analysis.native_diagnostics(historical_log.decode("utf-8")), historical_log.decode("utf-8"), local_diagnostics, local_epochs, context["process"], producer.metadata, producer.review,
                {"start": producer.plan["timestamp"], "end": record["capture_completed_at"]}, record["before"])
            check(initial_review == saved["native_diagnostics"], "Original waiter closed-capture diagnostic result differs")
            returned = next(row for row in local_epochs if row["phase"] == "return" and row["sequence"] == saved["expected_sequence"])
            stability = core.trailing_stability(historical_samples, saved["expected_sequence"], returned["monotonic_nanos"], summary["policy"]["interval"] + summary["policy"]["freshness_seconds"])
            check(stability == saved["stability"] and stability["consumer_seconds"] >= 60 and stability["native_seconds"] >= 60, "Historical measured stable spans differ")
            check(producer.observer.instant(execution["completed_at"]) < producer.observer.instant(inputs[item["number"]]["input"]["issued_at"]), "Later input overlaps the historical result")
            source = base / Path(item["execution"]).parent / "waiter-source.py"
            check(execution["returned_exit_code"] == 0 and saved["status"] == "ready" and sha(source.read_bytes()) == execution["source_sha256"] == sha((base / "operators/wait_reload_ready.py").read_bytes()), "Original historical waiter source/exit differs")
            historical.append({"verified_count": item["number"], "strict_replay_exact": True, "stability": stability})
        failed = read(base / "waiters/007/result.json")
        check(failed["status"] == "failed" and "Expected sequence was superseded" in failed["error"] and read(base / "waiters/007/execution.json")["returned_exit_code"] == 2, "Seventh waiter failure was changed")
    artifact = read(base / "artifact-reference.json")
    manifest = read(base / "artifacts/companion.build.json")
    jar = REPOSITORY / artifact["product_jar_repository_path"]
    check(sha(jar.read_bytes()) == artifact["expected_sha256"] == manifest["sha256"] == producer.plan["artifact"]["sha256"], "Original product artifact differs")
    source_root = REPOSITORY / artifact["sources_repository_path"]
    with zipfile.ZipFile(jar) as archive:
        for path, expected in manifest["inputs"].items():
            source = source_root / path
            if source.is_file():
                value = source.read_bytes()
            else:
                entry = path.removeprefix("src/main/resources/") if path.startswith("src/main/resources/") else PurePosixPath(*PurePosixPath(path).parts[4:]).as_posix()
                value = archive.read(entry)
            check(sha(value) == expected, "Original 0.4.8 product input differs")
    collector = read(base / "collector-final/execution.json")
    for path, expected in collector["files"].items():
        if path == "native-snapshots.jsonl":
            continue
        check(sha((base / "collector-final" / Path(path)).read_bytes()) == expected, "Closed collector small payload differs")
    for path, expected in collector["sources"].items():
        check(sha((base / "collector-sources" / path).read_bytes()) == expected, "Collector source pin differs")
    check(collector["status"] == "exited" and collector["exit_code"] == 0 and collector["pid"] == context["process"]["pid"], "Actual normal exit boundary differs")
    export = collector["exports"][0]
    check(export["status"] == "readable" and all(row["exit_code"] == 0 for row in export["commands"]), "Post-OOM JFR metadata differs")
    oom_lines = [i for i, line in enumerate(log.decode("utf-8").splitlines(), 1) if "java.lang.OutOfMemoryError: Java heap space" in line]
    check(oom_lines == [521, 556, 592, 623], "Original OOM stack occurrences changed")
    return {"verified_at": dt.datetime.now(dt.timezone.utc).isoformat(), "integrity_passed": True, "session_accepted": False,
            "payloads": len(index), "inputs": len(inputs), "samples": len(samples), "verified_samples": len(observations),
            "final_strict_verified_reload_count": 0, "final_longest_verified_reload_run": 0,
            "retained_records": sorted(retained), "histories": historical, "epoch8_return_present": False,
            "fallback9_accepted": False, "fallback_registration": [422, 423], "oom_stack_log_lines": oom_lines,
            "original_product_inputs": len(manifest["inputs"]), "normal_jvm_exit_code": collector["exit_code"],
            "export01_recorded_sha256": export["sha256"], "jfr_or_collector_snapshots_read_copied_or_rehashed": False,
            "scope": "Failed-session integrity and exact historical-prefix replay only; no twenty-reload/performance/route acceptance."}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=True, indent=2))
