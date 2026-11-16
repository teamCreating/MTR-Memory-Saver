"""Qualify, freeze, run and independently audit an official whole-client experiment.

Preparation and qualification are separate. Planning never starts a client. Each
qualification and scheduled trial uses a fresh copy of an immutable prepared
instance; this tool never sends game input or attaches to an ordinary client.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
import zipfile

import packaged_client as packaged
from observe_packaged_client import WindowsProcess, verify_process_identity, windows_arguments
from windows_snapshot_io import read_snapshot_bytes
from native_diagnostic_review import review_diagnostics, validate_review
from client_experiment_analysis import (COMMON_METRICS, MODES, ROLES, analyze, assess_observation,
                                         client_log_completeness, execution_window_errors, finite, instant, native_diagnostics,
                                         native_snapshot_errors, process_key, schedule, validate_policy)

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC_REVIEW = ROOT / "config/native-diagnostic-review.json"
SCOPE = "official_whole_client_experiment"
INJECTED_ENV = ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH")
SOURCES = (Path(__file__), Path(__file__).with_name("client_experiment_analysis.py"),
           Path(packaged.__file__), Path(__file__).with_name("observe_packaged_client.py"),
           Path(__file__).with_name("windows_snapshot_io.py"), Path(__file__).with_name("native_diagnostic_review.py"),
           DIAGNOSTIC_REVIEW, ROOT / "config/targets.json")
RETAINED_PROCESSES = {}  # Keep actual handles while a failed export awaits recovery.


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value, *, exclusive=False):
    path = Path(path)
    content = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    else:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)


def fingerprint(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}


def verify_fingerprint(item):
    if fingerprint(item["path"]) != item:
        raise ValueError("Frozen file changed: " + item["path"])


def environment():
    if any(os.environ.get(key) for key in INJECTED_ENV):
        raise ValueError("Remove JVM-injecting environment variables before preparation, qualification or execution.")
    result = {"system": platform.platform(), "machine": platform.machine(), "processor": platform.processor(),
            "node": platform.node(), "cpu_count": os.cpu_count(), "injected_environment": {key: None for key in INJECTED_ENV}}
    if os.name == "nt":
        power = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, timeout=20, check=True)
        scheme = re.search(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", power.stdout)
        if not scheme:
            raise ValueError("Actual active Windows power scheme is unavailable.")
        command = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); " \
                  "$clientSystem = Get-CimInstance Win32_ComputerSystem; $clientOs = Get-CimInstance Win32_OperatingSystem; " \
                  "@{system=@{manufacturer=$clientSystem.Manufacturer; model=$clientSystem.Model; ram=[long]$clientSystem.TotalPhysicalMemory}; " \
                  "windows=@{version=$clientOs.Version; build=$clientOs.BuildNumber}; " \
                  "cpus=@(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors); " \
                  "gpus=@(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM)} | ConvertTo-Json -Depth 5 -Compress"
        hardware = subprocess.run(["pwsh", "-NoProfile", "-Command", command], capture_output=True, text=True,
                                  encoding="utf-8-sig", errors="strict", timeout=30, check=True)
        result.update(active_power_scheme=scheme.group(0).decode("ascii").lower(), hardware=json.loads(hardware.stdout))
    return result


def scenario_from_controls(controls):
    scenario = controls["context"]["declarations"]
    fields = {"schema", "scenario_name", "expected_registration", "world_name", "camera", "route", "cache_policy", "observation", "machine_context", "warmup"}
    if not isinstance(scenario, dict) or set(scenario) != fields or scenario["schema"] != 1:
        raise ValueError("Context must freeze the documented scenario schema, camera and route.")
    if any(not isinstance(scenario[field], str) or not scenario[field].strip() for field in ("scenario_name", "world_name")):
        raise ValueError("Require an explicit scenario and world name.")
    if not isinstance(scenario["camera"], dict) or not scenario["camera"] or not isinstance(scenario["route"], dict) or not scenario["route"]:
        raise ValueError("Freeze nonempty camera and route declarations; they do not substitute for observed state.")
    camera = scenario["camera"]
    if set(camera) != {"dimension", "player", "maximum_position_error", "maximum_angle_error"} or not isinstance(camera["dimension"], str) or not camera["dimension"]:
        raise ValueError("Camera must freeze dimension, player pose and explicit observation tolerances.")
    if not isinstance(camera["player"], dict) or set(camera["player"]) != {"x", "y", "z", "yaw", "pitch"} or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in camera["player"].values()) or any(not finite(camera[field]) for field in ("maximum_position_error", "maximum_angle_error")):
        raise ValueError("Invalid frozen player pose or camera tolerances.")
    route = scenario["route"]
    if set(route) != {"description", "route_ids", "vehicle_ids"} or not isinstance(route["description"], str) or not route["description"].strip() or any(not isinstance(route[field], list) or len(route[field]) != len(set(route[field])) or any(type(value) not in (str, int) for value in route[field]) for field in ("route_ids", "vehicle_ids")):
        raise ValueError("Route must freeze its description and permitted route/vehicle identities.")
    expected = scenario["expected_registration"]
    if not isinstance(expected, dict) or set(expected) != {"declarations", "distinct_ids"} or any(type(value) is not int or value <= 0 for value in expected.values()) or expected["distinct_ids"] > expected["declarations"]:
        raise ValueError("Require exact positive native catalogue registration counts.")
    if scenario["cache_policy"] != "fresh_jvm_warm_os_cache":
        raise ValueError("This protocol requires fresh JVM/world copies and declares uncontrolled warm OS cache.")
    observation = scenario["observation"]
    if not isinstance(observation, dict) or set(observation) != {"require_world", "require_unpaused", "require_train", "minimum_train_displacement"}:
        raise ValueError("Invalid scenario observation contract.")
    if observation["require_world"] is not True or observation["require_unpaused"] is not True or type(observation["require_train"]) is not bool or not finite(observation["minimum_train_displacement"]):
        raise ValueError("Whole-client qualification requires an unpaused world and explicit train observation policy.")
    if observation["minimum_train_displacement"] > 0 and not observation["require_train"]:
        raise ValueError("Train motion cannot be required with train observation disabled.")
    if observation["require_train"] and not route["route_ids"]:
        raise ValueError("Observed train qualification requires frozen route identities.")
    context = scenario["machine_context"]
    if not isinstance(context, dict) or set(context) != {"hardware", "windows", "power_mode", "background_workload"} or any(not isinstance(value, str) or not value.strip() for value in context.values()):
        raise ValueError("Declare hardware, Windows, power mode and background workload context.")
    warmup = scenario["warmup"]
    if not isinstance(warmup, dict) or set(warmup) != {"duration_seconds", "description"} or not finite(warmup["duration_seconds"], positive=True) or not isinstance(warmup["description"], str) or not warmup["description"].strip():
        raise ValueError("Freeze an explicit warm-up duration and description.")
    return scenario


def core_arguments(arguments):
    return [argument for argument in arguments if not argument.startswith(("-XX:StartFlightRecording=", "-Xlog:gc*,safepoint:"))]


def mode_independent_controls(controls):
    """Remove precisely the added instrumentation tokens wherever command copies occur."""
    if isinstance(controls, dict):
        return {key: mode_independent_controls(value) for key, value in controls.items()}
    if isinstance(controls, list):
        return [mode_independent_controls(value) for value in controls if not isinstance(value, str) or not value.startswith(("-XX:StartFlightRecording=", "-Xlog:gc*,safepoint:"))]
    return controls


def prepared_descriptor(path, role, mode, policy):
    path = Path(path).resolve(strict=True)
    plan = read(path)
    if plan.get("schema") != 2 or plan.get("scope") != "packaged_client_performance_preparation":
        raise ValueError("Require a strict schema-2 performance-prepared instance; legacy ordinary plans are not qualification.")
    instance = Path(plan["instance"]).resolve(strict=True)
    if path != instance / "packaged-client-plan.json":
        raise ValueError("Prepared plan must be the immutable instance's own plan.")
    packaged.verify_prepared_inputs(instance, plan)
    packaged.verify_performance_controls(instance, plan)
    controls = packaged.comparison_controls(plan)
    if controls.get("schema") != 1:
        raise ValueError("Unsupported comparison controls.")
    matrix = read(ROOT / "config/targets.json")
    identity = plan["artifact"]
    target = matrix["targets"][identity["target"]]
    if target["variant"] != "official" or identity["mtrSha256"] != matrix["mtr"]["official"]["sha256"] or matrix["mtr"]["official"]["version"] != "4.1.0-beta.2":
        raise ValueError("Only the exact official beta.2 target is in scope.")
    artifact_sha = identity.get("sha256", identity.get("output_sha256"))
    if not isinstance(artifact_sha, str) or not re.fullmatch("[0-9a-f]{64}", artifact_sha):
        raise ValueError("Require an exact companion artifact SHA-256.")
    companion = [item for item in plan["mods"] if item["sha256"] == artifact_sha]
    if len(companion) != 1:
        raise ValueError("Companion treatment artifact is missing or ambiguous.")
    if plan.get("jfr") is not (mode == "profile"):
        raise ValueError("Prepared instrumentation differs from qualification group.")
    arguments = packaged.jvm_arguments(plan)
    if "-XX:+UseG1GC" not in core_arguments(arguments):
        raise ValueError("This GC protocol requires a frozen explicit G1 collector in both modes.")
    neutral = []
    for item in plan["mods"]:
        jar_path = instance / "mods" / item["filename"]
        with zipfile.ZipFile(jar_path) as jar:
            if "mtr-native-observer-target.json" in jar.namelist():
                metadata = json.loads(jar.read("mtr-native-observer-target.json"))
                neutral.append((item, metadata))
    if len(neutral) != 1:
        raise ValueError("Exactly one independent native observer is required.")
    probe, metadata = neutral[0]
    if metadata.get("schema_version") != 1 or metadata.get("probe_kind") != "official-native-observer" or metadata.get("target") != identity["target"] or metadata.get("mtrSha256") != identity["mtrSha256"] or metadata.get("neoForge") != identity["neoForge"]:
        raise ValueError("Neutral observer metadata differs from the exact official target.")
    validate_review(read(DIAGNOSTIC_REVIEW), metadata, root=ROOT)
    diagnostic_review = fingerprint(DIAGNOSTIC_REVIEW)
    scenario = scenario_from_controls(controls)
    if scenario["warmup"]["duration_seconds"] != policy["warmup_seconds"]:
        raise ValueError("Frozen scenario warm-up differs from experiment policy.")
    if not plan.get("world") or plan["world"]["name"] != scenario["world_name"]:
        raise ValueError("Frozen scenario world differs from actual prepared world.")
    key_fields = {"role": role, "instrumentation": mode, "artifact_sha256": artifact_sha,
                  "controls_sha256": packaged.controls_sha256(plan), "neutral_probe_sha256": probe["sha256"],
                  "policy_sha256": canonical_sha(policy), "target": identity["target"],
                  "diagnostic_review_sha256": diagnostic_review["sha256"]}
    return {"role": role, "instrumentation": mode, "prepared_plan": fingerprint(path), "instance": str(instance),
            "controls": controls, "core_jvm_arguments": core_arguments(arguments), "scenario": scenario,
            "artifact_sha256": artifact_sha, "probe_metadata": metadata, "qualification_fields": key_fields,
            "diagnostic_review": diagnostic_review,
            "qualification_key": canonical_sha(key_fields)}


def validate_groups(prepared):
    if set(prepared) != {role + "_" + mode for role in ROLES for mode in MODES}:
        raise ValueError("Exactly four baseline/candidate and plain/profile preparation groups are required.")
    reference = prepared["baseline_plain"]
    for role in ROLES:
        for mode in MODES:
            descriptor = prepared[role + "_" + mode]
            if descriptor["role"] != role or descriptor["instrumentation"] != mode:
                raise ValueError("Prepared group role/instrumentation differs from its key.")
            if descriptor["core_jvm_arguments"] != reference["core_jvm_arguments"] or descriptor["scenario"] != reference["scenario"]:
                raise ValueError("Core JVM flags, camera/route/scenario must match all four qualification groups.")
            if descriptor["qualification_fields"]["neutral_probe_sha256"] != reference["qualification_fields"]["neutral_probe_sha256"]:
                raise ValueError("Both treatment arms and modes require the exact same neutral observer bytes.")
            if descriptor["qualification_fields"]["target"] != reference["qualification_fields"]["target"]:
                raise ValueError("Do not mix official loader targets within an experiment.")
    for mode in MODES:
        if prepared["baseline_" + mode]["controls"] != prepared["candidate_" + mode]["controls"]:
            raise ValueError("Baseline/candidate controls differ in " + mode + ".")
    if mode_independent_controls(prepared["baseline_plain"]["controls"]) != mode_independent_controls(prepared["baseline_profile"]["controls"]):
        raise ValueError("Plain/profile differ in controls beyond JFR and GC logging arguments.")
    if reference["artifact_sha256"] == prepared["candidate_plain"]["artifact_sha256"]:
        raise ValueError("Baseline and candidate treatments must be distinct exact artifacts.")
    for role in ROLES:
        if prepared[role + "_plain"]["artifact_sha256"] != prepared[role + "_profile"]["artifact_sha256"]:
            raise ValueError("Plain/profile must use the same artifact for " + role + ".")


def instrumentation_contract(prepared, policy):
    return {mode: {"jvm_arguments": packaged.jvm_arguments(read(prepared["baseline_" + mode]["prepared_plan"]["path"])),
                   "neutral_probe_sha256": prepared["baseline_plain"]["qualification_fields"]["neutral_probe_sha256"],
                   "sampling_seconds": policy["sample_interval_seconds"], "jfr": mode == "profile", "os_memory": True} for mode in MODES}


def verify_descriptor(descriptor, policy):
    verify_fingerprint(descriptor["prepared_plan"])
    current = prepared_descriptor(descriptor["prepared_plan"]["path"], descriptor["role"], descriptor["instrumentation"], policy)
    if current != {key: value for key, value in descriptor.items() if key != "qualification"}:
        raise ValueError("Current prepared artifact/context no longer matches frozen qualification.")


def raw_files(root):
    return [{"relative_path": path.relative_to(root).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size}
            for path in sorted(root.rglob("*")) if path.is_file() and path.name not in ("qualification.json", "result.json")
            and not path.relative_to(root).parts[0] == "instance"]


def verify_raw_files(root, items):
    for item in items:
        path = (root / item["relative_path"]).resolve(strict=True)
        if root.resolve() not in path.parents or digest(path) != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise ValueError("Raw evidence changed or escaped attempt directory: " + item["relative_path"])
    if items != raw_files(root):
        raise ValueError("Raw evidence inventory is incomplete, duplicated or changed.")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def audit_observation(root, policy, scenario, mode, *, expected_trial=None, experiment_started=None):
    root = Path(root).resolve(strict=True)
    evidence = read(root / "observation.json")
    prepared = read(root / "prepared-plan.json")
    if Path(prepared["instance"]).resolve() != root / "instance" or evidence.get("capture_root") != str(root):
        raise ValueError("Raw observation belongs to another actual instance/capture root; replay is invalid.")
    if evidence.get("run_start") != read(root / "run-start.json") or evidence.get("run_finish") != read(root / "run-finish.json") or evidence.get("run_start_sha256") != digest(root / "run-start.json"):
        raise ValueError("Execution window differs from raw producer start/finish receipts.")
    window_errors = execution_window_errors(evidence, expected_trial, experiment_started)
    if window_errors:
        raise ValueError("Invalid raw execution window: " + "; ".join(window_errors))
    diagnostic_events = read_jsonl(root / "native-invalid-model.jsonl")
    diagnostic_review = read(root / "diagnostic-review.json")
    metadata = prepared["controls"]["observer"]["target"]
    validate_review(diagnostic_review, metadata, root=ROOT)
    if diagnostic_review != read(DIAGNOSTIC_REVIEW) or evidence.get("diagnostic_review_sha256") != digest(root / "diagnostic-review.json"):
        raise ValueError("Actual diagnostic review differs from the frozen current proof.")
    if evidence.get("diagnostic_events") != diagnostic_events:
        raise ValueError("Diagnostic attribution events differ from raw JSONL.")
    if evidence.get("client_diagnostics") != assess_native_diagnostics(root, evidence, metadata, diagnostic_review):
        raise ValueError("Native/client diagnostic assessment differs from full raw log.")
    if evidence.get("process") != read(root / "actual-process.json") or evidence.get("launch") != read(root / "launch.json"):
        raise ValueError("Process/launch evidence differs from its independent raw capture.")
    if evidence.get("client_log_completeness") != client_log_completeness((root / "latest.log").read_bytes(), evidence["samples"], prepared["instance"]):
        raise ValueError("Client log completeness differs from independent raw prefix analysis.")
    if evidence["launch"]["plan_sha256"] != digest(root / "prepared-plan.json"):
        raise ValueError("Launch-time prepared plan bytes differ from raw preparation evidence.")
    if evidence["launch"]["jvm_arguments"] != packaged.jvm_arguments(prepared):
        raise ValueError("Actual launched instrumentation differs from frozen prepared flags.")
    if packaged.command_template(evidence["launch"]["command"], prepared["instance"], prepared["java"]) != prepared["controls"]["launcher"]["command_template"]:
        raise ValueError("Actual client command differs from the frozen loader/runtime/scene controls.")
    if evidence["process"]["pid"] != evidence["launch"]["pid"] or Path(evidence["process"]["executable"]).resolve() != Path(prepared["java"]).resolve():
        raise ValueError("Actual process differs from the launched runtime/PID.")
    verify_process_identity(prepared, evidence["launch"], evidence["process"], evidence["process"]["arguments"])
    if evidence.get("samples") != read_jsonl(root / "samples.jsonl"):
        raise ValueError("Observation samples differ from raw samples JSONL.")
    if evidence.get("epochs") != read_jsonl(root / "native-resource-epochs.jsonl"):
        raise ValueError("Native epoch evidence differs from raw JSONL.")
    if mode == "profile":
        events, coverage = audit_jfr(root, prepared)
        if evidence.get("jfr_events") != events or evidence.get("jfr_coverage") != coverage:
            raise ValueError("JFR observations differ from independently parsed raw output.")
    return evidence, assess_observation(evidence, policy, scenario, mode)


def verify_observed_identity(root, descriptor):
    prepared = read(root / "prepared-plan.json")
    fields = descriptor["qualification_fields"]
    if packaged.controls_sha256(prepared) != fields["controls_sha256"] or prepared["artifact"]["sha256"] != fields["artifact_sha256"]:
        raise ValueError("Observed artifact or controls differ from current qualification.")
    probes = [item for item in prepared["mods"] if item.get("role") == "observer"]
    if len(probes) != 1 or probes[0]["sha256"] != fields["neutral_probe_sha256"]:
        raise ValueError("Observed independent probe bytes differ from current qualification.")
    if digest(root / "diagnostic-review.json") != fields["diagnostic_review_sha256"]:
        raise ValueError("Observed native diagnostic review differs from current qualification.")


def assess_native_diagnostics(root, evidence, metadata, review):
    text = (Path(root) / "latest.log").read_text(encoding="utf-8-sig")
    raw = native_diagnostics(text)
    try:
        final_snapshot = read(Path(root) / "native-observer-final.json")
    except (OSError, ValueError) as error:
        return {**raw, "reviewed_native": [], "native_attribution": {"passed": False, "errors": [str(error)]}}
    return review_diagnostics(raw, text, evidence.get("diagnostic_events", []), evidence.get("epochs", []),
        evidence.get("process", {}), metadata, review, {"start": evidence["started_at"], "end": evidence["finished_at"]},
        final_snapshot)


def audit_qualification(path, descriptor, policy):
    path = Path(path).resolve(strict=True)
    report = read(path)
    if report.get("schema") != 1 or report.get("scope") != "official_current_client_qualification" or report.get("qualification_key") != descriptor["qualification_key"]:
        raise ValueError("Qualification belongs to another artifact/control/probe/mode/policy group.")
    if report.get("fields") != descriptor["qualification_fields"] or report.get("environment") != environment():
        raise ValueError("Qualification inputs or environment differ from current frozen controls.")
    if report.get("sources") != [fingerprint(source) for source in SOURCES]:
        raise ValueError("Qualification tool sources changed; obtain a new current qualification.")
    verify_raw_files(path.parent, report["files"])
    evidence, result = audit_observation(path.parent, policy, descriptor["scenario"], descriptor["instrumentation"])
    verify_observed_identity(path.parent, descriptor)
    if result != report.get("result") or not result["passed"] or report.get("status") != "passed":
        raise ValueError("Qualification is incomplete, failed or differs from independent raw analysis.")
    if evidence.get("qualification_key") != descriptor["qualification_key"]:
        raise ValueError("Raw observation qualification identity differs.")
    return fingerprint(path)


def new_attempt(output, action, arguments):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    attempt = {"schema": 1, "action": action, "started_at": now(), "status": "preparing", "arguments": arguments}
    save(output / "attempt.json", attempt, exclusive=True)
    return output, attempt


def make_plan(args):
    arguments = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    arguments["qualification"] = [str(path) for path in args.qualification]
    output, attempt = new_attempt(args.output, "plan", arguments)
    try:
        policy = read(args.policy)
        validate_policy(policy)
        host = environment()
        prepared = {}
        for role in ROLES:
            for mode in MODES:
                key = role + "_" + mode
                prepared[key] = prepared_descriptor(getattr(args, key), role, mode, policy)
        reference = prepared["baseline_plain"]
        validate_groups(prepared)
        qualifications = {}
        for path in args.qualification:
            report = read(path)
            key = report.get("qualification_key")
            if key in qualifications:
                raise ValueError("Duplicate qualification group.")
            qualifications[key] = path
        for key, descriptor in prepared.items():
            qualification_path = qualifications.get(descriptor["qualification_key"])
            if qualification_path is None:
                raise ValueError("Missing current exact qualification: " + key + "; no baseline substitution or relaxed gate is allowed.")
            descriptor["qualification"] = audit_qualification(qualification_path, descriptor, policy)
        if len(qualifications) != 4:
            raise ValueError("Require exactly the four current qualification groups.")
        qualification_processes = {key: read(Path(item["qualification"]["path"]).parent / "actual-process.json")
                                   for key, item in prepared.items()}
        if len({process_key(value) for value in qualification_processes.values()}) != 4:
            raise ValueError("The four qualification groups require distinct actual JVMs.")
        plan = {"schema": 1, "scope": SCOPE, "created_at": now(), "policy": policy,
                "policy_file": fingerprint(args.policy), "environment": host, "environment_notes": args.environment_notes,
                "sources": [fingerprint(source) for source in SOURCES], "prepared": prepared,
                "scenario": reference["scenario"], "schedule": schedule(policy),
                "qualification_processes": qualification_processes,
                "neutral_probe_off_calibration": {"status": "outstanding", "required_before_uninstrumented_claim": True},
                "instrumentation_contract": instrumentation_contract(prepared, policy)}
        save(output / "plan.json", plan, exclusive=True)
        attempt.update(status="planned", scheduled_trials=len(plan["schedule"]), plan_sha256=digest(output / "plan.json"))
    except BaseException as error:
        attempt.update(status="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        attempt["finished_at"] = now()
        save(output / "attempt.json", attempt)
    return plan


def verify_plan(path, plan):
    if plan.get("schema") != 1 or plan.get("scope") != SCOPE or plan.get("schedule") != schedule(plan["policy"]):
        raise ValueError("Unsupported or changed whole-client experiment design.")
    if environment() != plan["environment"]:
        raise ValueError("Host/injected environment differs from frozen experiment.")
    validate_groups(plan["prepared"])
    if plan["scenario"] != plan["prepared"]["baseline_plain"]["scenario"] or read(plan["policy_file"]["path"]) != plan["policy"]:
        raise ValueError("Experiment policy/scenario differs from frozen input declarations.")
    if plan["instrumentation_contract"] != instrumentation_contract(plan["prepared"], plan["policy"]) or plan["neutral_probe_off_calibration"] != {"status": "outstanding", "required_before_uninstrumented_claim": True}:
        raise ValueError("Frozen instrumentation or pending calibration contract changed.")
    for item in [plan["policy_file"], *plan["sources"]]:
        verify_fingerprint(item)
    for descriptor in plan["prepared"].values():
        verify_descriptor(descriptor, plan["policy"])
        verify_fingerprint(descriptor["qualification"])
        audit_qualification(descriptor["qualification"]["path"], descriptor, plan["policy"])
    actual_qualifiers = {key: read(Path(item["qualification"]["path"]).parent / "actual-process.json")
                        for key, item in plan["prepared"].items()}
    if plan.get("qualification_processes") != actual_qualifiers or len({process_key(value) for value in actual_qualifiers.values()}) != 4:
        raise ValueError("Frozen qualifier JVM identities differ from independently audited raw qualification processes.")


def clone_prepared(descriptor, destination):
    template = Path(descriptor["instance"])
    plan = read(template / "packaged-client-plan.json")
    if (template / "packaged-client-launch.json").exists() or read(template / "vehicle-test-instance.json").get("pid"):
        raise ValueError("Prepared templates must never have launched; qualification uses a separate clone.")
    if (template / "logs").exists():
        raise ValueError("Prepared templates cannot contain prior client logs.")
    # Copy the complete template, including its frozen context and launcher files.
    # Existing directories are never reused, removed or reset.
    shutil.copytree(template, destination)
    plan["instance"] = str(destination.resolve())
    save(destination / "packaged-client-plan.json", plan)
    marker = read(destination / "vehicle-test-instance.json")
    marker.update(instance=str(destination.resolve()), pid=None)
    save(destination / "vehicle-test-instance.json", marker)
    packaged.verify_prepared_inputs(destination, plan)
    packaged.verify_performance_controls(destination, plan)
    return plan


def summary_coverage(text):
    start = re.search(r"^\s*Start:\s*(.+?)\s*$", text, re.MULTILINE)
    duration = re.search(r"^\s*Duration:\s*(\d+)\s+s\s*$", text, re.MULTILINE)
    if not start or not duration:
        raise ValueError("Unreadable JFR summary start/duration.")
    # JDK 21 summary reports whole seconds. Use the conservative lower end of its
    # end bound; dump after the phase so rounded metadata cannot falsely cover it.
    parsed = dt.datetime.strptime(start.group(1), "%Y-%m-%d %H:%M:%S (UTC)").replace(tzinfo=dt.timezone.utc)
    return {"start": parsed.isoformat(), "end": (parsed + dt.timedelta(seconds=int(duration.group(1)))).isoformat(), "readable": True,
            "resolution_seconds": 1, "end_bound": "conservative_whole_second"}


def parse_jfr_recording(path, java):
    """Independently parse the actual sealed binary using its frozen JDK tool."""
    path = Path(path)
    before = digest(path)
    suffix = ".exe" if os.name == "nt" else ""
    jfr = str(Path(java).with_name("jfr" + suffix))
    outputs = []
    for options in (("summary",), ("print", "--json", "--events", "mtrtest.ClientFrame,jdk.GarbageCollection,jdk.GCPhasePause")):
        result = subprocess.run([jfr, *options, str(path)], capture_output=True, text=True, encoding="utf-8-sig", errors="strict", timeout=60)
        if result.returncode != 0:
            raise ValueError("Sealed raw JFR failed independent parsing: " + options[0])
        outputs.append(result.stdout)
    if digest(path) != before:
        raise ValueError("Raw JFR changed during independent parsing.")
    events = json.loads(outputs[1])["recording"]["events"]
    if not isinstance(events, list):
        raise ValueError("Independent JFR parse lacks an event array.")
    return events, summary_coverage(outputs[0])


def audit_jfr(root, prepared):
    verified = [path for path in root.glob("jfr-export-attempt-*/receipt.json") if read(path).get("status") == "verified"]
    if len(verified) != 1:
        raise ValueError("Exactly one verified export must bind the canonical raw JFR.")
    attempt = verified[0].parent
    receipt = read(verified[0])
    binary_sha = digest(root / "recording.jfr")
    if receipt.get("recording_sha256") != binary_sha or digest(attempt / "recording.jfr") != binary_sha:
        raise ValueError("Sealed JFR binary differs from the actual verified export.")
    for label in ("jfr-summary", "jfr-print"):
        execution = read(attempt / (label + ".execution.json"))
        if execution.get("returncode") != 0 or execution.get("input_jfr_sha256") != binary_sha or execution.get("input_jfr_sha256_after") != binary_sha:
            raise ValueError("JFR parsing output is not bound to unchanged exact input bytes.")
        if execution.get("stdout_sha256") != digest(attempt / (label + ".stdout.log")):
            raise ValueError("JFR helper output bytes changed after parsing.")
    if digest(root / "jfr-summary.stdout.log") != digest(attempt / "jfr-summary.stdout.log"):
        raise ValueError("Canonical JFR summary differs from verified helper output.")
    captured = read(root / "jfr-events.json")["recording"]["events"]
    if captured != read(attempt / "jfr-print.stdout.log")["recording"]["events"]:
        raise ValueError("Canonical JFR events differ from verified helper output.")
    events, coverage = parse_jfr_recording(root / "recording.jfr", prepared["java"])
    if events != captured or coverage != summary_coverage((root / "jfr-summary.stdout.log").read_text(encoding="utf-8")):
        raise ValueError("Saved JFR observations differ from independent sealed-binary parsing.")
    return events, coverage


def export_jfr(plan, process, instance, root):
    java = Path(plan["java"])
    suffix = ".exe" if os.name == "nt" else ""
    jcmd, jfr = java.with_name("jcmd" + suffix), java.with_name("jfr" + suffix)
    sequence = len(list(root.glob("jfr-export-attempt-*"))) + 1
    attempt = root / f"jfr-export-attempt-{sequence:02d}"
    attempt.mkdir(exist_ok=False)
    exported = instance / f"experiment-export-{sequence:02d}.jfr"
    commands = []
    if process.poll() is None:
        commands.append(([str(jcmd), str(process.pid), "JFR.dump", "name=acceptance", "filename=" + exported.name], "jfr-dump"))
    else:
        # An actual exited JVM cannot be kept alive. Preserve its dumponexit file
        # and independently verify it; absence or corruption remains a failure.
        shutil.copyfile(instance / "acceptance.jfr", exported)
    commands += [([str(jfr), "summary", str(exported)], "jfr-summary"),
                 ([str(jfr), "print", "--json", "--events", "mtrtest.ClientFrame,jdk.GarbageCollection,jdk.GCPhasePause", str(exported)], "jfr-print")]
    receipt = {"started_at": now(), "status": "running", "pid": process.pid}
    try:
        for command, label in commands:
            input_sha = digest(exported) if label != "jfr-dump" else None
            with (attempt / (label + ".stdout.log")).open("x", encoding="utf-8") as stdout, (attempt / (label + ".stderr.log")).open("x", encoding="utf-8") as stderr:
                result = subprocess.run(command, cwd=instance, stdout=stdout, stderr=stderr, timeout=60)
            after_sha = digest(exported) if exported.is_file() else None
            save(attempt / (label + ".execution.json"), {"command": command, "returncode": result.returncode, "finished_at": now(),
                "input_jfr_sha256": input_sha, "input_jfr_sha256_after": after_sha,
                "stdout_sha256": digest(attempt / (label + ".stdout.log"))}, exclusive=True)
            if result.returncode != 0 or (label == "jfr-dump" and not exported.is_file()):
                raise ValueError("Actual JFR export/read failed: " + label)
            if label != "jfr-dump" and input_sha != after_sha:
                raise ValueError("Actual JFR input changed during helper parsing.")
        events = read(attempt / "jfr-print.stdout.log")
        event_list = events["recording"]["events"]
        if not isinstance(event_list, list):
            raise ValueError("JFR JSON event list is invalid.")
        coverage = summary_coverage((attempt / "jfr-summary.stdout.log").read_text(encoding="utf-8"))
        save(root / "jfr-events.json", events, exclusive=True)
        shutil.copyfile(attempt / "jfr-summary.stdout.log", root / "jfr-summary.stdout.log")
        shutil.copyfile(exported, root / "recording.jfr")
        if digest(exported) != after_sha or digest(root / "recording.jfr") != after_sha:
            raise ValueError("Verified JFR input changed before evidence sealing.")
        receipt["status"] = "verified"
        receipt["recording_sha256"] = after_sha
        return event_list, coverage
    except BaseException as error:
        receipt.update(status="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        if exported.is_file():
            shutil.copyfile(exported, attempt / "recording.jfr")
        receipt["finished_at"] = now()
        save(attempt / "receipt.json", receipt, exclusive=True)


def collect_trial(descriptor, policy, root, *, trial_spec=None):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    instance = root / "instance"
    evidence = {"schema": 1, "status": "running", "qualification_key": descriptor["qualification_key"],
                "started_at": now(), "samples": [], "epochs": [], "windows": {}, "jfr_events": [], "jfr_coverage": None}
    evidence["capture_root"] = str(root)
    evidence["run_start"] = {"schema": 1, "scope": "official_client_performance_trial" if trial_spec is not None else "official_current_client_qualification",
                             "root": str(root), "started_at": evidence["started_at"], "trial_spec": trial_spec,
                             "qualification_key": descriptor["qualification_key"]}
    save(root / "run-start.json", evidence["run_start"], exclusive=True)
    evidence["run_start_sha256"] = digest(root / "run-start.json")
    process, observer, plan, interrupt_error = None, None, None, None
    jfr_verified = descriptor["instrumentation"] == "plain"
    epochs_path = instance / descriptor["probe_metadata"]["epochs_path"]
    snapshot_path = instance / descriptor["probe_metadata"]["snapshot_path"]
    diagnostic_path = instance / descriptor["probe_metadata"]["diagnostics_path"]
    try:
        verify_descriptor(descriptor, policy)
        shutil.copyfile(descriptor["diagnostic_review"]["path"], root / "diagnostic-review.json")
        evidence["diagnostic_review_sha256"] = digest(root / "diagnostic-review.json")
        plan = clone_prepared(descriptor, instance)
        process = packaged.launch(SimpleNamespace(instance=instance, wait_seconds=None))
        if not isinstance(process, subprocess.Popen):
            raise ValueError("Launcher must return the owned actual JVM subprocess.")
        launch = read(instance / "packaged-client-launch.json")
        observer = WindowsProcess(plan, launch)
        evidence["process"] = {**observer.identity, "created": observer.created, "captured_at": now(),
                               "arguments": windows_arguments(observer.identity["command"])}
        evidence["launch"] = launch
        save(root / "actual-process.json", evidence["process"], exclusive=True)
        save(root / "launch.json", launch, exclusive=True)
        save(root / "prepared-plan.json", plan, exclusive=True)
        created = instant(observer.created)
        anchor = None
        scene_ready = None
        measurement_end = None
        interval = policy["sample_interval_seconds"]
        deadline = time.monotonic()
        with (root / "samples.jsonl").open("x", encoding="utf-8") as sample_log:
            while True:
                stamp = now()
                moment = instant(stamp)
                if measurement_end is not None and moment >= measurement_end - dt.timedelta(seconds=interval / 2):
                    break
                if scene_ready is None and (moment - created).total_seconds() > policy["startup_timeout_seconds"]:
                    raise TimeoutError("No qualified native completion and scene within the frozen startup timeout.")
                sample = {"observed_at": stamp, "os": observer.sample(), "native": None, "errors": []}
                if sample["os"].get("running") is not True:
                    raise RuntimeError("Actual JVM exited before observation completed.")
                try:
                    raw = read_snapshot_bytes(snapshot_path)
                    sample["native"] = json.loads(raw.decode("utf-8-sig"))
                    sample["native_snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
                except (OSError, ValueError) as error:
                    sample["errors"].append("Neutral snapshot unavailable: " + str(error))
                try:
                    evidence["epochs"] = read_jsonl(epochs_path)
                except (OSError, ValueError) as error:
                    sample["errors"].append("Native epoch evidence unavailable: " + str(error))
                try:
                    log_prefix = (instance / "logs/latest.log").read_bytes()
                    sample["client_log_witness"] = {"bytes": len(log_prefix), "sha256": hashlib.sha256(log_prefix).hexdigest()}
                except OSError as error:
                    sample["errors"].append("Client log prefix unavailable: " + str(error))
                stamp = now()
                moment = instant(stamp)
                sample["observed_at"] = stamp
                if anchor is None and sample["native"] and not native_snapshot_errors(sample["native"], evidence["process"], stamp, policy["snapshot_freshness_seconds"], descriptor["scenario"], require_scene=False):
                    returned = [event for event in evidence["epochs"] if event.get("phase") == "return" and event.get("pid") == process.pid]
                    if returned and instant(sample["native"]["observed_at"]) >= max(instant(event["timestamp"]) for event in returned):
                        anchor = moment
                        evidence["windows"]["startup"] = {"start": observer.created, "end": stamp}
                        evidence["loading_anchor"] = {"kind": "first_captured_settled_native_snapshot_after_return",
                            "native_snapshot_observed_at": sample["native"]["observed_at"], "captured_at": stamp,
                            "sample_interval_seconds": interval,
                            "capture_delay_seconds": (moment - instant(sample["native"]["observed_at"])).total_seconds()}
                if anchor is not None and scene_ready is None and sample["native"] and not native_snapshot_errors(sample["native"], evidence["process"], stamp, policy["snapshot_freshness_seconds"], descriptor["scenario"]):
                    scene_ready = moment
                    warm_end = scene_ready + dt.timedelta(seconds=policy["warmup_seconds"])
                    measurement_end = warm_end + dt.timedelta(seconds=policy["measurement_seconds"])
                    evidence["windows"].update(scene_load={"start": anchor.isoformat(), "end": stamp},
                        warmup={"start": stamp, "end": warm_end.isoformat()},
                        steady={"start": warm_end.isoformat(), "end": measurement_end.isoformat()})
                evidence["samples"].append(sample)
                sample_log.write(json.dumps(sample, ensure_ascii=False, allow_nan=False) + "\n")
                sample_log.flush()
                # Skip missed slots; do not manufacture catch-up samples.
                clock = time.monotonic()
                deadline += interval
                if deadline <= clock:
                    deadline += (int((clock - deadline) // interval) + 1) * interval
                time.sleep(max(0, deadline - time.monotonic()))
        time.sleep(max(0, (measurement_end - instant(now())).total_seconds()))
        evidence["measurement_completed_at"] = now()
        evidence["measurement_process_running"] = process.poll() is None
        if not evidence["measurement_process_running"]:
            raise RuntimeError("Owned JVM exited before the frozen measurement endpoint was confirmed.")
        if descriptor["instrumentation"] == "profile":
            # Both metadata start and duration have whole-second resolution.
            # Wait from the actual frozen end, not from the last sampled slot.
            time.sleep(max(0, (measurement_end + dt.timedelta(seconds=2) - instant(now())).total_seconds()))
            evidence["jfr_events"], evidence["jfr_coverage"] = export_jfr(plan, process, instance, root)
            jfr_verified = True
            evidence["jfr_export"] = {"verified": True, "partial_observation": False}
        evidence["status"] = "complete"
    except BaseException as error:
        evidence.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
                        error=type(error).__name__ + ": " + str(error))
        if isinstance(error, KeyboardInterrupt):
            interrupt_error = error
    finally:
        # Preserve partial profiling on every failure/interrupt before considering
        # process termination. A failed export leaves this exact owned JVM alive.
        if descriptor["instrumentation"] == "profile" and process is not None and plan is not None and not jfr_verified:
            try:
                evidence["jfr_events"], evidence["jfr_coverage"] = export_jfr(plan, process, instance, root)
                jfr_verified = True
                evidence["jfr_export"] = {"verified": True, "partial_observation": True}
            except BaseException as error:
                evidence["jfr_export"] = {"verified": False, "partial_observation": True,
                                          "error": type(error).__name__ + ": " + str(error)}
                if isinstance(error, KeyboardInterrupt):
                    interrupt_error = error
        if process is not None:
            if not jfr_verified and process.poll() is None:
                RETAINED_PROCESSES[process.pid] = {"process": process, "observer": observer}
                evidence["cleanup"] = {"exited": False, "pid": process.pid, "timestamp": now(),
                    "reason": "profiling_export_failed_process_preserved", "instance": str(instance.resolve())}
                save(root / "preserved-process.json", {"cleanup": evidence["cleanup"], "process": evidence.get("process"),
                    "launch": evidence.get("launch"), "jfr_export": evidence.get("jfr_export")}, exclusive=True)
                evidence["status"] = "interrupted" if interrupt_error is not None else "failed"
            else:
                try:
                    if process.poll() is None:
                        process.terminate()
                    exit_code = process.wait(timeout=30)
                    evidence["cleanup"] = {"exited": True, "exit_code": exit_code, "pid": process.pid,
                                            "reason": "owned_experiment_process_cleanup", "timestamp": now()}
                except (OSError, subprocess.TimeoutExpired) as error:
                    RETAINED_PROCESSES[process.pid] = {"process": process, "observer": observer}
                    evidence["cleanup"] = {"exited": False, "pid": process.pid, "timestamp": now(), "error": str(error)}
                    evidence["status"] = "failed"
        else:
            evidence["cleanup"] = {"exited": True, "reason": "no_client_launched", "timestamp": now()}
        if observer and evidence["cleanup"]["exited"]:
            observer.close()
        for source, filename in ((epochs_path, "native-resource-epochs.jsonl"),
                                 (diagnostic_path, "native-invalid-model.jsonl"),
                                 (snapshot_path, "native-observer-final.json"),
                                 (instance / "launch.stdout.log", "launch.stdout.log"),
                                 (instance / "launch.stderr.log", "launch.stderr.log"),
                                 (instance / "logs/latest.log", "latest.log"),
                                 (instance / "acceptance-gc.log", "gc.log")):
            if source.is_file():
                shutil.copyfile(source, root / filename)
        if (root / "native-resource-epochs.jsonl").is_file():
            try:
                evidence["epochs"] = read_jsonl(root / "native-resource-epochs.jsonl")
            except ValueError as error:
                evidence.update(status="failed", error="Incomplete native epoch JSONL: " + str(error))
        else:
            (root / "native-resource-epochs.jsonl").write_text("", encoding="utf-8")
        if not (root / "samples.jsonl").exists():
            (root / "samples.jsonl").write_text("", encoding="utf-8")
        evidence["diagnostic_events"] = []
        try:
            evidence["diagnostic_events"] = read_jsonl(root / "native-invalid-model.jsonl")
        except (OSError, ValueError) as error:
            evidence.update(status="failed", diagnostic_error="Incomplete native diagnostic JSONL: " + str(error))
        evidence["finished_at"] = now()
        try:
            raw_log = (root / "latest.log").read_bytes()
            evidence["client_diagnostics"] = assess_native_diagnostics(root, evidence, descriptor["probe_metadata"], read(root / "diagnostic-review.json"))
            evidence["client_log_completeness"] = client_log_completeness(raw_log, evidence["samples"], instance)
        except (OSError, UnicodeError, ValueError) as error:
            try:
                evidence["client_diagnostics"] = native_diagnostics((root / "latest.log").read_text(encoding="utf-8-sig"))
                evidence["client_diagnostics"].update(reviewed_native=[], native_attribution={"passed": False, "errors": [str(error)]})
            except (OSError, UnicodeError) as log_error:
                evidence["client_diagnostics"] = {"scanned": False, "unreviewed_native": [],
                    "other_errors_requiring_contextual_review": [], "error": str(log_error)}
            evidence["client_log_completeness"] = {"passed": False, "errors": [str(error)]}
        actual = evidence.get("process", {})
        evidence["run_finish"] = {"schema": 1, "scope": evidence["run_start"]["scope"], "root": str(root),
            "finished_at": evidence["finished_at"], "start_sha256": evidence["run_start_sha256"],
            "process": {"pid": actual.get("pid"), "created": actual.get("created")},
            "measurement_completed_at": evidence.get("measurement_completed_at"), "cleanup": evidence["cleanup"]}
        save(root / "run-finish.json", evidence["run_finish"], exclusive=True)
        save(root / "observation.json", evidence)
    result = assess_observation(evidence, policy, descriptor["scenario"], descriptor["instrumentation"])
    save(root / "result.json", result, exclusive=True)
    if interrupt_error is not None:
        raise interrupt_error
    return evidence, result


def qualify(args):
    output, attempt = new_attempt(args.output, "qualify", {"prepared_plan": str(args.prepared_plan), "role": args.role,
                                                           "instrumentation": args.instrumentation, "policy": str(args.policy)})
    try:
        policy = read(args.policy)
        validate_policy(policy)
        frozen_sources = [fingerprint(source) for source in SOURCES]
        descriptor = prepared_descriptor(args.prepared_plan, args.role, args.instrumentation, policy)
        host = environment()
        # Collect in the attempt root's dedicated child so preparation failures also
        # retain attempt.json and never overwrite an earlier run.
        trial_root = output / "trial"
        evidence, result = collect_trial(descriptor, policy, trial_root)
        for source in frozen_sources:
            verify_fingerprint(source)
        verify_descriptor(descriptor, policy)
        if environment() != host:
            raise ValueError("Host/injected environment changed during qualification.")
        report = {"schema": 1, "scope": "official_current_client_qualification", "status": "passed" if result["passed"] else "failed",
                  "created_at": now(), "qualification_key": descriptor["qualification_key"], "fields": descriptor["qualification_fields"],
                  "environment": host, "sources": frozen_sources, "result": result, "files": raw_files(trial_root)}
        save(trial_root / "qualification.json", report, exclusive=True)
        attempt.update(status=report["status"], qualification=str(trial_root / "qualification.json"), result=result)
        if not result["passed"]:
            return 2
    except BaseException as error:
        attempt.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        attempt["finished_at"] = now()
        save(output / "attempt.json", attempt)
    return 0


def run_plan(path):
    path = Path(path).resolve(strict=True)
    plan = read(path)
    state = {"schema": 1, "status": "running", "started_at": now(), "plan_sha256": digest(path), "trials": []}
    state_path = path.parent / "execution.json"
    save(state_path, state, exclusive=True)
    save(path.parent / "execution-start.json", {"schema": 1, "scope": SCOPE, "root": str(path.parent),
        "plan_sha256": state["plan_sha256"], "started_at": state["started_at"]}, exclusive=True)
    try:
        verify_plan(path, plan)
        for spec in plan["schedule"]:
            if digest(path) != state["plan_sha256"]:
                raise ValueError("Plan changed during execution.")
            verify_plan(path, plan)
            key = spec["role"] + "_" + spec["instrumentation"]
            descriptor = plan["prepared"][key]
            trial = {**spec, "status": "running", "started_at": now(), "qualification_key": descriptor["qualification_key"]}
            state["trials"].append(trial)
            save(state_path, state)
            print("Measuring " + spec["id"], flush=True)
            root = path.parent / spec["id"]
            try:
                evidence, result = collect_trial(descriptor, plan["policy"], root, trial_spec=spec)
                trial.update(status="complete" if result["passed"] else "failed", evidence=evidence, result=result, files=raw_files(root))
                if evidence.get("cleanup", {}).get("exited") is not True:
                    raise RuntimeError("Owned JVM cleanup failed; no subsequent independent trial may start.")
            finally:
                trial["finished_at"] = now()
                if root.exists():
                    trial["files"] = raw_files(root)
                save(state_path, state)
        verify_plan(path, plan)
        execution_start = read(path.parent / "execution-start.json")
        if execution_start != {"schema": 1, "scope": SCOPE, "root": str(path.parent),
                              "plan_sha256": state["plan_sha256"], "started_at": state["started_at"]}:
            raise ValueError("Execution summary differs from raw experiment-start receipt.")
        state["status"] = "complete" if all(trial["status"] == "complete" for trial in state["trials"]) else "failed"
    except BaseException as error:
        state.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        state["finished_at"] = now()
        save(state_path, state)
    report = audit(path)
    save(path.parent / "analysis.json", report, exclusive=True)
    return 0 if report["status"] == "pass" else 2


def audit(path):
    path = Path(path).resolve(strict=True)
    plan, state = read(path), read(path.parent / "execution.json")
    errors = []
    try:
        verify_plan(path, plan)
        execution_start = read(path.parent / "execution-start.json")
        if execution_start != {"schema": 1, "scope": SCOPE, "root": str(path.parent),
                              "plan_sha256": state["plan_sha256"], "started_at": state["started_at"]}:
            raise ValueError("Execution summary differs from raw experiment-start receipt.")
        if state["plan_sha256"] != digest(path):
            errors.append("Plan fingerprint differs from execution.")
        expected_ids = {spec["id"]: spec for spec in plan["schedule"]}
        for trial in state.get("trials", []):
            if trial.get("id") not in expected_ids:
                raise ValueError("Unexpected trial directory identity.")
            root = path.parent / trial["id"]
            verify_raw_files(root, trial.get("files", []))
            key = trial["role"] + "_" + trial["instrumentation"]
            evidence, result = audit_observation(root, plan["policy"], plan["scenario"], trial["instrumentation"],
                expected_trial=expected_ids[trial["id"]], experiment_started=execution_start["started_at"])
            if not instant(state["started_at"]) <= instant(trial["started_at"]) <= instant(evidence["run_start"]["started_at"]) or not instant(evidence["run_finish"]["finished_at"]) <= instant(trial["finished_at"]) <= instant(state["finished_at"]):
                raise ValueError("Edited trial/execution summary does not contain the raw actual execution window.")
            verify_observed_identity(root, plan["prepared"][key])
            if evidence != trial.get("evidence") or result != trial.get("result") or evidence.get("qualification_key") != plan["prepared"][key]["qualification_key"]:
                errors.append("Raw observations/results differ from execution: " + trial["id"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(type(error).__name__ + ": " + str(error))
    try:
        report = analyze(plan, state)
    except (ValueError, KeyError, TypeError) as error:
        report = {"status": "invalid", "performance_accepted": False, "errors": [str(error)],
                  "failure_denominator": {"scheduled_trials": len(plan.get("schedule", [])), "recorded_trials": len(state.get("trials", []))}}
    if errors:
        report.update(status="invalid", performance_accepted=False, instrumented_performance_accepted=False,
                      instrumented_comparison_status="invalid", integrity_errors=errors)
    return {**report, "plan_sha256": digest(path), "execution_sha256": digest(path.parent / "execution.json"),
            "analyzer_sha256": digest(Path(__file__).with_name("client_experiment_analysis.py"))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    qualification = commands.add_parser("qualify", help="Launch one fresh isolated JVM for one exact current qualification group.")
    qualification.add_argument("--prepared-plan", type=Path, required=True)
    qualification.add_argument("--role", choices=ROLES, required=True)
    qualification.add_argument("--instrumentation", choices=MODES, required=True)
    qualification.add_argument("--output", type=Path, required=True)
    qualification.add_argument("--policy", type=Path, default=ROOT / "config/client-experiment.json")
    planning = commands.add_parser("plan", help="Freeze all four already-qualified groups; never starts a client.")
    for role in ROLES:
        for mode in MODES:
            planning.add_argument("--" + role + "-" + mode, type=Path, required=True)
    planning.add_argument("--qualification", type=Path, action="append", default=[])
    planning.add_argument("--policy", type=Path, default=ROOT / "config/client-experiment.json")
    planning.add_argument("--output", type=Path, required=True)
    planning.add_argument("--environment-notes", required=True, help="Freeze power mode, scheduler/background load and known host confounders.")
    for action in ("run", "analyze"):
        command = commands.add_parser(action)
        command.add_argument("--plan", type=Path, required=True)
        if action == "analyze":
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "plan":
        make_plan(args)
        return 0
    if args.action == "qualify":
        return qualify(args)
    if args.action == "run":
        return run_plan(args.plan)
    report = audit(args.plan)
    save(args.output, report, exclusive=True)
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr, flush=True)
        raise SystemExit(2)
