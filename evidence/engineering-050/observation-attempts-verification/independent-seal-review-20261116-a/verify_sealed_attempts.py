"""Independent stdlib-only verifier. Never follows recorded source/runtime paths.

All evidence reads are confined to --sealed-root. All writes go to --output.
This verifier awards no runtime acceptance, irrespective of successful checks.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tomllib
import zipfile


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def instant(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Timestamp has no UTC offset: " + value)
    return parsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sealed-root", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    root, output = args.sealed_root.resolve(), args.output.resolve()
    if output.is_relative_to(root) or not output.is_relative_to(root.parent / "observation-attempts-verification"):
        raise ValueError("Output must be inside the separate verification sibling.")
    output.mkdir(parents=True, exist_ok=False)
    report = {"started_at": now(), "argv": sys.argv, "python_executable": sys.executable,
              "python_version": sys.version, "sealed_root": str(root),
              "checks": [], "read_receipts": [], "acceptance_granted": [],
              "limitations": [
                  "Only sealed bytes are consumed; recorded .cache and runtime paths are not opened.",
                  "Read receipts attest to captured copy boundaries, not a simultaneous multi-file transaction.",
                  "Original parent tool receipts were not persisted; reported exits are not independent exit proof.",
                  "The MTR binary and sixteen resource packs were not copied; their declared hashes cannot be independently rehashed in this review.",
                  "Later collector/native checkpoints do not repair or complete interrupted/failed attempts.",
                  "Successful integrity verification grants no startup, reload, gameplay, endurance, performance, visual, or process-exit acceptance."
              ]}
    raw_files = {}

    def check(name, condition, detail=None):
        report["checks"].append({"name": name, "passed": bool(condition), "detail": detail})

    def load(path):
        return json.loads(raw_files[path])

    def jsonl(path):
        raw = raw_files[path]
        complete = raw.rfind(b"\n") + 1
        lines = raw[:complete].splitlines()
        rows = [json.loads(line) for line in lines]
        return rows, len(raw) - complete

    def read_snapshot():
        inventory = {}
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("Symlink in sealed evidence: " + str(path))
            if path.is_file():
                name = path.relative_to(root).as_posix()
                started = now()
                raw = path.read_bytes()
                ended = now()
                inventory[name] = {"sha256": digest(raw), "bytes": len(raw)}
                report["read_receipts"].append({"target": name, "started_at": started,
                    "read_completed_at": ended, **inventory[name]})
                raw_files[name] = raw
        return inventory

    before = read_snapshot()
    index = load("sha256-index.json")["files"]
    for name in index:
        relative = PurePosixPath(name)
        check("safe index path: " + name,
              not relative.is_absolute() and ".." not in relative.parts and "\\" not in name)
    check("exact payload inventory", set(before) == set(index) | {"sha256-index.json"},
          {"missing": sorted(set(index) - set(before)),
           "unindexed": sorted(set(before) - set(index) - {"sha256-index.json"})})
    check("43 indexed payload files", len(index) == 43, {"indexed": len(index), "with_index": len(before)})
    for name, declared in index.items():
        check("indexed bytes and SHA-256: " + name, before.get(name) == declared,
              {"declared": declared, "recomputed": before.get(name)})
    check("no attempt02 payload or directory", not any("attempt02" in p.relative_to(root).as_posix().lower() for p in root.rglob("*")))
    report["inventory"] = before

    prefix = "capture-01/"
    assessment = load(prefix + "assessment.json")
    capture_start, capture_end = instant(assessment["started_at"]), instant(assessment["ended_at"])
    check("assessment capture interval", capture_start <= capture_end and assessment["evidence_capture_completed"] is True)
    receipts = assessment["read_receipts"]
    check("38 original copy read receipts", len(receipts) == 38 and len({r["target"] for r in receipts}) == 38)
    report["original_copy_read_receipts"] = receipts
    for receipt in receipts:
        name = prefix + receipt["target"]
        expected = {"sha256": receipt["sha256"], "bytes": receipt["bytes"]}
        check("copy receipt bytes/hash: " + receipt["target"], before.get(name) == expected)
        check("copy receipt temporal boundary: " + receipt["target"],
              capture_start <= instant(receipt["started_at"]) <= instant(receipt["read_completed_at"]) <= capture_end)
        sizes = [receipt[k] for k in ("source_path_size_before", "source_path_size_after",
                                      "source_handle_size_before", "source_handle_size_after")]
        check("copy receipt size frontier: " + receipt["target"],
              all(s is None or s >= receipt["bytes"] for s in sizes)
              and (receipt["shared_snapshot_reader"] or all(s is not None for s in sizes)))
        check("copy receipt excludes attempt02: " + receipt["target"], "attempt02" not in receipt["source"].lower())
    generated = {prefix + n for n in ("assessment.json", "parent-reported-tool-results.json", "instance/installed-bindings.json")} | {"README.md", "capture_attempts.py"}
    check("all other indexed files have copy receipts", set(index) - {prefix+r["target"] for r in receipts} == generated)
    check("shared snapshot reader retains null handle-size boundary", all(
        r["source_handle_size_before"] is None and r["source_handle_size_after"] is None
        for r in receipts if r["shared_snapshot_reader"]))
    report["copy_capture_interval"] = {"started_at": assessment["started_at"], "ended_at": assessment["ended_at"],
        "not_simultaneous_transaction": True}

    plan_path, launch_path = prefix + "instance/packaged-client-plan.json", prefix + "instance/packaged-client-launch.json"
    plan, launch = load(plan_path), load(launch_path)
    plan_hash, launch_hash = digest(raw_files[plan_path]), digest(raw_files[launch_path])
    for directory in ("attempts/reload-recorder", "collector-checkpoint"):
        check("identical frozen plan copy: " + directory, raw_files[prefix+directory+"/packaged-client-plan.json"] == raw_files[plan_path])
        check("identical frozen launch copy: " + directory, raw_files[prefix+directory+"/packaged-client-launch.json"] == raw_files[launch_path])
    check("launch binds actual plan hash", launch["plan_sha256"] == plan_hash)
    check("launch PID", launch["pid"] == 18796)
    collector_source = prefix + "collector-checkpoint/sources/packaged_client.py"
    check("launcher source hash binding", launch["launcher_tool_sha256"] == plan["source_hash"] == digest(raw_files[collector_source]))
    installed = load(prefix+"instance/installed-bindings.json")
    by_role = {mod["role"]: mod for mod in installed["mods"]}
    check("exact installed plan mod declarations", len(installed["mods"]) == len(plan["mods"]) == 3 and
          all(all(by_role[m["role"]][k] == m[k] for k in ("filename", "sha256", "role")) for m in plan["mods"]))
    embedded = {}
    for role in ("companion", "observer"):
        mod = by_role[role]
        path = prefix+"instance/mods/"+mod["filename"]
        check("copied installed JAR hash: " + role, mod["copied"] is True and digest(raw_files[path]) == mod["sha256"] == mod["actual_sha256"])
        with zipfile.ZipFile(io.BytesIO(raw_files[path])) as jar:
            check("JAR CRC integrity: " + role, jar.testzip() is None)
            member = "mtr-memory-target.json" if role == "companion" else "mtr-native-observer-target.json"
            metadata_raw = jar.read(member)
            metadata = json.loads(metadata_raw)
            mod_toml_raw = jar.read("META-INF/neoforge.mods.toml")
            mod_toml = tomllib.loads(mod_toml_raw.decode("utf-8"))
            manifest = jar.read("META-INF/MANIFEST.MF").decode("utf-8")
            embedded[role] = {"metadata": metadata, "metadata_sha256": digest(metadata_raw),
                "mods_toml_sha256": digest(mod_toml_raw), "mods": mod_toml["mods"], "manifest": manifest}
    product = embedded["companion"]["metadata"]
    observer = embedded["observer"]["metadata"]
    check("product manifest agrees with plan", installed["product_manifest_from_plan"] == plan["artifact"])
    check("product embedded version and target", product["version"] == plan["artifact"]["version"] == "0.4.7" and
          all(product[k] == plan["artifact"][k] for k in ("target", "minecraft", "neoForge", "mtrSha256")))
    check("companion TOML/manifest version", embedded["companion"]["mods"][0]["version"] == product["version"] and "Implementation-Version: 0.4.7" in embedded["companion"]["manifest"])
    check("observer embedded metadata", observer == installed["observer_metadata"] == load(prefix+"attempts/startup/observer-target.json") and observer["observer_version"] == "1.0.3")
    check("observer TOML/manifest version", embedded["observer"]["mods"][0]["version"] == observer["observer_version"] and "Implementation-Version: 1.0.3" in embedded["observer"]["manifest"])
    mtr = by_role["mtr"]
    check("uncopied MTR declaration agrees", mtr["copied"] is False and mtr["sha256"] == mtr["actual_sha256"] == observer["mtrSha256"] == product["mtrSha256"]
          and prefix+"instance/mods/"+mtr["filename"] not in raw_files)
    check("sixteen packs are declarations only", len(plan["packs"]) == 16)
    report["identity"] = {"plan_sha256": plan_hash, "launch_sha256": launch_hash, "pid": launch["pid"],
        "mods": installed["mods"], "embedded_JAR_metadata": embedded, "MTR_binary_independently_rehashed": False,
        "packs_independently_rehashed": False}

    journal_path = prefix+"attempts/reload-recorder/journal.jsonl"
    journal, tail = jsonl(journal_path)
    previous = None
    chain = []
    for sequence, (row, raw_line) in enumerate(zip(journal, raw_files[journal_path].splitlines(keepends=True)), 1):
        body = {k: row[k] for k in ("sequence", "previous_sha256", "event")}
        actual_hash = digest(canonical(body))
        check("recorder canonical journal link " + str(sequence), row["sequence"] == sequence and row["previous_sha256"] == previous and row["sha256"] == actual_hash and raw_line == canonical(row))
        chain.append({"sequence": sequence, "previous_sha256": previous, "sha256": actual_hash, "event": row["event"]})
        previous = row["sha256"]
    check("recorder terminal initialization failure only", tail == 0 and [r["event"]["kind"] for r in journal] == ["initializing", "initialization_failed"])
    check("assessment terminal event agrees", assessment["reload_recorder"]["terminal_journal_event"] == journal[-1]["event"])
    check("recorder exception configured timeout", "Get-CimInstance" in journal[-1]["event"]["error"] and journal[-1]["event"]["error"].endswith(", 20)"))
    check("recorder has no ready/session/publication/input artifact", not any(
        name.startswith(prefix+"attempts/reload-recorder/") and any(part in name.lower() for part in ("session-start", "session-end", "publication", "input-attempt", "before-state", "receipt.json")) for name in raw_files))
    interval = (instant(journal[-1]["event"]["recorded_at"]) - instant(journal[0]["event"]["recorded_at"])).total_seconds()
    report["recorder"] = {"journal_chain": chain, "trailing_partial_bytes": tail,
        "configured_subprocess_timeout_seconds": 20, "initialization_to_failure_wall_seconds": interval,
        "timeout_boundary": "20 is the subprocess timeout configuration in the exception; journal timestamps span 120.875254 seconds, not an exact 20-second wall latency."}

    summary = load(prefix+"attempts/reload-observation/summary.json")
    check("reload preflight failed with no samples", summary["status"] == "preflight_failed" and summary["passed"] is False and raw_files[prefix+"attempts/reload-observation/samples.jsonl"] == b"")
    check("reload failure identity query timeout literal", "Get-CimInstance" in summary["error"] and "timed out after 20 seconds" in summary["error"])
    for hash_key, relative in (("source_sha256", "observer-source.py"), ("current_source_sha256", "observer-source.py"),
                               ("snapshot_io_source_sha256", "windows_snapshot_io.py"), ("current_snapshot_io_source_sha256", "windows_snapshot_io.py"), ("samples_sha256", "samples.jsonl")):
        check("reload copied source/file binding: " + hash_key, summary[hash_key] == digest(raw_files[prefix+"attempts/reload-observation/"+relative]))
    check("reload plan/launch binding", summary["plan_sha256"] == plan_hash and summary["launch_sha256"] == launch_hash and summary["source_changed_during_observation"] is False)
    report["reload_observation"] = summary

    startup, startup_tail = jsonl(prefix+"attempts/startup/samples.jsonl")
    check("startup 201 complete lines with no summary", len(startup) == 201 and startup_tail == 0 and prefix+"attempts/startup/summary.json" not in raw_files)
    check("startup samples only report running PID 18796", all(r["process"]["running"] is True and r["observation"]["raw_state"]["pid"] == 18796 for r in startup))
    check("startup assessment remains unaccepted", assessment["startup"]["accepted"] is False and assessment["startup"]["summary_present"] is False and assessment["startup"]["retained_complete_sample_lines"] == len(startup))
    report["startup"] = {"complete_lines": len(startup), "trailing_partial_bytes": startup_tail,
        "summary_present": False, "first_timestamp": startup[0]["timestamp"], "last_timestamp": startup[-1]["timestamp"], "completion_proven": False}
    groups = [
        ["attempts/startup/observer-source.py", "attempts/reload-recorder/sources/observe_packaged_client.py", "attempts/reload-observation/observer-source.py"],
        ["attempts/startup/windows_snapshot_io.py", "attempts/reload-recorder/sources/windows_snapshot_io.py", "attempts/reload-observation/windows_snapshot_io.py", "collector-checkpoint/sources/windows_snapshot_io.py"],
        ["attempts/startup/client_experiment_analysis.py", "attempts/reload-recorder/sources/client_experiment_analysis.py"],
        ["attempts/startup/native_diagnostic_review.py", "attempts/reload-recorder/sources/native_diagnostic_review.py"],
        ["attempts/startup/reload_before_recorder.py", "attempts/reload-recorder/sources/reload_before_recorder.py"],
        ["attempts/startup/native-observer-consumer.json", "attempts/reload-recorder/sources/native-observer-consumer.json"]]
    for group in groups:
        check("matching copied source group: " + group[0], len({digest(raw_files[prefix+name]) for name in group}) == 1, group)

    execution = load(prefix+"collector-checkpoint/execution.json")
    collector, collector_tail = jsonl(prefix+"collector-checkpoint/native-snapshots.jsonl")
    exit_keys = {"ended", "ended_at", "exit", "exit_code", "returncode", "process_exit"}
    check("collector observing prefix and no exit field", execution["status"] == "observing" and execution["pid"] == 18796 and len(collector) == 503 and collector_tail == 0 and not (set(execution) & exit_keys))
    for name, expected in execution["sources"].items():
        check("collector copied source binding: " + name, digest(raw_files[prefix+"collector-checkpoint/sources/"+name]) == expected)
    check("collector snapshots bind PID and metadata", all(r["snapshot"]["pid"] == 18796 and r["snapshot"]["target"] == observer for r in collector))
    check("collector assessment checkpoint only", assessment["collector_checkpoint"]["checkpoint_only"] is True and assessment["collector_checkpoint"]["process_exit_proven"] is False and assessment["collector_checkpoint"]["retained_complete_snapshot_lines"] == len(collector))
    report["collector_checkpoint"] = {"execution": execution, "complete_lines": len(collector), "trailing_partial_bytes": collector_tail,
        "first_captured_at": collector[0]["captured_at"], "last_captured_at": collector[-1]["captured_at"], "process_exit_proven": False}

    native = load(prefix+"instance-checkpoint/game-probe/native-observer.json")
    check("native checkpoint PID and identity", native["pid"] == native["process"]["pid"] == launch["pid"] == assessment["client_pid_from_frozen_launch_and_native_snapshot"] and native["target"] == observer)
    check("native checkpoint zero observation errors", native["observation_errors"] == native["native_model_diagnostics"]["observation_errors"] == assessment["instance_checkpoint"]["observation_errors"] == 0)
    check("native checkpoint timestamp agrees", native["timestamp"] == assessment["instance_checkpoint"]["timestamp"])
    check("native process identity metadata", native["process_created"] == native["process"]["start_instant"] and native["process"]["executable"] == plan["java"] and native["process"]["java_version"] == "21.0.11")
    report["native_checkpoint"] = {k: native[k] for k in ("timestamp", "pid", "process_created", "process", "target", "observation_errors", "native_model_diagnostics")}

    parent = load(prefix+"parent-reported-tool-results.json")
    check("parent reported tool history explicitly non-original", "not an independently preserved tool receipt" in parent["origin"] and parent["startup"]["actual_exit_timestamp"] is None and parent["startup"]["independent_exit_cause_proven"] is False)
    check("exact parent-reported final poll object", parent["startup"]["final_tool_response_as_reported"] == {"chunk_id":"c23302", "wall_time_seconds":2.32e-05, "exit_code":1, "original_token_count":0, "output":""})
    check("reload original tool receipts absent", parent["reload_recorder"]["raw_tool_receipt_available"] is False and parent["reload_observation"]["raw_tool_receipt_available"] is False)
    report["parent_reported_history_not_original_receipt"] = parent
    check("no acceptance transfer in assessment", all(assessment[k]["accepted"] is False for k in ("startup", "reload_recorder", "reload_observation")) and assessment["instance_checkpoint"]["later_checkpoint_not_an_attempt_completion"] is True)

    after = read_snapshot()
    check("sealed inventory/bytes unchanged throughout independent review", before == after)
    report["ended_at"] = now()
    report["failed_checks"] = [c for c in report["checks"] if not c["passed"]]
    report["passed"] = not report["failed_checks"]
    report["check_count"] = len(report["checks"])
    result_path = output / "verification-result.json"
    with result_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": report["passed"], "checks": len(report["checks"]), "failed_checks": report["failed_checks"],
        "indexed_payloads": len(index), "copy_read_receipts": len(receipts), "startup_complete_lines": len(startup),
        "collector_complete_lines": len(collector), "recorder_initialization_failure_interval_seconds": interval,
        "acceptance_granted": [], "output": str(result_path)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
