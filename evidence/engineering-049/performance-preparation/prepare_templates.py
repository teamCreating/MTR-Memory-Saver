"""Prepare four strict immutable performance templates; never launch Minecraft."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import client_experiment as experiment
import packaged_client as packaged
from client_experiment_analysis import schedule, validate_policy


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy(path, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError("Do not overwrite prepared evidence")
    shutil.copy2(path, destination)


def require(value, message):
    if not value:
        raise ValueError(message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observer", type=Path, required=True)
    args = parser.parse_args()
    require(not (BASE / "preparation.execution.json").exists(), "Do not rerun an immutable four-template preparation")
    observer = args.observer.resolve(strict=True)
    with zipfile.ZipFile(observer) as archive:
        metadata = json.loads(archive.read("mtr-native-observer-target.json"))
    require(metadata["observer_version"] == "1.0.3" and metadata["target"] == "official-nf248",
            "Require the completed final neutral 1.0.3 NF248 observer")
    observer_manifest = observer.with_suffix(".build.json")
    observer_identity = read(observer_manifest)
    require(observer_identity["sha256"] == sha(observer), "Observer manifest/artifact mismatch")
    source = ROOT.parent / ".cache/game-test/nf248-official-3g"
    catalogue = ROOT.parent / "[MTR4.1原生目录]产物/catalog.json"
    baseline = ROOT / "dist/compatibility/neoforge-21.1.248/mtr-memory-sharing-neoforge-v030-nf248.jar"
    candidate = ROOT / "evidence/engineering-049/release/official-nf248/files/mtr-memory-saver-official-nf248-0.4.7.jar"
    policy = read(ROOT / "config/client-experiment.json")
    validate_policy(policy)
    require(policy["pairs"] == 6 and len(schedule(policy)) == 48, "Frozen policy is not the required 48-JVM six-pair protocol")
    scenario_path = BASE / "scenario.json"
    scenario = read(scenario_path)
    experiment.scenario_from_controls({"context": {"declarations": scenario}})
    require(scenario["warmup"]["duration_seconds"] == policy["warmup_seconds"], "Scenario warm-up differs from frozen policy")
    matrix = read(ROOT / "config/targets.json")
    packaged.verified_artifact(baseline, matrix, "official-030-nf248")
    candidate_identity = packaged.verified_artifact(candidate, matrix)
    require(candidate_identity["version"] == "0.4.7", "Wrong candidate version")
    packaged.verified_observer(observer, candidate_identity, matrix)
    for path in (observer, observer_manifest, baseline, baseline.with_suffix(".build.json"),
                 candidate, candidate.with_suffix(".build.json")):
        copy(path, BASE / "artifacts" / path.name)
    frozen_sources = {relative: sha(ROOT / relative) for relative in (
        "tools/packaged_client.py", "tools/legacy_identity.py", "tools/client_experiment.py",
        "tools/client_experiment_analysis.py", "tools/native_diagnostic_review.py", "tools/windows_snapshot_io.py",
        "config/targets.json", "config/legacy-baselines.json", "config/client-experiment.json", "config/native-diagnostic-review.json")}
    for relative in frozen_sources:
        copy(ROOT / relative, BASE / "source" / relative)
    for proof in read(ROOT / "config/native-diagnostic-review.json")["proofs"]:
        require(sha(ROOT / proof["path"]) == proof["sha256"], "Changed native diagnostic proof")
        copy(ROOT / proof["path"], BASE / "source" / proof["path"])
    copy(catalogue, BASE / "source/catalogue.json")
    world_before = packaged.inventory(source / "saves" / scenario["world_name"])
    write(BASE / "source-world-inventory.json", world_before)
    context = {"timestamp": now(), "source": str(source), "world_name": scenario["world_name"],
        "source_marker_sha256": sha(source / "vehicle-test-instance.json"),
        "source_options_sha256": sha(source / "options.txt"), "source_usercache_sha256": sha(source / "usercache.json"),
        "source_world_sha256": experiment.canonical_sha(world_before), "catalogue_sha256": sha(catalogue),
        "free_disk_bytes": shutil.disk_usage(ROOT).free, "world_file_count": len(world_before["files"]),
        "background_context": "Read-only machine-context.json and power-context.json are timestamped snapshots; no user process was stopped."}
    write(BASE / "preparation-context.json", context)
    receipt = {"started": now(), "runner_sha256": sha(Path(__file__)), "cwd": str(ROOT), "commands": [],
               "source_sha256": frozen_sources, "observer_sha256": sha(observer), "launched_game_jvms": 0,
               "passed": False, "qualification_status": "pending: no qualification JVM has run"}
    write(BASE / "preparation.execution.json", receipt)
    descriptors = {}
    try:
        for role, companion in (("baseline", baseline), ("candidate", candidate)):
            for mode in ("plain", "profile"):
                key = role + "_" + mode
                instance = ROOT / ".cache/acceptance" / ("official-nf248-perf-049-" + key.replace("_", "-"))
                directory = BASE / "commands" / key
                directory.mkdir(parents=True)
                command = [sys.executable, str(ROOT / "tools/packaged_client.py"), "prepare",
                    "--source", str(source), "--instance", str(instance), "--companion", str(companion),
                    "--observer", str(observer), "--world", scenario["world_name"], "--username", "VehicleTest",
                    "--catalogue", str(catalogue), "--performance", "--controls", str(scenario_path),
                    "--heap-mib", "3072", "--initial-heap-mib", "512", "--resolution-width", "1280",
                    "--resolution-height", "720", "--jvm-arg=-XX:+UseG1GC"]
                if role == "baseline":
                    command.extend(["--legacy-baseline", "official-030-nf248"])
                if mode == "profile":
                    command.append("--jfr")
                execution = {"group": key, "started": now(), "command": command, "instance": str(instance)}
                receipt["commands"].append(execution)
                write(BASE / "preparation.execution.json", receipt)
                with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
                    process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
                    execution["pid"] = process.pid
                    write(BASE / "preparation.execution.json", receipt)
                    execution["exit_code"] = process.wait()
                execution["ended"] = now()
                write(BASE / "preparation.execution.json", receipt)
                require(execution["exit_code"] == 0, "Actual strict preparation failed: " + key)
                plan = instance / "packaged-client-plan.json"
                require(not (instance / "packaged-client-launch.json").exists(), "Template was unexpectedly launched")
                descriptor = experiment.prepared_descriptor(plan, role, mode, policy)
                descriptors[key] = descriptor
                copy(plan, BASE / "plans" / (key + ".json"))
                for path in (instance / ".prepared-controls").iterdir():
                    copy(path, BASE / "plans" / key / ".prepared-controls" / path.name)
                execution.update(plan_sha256=sha(plan), schema=read(plan)["schema"],
                                 controls_sha256=packaged.controls_sha256(read(plan)), verified_unlaunched=True)
                print(json.dumps({"prepared": key, "schema": read(plan)["schema"], "unlaunched": True}), flush=True)
        experiment.validate_groups(descriptors)
        require(packaged.inventory(source / "saves" / scenario["world_name"]) == world_before, "Source world changed during preparation")
        require(all(sha(ROOT / relative) == digest for relative, digest in frozen_sources.items()),
                "Preparation/qualification source changed during template creation")
        write(BASE / "descriptors.json", descriptors)
        write(BASE / "assessment.json", {"timestamp": now(), "passed": True, "groups": list(descriptors),
            "schema": 2, "all_templates_unlaunched": True, "source_world_unchanged": True,
            "same_neutral_observer_sha256": sha(observer), "policy_sha256": sha(ROOT / "config/client-experiment.json"),
            "core_jvm_arguments": descriptors["baseline_plain"]["core_jvm_arguments"],
            "comparison_groups_verified": True, "planned_trial_jvms": len(schedule(policy)),
            "qualifications": {key: "pending: no actual qualification JVM has run" for key in descriptors},
            "observer_off_calibration": "pending", "performance_result": "unavailable: no experiment has been planned or run",
            "scope": "Immutable performance preparation only. Four exact actual qualifications are required before the frozen 48-trial plan."})
        receipt["passed"] = True
    except BaseException as error:
        receipt["error"] = repr(error)
        raise
    finally:
        receipt["ended"] = now()
        write(BASE / "preparation.execution.json", receipt)
