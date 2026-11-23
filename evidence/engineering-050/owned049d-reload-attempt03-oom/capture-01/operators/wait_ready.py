"""Wait for one attempt03 epoch and strictly replay its existing producer evidence.

This helper opens only a read-only identity handle; it never starts/stops a game,
recorder, consumer or UI action. Its result is not final consumer acceptance.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RECORDER = HERE.parent / "owned-049d-reload-recorder-attempt03"
CONSUMER = HERE.parent / "owned-049d-reload-observation-attempt03"
EVALUATOR = HERE / "evaluate_once.py"
EVALUATOR_SHA = "8107303eea520c20ae52d54f7477ba432067bab739c1d832e57c09c88b111ac7"


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


class Tee:
    def __init__(self, original, file):
        self.original, self.file = original, file

    def write(self, value):
        self.file.write(value)
        self.file.flush()
        self.original.write(value)
        self.original.flush()
        return len(value)

    def flush(self):
        self.file.flush()
        self.original.flush()


def run(args, folder, execution):
    sources = RECORDER / "sources"
    context = json.loads((RECORDER / "session-start.json").read_bytes())
    plan = json.loads((RECORDER / "packaged-client-plan.json").read_bytes())
    launch = json.loads((RECORDER / "packaged-client-launch.json").read_bytes())
    checks = {HERE / "wait_ready.py": execution["source_sha256"], EVALUATOR: EVALUATOR_SHA}
    for source, expected in context["source_sha256"].items():
        checks[Path(source)] = checks[sources / Path(source).name] = expected
    checks[HERE.parents[2] / "config/native-diagnostic-review.json"] = sha((CONSUMER / "native-diagnostic-review.json").read_bytes())
    for path, expected in checks.items():
        require(sha(path.read_bytes()) == expected, "Source anomaly: " + str(path))
    sys.path.insert(0, str(sources))
    import observe_packaged_client as observer
    import reload_before_recorder as recorder
    import windows_snapshot_io as snapshot_io
    import windows_process_identity as identity
    require(all(Path(module.__file__).resolve().is_relative_to(sources) for module in (observer, recorder, snapshot_io, identity)), "Import escaped frozen producer sources.")
    execution["frozen_import_root"] = str(sources)
    execution["process_pid"] = launch["pid"]
    execution["source_pins"] = {str(path): expected for path, expected in checks.items()}
    process = observer.WindowsProcess(plan, launch)
    api = identity.NativeApi(kernel=process.kernel)
    deadline = time.monotonic() + args.deadline_seconds
    heartbeat_at, probe = -float("inf"), 0
    expected_count = args.expected_sequence - 1
    try:
        while True:
            now_clock, read_started = time.monotonic(), utc()
            api.live(process.handle)
            require(process.creation_time() == process.created, "Actual process creation identity changed.")
            for path, expected in checks.items():
                require(sha(path.read_bytes()) == expected, "Source anomaly: " + str(path))
            raw_snapshot = snapshot_io.read_snapshot_bytes(Path(context["instance"]) / context["metadata"]["snapshot_path"])
            native = json.loads(raw_snapshot)
            require(native["pid"] == launch["pid"] and abs((observer.instant(native["process_created"]) - observer.instant(context["process"]["created"])).total_seconds()) <= 1, "Native process binding differs.")
            epochs_raw = recorder.read_prefix(Path(context["instance"]) / context["metadata"]["epochs_path"])
            samples_raw = recorder.read_prefix(CONSUMER / "samples.jsonl")
            journal_raw = recorder.read_prefix(RECORDER / "journal.jsonl")
            state = {"at": utc(), "elapsed_seconds": time.monotonic() - execution["start_clock"],
                "expected_sequence": args.expected_sequence, "native_sequence": native["resource_epochs"]["last_completed_sequence"],
                "native_started": native["resource_epochs"]["started"], "in_flight": native["resource_epochs"]["in_flight"],
                "native_pending": native["native_pending"], "native_settled": native["native_settled"],
                "observed_at": native["observed_at"], "read_started_at": read_started,
                "prefix_sha256": {"native_snapshot": sha(raw_snapshot), "epochs": sha(epochs_raw), "samples": sha(samples_raw), "journal": sha(journal_raw)}}
            execution["last_state"] = state
            require(state["native_sequence"] <= args.expected_sequence and state["native_started"] <= args.expected_sequence, "Expected sequence was superseded by a new native reload.")
            require(native.get("observation_errors") == 0, "Actual native observer reported errors.")
            reason = "waiting_for_actual_return"
            returned = None
            if all(not raw or raw.endswith(b"\n") for raw in (epochs_raw, samples_raw, journal_raw)):
                epochs, samples, journal = recorder.json_lines(epochs_raw), recorder.json_lines(samples_raw), recorder.verify_journal(journal_raw)
                returns = [row for row in epochs if row.get("pid") == launch["pid"] and row.get("sequence") == args.expected_sequence and row.get("phase") == "return"]
                require(len(returns) <= 1, "Duplicate actual RETURN for expected sequence.")
                returned = returns[0] if returns else None
                if returned is not None:
                    state["actual_returned_at"] = returned["timestamp"]
                    reason = "waiting_for_post_return_consumer_and_publication"
                    latest = samples[-1] if samples else {}
                    observation = latest.get("observation", {})
                    raw = observation.get("raw_state", {})
                    fresh_now = observer.instant(utc())
                    native_age = (fresh_now - observer.instant(native["observed_at"])).total_seconds()
                    sample_age = (fresh_now - observer.instant(latest["timestamp"])).total_seconds() if latest else float("inf")
                    state.update(native_age_seconds=native_age, consumer_sample_age_seconds=sample_age)
                    native_ready = -1 <= native_age <= args.freshness_seconds and state["native_sequence"] == args.expected_sequence and state["in_flight"] == 0 and state["native_pending"] == 0 and state["native_settled"] is True
                    consumer_ready = -1 <= sample_age <= args.interval + args.freshness_seconds and latest.get("process", {}).get("running") is True and observation.get("verified") is True and raw.get("resource_epochs", {}).get("last_completed_sequence") == args.expected_sequence and raw.get("capture_started_monotonic_nanos", -1) >= returned["monotonic_nanos"]
                    publications = [row["event"] for row in journal if row["event"]["kind"] == "published"]
                    publication = publications[-1] if publications else None
                    record = None
                    if publication:
                        receipt_bytes = (RECORDER / publication["receipt"]).read_bytes()
                        require(sha(receipt_bytes) == publication["receipt_sha256"], "Published receipt changed.")
                        receipt = json.loads(receipt_bytes)
                        before_bytes = (RECORDER / receipt["payload"]).read_bytes()
                        require(sha(before_bytes) == receipt["payload_sha256"], "Published payload changed.")
                        record = json.loads(before_bytes)
                    publication_ready = record is not None and 0 <= (fresh_now - observer.instant(publication["receipt_closed_at"])).total_seconds() <= context["freshness_seconds"] and record["before"]["resource_epochs"]["last_completed_sequence"] == args.expected_sequence and record["before"].get("capture_started_monotonic_nanos", -1) >= returned["monotonic_nanos"]
                    if native_ready and consumer_ready and publication_ready and not (RECORDER / "confirmation.lock").exists():
                        probe += 1
                        result_path = folder / f"evaluation-{probe:03d}.json"
                        number = int(record["event_id"].rsplit(":", 1)[1])
                        argv = [sys.executable, "-u", "-X", "utf8", str(EVALUATOR), "--record", str(number),
                                "--interval", str(args.interval), "--freshness-seconds", str(args.freshness_seconds), "--output", str(result_path)]
                        started = utc()
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            execution["status"] = "deadline_elapsed"
                            return 1
                        try:
                            child = subprocess.run(argv, capture_output=True, timeout=min(40, remaining))
                            stdout, stderr, code = child.stdout, child.stderr, child.returncode
                        except subprocess.TimeoutExpired as error:
                            stdout, stderr, code = error.stdout or b"", error.stderr or b"", None
                        (folder / f"evaluation-{probe:03d}.stdout.log").write_bytes(stdout)
                        (folder / f"evaluation-{probe:03d}.stderr.log").write_bytes(stderr)
                        receipt = {"argv": argv, "started_at": started, "completed_at": utc(), "exit_code": code,
                            "stdout_sha256": sha(stdout), "stderr_sha256": sha(stderr), "evaluator_sha256": EVALUATOR_SHA}
                        (folder / f"evaluation-{probe:03d}.execution.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                        require(code == 0, "Strict post-RETURN replay failed or timed out; see preserved evaluation output.")
                        result = json.loads(result_path.read_bytes())
                        execution["latest_result"] = str(result_path)
                        require(result["program_sha256"] == EVALUATOR_SHA and result["baseline_sequence"] == 1, "Replay source or baseline differs.")
                        strict = result["verified_reload_count"] == expected_count and result["longest_verified_reload_run"] == expected_count and len(result["reloads"]) == expected_count and all(row["verified"] and not row["failures"] for row in result["reloads"]) and result["native_attribution_passed"] and not result["native_attribution_errors"] and not result["unreviewed_native"] and result["last_completed_sequence"] == args.expected_sequence
                        require(strict, "Strict post-RETURN reload/diagnostic replay did not verify every retained input.")
                        state.update(verified_reload_count=result["verified_reload_count"], latest_sample_verified=result["latest_sample_verified"],
                            consumer_stable_seconds=result["trailing_consumer_stable_seconds"], native_stable_seconds=result["trailing_native_monotonic_seconds"])
                        reason = "waiting_for_two_measured_stable_spans"
                        if result["latest_sample_verified"] and result["trailing_consumer_stable_seconds"] >= 60 and result["trailing_native_monotonic_seconds"] >= 60:
                            api.live(process.handle)
                            require(process.creation_time() == process.created, "Process exited or identity changed after replay.")
                            require(all(sha(path.read_bytes()) == expected for path, expected in checks.items()), "Source changed after replay.")
                            require((observer.instant(utc()) - observer.instant(result["latest_sample_timestamp"])).total_seconds() <= args.interval + args.freshness_seconds, "Consumer result became stale during replay.")
                            execution["status"] = "ready"
                            print(json.dumps({"ready": True, "verified": expected_count, "sequence": args.expected_sequence,
                                "consumer_span": result["trailing_consumer_stable_seconds"], "native_span": result["trailing_native_monotonic_seconds"],
                                "result": str(result_path)}), flush=True)
                            return 0
            else:
                reason = "waiting_for_complete_append_publication"
            state["waiting_for"] = reason
            if time.monotonic() - heartbeat_at >= 35:
                print(json.dumps({"heartbeat": state}), flush=True)
                heartbeat_at = time.monotonic()
            if time.monotonic() >= deadline:
                execution["status"] = "deadline_elapsed"
                print(json.dumps({"ready": False, "reason": "deadline_elapsed", "last_state": state}), flush=True)
                return 1
            time.sleep(min(5, max(0, deadline - time.monotonic())))
    finally:
        process.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-sequence", required=True, type=int)
    parser.add_argument("--deadline-seconds", type=float, default=420)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--freshness-seconds", type=float, default=15)
    args = parser.parse_args()
    require(args.expected_sequence >= 2 and 0 < args.deadline_seconds <= 420 and args.interval > 0 and args.freshness_seconds > 0, "Invalid bounded wait policy.")
    folder = HERE / ("wait-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + f"-seq{args.expected_sequence}")
    folder.mkdir(exist_ok=False)
    source = Path(__file__).read_bytes()
    (folder / "wait-source.py").write_bytes(source)
    execution = {"started_at": utc(), "start_clock": time.monotonic(), "argv": sys.argv,
        "source_sha256": sha(source), "evaluator_sha256": EVALUATOR_SHA, "expected_sequence": args.expected_sequence,
        "deadline_seconds": args.deadline_seconds, "status": "initializing",
        "scope": "Read-only interim wait/replay. Returned code is the helper's own return value; final consumer summary/sealed acceptance remains required."}
    code = 2
    with (folder / "stdout.log").open("x", encoding="utf-8") as out, (folder / "stderr.log").open("x", encoding="utf-8") as err:
        stdout, stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = Tee(stdout, out), Tee(stderr, err)
        try:
            print(json.dumps({"wait_run": str(folder), "source_sha256": execution["source_sha256"], "expected_sequence": args.expected_sequence}), flush=True)
            code = run(args, folder, execution)
        except BaseException as error:
            execution.update(status="failed", error=repr(error))
            traceback.print_exc()
        finally:
            execution.update(completed_at=utc(), elapsed_seconds=time.monotonic() - execution.pop("start_clock"), returned_exit_code=code)
            (folder / "execution.json").write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
            sys.stdout, sys.stderr = stdout, stderr
    raise SystemExit(code)
