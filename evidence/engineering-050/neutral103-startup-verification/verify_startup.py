"""Independently inspect sealed startup records; never read a runtime instance."""
import argparse
import calendar
import ctypes
from ctypes import wintypes
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import zipfile

sys.dont_write_bytecode = True


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path):
    raw = path.read_bytes()
    assert not raw or raw.endswith(b"\n"), "Partial JSONL record"
    return [json.loads(line) for line in raw.splitlines()]


def utc_ns(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    fraction = re.search(r"\.(\d+)(?:Z|[+-]\d\d:\d\d)$", value)
    digits = fraction[1] if fraction else ""
    assert len(digits) <= 9
    return calendar.timegm(parsed.astimezone(dt.timezone.utc).timetuple())*10**9 + int(digits.ljust(9, "0") or "0")


def windows_argv(command):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = (wintypes.HLOCAL,)
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not pointer:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [pointer[index] for index in range(count.value)]
    finally:
        kernel.LocalFree(ctypes.cast(pointer, wintypes.HLOCAL))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sealed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sealed, output = args.sealed.resolve(), args.output.resolve()
    assert not output.exists() and not output.is_relative_to(sealed)
    index_path = sealed / "sha256-index.json"
    indexed = read(index_path)["files"]
    actual_names = {p.relative_to(sealed).as_posix() for p in sealed.rglob("*") if p.is_file() and p != index_path}
    assert set(indexed) == actual_names
    for relative, receipt in indexed.items():
        path = (sealed / relative).resolve()
        assert path.is_relative_to(sealed) and sha(path) == receipt["sha256"] and path.stat().st_size == receipt["bytes"]
    capture = sealed / "capture-01"
    observation = capture / "observation"
    summary = read(observation / "summary.json")
    plan, launch = read(capture / "instance/packaged-client-plan.json"), read(capture / "instance/packaged-client-launch.json")
    assert summary["plan_sha256"] == launch["plan_sha256"] == sha(capture / "instance/packaged-client-plan.json")
    assert summary["launch_sha256"] == sha(capture / "instance/packaged-client-launch.json")
    process = summary["process_identity"]
    assert process["pid"] == launch["pid"] and Path(process["executable"]) == Path(plan["java"])
    assert windows_argv(process["command"]) == launch["command"]
    assert launch["command"][0] == plan["java"]
    assert utc_ns(summary["process_created"]) == utc_ns(process["created"])
    assert -5 <= (utc_ns(launch["timestamp"])-utc_ns(process["created"]))/1e9 <= 30
    metadata = read(observation / "observer-target.json")
    assert metadata["observer_version"] == "1.0.3" and plan["artifact"]["version"] == "0.4.7"
    assert summary["neutral_observer_target"] == metadata
    assert summary["mode"] == "startup" and summary["status"] == "settled" and summary["passed"]
    assert summary["error"] is None and not summary["observed_failures"] and not summary["missing_observation_fields"]
    policy = summary["policy"]
    assert policy["interval"] == 5 and policy["stable_seconds"] == 60
    assert policy["require_world"] and policy["unpaused"] and policy["require_reloads"] == 0
    assert summary["elapsed_seconds"] >= policy["stable_seconds"]
    assert not summary["source_changed_during_observation"] and not summary["neutral_sources_changed"]
    assert summary["source_sha256"] == summary["current_source_sha256"] == sha(observation / "observer-source.py")
    assert summary["snapshot_io_source_sha256"] == summary["current_snapshot_io_source_sha256"] == sha(observation / "windows_snapshot_io.py")
    for source, expected in summary["neutral_source_sha256"].items():
        assert sha(observation / Path(source).name) == expected
    freeze = read(capture / "freeze.json")
    for receipt in freeze["read_receipts"]:
        path = capture / receipt["target"]
        assert sha(path) == receipt["sha256"] and path.stat().st_size == receipt["bytes"] == receipt["source_size_before"] == receipt["source_size_after"]
    rows = lines(observation / "samples.jsonl")
    assert sha(observation / "samples.jsonl") == summary["samples_sha256"]
    assert len(rows) == summary["sample_count"] == summary["verified_sample_count"] == 13
    assert sha(observation / "auxiliary-events.jsonl") == summary["auxiliary_events_sha256"]
    assert summary["auxiliary_shutdown"]["worker_stopped"] and not summary["auxiliary_shutdown"]["uncompleted_request_ids"]
    contract = read(observation / "native-observer-consumer.json")
    states, timing = [], []
    start_ns, end_ns = utc_ns(summary["started"]), utc_ns(summary["ended"])
    cache_counts = None
    for index, row in enumerate(rows):
        observed, state = row["observation"], row["observation"]["raw_state"]
        assert observed["verified"] and not observed["failures"] and not observed["missing"]
        assert row["process"]["running"] and all(row["process"][key] >= 0 for key in ("working_set", "private_usage"))
        sample_ns, native_ns, capture_ns = utc_ns(row["timestamp"]), utc_ns(state["timestamp"]), utc_ns(state["capture_started_at"])
        assert start_ns <= sample_ns <= end_ns and utc_ns(state["observed_at"]) == native_ns
        age = (sample_ns-native_ns)/1e9
        assert 0 <= age <= policy["freshness_seconds"] and math.isclose(age, observed["age_seconds"], abs_tol=1e-6)
        assert capture_ns <= native_ns <= sample_ns
        assert state["capture_started_monotonic_nanos"] <= state["monotonic_nanos"]
        assert round(row["elapsed_seconds"]/policy["interval"]) == index
        assert state["target"] == metadata and state["pid"] == state["process"]["pid"] == process["pid"]
        assert utc_ns(state["process_created"]) == utc_ns(state["process"]["start_instant"])
        assert utc_ns(state["process_created"])//10**6 == utc_ns(process["created"])//10**6
        assert Path(state["process"]["executable"]) == Path(process["executable"])
        assert all(state["capabilities"].get(name) is True for name in contract["required_capabilities"])
        assert all(state["capabilities"].get(name) is False for name in ("module_counters", "active_read_permits", "text_workspace"))
        assert state["registered_count"] == policy["expected_count"] and state["registered_declarations"] == policy["expected_declarations"]
        assert state["native_pending"] == 0 and state["native_settled"] and state["observation_errors"] == 0
        assert state["resource_epochs"]["in_flight"] == 0 and state["resource_epochs"]["started"] == state["resource_epochs"]["completed"] == 1
        assert state["resource_epochs"]["last_completed_sequence"] == summary["baseline_completed_epoch_sequence"] == 1
        assert state["native_model_diagnostics"]["in_flight"] == 0
        assert state["native_model_diagnostics"]["started"] == state["native_model_diagnostics"]["completed"] == 1
        assert state["in_world"] and state["screen"] is None and state["paused"] is False
        heap = state["heap"]
        assert 0 <= heap["used_bytes"] <= heap["committed_bytes"] <= heap["max_bytes"] == plan["heap_mib"]*1024**2
        resources = state["cache_state"]["resources"]
        counts = {r["resource_id"]: [(len(e["floors"]), len(e["doorways"])) for e in r["entries"]] for r in resources}
        assert state["cache_state"]["available"] and all(r["registered"] for r in resources)
        cache_counts = counts if cache_counts is None else cache_counts
        assert counts == cache_counts
        if states:
            assert state["monotonic_nanos"] > states[-1]["monotonic_nanos"]
            assert state["capture_started_monotonic_nanos"] > states[-1]["capture_started_monotonic_nanos"]
            assert native_ns > utc_ns(states[-1]["timestamp"])
            assert row["elapsed_seconds"] > rows[index-1]["elapsed_seconds"]
            assert row["elapsed_seconds"]-rows[index-1]["elapsed_seconds"] <= policy["interval"]+policy["freshness_seconds"]
        states.append(state)
        timing.append({"sample_timestamp": row["timestamp"], "elapsed_seconds": row["elapsed_seconds"],
                       "native_timestamp": state["timestamp"], "capture_started_at": state["capture_started_at"],
                       "recomputed_age_seconds": age, "capture_utc_duration_ns": native_ns-capture_ns,
                       "capture_monotonic_duration_ns": state["monotonic_nanos"]-state["capture_started_monotonic_nanos"]})
    sampled_span = rows[-1]["elapsed_seconds"]-rows[0]["elapsed_seconds"]
    assert sampled_span >= policy["stable_seconds"]
    epochs = lines(observation / "native-epoch-events-at-completion.jsonl")
    assert sha(observation / "native-epoch-events-at-completion.jsonl") == summary["native_epoch_events_sha256"]
    assert len(epochs) == 2 and [e["phase"] for e in epochs] == ["start", "return"]
    assert all(e["pid"] == process["pid"] and e["sequence"] == 1 and e["render_thread"] for e in epochs)
    assert epochs[0]["monotonic_nanos"] < epochs[1]["monotonic_nanos"] < states[0]["capture_started_monotonic_nanos"]
    sys.path.insert(0, str(observation))
    from client_experiment_analysis import native_diagnostics
    from native_diagnostic_review import review_diagnostics, validate_review
    review = read(observation / "native-diagnostic-review.json")
    validate_review(review, metadata, root=capture / "proofs")
    log_path = observation / "native-log-at-completion.log"
    assert sha(log_path) == summary["log_sha256_at_completion"]
    log = log_path.read_text(encoding="utf-8")
    replay = review_diagnostics(native_diagnostics(log), log, lines(observation / "native-diagnostic-events-at-completion.jsonl"),
                                epochs, process, metadata, review, {"start": plan["timestamp"], "end": summary["ended"]}, states[-1])
    assert replay == summary["native_diagnostics"] and replay["native_attribution"]["passed"] and not replay["unreviewed_native"]
    build_inputs = {}
    for mod in read(capture / "instance/mod-bindings.json")["mods"]:
        assert mod["actual_sha256"] == mod["sha256"] == next(p["sha256"] for p in plan["mods"] if p["role"] == mod["role"])
        if not mod["copied"]:
            continue
        jar_path = capture / "instance/mods" / mod["filename"]
        assert sha(jar_path) == mod["actual_sha256"]
        base = capture / "build-inputs" / mod["role"]
        manifest_path = next(base.glob("*.build.json"))
        manifest = read(manifest_path)
        assert manifest["sha256"] == mod["actual_sha256"]
        for relative, expected in manifest["inputs"].items():
            assert sha(base / "inputs" / relative) == expected
        build_inputs[mod["role"]] = len(manifest["inputs"])
        with zipfile.ZipFile(jar_path) as jar:
            if mod["role"] == "observer":
                assert json.loads(jar.read("mtr-native-observer-target.json")) == metadata
    pack_bindings = read(capture / "instance/pack-bindings.json")["packs"]
    assert len(pack_bindings) == len(plan["packs"]) == 16
    for actual, planned in zip(pack_bindings, plan["packs"]):
        assert actual["filename"] == planned["filename"]
        assert actual["plan_source"]["sha256"] == actual["installed"]["sha256"] == actual["expected_sha256"] == planned["sha256"]
        assert actual["plan_source"]["path"] == planned["source"]
        assert Path(actual["installed"]["path"]).name == planned["filename"]
        assert all(actual[arm]["stable_size_and_mtime"] for arm in ("plan_source", "installed"))
    result = {"verified_at": dt.datetime.now(dt.timezone.utc).isoformat(), "passed": True, "sealed_only": True,
              "indexed_payloads": len(indexed), "sample_count": len(rows), "elapsed_seconds": summary["elapsed_seconds"],
              "sampled_monotonic_span_seconds": sampled_span,
              "native_utc_span_seconds": (utc_ns(states[-1]["timestamp"])-utc_ns(states[0]["timestamp"]))/1e9,
              "native_monotonic_span_seconds": (states[-1]["monotonic_nanos"]-states[0]["monotonic_nanos"])/1e9,
              "maximum_native_age_seconds": max(t["recomputed_age_seconds"] for t in timing),
              "maximum_sample_gap_seconds": max(b["elapsed_seconds"]-a["elapsed_seconds"] for a,b in zip(rows,rows[1:])),
              "sample_timing": timing, "cache_region_counts": cache_counts, "exact_build_input_counts": build_inputs,
              "plan_source_installed_pack_pairs": len(pack_bindings), "diagnostic_replay_equal": True,
              "native_diagnostics": replay, "scope": "Historical settled native startup window only.",
              "limitations": ["Per-sample native-file byte hashes cannot be independently reconstructed from parsed raw_state; the original samples file SHA is verified.",
                              "Archive and uncopied MTR runtime hashes are preserved capture receipts, not independently reread by this sealed-only verifier.",
                              "Process identity is the original consumer's retained CIM result and matching native observations; no current process query or whole-process exit inference.",
                              "No 20 reloads, route, passenger/rendering, F2 train appearance, endurance or controlled performance acceptance."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"passed": True, "samples": len(rows), "indexed_payloads": len(indexed), "diagnostic_replay_equal": True}))


if __name__ == "__main__":
    main()
