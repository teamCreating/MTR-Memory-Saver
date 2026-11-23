"""One read-only progress evaluation of the existing owned049d attempt03."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RECORDER = HERE.parent / "owned-049d-reload-recorder-attempt03"
CONSUMER = HERE.parent / "owned-049d-reload-observation-attempt03"
READS = []


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def read_owned(path, *, append_only=False):
    started = utc()
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(before.st_size)
        after = os.fstat(stream.fileno())
    require(len(raw) == before.st_size and after.st_size >= before.st_size, "Owned input shrank during read: " + str(path))
    if not append_only:
        require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), "Immutable input changed during read: " + str(path))
    READS.append({"path": str(path), "started_at": started, "completed_at": utc(), "bytes": len(raw),
                  "sha256": sha(raw), "file_id": [before.st_dev, before.st_ino], "append_only_prefix": append_only})
    return raw


def evaluate(args):
    source_root = RECORDER / "sources"
    context = json.loads(read_owned(RECORDER / "session-start.json"))
    pinned = {}
    for original, expected in context["source_sha256"].items():
        frozen = source_root / Path(original).name
        require(sha(read_owned(frozen)) == expected, "Frozen producer source differs: " + str(frozen))
        pinned[str(frozen)] = expected
    for name in ("client_experiment_analysis.py", "native_diagnostic_review.py", "reload_before_recorder.py",
                 "native_log_stream.py", "windows_snapshot_io.py", "windows_process_identity.py",
                 "native-log-reader.json", "native-observer-consumer.json"):
        require(read_owned(CONSUMER / name) == read_owned(source_root / name), "Recorder/consumer dependency copies differ: " + name)
    require(read_owned(CONSUMER / "observer-source.py") == read_owned(source_root / "observe_packaged_client.py"), "Observer source copies differ.")
    sys.path.insert(0, str(source_root))
    import reload_before_recorder as recorder
    import observe_packaged_client as observer
    import native_log_stream as logs
    import native_diagnostic_review as diagnostics
    require(all(Path(module.__file__).resolve().is_relative_to(source_root) for module in (recorder, observer, logs, diagnostics)), "Import escaped the frozen producer source directory.")
    require(not (RECORDER / "confirmation.lock").exists(), "Input confirmation is still in progress.")
    ledger_raw = read_owned(RECORDER / "inputs.jsonl", append_only=True)
    inputs = recorder.input_events(RECORDER)
    require(recorder.json_lines(ledger_raw) == inputs, "Input ledger changed during closure verification.")
    journal_raw = read_owned(RECORDER / "journal.jsonl", append_only=True)
    journal = recorder.verify_journal(journal_raw)
    publications = [row for row in journal if row["event"]["kind"] == "published"]
    if args.record is not None:
        publications = [row for row in publications if row["event"]["record_id"].rsplit(":", 1)[1] == str(args.record)]
    require(publications, "No requested fully published recorder record.")
    publication = publications[-1]["event"]
    receipt_raw = read_owned(RECORDER / publication["receipt"])
    require(sha(receipt_raw) == publication["receipt_sha256"], "Publication receipt SHA differs.")
    receipt = json.loads(receipt_raw)
    before_raw = read_owned(RECORDER / receipt["payload"])
    require(sha(before_raw) == receipt["payload_sha256"], "Published payload SHA differs.")
    record = json.loads(before_raw)
    reference = record["native_log_stream"]
    log_root = RECORDER / "native-log"
    log_receipt_raw = read_owned(log_root / reference["receipt"])
    require(sha(log_receipt_raw) == reference["receipt_sha256"], "Published native-log receipt SHA differs.")
    require(sha(read_owned(log_root / "context.json")) == reference["context_sha256"], "Native-log context SHA differs.")
    for name in ("anchor.json", "anchor.bin"):
        read_owned(log_root / name)
    for segment in json.loads(log_receipt_raw)["segments"]:
        read_owned(log_root / segment["blob"])
    log = logs.verify_capture(log_root, log_root / reference["receipt"])
    require(log == read_owned(RECORDER / record["raw_files"]["client-log-prefix.log"]) and sha(log) == record["log_prefix_sha256"], "Published logical log/prefix differs.")
    epochs_raw = read_owned(RECORDER / record["raw_files"]["epochs-after.jsonl"])
    diagnostic_raw = read_owned(RECORDER / record["raw_files"]["diagnostics-after.jsonl"])
    require(sha(epochs_raw) == record["epochs_sha256"] and sha(diagnostic_raw) == record["diagnostics_sha256"], "Published callback-prefix SHA differs.")
    samples_raw = read_owned(CONSUMER / "samples.jsonl", append_only=True)
    samples = recorder.json_lines(samples_raw)
    eligible_samples = [sample for sample in samples if sample.get("observation", {}).get("verified")]
    require(eligible_samples and inputs, "No verified consumer baseline or selected input yet.")
    observations = [sample["observation"] for sample in eligible_samples]
    first = eligible_samples[0]
    baseline = first["observation"]["state"]["resource_epochs"]["last_completed_sequence"]
    require(observer.instant(first["timestamp"]) < observer.instant(inputs[0]["input"]["issued_at"]), "Consumer baseline was not recorded before first input.")
    launch = json.loads(read_owned(RECORDER / "packaged-client-launch.json"))
    plan = json.loads(read_owned(RECORDER / "packaged-client-plan.json"))
    metadata = json.loads(read_owned(CONSUMER / "observer-target.json"))
    review = json.loads(read_owned(CONSUMER / "native-diagnostic-review.json"))
    require(review == json.loads(read_owned(RECORDER / "native-diagnostic-review.json")), "Frozen diagnostic reviews differ.")
    require(metadata == context["metadata"] and context["process"]["pid"] == launch["pid"], "Recorder/consumer target or process differs.")
    expected = context["expected_registration"]
    results, diagnostic_review = observer.neutral_reload_evidence(log, inputs, recorder.json_lines(epochs_raw),
        recorder.json_lines(diagnostic_raw), observations, baseline, launch, context["process"],
        expected["distinct_ids"], expected["declarations"], metadata, review, plan["timestamp"], samples[-1]["timestamp"])
    require(read_owned(RECORDER / "inputs.jsonl", append_only=True) == ledger_raw and not (RECORDER / "confirmation.lock").exists(), "New input arrived during evaluation; this snapshot is not coherent.")
    require(all(sha(read_owned(Path(path))) == expected_hash for path, expected_hash in pinned.items()), "Frozen source changed during evaluation.")
    compact = []
    for result in results:
        native = result.get("native_epoch", {})
        settled = next((item["raw_state"] for item in observations if item.get("state_sha256") == native.get("settled_state_sha256")), {})
        compact.append({"event_id": result["event"]["event_id"], "input_issued_at": result["event"]["input"]["issued_at"],
            "verified": result["verified"], "failures": result["failures"], "sequence": result.get("sequence"),
            "head": native.get("start", {}).get("timestamp"), "returned": native.get("returned", {}).get("timestamp"),
            "return_monotonic_nanos": native.get("returned", {}).get("monotonic_nanos"),
            "settled": native.get("settled_timestamp"), "settled_state_sha256": native.get("settled_state_sha256"),
            "settled_capture_started_monotonic_nanos": settled.get("capture_started_monotonic_nanos"),
            "declared_vehicle_count": result.get("declared_vehicle_count")})
    last = samples[-1]
    last_raw = last.get("observation", {}).get("raw_state", {})
    sequence = last_raw.get("resource_epochs", {}).get("last_completed_sequence")
    returned_mono = max((row.get("native_epoch", {}).get("returned", {}).get("monotonic_nanos", -1) for row in results if row.get("sequence") == sequence), default=-1)
    stable = []
    for sample in reversed(samples):
        state = sample.get("observation", {})
        raw = state.get("raw_state", {})
        if not sample["process"].get("running") or not state.get("verified") or raw.get("resource_epochs", {}).get("last_completed_sequence") != sequence or raw.get("capture_started_monotonic_nanos", -1) < returned_mono:
            break
        if stable and not 0 < stable[-1]["elapsed_seconds"] - sample["elapsed_seconds"] <= args.interval + args.freshness_seconds:
            break
        stable.append(sample)
    stable.reverse()
    return {"evaluated_at": utc(), "program_sha256": sha(Path(__file__).read_bytes()),
        "frozen_import_root": str(source_root), "frozen_source_sha256": pinned,
        "read_receipts": READS, "selected_published_record": record["event_id"],
        "samples": len(samples), "eligible_samples": len(eligible_samples), "baseline_sequence": baseline,
        "first_verified_consumer_timestamp": first["timestamp"], "reloads": compact,
        "verified_reload_count": sum(item["verified"] for item in results),
        "longest_verified_reload_run": observer.consecutive_reloads(results),
        "native_attribution_passed": diagnostic_review["native_attribution"]["passed"],
        "native_attribution_errors": diagnostic_review["native_attribution"]["errors"],
        "unreviewed_native": diagnostic_review["unreviewed_native"], "last_completed_sequence": sequence,
        "latest_sample_timestamp": last["timestamp"], "latest_sample_verified": last.get("observation", {}).get("verified"),
        "trailing_same_sequence_settled_samples": len(stable),
        "trailing_consumer_stable_seconds": stable[-1]["elapsed_seconds"] - stable[0]["elapsed_seconds"] if stable else 0,
        "trailing_native_monotonic_seconds": (stable[-1]["observation"]["raw_state"]["monotonic_nanos"] - stable[0]["observation"]["raw_state"]["monotonic_nanos"]) / 1e9 if stable else 0,
        "stable_duration_sampling_policy": {"declared_interval": args.interval, "declared_freshness_seconds": args.freshness_seconds, "maximum_gap_seconds": args.interval + args.freshness_seconds, "inclusive_interval_credit": 0},
        "scope": "Interim replay of existing attempt03. The producer filters verified epoch observations; all original samples remain untouched. No new reader, input, UI, runtime change or final acceptance. Final consumer summary/sealed audit remains authoritative."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=int)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--freshness-seconds", type=float, default=15)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = (args.output or HERE / ("evaluation-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")).resolve()
    require(output.is_relative_to(HERE), "Progress output must stay inside its ignored task directory.")
    result = evaluate(args)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: value for key, value in result.items() if key not in ("read_receipts", "frozen_source_sha256")}, ensure_ascii=True, indent=2))
    print("Result:", str(output))
