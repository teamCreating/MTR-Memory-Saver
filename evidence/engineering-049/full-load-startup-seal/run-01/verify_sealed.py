"""Independently verify sealed startup data without reading current instance inputs."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import zipfile
sys.dont_write_bytecode = True
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sealed", type=Path, default=Path(__file__).resolve().parent)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
folder, output = args.sealed.resolve(), args.output.resolve()
assert not output.exists(), "Fresh output path required"
def read(path):
    return json.loads(path.read_bytes())
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def instant(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
prefix, accepted = folder / "capture-01", folder / "assessment-03"
freeze, assessment = read(prefix / "freeze.json"), read(accepted / "assessment.json")
for relative, receipt in freeze["files"].items():
    path = prefix / relative
    assert sha(path) == receipt["sha256"]
    assert path.stat().st_size == receipt["bytes"] == receipt["source_size_before"] == receipt["source_size_after"]
plan, launch = read(prefix / "packaged-client-plan.json"), read(prefix / "packaged-client-launch.json")
process, native = read(accepted / "process.json"), read(prefix / "game-probe/native-observer.json")
assert launch["plan_sha256"] == sha(prefix / "packaged-client-plan.json")
assert process["pid"] == launch["pid"] == native["pid"] == assessment["pid"]
assert Path(process["executable"]) == Path(plan["java"])
assert abs((instant(process["created"]) - instant(native["process"]["start_instant"])).total_seconds()) < .002
for name in ("process-execution.json", "process.stdout.json", "process.stderr.log"):
    assert sha(accepted / name) == sha(folder / "assessment-01" / name)
raw = (accepted / "collector-read.jsonl.raw").read_bytes()
receipt = read(accepted / "collector-read-receipt.json")
assert hashlib.sha256(raw).hexdigest() == receipt["sha256"] and len(raw) == receipt["bytes"]
lines = raw[:raw.rfind(b"\n") + 1].splitlines(keepends=True)
kept = [line for line in lines if instant(json.loads(line)["captured_at"]) <= instant(freeze["ended"])]
assert b"".join(kept) == (prefix / "native-snapshots-prefix.jsonl").read_bytes()
rows = [json.loads(line) for line in kept]
assert len(rows) == assessment["native_snapshot_prefix_count"]
assert all(instant(a["snapshot"]["timestamp"]) < instant(b["snapshot"]["timestamp"]) for a,b in zip(rows, rows[1:]))
window = assessment["startup_stability"]
selected = [r for r in rows if instant(window["start"]) <= instant(r["snapshot"]["timestamp"]) <= instant(window["end"])]
assert len(selected) == window["samples"]
for row in selected:
    state = row["snapshot"]
    assert state["pid"] == process["pid"] and state["in_world"] and not state["paused"] and state["screen"] is None
    assert state["native_settled"] and state["native_pending"] == state["observation_errors"] == 0
    assert state["registered_count"] == assessment["native_counts"]["distinct_ids"]
    assert state["registered_declarations"] == assessment["native_counts"]["declarations"]
assert (instant(window["end"]) - instant(window["start"])).total_seconds() == window["seconds"] >= 60
assert max((instant(b["snapshot"]["timestamp"]) - instant(a["snapshot"]["timestamp"])).total_seconds() for a,b in zip(selected, selected[1:])) == window["maximum_gap_seconds"] <= 2
assert max((instant(r["captured_at"]) - instant(r["snapshot"]["timestamp"])).total_seconds() for r in selected) == window["maximum_capture_delay_seconds"]
errors = read(accepted / "collector-execution-prefix.json")["capture_errors"]
assert errors == assessment["all_collector_errors_retained"] and bool(errors) == (not assessment["whole_collector_error_free"])
assert not any(instant(window["start"]) <= instant(e["at"]) <= instant(window["end"]) for e in errors)
bindings = read(accepted / "installed-bindings.json")
for item in bindings["mods"]:
    planned = next(m for m in plan["mods"] if m["role"] == item["role"])
    assert item["actual_sha256"] == item["sha256"] == planned["sha256"]
    if item["role"] in {"observer", "companion"}:
        assert sha(accepted / "installed-tools" / item["filename"]) == item["sha256"]
for pack, planned in zip(bindings["packs"], plan["packs"]):
    assert pack["source_sha256"] == pack["installed_sha256"] == pack["sha256"] == planned["sha256"]
build = read(folder / "build-bindings-02/assessment.json")
counts = {}
for mod in build["bound_manifests"]:
    base = folder / "build-bindings-02" / mod["role"]
    manifest = read(base / (Path(mod["artifact"]).stem + ".build.json"))
    assert manifest["sha256"] == mod["artifact_sha256"]
    assert {r["path"]:r["expected_sha256"] for r in mod["inputs"]} == manifest["inputs"]
    for row in mod["inputs"]:
        assert sha(base / "inputs" / row["path"]) == row["resolved_input_sha256"] == row["expected_sha256"]
    counts[mod["role"]] = len(mod["inputs"])
sys.path.insert(0, str(accepted / "sources/tools"))
from client_experiment_analysis import native_diagnostics
from native_diagnostic_review import review_diagnostics, validate_review
review, metadata = read(accepted / "sources/config/native-diagnostic-review.json"), read(accepted / "observer-target.json")
validate_review(review, metadata, root=accepted / "proofs")
log = (prefix / "logs/latest.log").read_text(encoding="utf-8")
def stream(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]
replay = review_diagnostics(native_diagnostics(log), log, stream(prefix / "game-probe/native-invalid-model.jsonl"), stream(prefix / "game-probe/native-resource-epochs.jsonl"), process, metadata, review, {"start":plan["timestamp"], "end":freeze["ended"]}, native)
assert replay == read(accepted / "native-diagnostic-review.json")
assert sha(folder / assessment["image"]["path"]) == assessment["image"]["sha256"]
outer = folder / "sha256-index.json"
indexed = None
if outer.exists():
    index = read(outer)["files"]
    assert set(index) == {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and p != outer}
    for name, receipt in index.items():
        assert sha(folder / name) == receipt["sha256"] and (folder / name).stat().st_size == receipt["bytes"]
    indexed = len(index)
result = {"timestamp":dt.datetime.now(dt.timezone.utc).isoformat(), "sealed_only":True, "passed":True,
          "frozen_core_files":len(freeze["files"]), "prefix_samples":len(rows), "startup_stability":window,
          "exact_build_input_counts":counts, "native_diagnostic_replay_equal":True,
          "collector_errors_retained":errors, "whole_collector_error_free":not errors,
          "outer_index_verified_payloads":indexed, "scope":assessment["scope"]}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
