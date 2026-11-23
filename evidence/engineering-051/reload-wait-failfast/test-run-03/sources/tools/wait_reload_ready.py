"""Read-only reload progress: reject completed native errors before waiting for readiness.

Recorder/consumer/output locations are explicit. Frozen producer modules perform
the same input, log and diagnostic checks as the consumer. This helper never
controls game input or replaces the final consumer summary.
"""
import argparse
from contextlib import AbstractContextManager
import datetime as dt
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("windows_snapshot_io", "windows_process_identity", "native_log_stream", "client_experiment_analysis",
           "native_diagnostic_review", "observe_packaged_client", "reload_before_recorder")


class EvidenceError(ValueError):
    pass


class PendingPublication(Exception):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


class FrozenProducer(AbstractContextManager):
    """One isolated CLI/test context; import only hash-pinned producer copies."""
    def __init__(self, recorder, consumer):
        self.recorder, self.consumer = Path(recorder).resolve(), Path(consumer).resolve()
        self.sources = self.recorder / "sources"
        self.context = read(self.recorder / "session-start.json")
        self.plan = read(self.recorder / "packaged-client-plan.json")
        self.launch = read(self.recorder / "packaged-client-launch.json")
        self.metadata = read(self.consumer / "observer-target.json")
        self.review = read(self.consumer / "native-diagnostic-review.json")
        self.pins = {}
        for path in (self.recorder / "session-start.json", self.recorder / "packaged-client-plan.json", self.recorder / "packaged-client-launch.json",
                     self.consumer / "observer-target.json", self.consumer / "native-diagnostic-review.json", self.recorder / "native-diagnostic-review.json"):
            self.pins[path] = sha(path.read_bytes())
        for original, expected in self.context["source_sha256"].items():
            name = Path(original).name
            frozen = self.sources / name
            self.pins[frozen] = expected
            counterpart = self.consumer / ("observer-source.py" if name == "observe_packaged_client.py" else name)
            self.pins[counterpart] = expected
        self.check_sources()
        require(self.metadata == self.context["metadata"], "Consumer/recorder target differs.")
        require(Path(self.context["instance"]).resolve() == Path(self.plan["instance"]).resolve(), "Recorder instance differs from its frozen plan.")
        require(self.review == read(self.recorder / "native-diagnostic-review.json"), "Diagnostic review copies differ.")
        require(sha((self.recorder / "packaged-client-plan.json").read_bytes()) == self.context["plan_sha256"] == self.launch["plan_sha256"], "Plan pin differs.")
        require(sha((self.recorder / "packaged-client-launch.json").read_bytes()) == self.context["launch_sha256"] and self.launch["pid"] == self.context["process"]["pid"], "Launch/process pin differs.")

    def check_sources(self, *, live=False):
        for path, expected in self.pins.items():
            require(path.is_file() and sha(path.read_bytes()) == expected, "Producer source pin differs: " + str(path))
        if live:
            for path, expected in self.context["source_sha256"].items():
                require(Path(path).is_file() and sha(Path(path).read_bytes()) == expected, "Live producer source changed: " + path)
            roots = {Path(path).resolve().parents[1] for path in self.context["source_sha256"] if Path(path).name == "reload_before_recorder.py"}
            require(len(roots) == 1, "Original producer root is ambiguous.")
            require((next(iter(roots)) / "config/native-diagnostic-review.json").read_bytes() == (self.consumer / "native-diagnostic-review.json").read_bytes(), "Live diagnostic review changed.")

    def __enter__(self):
        self.old_path, self.old_modules = list(sys.path), {name: sys.modules.get(name) for name in MODULES}
        self.old_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            for name in MODULES:
                sys.modules.pop(name, None)
            sys.path.insert(0, str(self.sources))
            loaded = {name: importlib.import_module(name) for name in MODULES}
            require(all(Path(module.__file__).resolve().parent == self.sources for module in loaded.values()), "Import escaped frozen producer copies.")
            self.observer = loaded["observe_packaged_client"]
            self.rec = loaded["reload_before_recorder"]
            self.logs = loaded["native_log_stream"]
            self.analysis = loaded["client_experiment_analysis"]
            self.diagnostics = loaded["native_diagnostic_review"]
            self.io = loaded["windows_snapshot_io"]
            self.identity = loaded["windows_process_identity"]
            self.observer.NEUTRAL_CONTRACT_FILE = self.sources / "native-observer-consumer.json"
            self.logs.REVIEW_FILE = self.sources / "native-log-reader.json"
            self.diagnostics.validate_review(self.review, self.metadata, root=ROOT)
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def __exit__(self, *unused):
        sys.path[:] = self.old_path
        for name, old in self.old_modules.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
        sys.dont_write_bytecode = self.old_bytecode

    def prefix(self, path, receipts):
        started = utc()
        with self.io.open_snapshot(Path(path)) as stream:
            before = os.fstat(stream.fileno())
            raw = stream.read(before.st_size)
            after = os.fstat(stream.fileno())
        require(len(raw) == before.st_size and after.st_size >= before.st_size, "Owned prefix shrank: " + str(path))
        receipts.append({"path": str(path), "started_at": started, "completed_at": utc(), "bytes": len(raw), "sha256": sha(raw)})
        return raw


def rows(producer, raw):
    if raw and not raw.endswith(b"\n"):
        raise PendingPublication("An append publication is not complete.")
    return producer.rec.json_lines(raw)


def closed_capture(producer, journal, receipts):
    """Published and ineligible records both retain closed raw inputs."""
    closed = [row["event"] for row in journal if row["event"]["kind"] in ("published", "ineligible")]
    if not closed:
        return None
    event = closed[-1]
    record_id = event["record_id"]
    number = int(record_id.rsplit(":", 1)[1])
    folder = producer.recorder / "records" / f"{number:08d}"
    raw_entries = rows(producer, producer.prefix(folder / "raw-evidence.jsonl", receipts))
    raw = {}
    for item in raw_entries:
        value = producer.prefix(producer.rec.owned_path(producer.recorder, item["path"]), receipts)
        require(len(value) == item["bytes"] and sha(value) == item["sha256"], "Closed raw capture pin differs.")
        require(item["name"] not in raw, "Duplicate closed capture input.")
        raw[item["name"]] = value
    required = {"epochs-before.jsonl", "epochs-after.jsonl", "diagnostics-before.jsonl", "diagnostics-after.jsonl", "native-snapshot.json", "client-log-prefix.log"}
    require(set(raw) == required, "Closed capture raw inventory differs.")
    if raw["epochs-before.jsonl"] != raw["epochs-after.jsonl"] or raw["diagnostics-before.jsonl"] != raw["diagnostics-after.jsonl"]:
        return None  # The producer explicitly retained a callback transition, not a stable diagnostic boundary.
    if event["kind"] == "published":
        receipt_bytes = producer.prefix(producer.rec.owned_path(producer.recorder, event["receipt"]), receipts)
        require(sha(receipt_bytes) == event["receipt_sha256"], "Publication receipt pin differs.")
        publication = json.loads(receipt_bytes)
        before_bytes = producer.prefix(producer.rec.owned_path(producer.recorder, publication["payload"]), receipts)
        require(sha(before_bytes) == publication["payload_sha256"], "Published payload pin differs.")
        before = json.loads(before_bytes)
        require(before["event_id"] == record_id and before["before"] == json.loads(raw["native-snapshot.json"]), "Publication identity/raw state differs.")
        start, finish, reference = before["capture_started_at"], before["capture_completed_at"], before["native_log_stream"]
    else:
        start, finish = event["capture_started_at"], event["capture_completed_at"]
        matches = []
        for path in sorted((producer.recorder / "native-log/captures").glob("*.json"), reverse=True):
            if not path.stem.isdigit():
                continue
            candidate_bytes = producer.prefix(path, receipts)
            if not candidate_bytes.endswith(b"\n"):
                continue  # A newer capture may still be publishing; the selected closed receipt must be complete.
            candidate = json.loads(candidate_bytes)
            if producer.observer.instant(candidate["completed_at"]) < producer.observer.instant(start):
                break
            if (candidate["sha256"] == sha(raw["client-log-prefix.log"])
                    and producer.observer.instant(start) <= producer.observer.instant(candidate["started_at"])
                    <= producer.observer.instant(candidate["completed_at"]) <= producer.observer.instant(finish)):
                matches.append({"receipt": path.relative_to(producer.recorder / "native-log").as_posix(), "receipt_sha256": sha(candidate_bytes)})
        require(len(matches) == 1, "Ineligible capture has no unique complete native-log receipt.")
        reference = matches[0]
    log_root = producer.recorder / "native-log"
    require(sha((log_root / reference["receipt"]).read_bytes()) == reference["receipt_sha256"], "Closed logical-log receipt changed.")
    log_context = read(log_root / "context.json")
    require(log_context["plan_sha256"] == producer.context["plan_sha256"] and log_context["launch_sha256"] == producer.context["launch_sha256"], "Log capture belongs to another launch.")
    log = producer.logs.verify_capture(log_root, log_root / reference["receipt"])
    require(log == raw["client-log-prefix.log"], "Closed logical log does not reconstruct from original segments.")
    return {"kind": event["kind"], "record_id": record_id, "completed_at": finish, "snapshot": json.loads(raw["native-snapshot.json"]),
            "epochs": rows(producer, raw["epochs-after.jsonl"]), "events": rows(producer, raw["diagnostics-after.jsonl"]),
            "log": log, "reference": reference}


def trailing_stability(samples, sequence, returned_mono, maximum_gap):
    stable = []
    for sample in reversed(samples):
        observation = sample.get("observation", {})
        raw = observation.get("raw_state", {})
        if (not sample.get("process", {}).get("running") or not observation.get("verified")
                or raw.get("resource_epochs", {}).get("last_completed_sequence") != sequence
                or raw.get("capture_started_monotonic_nanos", -1) < returned_mono):
            break
        if stable and not 0 < stable[-1]["elapsed_seconds"] - sample["elapsed_seconds"] <= maximum_gap:
            break
        stable.append(sample)
    stable.reverse()
    return {"samples": len(stable),
        "consumer_seconds": stable[-1]["elapsed_seconds"] - stable[0]["elapsed_seconds"] if stable else 0,
        "native_seconds": (stable[-1]["observation"]["raw_state"]["monotonic_nanos"] - stable[0]["observation"]["raw_state"]["monotonic_nanos"]) / 1e9 if stable else 0}


def inspect(producer, native, samples, epoch_rows, journal, expected_sequence, now, *, interval=5, freshness=15, stable_seconds=60):
    receipts = []
    state = {"status": "waiting", "expected_sequence": expected_sequence, "native_sequence": native["resource_epochs"]["last_completed_sequence"],
        "native_pending": native["native_pending"], "in_flight": native["resource_epochs"]["in_flight"], "native_observed_at": native["observed_at"], "read_receipts": receipts}
    require(native["pid"] == producer.launch["pid"] and native.get("target") == producer.metadata, "Native process or target differs.")
    require(abs((producer.observer.instant(native["process_created"]) - producer.observer.instant(producer.context["process"]["created"])).total_seconds()) <= 1, "Native process creation identity differs.")
    require(native.get("observation_errors") == 0, "Native observer reported errors.")
    require(state["native_sequence"] <= expected_sequence and native["resource_epochs"]["started"] <= expected_sequence, "Expected sequence was superseded.")
    returned = [row for row in epoch_rows if row.get("pid") == producer.launch["pid"] and row.get("sequence") == expected_sequence and row.get("phase") == "return"]
    require(len(returned) <= 1, "Duplicate target RETURN.")
    if not returned:
        return {**state, "waiting_for": "actual_return"}
    returned = returned[0]
    state["returned_at"] = returned["timestamp"]
    capture = closed_capture(producer, journal, receipts)
    if capture is None or not any(row.get("phase") == "return" and row.get("sequence") == expected_sequence for row in capture["epochs"]) or capture["snapshot"].get("capture_started_monotonic_nanos", -1) < returned["monotonic_nanos"]:
        return {**state, "waiting_for": "closed_post_return_capture"}
    state.update(capture_kind=capture["kind"], capture_record_id=capture["record_id"], log_sha256=sha(capture["log"]))
    text = capture["log"].decode("utf-8")
    diagnostic = producer.diagnostics.review_diagnostics(producer.analysis.native_diagnostics(text), text, capture["events"], capture["epochs"],
        producer.context["process"], producer.metadata, producer.review,
        {"start": producer.plan["timestamp"], "end": capture["completed_at"]}, capture["snapshot"])
    state["native_diagnostics"] = diagnostic
    # This check precedes consumer eligibility and a successful recorder publication.
    if diagnostic["unreviewed_native"] or not diagnostic["native_attribution"]["passed"]:
        return {**state, "status": "diagnostics_failed"}
    eligible = [sample for sample in samples if sample.get("observation", {}).get("verified")]
    if not samples or not eligible:
        return {**state, "waiting_for": "verified_consumer_baseline"}
    latest = samples[-1]
    latest_raw = latest.get("observation", {}).get("raw_state", {})
    age = (now - producer.observer.instant(latest["timestamp"])).total_seconds()
    native_age = (now - producer.observer.instant(native["observed_at"])).total_seconds()
    capture_age = (now - producer.observer.instant(capture["completed_at"])).total_seconds()
    if (capture["kind"] != "published" or latest.get("observation", {}).get("verified") is not True
            or latest_raw.get("resource_epochs", {}).get("last_completed_sequence") != expected_sequence
            or latest_raw.get("capture_started_monotonic_nanos", -1) < returned["monotonic_nanos"]
            or native["resource_epochs"]["last_completed_sequence"] != expected_sequence
            or not -1 <= age <= interval + freshness or not -1 <= native_age <= freshness
            or not 0 <= capture_age <= producer.context["freshness_seconds"]
            or native["native_pending"] != 0 or native["native_settled"] is not True or native["resource_epochs"]["in_flight"] != 0):
        return {**state, "waiting_for": "fresh_eligible_consumer_and_publication"}
    require(not (producer.recorder / "confirmation.lock").exists(), "Input confirmation is still in progress.")
    inputs = producer.rec.input_events(producer.recorder)
    baseline = eligible[0]["observation"]["state"]["resource_epochs"]["last_completed_sequence"]
    require(inputs and producer.observer.instant(eligible[0]["timestamp"]) < producer.observer.instant(inputs[0]["input"]["issued_at"]), "Consumer baseline does not predate first input.")
    count = expected_sequence - baseline
    require(count > 0, "Expected sequence does not follow the baseline.")
    observations = [sample["observation"] for sample in eligible]
    expected = producer.context["expected_registration"]
    reloads, full_review = producer.observer.neutral_reload_evidence(capture["log"], inputs, capture["epochs"], capture["events"], observations,
        baseline, producer.launch, producer.context["process"], expected["distinct_ids"], expected["declarations"], producer.metadata,
        producer.review, producer.plan["timestamp"], latest["timestamp"])
    state.update(baseline_sequence=baseline, verified_reload_count=sum(row["verified"] for row in reloads),
        longest_verified_reload_run=producer.observer.consecutive_reloads(reloads),
        reloads=[{"event_id": row["event"]["event_id"], "sequence": row.get("sequence"), "verified": row["verified"], "failures": row["failures"]} for row in reloads])
    if (len(reloads) != count or not all(row["verified"] for row in reloads) or state["verified_reload_count"] != count
            or state["longest_verified_reload_run"] != count or not full_review["native_attribution"]["passed"] or full_review["unreviewed_native"]):
        return {**state, "status": "reload_replay_failed"}
    stability = trailing_stability(samples, expected_sequence, returned["monotonic_nanos"], interval + freshness)
    state["stability"] = stability
    return {**state, "status": "ready" if stability["consumer_seconds"] >= stable_seconds and stability["native_seconds"] >= stable_seconds else "waiting", "waiting_for": "measured_stable_spans"}


def wait(args, producer, emit, *, monotonic=time.monotonic, sleep=time.sleep):
    source_sha = sha(Path(__file__).read_bytes())
    require(args.freshness_seconds <= producer.context["freshness_seconds"], "Waiter freshness must not exceed the recorder's frozen criterion.")
    process = producer.observer.WindowsProcess(producer.plan, producer.launch)
    try:
        api = producer.identity.NativeApi(kernel=process.kernel)
        deadline, heartbeat = monotonic() + args.deadline_seconds, -math.inf
        while True:
            api.live(process.handle)
            require(sha(Path(__file__).read_bytes()) == source_sha, "Waiter source changed during execution.")
            require(process.creation_time() == process.created, "Observed process creation identity changed.")
            producer.check_sources(live=True)
            receipts = []
            try:
                native = json.loads(producer.prefix(Path(producer.context["instance"]) / producer.metadata["snapshot_path"], receipts))
                epochs = rows(producer, producer.prefix(Path(producer.context["instance"]) / producer.metadata["epochs_path"], receipts))
                samples = rows(producer, producer.prefix(producer.consumer / "samples.jsonl", receipts))
                journal_raw = producer.prefix(producer.recorder / "journal.jsonl", receipts)
                rows(producer, journal_raw)
                journal = producer.rec.verify_journal(journal_raw)
                require(not any(row["event"]["kind"] in ("capture_failed", "initialization_failed", "failed") for row in journal), "Recorder reported a terminal capture/source failure.")
                result = inspect(producer, native, samples, epochs, journal, args.expected_sequence, dt.datetime.now(dt.timezone.utc),
                    interval=args.interval, freshness=args.freshness_seconds, stable_seconds=args.stable_seconds)
                result["read_receipts"] = receipts + result["read_receipts"]
            except PendingPublication as error:
                result = {"status": "waiting", "waiting_for": str(error), "read_receipts": receipts}
            if result["status"] != "waiting":
                producer.check_sources(live=True)
                api.live(process.handle)
                require(sha(Path(__file__).read_bytes()) == source_sha, "Waiter source changed during assessment.")
                if result["status"] == "ready" and monotonic() >= deadline:
                    return {**result, "status": "deadline_elapsed", "ready_not_granted": "assessment_completed_after_deadline"}, 1
                return result, 0 if result["status"] == "ready" else 2
            if monotonic() >= deadline:
                return {**result, "status": "deadline_elapsed"}, 1
            require(not (producer.recorder / "session-end.json").exists() and not (producer.consumer / "summary.json").exists(), "A required producer has already stopped.")
            if monotonic() - heartbeat >= 35:
                emit({"heartbeat_at": utc(), "status": result["status"], "waiting_for": result.get("waiting_for"), "sequence": result.get("native_sequence"),
                    "native_pending": result.get("native_pending"), "in_flight": result.get("in_flight"), "native_observed_at": result.get("native_observed_at"), "stability": result.get("stability")})
                heartbeat = monotonic()
            sleep(min(5, max(0, deadline - monotonic())))
    finally:
        process.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recorder", required=True, type=Path)
    parser.add_argument("--consumer", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-sequence", required=True, type=int)
    parser.add_argument("--deadline-seconds", type=float, default=420)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--freshness-seconds", type=float, default=15)
    parser.add_argument("--stable-seconds", type=float, default=60)
    args = parser.parse_args(argv)
    require(args.expected_sequence > 0 and all(math.isfinite(x) and x > 0 for x in (args.deadline_seconds, args.interval, args.freshness_seconds, args.stable_seconds)) and args.deadline_seconds <= 420 and args.stable_seconds >= 60, "Invalid wait policy; deadline <=420 and stable duration >=60 are required.")
    args.output = args.output.resolve()
    instance = Path(read(args.recorder / "session-start.json")["instance"]).resolve()
    require(all(not args.output.is_relative_to(path.resolve()) for path in (args.recorder, args.consumer, instance)), "Output must stay outside producer and game-instance directories.")
    require(not args.output.exists(), "Use a fresh output directory.")
    args.output.mkdir(parents=True)
    started = utc()
    source = Path(__file__).read_bytes()
    (args.output / "waiter-source.py").write_bytes(source)
    code, result = 2, {}
    with (args.output / "stdout.log").open("x", encoding="utf-8") as stdout, (args.output / "stderr.log").open("x", encoding="utf-8") as stderr:
        def emit(value):
            text = json.dumps(value, ensure_ascii=True)
            stdout.write(text + "\n"); stdout.flush()
            print(text, flush=True)
        try:
            with FrozenProducer(args.recorder, args.consumer) as producer:
                emit({"started_at": started, "source_sha256": sha(source), "frozen_import_root": str(producer.sources)})
                result, code = wait(args, producer, emit)
        except BaseException as error:
            result = {"status": "failed", "error": repr(error)}
            traceback.print_exc(file=stderr); stderr.flush()
            traceback.print_exc()
        (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        emit({"status": result["status"], "returned_exit_code": code, "result": str(args.output / "result.json"), "scope": "Interim evidence only; final consumer summary and sealed acceptance remain required."})
    (args.output / "execution.json").write_text(json.dumps({"started_at": started, "completed_at": utc(), "argv": sys.argv if argv is None else argv,
        "source_sha256": sha(source), "current_source_sha256": sha(Path(__file__).read_bytes()), "returned_exit_code": code,
        "stdout_sha256": sha((args.output / "stdout.log").read_bytes()), "stderr_sha256": sha((args.output / "stderr.log").read_bytes())}, indent=2) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
