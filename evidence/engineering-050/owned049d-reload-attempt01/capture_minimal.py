"""Copy the terminated attempt's explicit dependency closure, without live sampling."""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "capture-01"
OUTPUT.mkdir(exist_ok=False)
READS = []


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def copy(source, relative):
    started = stamp()
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or len(raw) != before.st_size:
        raise ValueError("Source changed during its explicitly timed copy: " + str(source))
    path = OUTPUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Duplicate closure destination has different original bytes.")
    else:
        with path.open("xb") as stream:
            stream.write(raw)
    READS.append({"source": str(source), "destination": path.relative_to(OUTPUT).as_posix(),
                  "started_at": started, "completed_at": stamp(), "bytes": len(raw), "sha256": sha(raw),
                  "source_file_id": [before.st_dev, before.st_ino], "source_mtime_ns": before.st_mtime_ns})
    return raw


def load(source, relative):
    return json.loads(copy(source, relative))


def log_closure(source, relative, reference):
    for name in ("context.json", "anchor.json", "anchor.bin", "plan.json", "launch.json", "log4j2.xml", "review.json"):
        copy(source / name, relative / name)
    receipt = load(source / reference["receipt"], relative / reference["receipt"])
    if sha((OUTPUT / relative / reference["receipt"]).read_bytes()) != reference["receipt_sha256"]:
        raise ValueError("Original producer receipt differs from its reference.")
    for segment in receipt["segments"]:
        copy(source / segment["blob"], relative / segment["blob"])


base = ROOT / ".cache/acceptance"
observer = base / "owned-049d-reload-observation-attempt01"
recorder = base / "owned-049d-reload-recorder-attempt01"
ui = base / "owned-049d-ui"
collector = base / "capture-owned-049d"
summary = load(observer / "summary.json", Path("observer/summary.json"))
if summary["status"] != "stopped" or summary["passed"] is not False:
    raise ValueError("This is not the terminated failed attempt being sealed.")
for name in ("samples.jsonl", "stop-request", "stop-request-captured.bin", "stop-request-receipt.json",
             "auxiliary-events.jsonl", "native-log-at-completion.log", "native-epoch-events-at-completion.jsonl",
             "native-diagnostic-events-at-completion.jsonl", "external-input-events-at-completion.jsonl"):
    copy(observer / name, Path("observer") / name)
for path in observer.iterdir():
    if path.is_file() and (path.suffix == ".py" or path.name in ("observer-target.json", "native-diagnostic-review.json", "native-log-reader.json", "native-observer-consumer.json")):
        copy(path, Path("observer") / path.name)
log_closure(observer / "native-log", Path("observer/native-log"), summary["native_log_stream"])
for name in ("session-start.json", "session-end.json", "packaged-client-plan.json", "packaged-client-launch.json",
             "journal.jsonl", "inputs.jsonl", "stop-request", "native-diagnostic-review.json", "observer-target.json"):
    copy(recorder / name, Path("recorder") / name)
for path in (recorder / "sources").iterdir():
    if path.is_file():
        copy(path, Path("recorder/sources") / path.name)
events = [json.loads(line) for line in (OUTPUT / "recorder/inputs.jsonl").read_bytes().splitlines()]
if len(events) != 1 or events[0]["event_id"].rsplit(":", 1)[1] != "44":
    raise ValueError("Unexpected input ledger; do not broaden the selected record silently.")
event = events[0]
attempt = recorder / "input-attempts" / event["attempt_id"]
if {path.name for path in (recorder / "input-attempts").iterdir()} != {event["attempt_id"]}:
    raise ValueError("Unaccounted input attempt directory.")
for path in attempt.iterdir():
    if path.is_file():
        copy(path, Path("recorder/input-attempts") / event["attempt_id"] / path.name)
for name in ("before.json", "receipt.json", "raw-evidence.jsonl"):
    copy(recorder / "records/00000044" / name, Path("recorder/records/00000044") / name)
for relative in set(event["raw_files"].values()):
    copy(recorder / relative, Path("recorder") / relative)
log_closure(recorder / "native-log", Path("recorder/native-log"), event["native_log_stream"])
for path in ui.iterdir():
    if path.is_file():
        copy(path, Path("ui") / path.name)
for name in ("execution.json", "export-request-01", "export-01-dump.stdout.log", "export-01-dump.stderr.log",
             "export-01-summary.stdout.log", "export-01-summary.stderr.log"):
    copy(collector / name, Path("collector-checkpoint") / name)
review = json.loads((OUTPUT / "observer/native-diagnostic-review.json").read_bytes())
for proof in review["proofs"]:
    raw = copy(ROOT / proof["path"], Path("proof-root") / proof["path"])
    if sha(raw) != proof["sha256"]:
        raise ValueError("Original diagnostic proof pin differs: " + proof["path"])
(OUTPUT / "read-receipts.json").write_text(json.dumps({"completed_at": stamp(), "reads": READS,
    "scope": "Explicit terminated-attempt closure and one read-timed collector execution/export checkpoint. No native-snapshots JSONL read, JFR binary copy, live sampling, UI or runtime modification."}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"copied_reads": len(READS), "selected_record": "00000044", "other_record_payloads_copied": 0}))
