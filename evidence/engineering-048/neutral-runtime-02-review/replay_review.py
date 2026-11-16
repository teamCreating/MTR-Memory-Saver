"""Reproduce the attribution from frozen consumer sources and runtime inputs."""
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
CAPTURE = BASE / "capture-02"
sys.dont_write_bytecode = True
sys.path.insert(0, str(CAPTURE / "sources/tools"))
from client_experiment_analysis import client_log_completeness, native_diagnostics
from native_diagnostic_review import review_diagnostics, validate_review


def read(relative):
    return json.loads((CAPTURE / relative).read_bytes())


capture = read("capture.json")
plan, launch = read("packaged-client-plan.json"), read("packaged-client-launch.json")
assert capture["status"] == "captured"
assert hashlib.sha256((CAPTURE / "packaged-client-plan.json").read_bytes()).hexdigest() == launch["plan_sha256"]
process = read("process.json")
assert process["pid"] == launch["pid"] == capture["pid"]
assert Path(process["executable"]) == Path(plan["java"])
for relative, expected in capture["consumer_sources"].items():
    assert hashlib.sha256((CAPTURE / "sources" / relative).read_bytes()).hexdigest() == expected
for entry in capture["observer_source_checks"]:
    assert entry["matches"] and entry["expected"] == entry["actual"]
    assert hashlib.sha256((CAPTURE / "sources" / entry["path"]).read_bytes()).hexdigest() == entry["expected"]
assert capture["launcher_source_matches_receipt"] and capture["options_match_plan_at_capture"]
log_bytes = (CAPTURE / "logs/latest.log").read_bytes()
witness = capture["stream_captures"]["logs/latest.log"]
completeness = client_log_completeness(log_bytes, [{"client_log_witness": witness}], Path(plan["instance"]))
assert completeness["passed"], completeness
metadata, review = read("observer-target.json"), read("sources/config/native-diagnostic-review.json")
validate_review(review, metadata, root=ROOT)
log_text = log_bytes.decode("utf-8")
events = [json.loads(line) for line in (CAPTURE / "game-probe/native-invalid-model.jsonl").read_bytes().splitlines()]
epochs = [json.loads(line) for line in (CAPTURE / "game-probe/native-resource-epochs.jsonl").read_bytes().splitlines()]
result = review_diagnostics(native_diagnostics(log_text), log_text, events, epochs, process, metadata, review,
                            read("run-window.json"), read("final-snapshot.json"))
assert result == read("diagnostic-review.json"), "Frozen review did not replay byte-equivalent data."
assert result["native_attribution"]["passed"], result["native_attribution"]
report = {"passed": True, "raw_log_completeness": completeness,
          "native_attribution": result["native_attribution"], "consumer_source_count": len(capture["consumer_sources"]),
          "observer_source_count": len(capture["observer_source_checks"]), "observer_class_count": len(capture["observer_classes"]),
          "scope": "Replay of a live startup prefix; no gameplay or performance acceptance"}
print(json.dumps(report, indent=2, ensure_ascii=False))
