"""Continuously seal native reload-before evidence without controlling the game.

Use record against an existing launched JVM; create OUTPUT/stop-request to stop
only this reader. Use confirm with an actual external input receipt afterwards.
Every confirmation attempt is retained, including missing/stale/failed evidence.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid
import zipfile
import native_log_stream

import client_experiment_analysis as analysis
import native_diagnostic_review as diagnostics
import observe_packaged_client as observer
import windows_snapshot_io

FRESHNESS_SECONDS = 15
ROOT = Path(__file__).resolve().parent.parent


class NotReady(ValueError):
    """An observed transition is preserved but cannot be an input anchor."""


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_once(path, raw):
    """Do not publish until the owned writer has flushed, synced and closed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return now()


def append_bytes(path, raw):
    with path.open("ab") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def read_prefix(path):
    # The handle remains owned until all bytes are read. File sharing permits the
    # actual native publisher to replace snapshots and append trace/log streams.
    with windows_snapshot_io.open_snapshot(path) as stream:
        length = os.fstat(stream.fileno()).st_size
        raw = stream.read(length)
        if len(raw) != length:
            raise OSError("Source shrank during the owned prefix read: " + str(path))
        return raw


def json_lines(raw):
    if raw and not raw.endswith(b"\n"):
        raise ValueError("An append-only evidence stream ends in an incomplete record.")
    return [json.loads(line) for line in raw.splitlines()]


class Journal:
    def __init__(self, path):
        self.path, self.sequence, self.previous = path, 0, None
        write_once(path, b"")

    def add(self, kind, **fields):
        body = {"sequence": self.sequence + 1, "previous_sha256": self.previous,
                "event": {"kind": kind, "recorded_at": now(), **fields}}
        value = {**body, "sha256": sha(canonical(body))}
        append_bytes(self.path, canonical(value))
        self.sequence += 1
        self.previous = value["sha256"]
        return value


def verify_journal(raw):
    rows, previous = json_lines(raw), None
    for sequence, row in enumerate(rows, 1):
        body = {key: row[key] for key in ("sequence", "previous_sha256", "event")}
        if row["sequence"] != sequence or row["previous_sha256"] != previous or row["sha256"] != sha(canonical(body)):
            raise ValueError("Recorder journal chain is missing, changed or reordered.")
        previous = row["sha256"]
    return rows


def source_files():
    return [Path(__file__), Path(observer.__file__), Path(analysis.__file__),
            Path(diagnostics.__file__), Path(windows_snapshot_io.__file__),
            Path(observer.windows_process_identity.__file__), Path(native_log_stream.__file__),
            native_log_stream.REVIEW_FILE, observer.NEUTRAL_CONTRACT_FILE]


def before_errors(state, process, stamp, expected, metadata, log, epochs, events, review, plan):
    errors = analysis.native_snapshot_errors(state, process, stamp, FRESHNESS_SECONDS,
                                            {"expected_registration": expected}, require_scene=False)
    if state.get("target") != metadata:
        errors.append("Native snapshot metadata differs from its actual pinned observer.")
    try:
        observer.validate_neutral_contract(metadata, state)
    except ValueError as error:
        errors.append(str(error))
    if state.get("in_world") is not True or state.get("screen") is not None or state.get("paused") is not False:
        errors.append("Actual unpaused, unobstructed game screen is required.")
    if state.get("timestamp") != state.get("observed_at"):
        errors.append("Native timestamp aliases differ.")
    raw_log = log.encode("utf-8")
    completeness = analysis.client_log_completeness(raw_log, [{"client_log_witness": {"bytes": len(raw_log), "sha256": sha(raw_log)}}], Path(plan["instance"]))
    errors.extend(completeness["errors"])
    if observer.instant(state["observed_at"]) > observer.instant(stamp):
        errors.append("Native snapshot is future dated.")
    result = diagnostics.review_diagnostics(analysis.native_diagnostics(log), log, events, epochs,
                                           process, metadata, review,
                                           {"start": plan["timestamp"], "end": stamp}, state)
    if not result["native_attribution"]["passed"]:
        errors.extend(result["native_attribution"]["errors"])
    if result["unreviewed_native"]:
        errors.append("Unreviewed native diagnostics remain in the actual log prefix.")
    return errors


class Recorder:
    def __init__(self, instance, output, expected, *, process_factory=observer.WindowsProcess, log_prefix_witness=None):
        self.instance, self.output = Path(instance).resolve(), Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.journal = Journal(self.output / "journal.jsonl")
        self.process, self.number, self.prefixes = None, 0, {}
        self.session_id = str(uuid.uuid4())
        self.journal.add("initializing", session_id=self.session_id)
        try:
            self.source_hashes = {}
            for path in source_files():
                raw = path.read_bytes()
                write_once(self.output / "sources" / path.name, raw)
                self.source_hashes[str(path)] = sha(raw)
            self.plan, self.launch = observer.frozen_context(self.instance)
            for name in ("packaged-client-plan.json", "packaged-client-launch.json"):
                write_once(self.output / name, (self.instance / name).read_bytes())
            self.plan_hash = observer.digest(self.output / "packaged-client-plan.json")
            self.launch_hash = observer.digest(self.output / "packaged-client-launch.json")
            self.process = process_factory(self.plan, self.launch)
            if not self.process.sample()["running"]:
                raise ValueError("The actual launched JVM has exited.")
            self.identity = {**self.process.identity, "created": self.process.created}
            installed = next(item for item in self.plan["mods"] if item["role"] == "observer")
            with zipfile.ZipFile(self.instance / "mods" / installed["filename"]) as jar:
                metadata_raw = jar.read("mtr-native-observer-target.json")
            self.metadata = json.loads(metadata_raw)
            write_once(self.output / "observer-target.json", metadata_raw)
            review_raw = (ROOT / "config/native-diagnostic-review.json").read_bytes()
            self.review = json.loads(review_raw)
            diagnostics.validate_review(self.review, self.metadata, root=ROOT)
            write_once(self.output / "native-diagnostic-review.json", review_raw)
            self.expected = expected
            self.log_stream = native_log_stream.NativeLogStream.from_launch(self.instance, self.plan, self.launch,
                self.output / "native-log", self.identity, prefix_witness=log_prefix_witness)
            self.context = {"schema": 1, "session_id": self.session_id, "created_at": now(), "instance": str(self.instance),
                            "process": self.identity, "expected_registration": expected, "metadata": self.metadata,
                            "plan_sha256": self.plan_hash, "launch_sha256": self.launch_hash,
                            "freshness_seconds": FRESHNESS_SECONDS, "source_sha256": self.source_hashes,
                            "native_log_context": {"path": "native-log/context.json", "sha256": self.log_stream.context_sha256},
                            "native_log_prefix_witness": self.log_stream.context["prefix_witness"],
                            "scope": "Read-only native input-before evidence; no input or gameplay/performance acceptance"}
            self.context_hash = sha(canonical(self.context))
            write_once(self.output / "session-start.json", canonical(self.context))
            self.journal.add("ready", session_start_sha256=self.context_hash)
        except BaseException as error:
            self.journal.add("initialization_failed", error=repr(error))
            self.close()
            raise

    def close(self):
        if self.process is not None:
            self.process.close()
            self.process = None

    def store_raw(self, directory, name, raw):
        path = self.output / "blobs" / (sha(raw) + ".bin")
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError("An immutable captured blob changed: " + str(path))
        else:
            write_once(path, raw)
        relative = path.relative_to(self.output).as_posix()
        append_bytes(directory / "raw-evidence.jsonl", canonical({"name": name, "path": relative,
                     "sha256": sha(raw), "bytes": len(raw), "retained_at": now()}))
        return relative

    def capture(self):
        self.number += 1
        record_id = f"{self.session_id}:{self.number}"
        directory = self.output / "records" / f"{self.number:08d}"
        directory.mkdir(parents=True, exist_ok=False)
        started, started_nanos = now(), time.monotonic_ns()
        self.journal.add("capture_started", record_id=record_id, capture_started_at=started)
        try:
            if not self.process.sample()["running"]:
                raise RuntimeError("The owned JVM has exited.")
            if observer.digest(self.instance / "packaged-client-plan.json") != self.plan_hash or observer.digest(self.instance / "packaged-client-launch.json") != self.launch_hash:
                raise ValueError("The launch context changed during recording.")
            for path, expected_sha in self.source_hashes.items():
                if observer.digest(Path(path)) != expected_sha:
                    raise ValueError("Recorder source changed while running: " + path)
            names = {"epochs": self.metadata["epochs_path"], "diagnostics": self.metadata["diagnostics_path"]}
            first = {key: read_prefix(self.instance / relative) for key, relative in names.items()}
            raw_files = {}
            for key, raw in first.items():
                name = key + "-before.jsonl"
                raw_files[name] = self.store_raw(directory, name, raw)
            state_raw = windows_snapshot_io.read_snapshot_bytes(self.instance / self.metadata["snapshot_path"])
            raw_files["native-snapshot.json"] = self.store_raw(directory, "native-snapshot.json", state_raw)
            log_snapshot = self.log_stream.read()
            log = log_snapshot.data
            raw_files["client-log-prefix.log"] = self.store_raw(directory, "client-log-prefix.log", log)
            second = {key: read_prefix(self.instance / relative) for key, relative in names.items()}
            for key, raw in second.items():
                name = key + "-after.jsonl"
                raw_files[name] = self.store_raw(directory, name, raw)
            if not self.process.sample()["running"]:
                raise RuntimeError("The owned JVM exited during capture.")
            completed, completed_nanos = now(), time.monotonic_ns()
            raw_streams = {**second, "log": log}
            for key, raw in raw_streams.items():
                if key in self.prefixes and not raw.startswith(self.prefixes[key]):
                    raise ValueError("An observed source stream was changed or truncated: " + key)
            self.prefixes = raw_streams
            if first != second:
                raise NotReady("Native callback streams advanced during capture.")
            state, epochs, events = json.loads(state_raw), json_lines(second["epochs"]), json_lines(second["diagnostics"])
            errors = before_errors(state, self.identity, completed, self.expected, self.metadata,
                                   log.decode("utf-8"), epochs, events, self.review, self.plan)
            if errors:
                raise NotReady("; ".join(errors))
            record = {"schema_version": 1, "event_id": record_id, "timestamp": completed,
                      "capture_started_at": started, "capture_completed_at": completed,
                      "capture_started_monotonic_ns": started_nanos, "capture_completed_monotonic_ns": completed_nanos,
                      "pid": self.identity["pid"], "process_created": self.identity["created"], "method": "native_f3_t",
                      "before": state, "before_state_sha256": sha(state_raw), "log_offset": len(log), "log_prefix_sha256": sha(log),
                      "plan_sha256": self.plan_hash, "launch_sha256": self.launch_hash, "session_start_sha256": self.context_hash,
                      "epochs_sha256": sha(second["epochs"]), "diagnostics_sha256": sha(second["diagnostics"]), "raw_files": raw_files}
            record["native_log_stream"] = self.log_stream.reference()
            payload = canonical(record)
            payload_closed = write_once(directory / "before.json", payload)
            receipt = {"schema": 1, "record_id": record_id, "session_id": self.session_id,
                       "payload": str((directory / "before.json").relative_to(self.output).as_posix()),
                       "payload_sha256": sha(payload), "payload_closed_at": payload_closed,
                       "capture_started_at": started, "capture_completed_at": completed, "session_start_sha256": self.context_hash}
            receipt_raw = canonical(receipt)
            receipt_closed = write_once(directory / "receipt.json", receipt_raw)
            return self.journal.add("published", record_id=record_id,
                                    receipt=str((directory / "receipt.json").relative_to(self.output).as_posix()),
                                    receipt_sha256=sha(receipt_raw), receipt_closed_at=receipt_closed)
        except NotReady as error:
            self.journal.add("ineligible", record_id=record_id, capture_started_at=started, capture_completed_at=now(), error=str(error))
            return None
        except BaseException as error:
            self.journal.add("capture_failed", record_id=record_id, capture_started_at=started, capture_completed_at=now(), error=repr(error))
            raise


def owned_path(root, relative):
    path = (root / relative).resolve(strict=True)
    if root.resolve() not in path.parents:
        raise ValueError("Evidence path escapes its recorder directory.")
    return path


def select_before(output, receipt, journal_raw):
    """Choose the unique nearest completed publication; never fall back past a failure."""
    context_raw = (output / "session-start.json").read_bytes()
    context = json.loads(context_raw)
    for relative, expected in (("packaged-client-plan.json", context["plan_sha256"]), ("packaged-client-launch.json", context["launch_sha256"])):
        if sha((output / relative).read_bytes()) != expected:
            raise ValueError("Frozen recorder launch context changed: " + relative)
    for path, expected in context["source_sha256"].items():
        if sha((output / "sources" / Path(path).name).read_bytes()) != expected:
            raise ValueError("Frozen recorder source changed: " + path)
    if context["freshness_seconds"] != FRESHNESS_SECONDS:
        raise ValueError("Recorder changed the frozen 15-second input-before criterion.")
    issued, confirmed = observer.instant(receipt["issued_at"]), observer.instant(receipt["confirmed_at"])
    if type(receipt.get("succeeded")) is not bool or receipt.get("method") != "native_f3_t" or not receipt.get("provider") or confirmed < issued:
        raise ValueError("Require an actual external native-input receipt, including its success/failure result.")
    rows = verify_journal(journal_raw)
    published = [row for row in rows if row["event"]["kind"] == "published" and observer.instant(row["event"]["receipt_closed_at"]) <= issued]
    if not published:
        raise ValueError("No fully published before record predates this actual input.")
    latest = max(observer.instant(row["event"]["receipt_closed_at"]) for row in published)
    choices = [row for row in published if observer.instant(row["event"]["receipt_closed_at"]) == latest]
    if len(choices) != 1:
        raise ValueError("Last publication time is ambiguous; no unique before record.")
    selected = choices[0]
    for row in rows[selected["sequence"]:]:
        event = row["event"]
        if event["kind"] in ("ineligible", "capture_failed", "initialization_failed", "failed") and observer.instant(event["recorded_at"]) <= issued:
            raise ValueError("A later failed/ineligible observation invalidates the previous before record.")
    event = selected["event"]
    receipt_path = owned_path(output, event["receipt"])
    publication_raw = receipt_path.read_bytes()
    if sha(publication_raw) != event["receipt_sha256"]:
        raise ValueError("Published receipt hash differs from the journal.")
    publication = json.loads(publication_raw)
    before_path = owned_path(output, publication["payload"])
    before_raw = before_path.read_bytes()
    if sha(before_raw) != publication["payload_sha256"]:
        raise ValueError("Immutable before payload hash differs from its publication receipt.")
    record = json.loads(before_raw)
    if record["event_id"] != publication["record_id"] or record["event_id"] != event["record_id"] or publication["session_id"] != context["session_id"]:
        raise ValueError("Publication and before record identities differ.")
    if record["session_start_sha256"] != sha(context_raw) or publication["session_start_sha256"] != sha(context_raw):
        raise ValueError("Published before record belongs to another recorder session.")
    if record["pid"] != context["process"]["pid"] or record["process_created"] != context["process"]["created"] or record["plan_sha256"] != context["plan_sha256"] or record["launch_sha256"] != context["launch_sha256"]:
        raise ValueError("Published process or launch binding differs.")
    times = [observer.instant(record[key]) for key in ("capture_started_at", "capture_completed_at")]
    times += [observer.instant(publication["payload_closed_at"]), observer.instant(event["receipt_closed_at"]), issued]
    if times != sorted(times) or record["timestamp"] != record["capture_completed_at"]:
        raise ValueError("Capture/write/publication/input ordering is invalid.")
    if any(record[key] != publication[key] for key in ("capture_started_at", "capture_completed_at")):
        raise ValueError("Published capture timing differs from the canonical payload.")
    for stamp in (record["before"]["timestamp"], record["timestamp"], event["receipt_closed_at"]):
        if not 0 <= (issued - observer.instant(stamp)).total_seconds() <= FRESHNESS_SECONDS:
            raise ValueError("Nearest published before record is stale for the frozen 15-second criterion.")
    for name, expected in (("native-snapshot.json", record["before_state_sha256"]), ("client-log-prefix.log", record["log_prefix_sha256"]),
                           ("epochs-after.jsonl", record["epochs_sha256"]), ("diagnostics-after.jsonl", record["diagnostics_sha256"])):
        if sha(owned_path(output, record["raw_files"][name]).read_bytes()) != expected:
            raise ValueError("Published raw evidence fingerprint differs: " + name)
    if json.loads(owned_path(output, record["raw_files"]["native-snapshot.json"]).read_bytes()) != record["before"]:
        raise ValueError("Canonical before state differs from its preserved native snapshot.")
    if owned_path(output, record["raw_files"]["client-log-prefix.log"]).stat().st_size != record["log_offset"]:
        raise ValueError("Before log offset differs from the actual preserved prefix.")
    reference = record["native_log_stream"]
    log_root = owned_path(output, "native-log")
    receipt_path = owned_path(log_root, reference["receipt"])
    if (sha(receipt_path.read_bytes()) != reference["receipt_sha256"]
            or reference["context_sha256"] != context["native_log_context"]["sha256"]
            or sha((log_root / "context.json").read_bytes()) != context["native_log_context"]["sha256"]):
        raise ValueError("Native rolling log receipt/context differs from this recorder session.")
    log_context = json.loads((log_root / "context.json").read_bytes())
    if (log_context["plan_sha256"] != context["plan_sha256"] or log_context["launch_sha256"] != context["launch_sha256"]
            or log_context["process"]["pid"] != context["process"]["pid"]
            or observer.instant(log_context["process"]["created"]) != observer.instant(context["process"]["created"])):
        raise ValueError("Native rolling log belongs to another plan/launch/process.")
    if native_log_stream.verify_capture(log_root, receipt_path) != owned_path(output, record["raw_files"]["client-log-prefix.log"]).read_bytes():
        raise ValueError("Native rolling log segments do not reconstruct this input prefix.")
    stream_receipt = json.loads(receipt_path.read_bytes())
    if not observer.instant(record["capture_started_at"]) <= observer.instant(stream_receipt["started_at"]) <= observer.instant(stream_receipt["completed_at"]) <= observer.instant(record["capture_completed_at"]):
        raise ValueError("Native log publication was captured outside its before-record interval.")
    return before_path, {"journal_sequence": selected["sequence"], "journal_sha256": selected["sha256"],
                         "receipt_sha256": event["receipt_sha256"], "receipt_closed_at": event["receipt_closed_at"]}


def input_events(output, *, pending_attempt=None):
    """Load the whole attempt ledger; incomplete confirmations cannot disappear.

    Full-chain consumers must call this instead of treating inputs.jsonl alone as
    complete. It raises if any retained submission is absent from that stream.
    """
    output = Path(output)
    events = json_lines((output / "inputs.jsonl").read_bytes()) if (output / "inputs.jsonl").exists() else []
    by_id = {}
    for event in events:
        if event["attempt_id"] in by_id:
            raise ValueError("Duplicate confirmation attempt in the input ledger.")
        by_id[event["attempt_id"]] = event
    attempts = [path for path in (output / "input-attempts").iterdir() if path.name != pending_attempt] if (output / "input-attempts").exists() else []
    if set(by_id) != {path.name for path in attempts}:
        raise ValueError("Input ledger omits a retained confirmation attempt or includes an unknown attempt.")
    for path in attempts:
        event = by_id[path.name]
        if json.loads((path / "result.json").read_bytes()) != event or sha((path / "external-receipt.json").read_bytes()) != event["external_receipt_sha256"]:
            raise ValueError("Input ledger differs from an immutable original attempt.")
        submission = json.loads((path / "submission.json").read_bytes())
        if (submission["attempt_id"] != path.name or submission["submitted_at"] != event["attempt_submitted_at"]
                or submission["external_receipt_sha256"] != event["external_receipt_sha256"]):
            raise ValueError("Input ledger differs from its original submission receipt.")
        if event.get("record_status") == "selected":
            receipt = json.loads((path / "external-receipt.json").read_bytes())
            before_path, publication = select_before(output, receipt, (path / "journal-prefix.jsonl").read_bytes())
            before = json.loads(before_path.read_bytes())
            if (event.get("publication") != publication or event.get("input") != receipt
                    or event.get("before_record_sha256") != sha(before_path.read_bytes())
                    or any(event.get(key) != value for key, value in before.items())):
                raise ValueError("Selected input differs from its independently sealed before evidence.")
        elif event.get("record_status") != "rejected":
            raise ValueError("Unknown retained input attempt status.")
    return events


def confirm(output, receipt_path):
    output = Path(output).resolve(strict=True)
    attempt_id = str(uuid.uuid4())
    attempt = output / "input-attempts" / attempt_id
    attempt.mkdir(parents=True, exist_ok=False)
    receipt_raw = Path(receipt_path).read_bytes()
    write_once(attempt / "external-receipt.json", receipt_raw)
    submitted = now()
    write_once(attempt / "submission.json", canonical({"attempt_id": attempt_id, "submitted_at": submitted, "external_receipt_sha256": sha(receipt_raw)}))
    lock = output / "confirmation.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(attempt_id)
    try:
        context = json.loads((output / "session-start.json").read_bytes())
        receipt = None
        try:
            receipt = json.loads(receipt_raw)
            if observer.instant(receipt["confirmed_at"]) > observer.instant(submitted):
                raise ValueError("Actual input confirmation cannot be future dated relative to its submission.")
            journal_raw = read_prefix(output / "journal.jsonl")
            write_once(attempt / "journal-prefix.jsonl", journal_raw)
            before_path, selection = select_before(output, receipt, journal_raw)
            prior = input_events(output, pending_attempt=attempt_id)
            record_id = json.loads(before_path.read_bytes())["event_id"]
            if any(row.get("event_id") == record_id for row in prior):
                raise ValueError("The unique nearest published before record was already used by an input attempt.")
            event = observer.confirm_reload_input(before_path, attempt / "confirmed-event.jsonl", receipt)
            with (attempt / "confirmed-event.jsonl").open("ab") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            event.update(attempt_id=attempt_id, attempt_submitted_at=submitted, external_receipt_sha256=sha(receipt_raw), publication=selection, record_status="selected")
        except (OSError, ValueError, KeyError, TypeError) as error:
            event = {"schema_version": 1, "event_id": "rejected:" + attempt_id, "attempt_id": attempt_id,
                     "timestamp": submitted, "attempt_submitted_at": submitted, "pid": context["process"]["pid"],
                     "process_created": context["process"]["created"], "method": "native_f3_t", "input": receipt,
                     "external_receipt_sha256": sha(receipt_raw), "record_status": "rejected", "selection_error": str(error)}
        event_raw = canonical(event)
        write_once(attempt / "result.json", event_raw)
        append_bytes(output / "inputs.jsonl", event_raw)
        return event
    finally:
        lock.unlink()


def record(args):
    recorder = Recorder(args.instance, args.output,
                        {"distinct_ids": args.expected_count, "declarations": args.expected_declarations},
                        log_prefix_witness=getattr(args, "log_prefix_witness", None))
    deadline = time.monotonic() + args.duration_seconds if args.duration_seconds else None
    status = "stopped"
    try:
        while not (recorder.output / "stop-request").exists() and (deadline is None or time.monotonic() < deadline):
            recorder.capture()
            time.sleep(args.interval_seconds)
        recorder.journal.add("stopped", reason="stop_request" if (recorder.output / "stop-request").exists() else "duration_elapsed")
    except BaseException as error:
        status = "failed"
        recorder.journal.add("failed", error=repr(error))
        raise
    finally:
        recorder.close()
        write_once(recorder.output / "session-end.json", canonical({"status": status, "ended_at": now(), "captures": recorder.number,
                   "process_handle_closed": recorder.process is None, "journal_sha256": observer.digest(recorder.output / "journal.jsonl")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    collect = modes.add_parser("record")
    collect.add_argument("--instance", type=Path, required=True)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--expected-count", type=int, required=True)
    collect.add_argument("--expected-declarations", type=int, required=True)
    collect.add_argument("--interval-seconds", type=observer.finite_positive, default=1)
    collect.add_argument("--duration-seconds", type=observer.finite_positive)
    collect.add_argument("--log-prefix-witness", type=Path, help="Existing independent prefix from this exact launched JVM, required after rollover.")
    confirm_parser = modes.add_parser("confirm")
    confirm_parser.add_argument("--output", type=Path, required=True)
    confirm_parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "record":
        if args.expected_count <= 0 or args.expected_declarations < args.expected_count:
            parser.error("Require positive distinct counts and declarations at least as large.")
        record(args)
    else:
        result = confirm(args.output, args.receipt)
        print(json.dumps({"attempt_id": result["attempt_id"], "record_status": result["record_status"],
                          "error": result.get("selection_error")}, ensure_ascii=False))
        return 0 if result["record_status"] == "selected" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
