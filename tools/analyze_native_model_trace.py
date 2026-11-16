"""Attribute captured native invalid-model events without dismissing other errors.

The report is diagnostic evidence, never whole-client or gameplay acceptance.
Only the exact official default-rail call chain is classified as generated.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import zipfile


def digest(path):
    with pathlib.Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ancestors(event):
    frames = [(frame["class"], frame["method"]) for frame in event["stack"]]
    factory = ("org.mtr.resource.VehicleModel", "getModelLoaderBase")
    require(factory in frames, "Trace event lacks the actual native factory frame")
    return frames[frames.index(factory):]


def analyze(events, log_text, target, pid, process_started_at):
    require(events and events[0]["phase"] == "installed", "Missing initial trace installation receipt")
    process_start = dt.datetime.fromisoformat(process_started_at)
    pending, calls = {}, []
    previous_nanos = -1
    require(sum(row["phase"] == "installed" for row in events) == 1, "Trace installation must occur exactly once")
    for sequence, event in enumerate(events, 1):
        require(event["schema_version"] == 1 and event["sequence"] == sequence, "Trace sequence is missing, duplicated, or reordered")
        require(event["target"] == target, "Trace target differs from the installed diagnostic metadata")
        require(event["pid"] == pid and event["process_started_at"] == process_started_at, "Trace belongs to a different JVM")
        require(event["observation_errors"] == 0, "Diagnostic observation failed")
        require(dt.datetime.fromisoformat(event["timestamp"]) >= process_start, "Trace predates its JVM creation")
        require(event["monotonic_nanos"] >= previous_nanos, "Trace monotonic time regressed")
        previous_nanos = event["monotonic_nanos"]
        if event["phase"] == "installed":
            continue
        thread = event["thread_id"]
        if event["phase"] == "before_native_invalid_log":
            require(thread not in pending, "Unfinished invalid factory invocation on the same thread")
            require(isinstance(event["model_resource"], str) and isinstance(event["texture_resource"], str), "Native model arguments are not strings")
            native_stack = ancestors(event)
            expected = [("org.mtr.resource.VehicleModel", "getModelLoaderBase"),
                        ("org.mtr.resource.RailResource", "<init>"),
                        ("org.mtr.client.CustomResourceLoader", "reload")]
            generated = event["model_resource"] == event["texture_resource"] == "" and native_stack[:3] == expected
            pending[thread] = (event, native_stack, generated)
        elif event["phase"] == "native_fallback_return":
            require(thread in pending, "Native fallback return has no captured invalid-log invocation")
            begin, native_stack, generated = pending.pop(thread)
            require(all(event[key] == begin[key] for key in ("model_resource", "texture_resource", "flip_texture_v")), "Factory arguments changed between trace events")
            require(ancestors(event) == native_stack, "Factory return belongs to another native call chain")
            require(event["returned_loader_class"] == "org.mtr.model.BlockbenchModelLoader", "Unsupported-model fallback returned an unexpected loader")
            calls.append({"before_sequence": begin["sequence"], "return_sequence": event["sequence"],
                          "thread_id": thread, "timestamp": begin["timestamp"],
                          "classification": "official_generated_default_rail" if generated else "unattributed_native_model",
                          "model_resource": begin["model_resource"], "texture_resource": begin["texture_resource"],
                          "native_call_chain": [{"class": cls, "method": method} for cls, method in native_stack[:3]],
                          "returned_loader_class": event["returned_loader_class"]})
        else:
            raise ValueError("Unknown native trace phase: " + event["phase"])
    require(not pending, "An invalid factory invocation has no observed return")
    log_events = [{"line": number, "text": line, "texture_identifier": match.group(1)}
                  for number, line in enumerate(log_text.splitlines(), 1)
                  if (match := re.search(r"\[([^\[\]]+)\] Invalid model!\s*$", line))]
    require("Native model diagnostic observation failed" not in log_text, "Diagnostic write failure occurred in the raw log")
    require(len(log_events) == len(calls) and calls, "Raw invalid-model log count differs from captured native calls or is empty")
    for call, log in zip(calls, log_events):
        call["log"] = log
        if call["classification"] == "official_generated_default_rail":
            require(log["texture_identifier"] == "mtr:textures/block/transparent.png", "Generated empty texture does not match the native log")
    return {"scope": "Captured invalid-model attribution only; no other error, rendering, performance, or gameplay acceptance",
            "pid": pid, "process_started_at": process_started_at, "target": target,
            "captured_events": len(events), "invalid_factory_calls": len(calls),
            "all_captured_invalid_calls_attributed": all(call["classification"] == "official_generated_default_rail" for call in calls),
            "calls": calls,
            "limitations": ["A live snapshot only covers its captured prefix; later log events remain outside this report.",
                            "Native empty fallback work still occurs. This observation does not measure its cost.",
                            "Historical untraced occurrences are not retroactively attributed.",
                            "World rail styles and actual rendering/interaction require separate evidence."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trace", "log", "plan", "launch", "probe", "native-snapshot", "output"):
        parser.add_argument("--" + name, type=pathlib.Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "Refuse to overwrite prior attribution evidence")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    launch = json.loads(args.launch.read_text(encoding="utf-8"))
    require(launch["plan_sha256"] == digest(args.plan), "Launch receipt does not bind the captured plan")
    native = json.loads(args.native_snapshot.read_text(encoding="utf-8"))
    require(native["process"]["pid"] == launch["pid"], "Independent native snapshot belongs to another JVM")
    probe_hash = digest(args.probe)
    require(any(mod["filename"] == args.probe.name and mod["sha256"] == probe_hash for mod in plan["mods"]), "Diagnostic JAR is not the prepared/recorded artifact")
    with zipfile.ZipFile(args.probe) as jar:
        target = json.loads(jar.read("mtr-model-trace-target.json"))
    require(target["variant"] == "official" and target["target"] == plan["artifact"]["target"], "Client and diagnostic target differ")
    require(any(mod["role"] == "mtr" and mod["sha256"] == target["mtrSha256"] for mod in plan["mods"]), "Prepared MTR hash differs from diagnostic target")
    events = [json.loads(line) for line in args.trace.read_text(encoding="utf-8").splitlines()]
    # Separate native observer supplies the independently captured ProcessHandle start identity.
    report = analyze(events, args.log.read_text(encoding="utf-8"), target, launch["pid"], native["process"]["start_instant"])
    report["timestamp"] = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()
    report["inputs"] = {name: {"path": str(getattr(args, name).resolve()), "sha256": digest(getattr(args, name))}
                        for name in ("trace", "log", "plan", "launch", "probe", "native_snapshot")}
    report["analyzer_sha256"] = digest(__file__)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("invalid_factory_calls", "all_captured_invalid_calls_attributed")}))


if __name__ == "__main__":
    main()
