"""Preserve the stopped four-input OOM attempt and its historical prefix proofs."""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "capture-01"
OUTPUT.mkdir(exist_ok=False)
READS = []


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def copy(source, relative):
    started = now()
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or len(raw) != before.st_size:
        raise ValueError("Source changed during timed copy: " + str(source))
    path = OUTPUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Conflicting closure bytes.")
    else:
        with path.open("xb") as stream:
            stream.write(raw)
    READS.append({"source": str(source), "destination": path.relative_to(OUTPUT).as_posix(), "started_at": started,
                  "completed_at": now(), "bytes": len(raw), "sha256": sha(raw),
                  "file_id": [before.st_dev, before.st_ino], "mtime_ns": before.st_mtime_ns})
    return raw


def load(source, relative):
    return json.loads(copy(source, relative))


def log_closure(source, relative, reference):
    for name in ("context.json", "anchor.json", "anchor.bin", "plan.json", "launch.json", "log4j2.xml", "review.json"):
        copy(source / name, relative / name)
    raw = copy(source / reference["receipt"], relative / reference["receipt"])
    if sha(raw) != reference["receipt_sha256"]:
        raise ValueError("Producer native-log receipt differs from its pin.")
    for segment in json.loads(raw)["segments"]:
        copy(source / segment["blob"], relative / segment["blob"])


base = ROOT / ".cache/acceptance"
obs = base / "owned-049d-reload-observation-attempt03"
rec = base / "owned-049d-reload-recorder-attempt03"
progress = base / "owned-049d-reload-progress03"
summary = load(obs / "summary.json", Path("observer/summary.json"))
if summary["status"] != "stopped" or summary["passed"] is not False or summary["verified_reload_count"] != 0:
    raise ValueError("Unexpected final failure boundary.")
for name in ("samples.jsonl", "stop-request", "stop-request-captured.bin", "stop-request-receipt.json", "auxiliary-events.jsonl",
             "native-log-at-completion.log", "native-epoch-events-at-completion.jsonl", "native-diagnostic-events-at-completion.jsonl",
             "external-input-events-at-completion.jsonl"):
    copy(obs / name, Path("observer") / name)
for path in obs.iterdir():
    if path.is_file() and (path.suffix == ".py" or path.name in ("observer-target.json", "native-diagnostic-review.json", "native-log-reader.json", "native-observer-consumer.json")):
        copy(path, Path("observer") / path.name)
log_closure(obs / "native-log", Path("observer/native-log"), summary["native_log_stream"])
for name in ("session-start.json", "session-end.json", "packaged-client-plan.json", "packaged-client-launch.json", "journal.jsonl",
             "inputs.jsonl", "stop-request", "native-diagnostic-review.json", "observer-target.json"):
    copy(rec / name, Path("recorder") / name)
for path in (rec / "sources").iterdir():
    if path.is_file():
        copy(path, Path("recorder/sources") / path.name)
events = [json.loads(line) for line in (OUTPUT / "recorder/inputs.jsonl").read_bytes().splitlines()]
if len(events) != 4:
    raise ValueError("All four actual inputs must remain in the closure.")
record_numbers = {int(event["event_id"].rsplit(":", 1)[1]) for event in events}
attempts = {event["attempt_id"] for event in events}
if {path.name for path in (rec / "input-attempts").iterdir()} != attempts:
    raise ValueError("Unaccounted input-attempt directory.")
for attempt in sorted(attempts):
    for path in (rec / "input-attempts" / attempt).iterdir():
        if path.is_file():
            copy(path, Path("recorder/input-attempts") / attempt / path.name)
histories = [(progress / "evaluation-20261117T102844542541Z.json", "one"),
             (progress / "evaluation-20261117T104052486358Z.json", "two"),
             (progress / "wait-20261117T105138251245Z-seq4/evaluation-001.json", "three")]
bindings = []
for source, label in histories:
    result = load(source, Path("history") / label / "result.json")
    record_numbers.add(int(result["selected_published_record"].rsplit(":", 1)[1]))
    ranges = []
    for original, sealed in ((obs / "samples.jsonl", "observer/samples.jsonl"), (rec / "journal.jsonl", "recorder/journal.jsonl"), (rec / "inputs.jsonl", "recorder/inputs.jsonl")):
        matching = [item for item in result["read_receipts"] if Path(item["path"]) == original]
        if not matching:
            raise ValueError("Historical evaluator lacks its original owned-prefix receipt.")
        for item in matching:
            raw = (OUTPUT / sealed).read_bytes()[:item["bytes"]]
            if len(raw) != item["bytes"] or sha(raw) != item["sha256"]:
                raise ValueError("Historical exact prefix no longer exists in the final raw stream.")
        item = matching[0]
        ranges.append({"final_payload": sealed, "offset": 0, "bytes": item["bytes"], "sha256": item["sha256"]})
    bindings.append({"label": label, "result": f"history/{label}/result.json", "original_result": str(source),
                     "verified_count": result["verified_reload_count"], "record_number": int(result["selected_published_record"].rsplit(":", 1)[1]), "exact_prefixes": ranges})
for folder, label in ((progress / "wait-20261117T105138251245Z-seq4", "ready-three"),
                      (progress / "wait-20261117T105223464434Z-seq5", "deadline-four")):
    for path in folder.iterdir():
        if path.is_file():
            copy(path, Path("waiter") / label / path.name)
copy(progress / "evaluate_once.py", Path("operators/evaluate_once.py"))
copy(progress / "wait_ready.py", Path("operators/wait_ready.py"))
journal = [json.loads(line) for line in (OUTPUT / "recorder/journal.jsonl").read_bytes().splitlines()]
last = next(row for row in reversed(journal) if row["event"]["kind"] == "ineligible")
last_number = int(last["event"]["record_id"].rsplit(":", 1)[1])
record_numbers.add(last_number)
for number in sorted(record_numbers):
    folder = Path("recorder/records") / f"{number:08d}"
    source = rec / "records" / f"{number:08d}"
    raw_rows = [json.loads(line) for line in copy(source / "raw-evidence.jsonl", folder / "raw-evidence.jsonl").splitlines()]
    for row in raw_rows:
        raw = copy(rec / row["path"], Path("recorder") / row["path"])
        if len(raw) != row["bytes"] or sha(raw) != row["sha256"]:
            raise ValueError("Original retained raw blob differs.")
    if number == last_number:
        log_row = next(row for row in raw_rows if row["name"] == "client-log-prefix.log")
        relative = f"captures/{number:08d}.json"
        receipt_raw = (rec / "native-log" / relative).read_bytes()
        if json.loads(receipt_raw)["sha256"] != log_row["sha256"]:
            raise ValueError("Last ineligible capture has no exact matching native-log receipt.")
        reference = {"receipt": relative, "receipt_sha256": sha(receipt_raw)}
    else:
        before = load(source / "before.json", folder / "before.json")
        copy(source / "receipt.json", folder / "receipt.json")
        reference = before["native_log_stream"]
    log_closure(rec / "native-log", Path("recorder/native-log"), reference)
for path in (base / "owned-049d-ui-resume03").iterdir():
    if path.is_file():
        copy(path, Path("ui") / path.name)
collector = base / "capture-owned-049d"
execution = load(collector / "execution.json", Path("collector-checkpoint/execution.json"))
if execution["exports"][-1]["status"] != "readable" or not execution["exports"][-1]["recording"].endswith("diagnostic-02.jfr"):
    raise ValueError("Post-OOM export02 is not a completed readable export.")
for name in ("export-request-02", "export-02-dump.stdout.log", "export-02-dump.stderr.log", "export-02-summary.stdout.log", "export-02-summary.stderr.log"):
    copy(collector / name, Path("collector-checkpoint") / name)
review = json.loads((OUTPUT / "observer/native-diagnostic-review.json").read_bytes())
for proof in review["proofs"]:
    if sha(copy(ROOT / proof["path"], Path("proof-root") / proof["path"])) != proof["sha256"]:
        raise ValueError("Pinned diagnostic proof changed.")
plan = json.loads((OUTPUT / "recorder/packaged-client-plan.json").read_bytes())
fingerprints = []
for mod in plan["mods"]:
    path = Path(plan["instance"]) / "mods" / mod["filename"]
    started, before = now(), path.stat()
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    if actual != mod["sha256"] or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("Actual installed artifact differs from its frozen launch plan.")
    fingerprints.append({**mod, "path": str(path), "bytes": before.st_size, "actual_sha256": actual,
                         "started_at": started, "completed_at": now(), "binary_copied": False})
(OUTPUT / "installed-fingerprints.json").write_text(json.dumps(fingerprints, indent=2) + "\n", encoding="utf-8")
(OUTPUT / "history-bindings.json").write_text(json.dumps({"histories": bindings, "retained_record_numbers": sorted(record_numbers),
    "last_ineligible_record_number": last_number, "last_ineligible_log_receipt": f"captures/{last_number:08d}.json"}, indent=2) + "\n", encoding="utf-8")
(OUTPUT / "read-receipts.json").write_text(json.dumps({"completed_at": now(), "reads": READS,
    "scope": "Closed consumer/recorder evidence, bounded historical prefix ranges and one collector checkpoint. No growing native-snapshots, JFR binary copy/rehash, UI or runtime change."}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"copied_reads": len(READS), "retained_record_numbers": sorted(record_numbers), "final_verified_reloads": summary["verified_reload_count"]}))
