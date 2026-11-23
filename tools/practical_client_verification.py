"""Execute and independently audit the 12-JVM practical paired verification.

Covers balanced A/B plain, A/B profile+Spark 100ms, A/A plain noise control,
and 2-mod observer-off calibration without touching product binaries or relaxed
acceptance thresholds. Separate from the 48-trial gate in client_experiment.py.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

import client_experiment as exp
import client_experiment_analysis as analysis
import native_log_stream
from observe_packaged_client import WindowsProcess, verify_process_identity, windows_arguments
import packaged_client as packaged
import spark_client_sampler as sampler
from windows_snapshot_io import read_snapshot_bytes


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/client-practical-verification.json"
DEFAULT_EXP_POLICY = ROOT / "config/client-experiment.json"
DEFAULT_SOURCE = ROOT.parent / ".cache/game-test/nf248-official-3g"
DEFAULT_COMPANION_048 = ROOT / "evidence/engineering-051/streamed-obj-input/runs/02-final-nf248/mtr-memory-saver-official-nf248-0.4.8.jar"
DEFAULT_CATALOGUE = ROOT.parent / "[MTR4.1原生目录]产物/catalog.json"
DEFAULT_TEMPLATES_ROOT = ROOT / ".cache/acceptance"
DEFAULT_TEMPLATE_PREFIX = "official-nf248-spark048-"
DEFAULT_PROBE_OFF_TEMPLATE = ROOT / ".cache/acceptance/official-nf248-probeoff048-template"
CANDIDATE_048_NF248_SHA = "943b3d455fa3ce9d3ede74bc1a2071ece7bf70b09d9b7f829027347b53a9b588"
PROBE_OFF_SCOPE = "official_practical_probe_off_trial"
TRIAL_INVENTORY_EXCLUSIONS = ("trial-summary.json",)
READONLY_CLONE_DIRS = {"assets", "libraries", "versions", "resourcepacks", "mods", ".prepared-controls"}
DEFAULT_RAIL_ERROR_RE = re.compile(
    r"^\[[^\]\r\n]+\]\s+\[Render thread/ERROR\]\s+\[MinecraftTransitRailway/\]:\s+"
    r"\[mtr:textures/block/transparent\.png\] Invalid model!\s*$"
)
LOADED_VEHICLES_RE = re.compile(rb"Loaded (\d+) vehicles and completed door movement validation")
SHARE_LINE_RE = re.compile(
    r"MTR memory sharing:\s+(\d+) requests,\s+(\d+) path hits,\s+(\d+) unique parses,\s+"
    r"(\d+) failures,\s+(\d+) pending,\s+(\d+) outstanding,\s+(\d+) queued"
)
STREAMED_OBJ_RE = re.compile(
    r"MTR streamed OBJ:\s+(\d+) requests,\s+(\d+) path hits,\s+(\d+) parses,\s+"
    r"(\d+) failures,\s+(\d+) pending,\s+(\d+) outstanding,\s+(\d+) queued"
)
PROBE_OFF_REQUIRED_LINES = (
    "Loaded 1092 vehicles and completed door movement validation",
    "Loaded 142 signs",
    "Loaded 23 rails",
    "Loaded 290 objects",
    "Loaded 1 lifts",
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, data, *, exclusive=False):
    exp.save(path, data, exclusive=exclusive)


def digest(path):
    return exp.digest(path)


def now():
    return exp.now()


def instant(text):
    return analysis.instant(text)


def load_policy(path=DEFAULT_POLICY):
    policy = read(path)
    required = {
        "schema", "scope", "target", "description", "startup_timeout_seconds",
        "warmup_seconds", "measurement_seconds", "sample_interval_seconds",
        "maximum_sample_gap_seconds", "snapshot_freshness_seconds",
        "jfr_boundary_tolerance_seconds", "probe_off_post_load_warmup_seconds",
        "probe_off_steady_seconds", "spark_sampler_id", "spark_interval_microseconds",
        "spark_duration_seconds", "budgets", "schedule",
    }
    if set(policy) != required or policy["schema"] != 1 or policy["scope"] != "official_practical_paired_verification":
        raise ValueError("Invalid practical verification policy schema or scope.")
    if not policy["schedule"] or len({item["id"] for item in policy["schedule"]}) != len(policy["schedule"]):
        raise ValueError("Practical verification schedule must have unique trial IDs.")
    return policy


def verify_probe_off_template(instance):
    instance = Path(instance).resolve(strict=True)
    plan_path = instance / "packaged-client-plan.json"
    plan = read(plan_path)
    if plan.get("schema") != 1 or plan.get("scope") != "packaged_client_preparation":
        raise ValueError("Probe-off template must be a schema-1 uninstrumented prepared client.")
    if (instance / "packaged-client-launch.json").exists() or read(instance / "vehicle-test-instance.json").get("pid"):
        raise ValueError("Probe-off template must never have launched.")
    if (instance / "logs").exists():
        raise ValueError("Probe-off template cannot contain prior logs.")
    packaged.verify_prepared_inputs(instance, plan)
    matrix = read(ROOT / "config/targets.json")
    mods = plan["mods"]
    if len(mods) != 2 or {mod["role"] for mod in mods} != {"mtr", "companion"}:
        raise ValueError("Probe-off template must install only official MTR and candidate companion.")
    companion = next(mod for mod in mods if mod["role"] == "companion")
    mtr_mod = next(mod for mod in mods if mod["role"] == "mtr")
    if companion["sha256"] != CANDIDATE_048_NF248_SHA or mtr_mod["sha256"] != matrix["mtr"]["official"]["sha256"]:
        raise ValueError("Probe-off template artifact or MTR bytes differ from the frozen 0.4.8 target.")
    if plan.get("jfr") is not False or plan.get("native_memory_tracking") is not None:
        raise ValueError("Probe-off template must disable JFR and NMT.")
    if "-XX:+UseG1GC" not in packaged.jvm_arguments(plan) or plan.get("heap_mib") != 3072 or plan.get("initial_heap_mib") != 512:
        raise ValueError("Probe-off template JVM heap/GC settings differ from the comparison baseline.")
    if not plan.get("world") or plan["world"].get("name") != "Vehicle Acceptance 1_21_1" or len(plan.get("packs", [])) != 16:
        raise ValueError("Probe-off template world or 16-pack inventory differs.")
    return {"instance": str(instance), "prepared_plan": exp.fingerprint(plan_path), "artifact_sha256": companion["sha256"]}


def prepare_probe_off(output, *, source=DEFAULT_SOURCE, companion=DEFAULT_COMPANION_048,
                      catalogue=DEFAULT_CATALOGUE, world="Vehicle Acceptance 1_21_1", username="VehicleTest"):
    output = Path(output).resolve()
    if digest(companion) != CANDIDATE_048_NF248_SHA:
        raise ValueError("Supplied 0.4.8 NF248 companion differs from frozen artifact hash.")
    argv = [
        sys.executable, "-u", "-X", "utf8", str(ROOT / "tools/packaged_client.py"), "prepare",
        "--source", str(Path(source).resolve()),
        "--instance", str(output),
        "--companion", str(Path(companion).resolve()),
        "--catalogue", str(Path(catalogue).resolve()),
        "--world", world,
        "--username", username,
        "--heap-mib", "3072",
        "--initial-heap-mib", "512",
        "--jvm-arg=-XX:+UseG1GC",
    ]
    subprocess.run(argv, cwd=ROOT, check=True)
    return verify_probe_off_template(output)


def clone_probe_off(template, destination):
    template = Path(template).resolve(strict=True)
    verify_probe_off_template(template)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for entry in template.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            if entry.name in READONLY_CLONE_DIRS:
                shutil.copytree(entry, target, copy_function=exp._link_or_copy)
            else:
                shutil.copytree(entry, target)
        else:
            shutil.copy2(entry, target)
    plan = read(destination / "packaged-client-plan.json")
    plan["instance"] = str(destination.resolve())
    save(destination / "packaged-client-plan.json", plan)
    marker = read(destination / "vehicle-test-instance.json")
    marker.update(instance=str(destination.resolve()), pid=None)
    save(destination / "vehicle-test-instance.json", marker)
    packaged.verify_prepared_inputs(destination, plan)
    return plan


def collect_profile_spark_trial(descriptor, base_policy, sampler_spec, root, *, trial_spec):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    instance = root / "instance"
    evidence = {
        "schema": 1, "status": "running", "qualification_key": descriptor["qualification_key"],
        "started_at": now(), "samples": [], "epochs": [], "windows": {}, "jfr_events": [], "jfr_coverage": None,
    }
    evidence["capture_root"] = str(root)
    evidence["run_start"] = {
        "schema": 1, "scope": "official_client_performance_trial", "root": str(root),
        "started_at": evidence["started_at"], "trial_spec": trial_spec,
        "qualification_key": descriptor["qualification_key"], "native_log_stream_contract": 1,
    }
    save(root / "run-start.json", evidence["run_start"], exclusive=True)
    evidence["run_start_sha256"] = digest(root / "run-start.json")
    process, observer, plan, interrupt_error, log_stream = None, None, None, None, None
    jfr_verified = False
    epochs_path = instance / descriptor["probe_metadata"]["epochs_path"]
    snapshot_path = instance / descriptor["probe_metadata"]["snapshot_path"]
    diagnostic_path = instance / descriptor["probe_metadata"]["diagnostics_path"]
    try:
        exp.verify_descriptor(descriptor, base_policy)
        shutil.copyfile(descriptor["diagnostic_review"]["path"], root / "diagnostic-review.json")
        evidence["diagnostic_review_sha256"] = digest(root / "diagnostic-review.json")
        plan = exp.clone_prepared(descriptor, instance)
        process = packaged.launch(SimpleNamespace(instance=instance, wait_seconds=None))
        if not isinstance(process, subprocess.Popen):
            raise ValueError("Launcher must return the owned actual JVM subprocess.")
        launch = read(instance / "packaged-client-launch.json")
        observer = WindowsProcess(plan, launch)
        evidence["process"] = {
            **observer.identity, "created": observer.created, "captured_at": now(),
            "arguments": windows_arguments(observer.identity["command"]),
        }
        evidence["launch"] = launch
        save(root / "actual-process.json", evidence["process"], exclusive=True)
        save(root / "launch.json", launch, exclusive=True)
        save(root / "prepared-plan.json", plan, exclusive=True)
        log_stream = native_log_stream.NativeLogStream.from_launch(
            instance, plan, launch, root / "native-log", evidence["process"]
        )
        created = instant(observer.created)
        anchor = None
        spark_requested = False
        spark_continued = False
        request_deadline = None
        scene_ready = None
        measurement_end = None
        interval = base_policy["sample_interval_seconds"]
        deadline = time.monotonic()
        with (root / "samples.jsonl").open("x", encoding="utf-8") as sample_log:
            while True:
                stamp = now()
                moment = instant(stamp)
                if measurement_end is not None and moment >= measurement_end - dt.timedelta(seconds=interval / 2):
                    break
                if scene_ready is None and (moment - created).total_seconds() > base_policy["startup_timeout_seconds"]:
                    raise TimeoutError("No qualified native completion, Spark start and scene within startup timeout.")
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
                    evidence["epochs"] = exp.read_jsonl(epochs_path)
                except (OSError, ValueError) as error:
                    sample["errors"].append("Native epoch evidence unavailable: " + str(error))
                try:
                    log_prefix = log_stream.read().data
                    sample["client_log_witness"] = {"bytes": len(log_prefix), "sha256": hashlib.sha256(log_prefix).hexdigest()}
                except OSError as error:
                    sample["errors"].append("Client log prefix unavailable: " + str(error))
                stamp = now()
                moment = instant(stamp)
                sample["observed_at"] = stamp
                if anchor is None and sample["native"] and not analysis.native_snapshot_errors(
                    sample["native"], evidence["process"], stamp, base_policy["snapshot_freshness_seconds"],
                    descriptor["scenario"], require_scene=False
                ):
                    returned = [event for event in evidence["epochs"] if event.get("phase") == "return" and event.get("pid") == process.pid]
                    if returned and instant(sample["native"]["observed_at"]) >= max(instant(event["timestamp"]) for event in returned):
                        anchor = moment
                        evidence["windows"]["startup"] = {"start": observer.created, "end": stamp}
                        evidence["loading_anchor"] = {
                            "kind": "first_captured_settled_native_snapshot_after_return",
                            "native_snapshot_observed_at": sample["native"]["observed_at"],
                            "captured_at": stamp,
                            "sample_interval_seconds": interval,
                            "capture_delay_seconds": (moment - instant(sample["native"]["observed_at"])).total_seconds(),
                        }
                if anchor is not None and not spark_requested and sample["native"] and not analysis.native_snapshot_errors(
                    sample["native"], evidence["process"], stamp, base_policy["snapshot_freshness_seconds"], descriptor["scenario"]
                ):
                    sampler.request(root, sampler_spec, evidence["process"], instance, stamp)
                    spark_requested = True
                    request_deadline = moment + dt.timedelta(seconds=sampler_spec["operator_timeout_seconds"])
                if spark_requested and scene_ready is None:
                    if not spark_continued:
                        if (root / "sampler-operator-failed.json").is_file():
                            raise RuntimeError("Spark window operator failed to start local profiling.")
                        if sampler.continued(root):
                            spark_continued = True
                        elif moment > request_deadline:
                            raise TimeoutError("Timed out waiting for Spark operator continuation.")
                    if spark_continued and sample["native"] and not analysis.native_snapshot_errors(
                        sample["native"], evidence["process"], stamp, base_policy["snapshot_freshness_seconds"], descriptor["scenario"]
                    ):
                        scene_ready = moment
                        warm_end = scene_ready + dt.timedelta(seconds=base_policy["warmup_seconds"])
                        measurement_end = warm_end + dt.timedelta(seconds=base_policy["measurement_seconds"])
                        evidence["windows"].update(
                            scene_load={"start": anchor.isoformat(), "end": stamp},
                            warmup={"start": stamp, "end": warm_end.isoformat()},
                            steady={"start": warm_end.isoformat(), "end": measurement_end.isoformat()},
                        )
                evidence["samples"].append(sample)
                sample_log.write(json.dumps(sample, ensure_ascii=False, allow_nan=False) + "\n")
                sample_log.flush()
                clock = time.monotonic()
                deadline += interval
                if deadline <= clock:
                    deadline += (int((clock - deadline) // interval) + 1) * interval
                time.sleep(max(0, deadline - time.monotonic()))
        time.sleep(max(0, (measurement_end - instant(now())).total_seconds()))
        evidence["measurement_completed_at"] = now()
        evidence["measurement_process_running"] = process.poll() is None
        if not evidence["measurement_process_running"]:
            raise RuntimeError("Owned JVM exited before frozen measurement endpoint was confirmed.")
        time.sleep(max(0, (measurement_end + dt.timedelta(seconds=2) - instant(now())).total_seconds()))
        evidence["jfr_events"], evidence["jfr_coverage"] = exp.export_jfr(plan, process, instance, root)
        jfr_verified = True
        evidence["jfr_export"] = {"verified": True, "partial_observation": False}
        sampler.wait_for_file(root, instance, sampler_spec, process)
        evidence["status"] = "complete"
    except BaseException as error:
        evidence.update(
            status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
            error=type(error).__name__ + ": " + str(error),
        )
        if isinstance(error, KeyboardInterrupt):
            interrupt_error = error
    finally:
        if process is not None and plan is not None and not jfr_verified:
            try:
                evidence["jfr_events"], evidence["jfr_coverage"] = exp.export_jfr(plan, process, instance, root)
                jfr_verified = True
                evidence["jfr_export"] = {"verified": True, "partial_observation": True}
            except BaseException as error:
                evidence["jfr_export"] = {"verified": False, "partial_observation": True, "error": f"{type(error).__name__}: {error}"}
                if isinstance(error, KeyboardInterrupt):
                    interrupt_error = error
        if process is not None:
            if not jfr_verified and process.poll() is None:
                exp.RETAINED_PROCESSES[process.pid] = {"process": process, "observer": observer}
                evidence["cleanup"] = {
                    "exited": False, "pid": process.pid, "timestamp": now(),
                    "reason": "profiling_export_failed_process_preserved", "instance": str(instance.resolve()),
                }
                save(root / "preserved-process.json", {
                    "cleanup": evidence["cleanup"], "process": evidence.get("process"),
                    "launch": evidence.get("launch"), "jfr_export": evidence.get("jfr_export"),
                }, exclusive=True)
                evidence["status"] = "interrupted" if interrupt_error is not None else "failed"
            else:
                try:
                    if process.poll() is None:
                        process.terminate()
                    exit_code = process.wait(timeout=30)
                    evidence["cleanup"] = {
                        "exited": True, "exit_code": exit_code, "pid": process.pid,
                        "reason": "owned_experiment_process_cleanup", "timestamp": now(),
                    }
                except (OSError, subprocess.TimeoutExpired) as error:
                    exp.RETAINED_PROCESSES[process.pid] = {"process": process, "observer": observer}
                    evidence["cleanup"] = {"exited": False, "pid": process.pid, "timestamp": now(), "error": str(error)}
                    evidence["status"] = "failed"
        else:
            evidence["cleanup"] = {"exited": True, "reason": "no_client_launched", "timestamp": now()}
        if observer and evidence["cleanup"]["exited"]:
            observer.close()
        for source, filename in (
            (epochs_path, "native-resource-epochs.jsonl"),
            (diagnostic_path, "native-invalid-model.jsonl"),
            (snapshot_path, "native-observer-final.json"),
            (instance / "launch.stdout.log", "launch.stdout.log"),
            (instance / "launch.stderr.log", "launch.stderr.log"),
            (instance / "acceptance-gc.log", "gc.log"),
        ):
            if source.is_file():
                shutil.copyfile(source, root / filename)
        if log_stream is not None:
            try:
                (root / "latest.log").write_bytes(log_stream.read().data)
                evidence["native_log_stream"] = log_stream.reference()
            except Exception as log_error:
                evidence.update(status="failed", native_log_stream_error=repr(log_error))
                if log_stream.last is not None:
                    (root / "latest.log").write_bytes(log_stream.last.data)
                    evidence["native_log_stream"] = {**log_stream.reference(), "completion_read_failed": True}
        if (root / "native-resource-epochs.jsonl").is_file():
            try:
                evidence["epochs"] = exp.read_jsonl(root / "native-resource-epochs.jsonl")
            except ValueError as error:
                evidence.update(status="failed", error="Incomplete native epoch JSONL: " + str(error))
        else:
            (root / "native-resource-epochs.jsonl").write_text("", encoding="utf-8")
        if not (root / "samples.jsonl").exists():
            (root / "samples.jsonl").write_text("", encoding="utf-8")
        evidence["diagnostic_events"] = []
        try:
            evidence["diagnostic_events"] = exp.read_jsonl(root / "native-invalid-model.jsonl")
        except (OSError, ValueError) as error:
            evidence.update(status="failed", diagnostic_error="Incomplete native diagnostic JSONL: " + str(error))
        evidence["finished_at"] = now()
        try:
            raw_log = (root / "latest.log").read_bytes()
            evidence["client_diagnostics"] = exp.assess_native_diagnostics(
                root, evidence, descriptor["probe_metadata"], read(root / "diagnostic-review.json")
            )
            evidence["client_log_completeness"] = analysis.client_log_completeness(raw_log, evidence["samples"], instance)
        except (OSError, UnicodeError, ValueError) as error:
            try:
                evidence["client_diagnostics"] = analysis.native_diagnostics((root / "latest.log").read_text(encoding="utf-8-sig"))
                evidence["client_diagnostics"].update(reviewed_native=[], native_attribution={"passed": False, "errors": [str(error)]})
            except (OSError, UnicodeError) as log_error:
                evidence["client_diagnostics"] = {
                    "scanned": False, "unreviewed_native": [],
                    "other_errors_requiring_contextual_review": [], "error": str(log_error),
                }
            evidence["client_log_completeness"] = {"passed": False, "errors": [str(error)]}
        actual = evidence.get("process", {})
        evidence["run_finish"] = {
            "schema": 1, "scope": evidence["run_start"]["scope"], "root": str(root),
            "finished_at": evidence["finished_at"], "start_sha256": evidence["run_start_sha256"],
            "process": {"pid": actual.get("pid"), "created": actual.get("created")},
            "measurement_completed_at": evidence.get("measurement_completed_at"),
            "cleanup": evidence["cleanup"],
        }
        save(root / "run-finish.json", evidence["run_finish"], exclusive=True)
        save(root / "observation.json", evidence)
    result = analysis.assess_observation(evidence, base_policy, descriptor["scenario"], "profile")
    spark_assessment = None
    if evidence.get("status") == "complete" and (root / "spark/recording.sparkprofile").is_file():
        try:
            spark_assessment = sampler.finish(root, plan, evidence, sampler_spec)
        except Exception as error:
            spark_assessment = {"verified": False, "error": f"{type(error).__name__}: {error}"}
            result["passed"] = False
            result["errors"].append("Spark validation failed: " + spark_assessment["error"])
    elif result["passed"]:
        result["passed"] = False
        result["errors"].append("Spark recording was not captured.")
    save(root / "result.json", result, exclusive=True)
    if interrupt_error is not None:
        raise interrupt_error
    return evidence, result, spark_assessment


def collect_probe_off_trial(template, policy, root, *, trial_spec):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    instance = root / "instance"
    evidence = {
        "schema": 1, "status": "running", "scope": PROBE_OFF_SCOPE,
        "started_at": now(), "samples": [], "windows": {},
    }
    evidence["capture_root"] = str(root)
    evidence["run_start"] = {
        "schema": 1, "scope": PROBE_OFF_SCOPE, "root": str(root),
        "started_at": evidence["started_at"], "trial_spec": trial_spec,
        "native_log_stream_contract": 1,
    }
    save(root / "run-start.json", evidence["run_start"], exclusive=True)
    evidence["run_start_sha256"] = digest(root / "run-start.json")
    process, observer, plan, interrupt_error, log_stream = None, None, None, None, None
    try:
        plan = clone_probe_off(template, instance)
        process = packaged.launch(SimpleNamespace(instance=instance, wait_seconds=None))
        if not isinstance(process, subprocess.Popen):
            raise ValueError("Launcher must return the owned actual JVM subprocess.")
        launch = read(instance / "packaged-client-launch.json")
        observer = WindowsProcess(plan, launch)
        evidence["process"] = {
            **observer.identity, "created": observer.created, "captured_at": now(),
            "arguments": windows_arguments(observer.identity["command"]),
        }
        evidence["launch"] = launch
        save(root / "actual-process.json", evidence["process"], exclusive=True)
        save(root / "launch.json", launch, exclusive=True)
        save(root / "prepared-plan.json", plan, exclusive=True)
        log_stream = native_log_stream.NativeLogStream.from_launch(
            instance, plan, launch, root / "native-log", evidence["process"]
        )
        created = instant(observer.created)
        anchor = None
        measurement_end = None
        interval = policy["sample_interval_seconds"]
        warmup_seconds = policy["probe_off_post_load_warmup_seconds"]
        steady_seconds = policy["probe_off_steady_seconds"]
        deadline = time.monotonic()
        with (root / "samples.jsonl").open("x", encoding="utf-8") as sample_log:
            while True:
                stamp = now()
                moment = instant(stamp)
                if measurement_end is not None and moment >= measurement_end - dt.timedelta(seconds=interval / 2):
                    break
                if anchor is None and (moment - created).total_seconds() > policy["startup_timeout_seconds"]:
                    raise TimeoutError("Probe-off client did not finish MTR vehicle registration within startup timeout.")
                sample = {"observed_at": stamp, "os": observer.sample(), "errors": []}
                if sample["os"].get("running") is not True:
                    raise RuntimeError("Probe-off JVM exited before observation completed.")
                log_prefix = None
                try:
                    log_prefix = log_stream.read().data
                    sample["client_log_witness"] = {"bytes": len(log_prefix), "sha256": hashlib.sha256(log_prefix).hexdigest()}
                except OSError as error:
                    sample["errors"].append("Client log prefix unavailable: " + str(error))
                stamp = now()
                moment = instant(stamp)
                sample["observed_at"] = stamp
                if anchor is None and log_prefix is not None:
                    matched = LOADED_VEHICLES_RE.search(log_prefix)
                    if matched:
                        if int(matched.group(1)) != 1092:
                            raise ValueError(f"Unexpected registered vehicle count in probe-off log: {matched.group(1)!r}")
                        anchor = moment
                        warm_end = anchor + dt.timedelta(seconds=warmup_seconds)
                        measurement_end = warm_end + dt.timedelta(seconds=steady_seconds)
                        evidence["windows"] = {
                            "startup": {"start": observer.created, "end": stamp},
                            "warmup": {"start": stamp, "end": warm_end.isoformat()},
                            "steady": {"start": warm_end.isoformat(), "end": measurement_end.isoformat()},
                        }
                        evidence["loading_anchor"] = {
                            "kind": "first_observed_loaded_vehicles_log_line",
                            "captured_at": stamp,
                            "sample_interval_seconds": interval,
                        }
                evidence["samples"].append(sample)
                sample_log.write(json.dumps(sample, ensure_ascii=False, allow_nan=False) + "\n")
                sample_log.flush()
                clock = time.monotonic()
                deadline += interval
                if deadline <= clock:
                    deadline += (int((clock - deadline) // interval) + 1) * interval
                time.sleep(max(0, deadline - time.monotonic()))
        time.sleep(max(0, (measurement_end - instant(now())).total_seconds()))
        evidence["measurement_completed_at"] = now()
        evidence["measurement_process_running"] = process.poll() is None
        if not evidence["measurement_process_running"]:
            raise RuntimeError("Probe-off JVM exited before frozen measurement endpoint.")
        evidence["status"] = "complete"
    except BaseException as error:
        evidence.update(
            status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
            error=type(error).__name__ + ": " + str(error),
        )
        if isinstance(error, KeyboardInterrupt):
            interrupt_error = error
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                exit_code = process.wait(timeout=30)
                evidence["cleanup"] = {
                    "exited": True, "exit_code": exit_code, "pid": process.pid,
                    "reason": "owned_probe_off_process_cleanup", "timestamp": now(),
                }
            except (OSError, subprocess.TimeoutExpired) as error:
                exp.RETAINED_PROCESSES[process.pid] = {"process": process, "observer": observer}
                evidence["cleanup"] = {"exited": False, "pid": process.pid, "timestamp": now(), "error": str(error)}
                evidence["status"] = "failed"
        else:
            evidence["cleanup"] = {"exited": True, "reason": "no_client_launched", "timestamp": now()}
        if observer and evidence["cleanup"]["exited"]:
            observer.close()
        for source, filename in (
            (instance / "launch.stdout.log", "launch.stdout.log"),
            (instance / "launch.stderr.log", "launch.stderr.log"),
        ):
            if source.is_file():
                shutil.copyfile(source, root / filename)
        if log_stream is not None:
            try:
                (root / "latest.log").write_bytes(log_stream.read().data)
                evidence["native_log_stream"] = log_stream.reference()
            except Exception as log_error:
                evidence.update(status="failed", native_log_stream_error=repr(log_error))
                if log_stream.last is not None:
                    (root / "latest.log").write_bytes(log_stream.last.data)
                    evidence["native_log_stream"] = {**log_stream.reference(), "completion_read_failed": True}
        if not (root / "samples.jsonl").exists():
            (root / "samples.jsonl").write_text("", encoding="utf-8")
        evidence["finished_at"] = now()
        try:
            raw_log = (root / "latest.log").read_bytes()
            text_log = raw_log.decode("utf-8-sig")
            evidence["client_diagnostics"] = analysis.native_diagnostics(text_log)
            evidence["client_log_completeness"] = analysis.client_log_completeness(raw_log, evidence["samples"], instance)
        except (OSError, UnicodeError) as error:
            evidence["client_diagnostics"] = {"scanned": False, "unreviewed_native": [], "other_errors_requiring_contextual_review": [], "error": str(error)}
            evidence["client_log_completeness"] = {"passed": False, "errors": [str(error)]}
        actual = evidence.get("process", {})
        evidence["run_finish"] = {
            "schema": 1, "scope": PROBE_OFF_SCOPE, "root": str(root),
            "finished_at": evidence["finished_at"], "start_sha256": evidence["run_start_sha256"],
            "process": {"pid": actual.get("pid"), "created": actual.get("created")},
            "measurement_completed_at": evidence.get("measurement_completed_at"),
            "cleanup": evidence["cleanup"],
        }
        save(root / "run-finish.json", evidence["run_finish"], exclusive=True)
        save(root / "observation.json", evidence)
    result = assess_probe_off_observation(evidence, policy, (root / "latest.log").read_text(encoding="utf-8-sig") if (root / "latest.log").is_file() else "")
    save(root / "result.json", result, exclusive=True)
    if interrupt_error is not None:
        raise interrupt_error
    return evidence, result


def assess_probe_off_observation(evidence, policy, log_text):
    errors = []
    metrics = {metric: None for metric in analysis.METRICS}
    start, finish = evidence.get("run_start", {}), evidence.get("run_finish", {})
    try:
        if start.get("scope") != PROBE_OFF_SCOPE or finish.get("scope") != PROBE_OFF_SCOPE:
            errors.append("Invalid probe-off run receipt scope.")
        if start.get("root") != finish.get("root") or start.get("root") != evidence.get("capture_root"):
            errors.append("Probe-off receipt root mismatch.")
        if finish.get("start_sha256") != evidence.get("run_start_sha256"):
            errors.append("Probe-off finish receipt does not bind start receipt.")
        if analysis.process_key(finish["process"]) != analysis.process_key(evidence["process"]):
            errors.append("Probe-off finish receipt belongs to another JVM.")
        started, finished = instant(start["started_at"]), instant(finish["finished_at"])
        created, captured = instant(evidence["process"]["created"]), instant(evidence["process"]["captured_at"])
        launched = instant(evidence["launch"]["timestamp"])
        completed = instant(evidence["measurement_completed_at"])
        cleanup = instant(evidence["cleanup"]["timestamp"])
        if not started <= created <= launched <= captured <= completed <= cleanup <= finished:
            errors.append("Probe-off process/measurement times fall outside execution window.")
    except (KeyError, ValueError, TypeError, AttributeError):
        errors.append("Missing/invalid probe-off execution receipts.")

    if evidence.get("client_log_completeness", {}).get("passed") is not True:
        errors.append("Complete probe-off client log was not established.")
    diagnostics = evidence.get("client_diagnostics")
    if not isinstance(diagnostics, dict) or diagnostics.get("scanned") is not True:
        errors.append("Probe-off client log diagnostic scan unavailable.")
    else:
        unexpected = [row for row in diagnostics.get("unreviewed_native", []) if not DEFAULT_RAIL_ERROR_RE.fullmatch(row.get("text", ""))]
        default_rail = [row for row in diagnostics.get("unreviewed_native", []) if DEFAULT_RAIL_ERROR_RE.fullmatch(row.get("text", ""))]
        if unexpected:
            errors.append("Unexpected native/client errors in probe-off log.")
        if len(default_rail) != 1:
            errors.append("Expected exactly one static official default-rail diagnostic in probe-off startup.")

    for required in PROBE_OFF_REQUIRED_LINES:
        if required not in log_text:
            errors.append("Missing required MTR registration summary line: " + required)
    share_matches = SHARE_LINE_RE.findall(log_text)
    obj_matches = STREAMED_OBJ_RE.findall(log_text)
    if not share_matches or any(int(value) != 0 for value in share_matches[-1][3:]):
        errors.append("Missing or unsettled MTR memory sharing summary in probe-off log.")
    if not obj_matches or any(int(value) != 0 for value in obj_matches[-1][3:]):
        errors.append("Missing or unsettled MTR streamed OBJ summary in probe-off log.")

    try:
        process = evidence["process"]
        created = instant(process["created"])
        windows = evidence["windows"]
        native_end = instant(windows["startup"]["end"])
        warm_start, warm_end = map(instant, (windows["warmup"]["start"], windows["warmup"]["end"]))
        start_t, end_t = map(instant, (windows["steady"]["start"], windows["steady"]["end"]))
        completed_at = instant(evidence["measurement_completed_at"])
        if not end_t <= completed_at <= end_t + dt.timedelta(seconds=policy["maximum_sample_gap_seconds"]) or evidence.get("measurement_process_running") is not True:
            errors.append("Probe-off measurement endpoint was not confirmed.")
        if not created < native_end <= warm_start < warm_end == start_t < end_t:
            errors.append("Invalid probe-off phase ordering.")
        if abs((warm_end - warm_start).total_seconds() - policy["probe_off_post_load_warmup_seconds"]) > 0.05 or abs((end_t - start_t).total_seconds() - policy["probe_off_steady_seconds"]) > 0.05:
            errors.append("Probe-off phase durations differ from frozen policy.")
        if (native_end - created).total_seconds() > policy["startup_timeout_seconds"]:
            errors.append("Probe-off startup exceeded timeout.")
    except (KeyError, ValueError, TypeError, AttributeError):
        return {"passed": False, "errors": errors + ["Missing/invalid probe-off phase windows."], "metrics": metrics}

    samples = evidence.get("samples", [])
    startup, postload, steady = [], [], []
    previous = None
    for sample in samples:
        try:
            stamp = instant(sample["observed_at"])
            if previous is not None and stamp <= previous:
                errors.append("Probe-off sample timestamps do not strictly advance.")
            previous = stamp
            os_state = sample.get("os", {})
            if os_state.get("running") is not True:
                errors.append("Probe-off JVM unavailable during sampling.")
            for field in ("private_usage", "working_set", "peak_working_set_since_process_start"):
                if not analysis.finite(os_state.get(field), positive=True):
                    errors.append("Invalid probe-off OS memory: " + field)
            if stamp <= native_end:
                startup.append(sample)
            if warm_start <= stamp <= end_t:
                postload.append(sample)
                errors.extend(sample.get("errors", []))
                if sample.get("client_log_witness") is None:
                    errors.append("Missing postload probe-off log witness.")
            if start_t <= stamp <= end_t:
                steady.append(sample)
        except (KeyError, ValueError, TypeError, AttributeError):
            errors.append("Malformed probe-off sample.")

    for left, right in ((warm_start, start_t), (start_t, end_t)):
        phase_stamps = [left, *[instant(s["observed_at"]) for s in postload if left <= instant(s["observed_at"]) <= right], right]
        if len(phase_stamps) < 3 or any((b - a).total_seconds() > policy["maximum_sample_gap_seconds"] for a, b in zip(phase_stamps, phase_stamps[1:])):
            errors.append("Incomplete probe-off phase sampling coverage.")
    if not startup or not steady:
        errors.append("Probe-off startup or steady samples missing.")
    else:
        metrics.update(
            loading_ms=(native_end - created).total_seconds() * 1000,
            startup_peak_working_set_bytes=max(s["os"]["peak_working_set_since_process_start"] for s in startup),
            steady_private_bytes=statistics.median(s["os"]["private_usage"] for s in steady),
            steady_working_set_bytes=statistics.median(s["os"]["working_set"] for s in steady),
        )
    if evidence.get("status") != "complete" or evidence.get("cleanup", {}).get("exited") is not True:
        errors.append("Probe-off observation or cleanup incomplete.")
    return {
        "passed": not errors,
        "errors": errors,
        "metrics": metrics,
        "unavailable_metrics": sorted(metric for metric, value in metrics.items() if value is None),
        "phases": windows,
        "sample_count": len(samples),
        "attribution_limit": "No live observer installed in probe_off; static match only for known official transparent.png rail message.",
    }


def trial_raw_files(trial_dir):
    return exp.raw_files(trial_dir, excluded_root_files=TRIAL_INVENTORY_EXCLUSIONS)


def resolve_templates(templates_root, prefix, probe_off_template, base_policy):
    templates_root = Path(templates_root).resolve()
    descriptors = {}
    sampler_spec = None
    for role in analysis.ROLES:
        for mode in analysis.MODES:
            key = f"{role}_{mode}"
            plan_path = templates_root / f"{prefix}{role}-{mode}/packaged-client-plan.json"
            descriptor = exp.prepared_descriptor(plan_path, role, mode, base_policy)
            plan = read(plan_path)
            found_spec = sampler.spec_for_plan(plan)
            if found_spec is None:
                raise ValueError(f"Template {plan_path} lacks pinned Spark measurement mod.")
            if sampler_spec is None:
                sampler_spec = found_spec
            elif found_spec["jar_sha256"] != sampler_spec["jar_sha256"]:
                raise ValueError("Templates disagree on Spark measurement mod bytes.")
            descriptors[key] = descriptor
    exp.validate_groups(descriptors)
    probe_off = verify_probe_off_template(probe_off_template)
    return descriptors, sampler_spec, probe_off


def audit_single_trial(trial_dir, spec, descriptors, sampler_spec, policy, base_policy, experiment_started):
    trial_dir = Path(trial_dir).resolve(strict=True)
    summary = read(trial_dir / "trial-summary.json")
    if summary.get("spec") != spec:
        raise ValueError(f"Trial spec mismatch in {trial_dir}")
    exp.verify_raw_files(trial_dir, summary.get("files", []), excluded_root_files=TRIAL_INVENTORY_EXCLUSIONS)
    if spec["mode"] == "probe_off":
        evidence = read(trial_dir / "observation.json")
        prepared = read(trial_dir / "prepared-plan.json")
        if Path(prepared["instance"]).resolve() != trial_dir / "instance" or evidence.get("capture_root") != str(trial_dir):
            raise ValueError("Probe-off capture root mismatch.")
        if evidence.get("run_start") != read(trial_dir / "run-start.json") or evidence.get("run_finish") != read(trial_dir / "run-finish.json"):
            raise ValueError("Probe-off start/finish receipts differ.")
        if evidence.get("process") != read(trial_dir / "actual-process.json") or evidence.get("launch") != read(trial_dir / "launch.json"):
            raise ValueError("Probe-off process/launch receipts differ.")
        verify_process_identity(prepared, evidence["launch"], evidence["process"], evidence["process"]["arguments"])
        if evidence.get("samples") != exp.read_jsonl(trial_dir / "samples.jsonl"):
            raise ValueError("Probe-off samples differ from raw JSONL.")
        ref = evidence.get("native_log_stream")
        if not ref or ref.get("completion_read_failed"):
            raise ValueError("Probe-off rolling log capture incomplete.")
        stream_root = trial_dir / "native-log"
        receipt_path = (stream_root / ref["receipt"]).resolve(strict=True)
        if not receipt_path.is_relative_to(stream_root) or digest(receipt_path) != ref["receipt_sha256"]:
            raise ValueError("Probe-off rolling log receipt mismatch.")
        if native_log_stream.verify_capture(stream_root, receipt_path) != (trial_dir / "latest.log").read_bytes():
            raise ValueError("Probe-off log segments do not reconstruct latest.log.")
        context = read(stream_root / "context.json")
        if (digest(stream_root / "context.json") != ref["context_sha256"]
                or context["process"]["pid"] != evidence["process"]["pid"]
                or instant(context["process"]["created"]) != instant(evidence["process"]["created"])):
            raise ValueError("Probe-off rolling log identity differs from trial JVM.")
        if experiment_started is not None and instant(experiment_started) > instant(evidence["run_start"]["started_at"]):
            raise ValueError("Probe-off trial predates experiment start.")
        result = assess_probe_off_observation(evidence, policy, (trial_dir / "latest.log").read_text(encoding="utf-8-sig"))
        spark_report = None
        idle_report = None
    else:
        key = f"{spec['role']}_{spec['mode']}"
        descriptor = descriptors[key]
        evidence, result = exp.audit_observation(
            trial_dir, base_policy, descriptor["scenario"], spec["mode"],
            expected_trial=spec, experiment_started=experiment_started,
        )
        exp.verify_observed_identity(trial_dir, descriptor)
        if spec["mode"] == "plain":
            idle_report = sampler.verify_idle(trial_dir / "instance", sampler_spec)
            if read(trial_dir / "spark-idle.json") != idle_report:
                raise ValueError("Saved spark-idle.json differs from independent idle check.")
            spark_report = None
        else:
            prepared = read(trial_dir / "prepared-plan.json")
            spark_report = sampler.audit(trial_dir, prepared, evidence, sampler_spec)
            idle_report = None
    if result != read(trial_dir / "result.json"):
        raise ValueError(f"Saved result.json differs from independent re-evaluation in {trial_dir}")
    return {"evidence": evidence, "result": result, "spark": spark_report, "idle": idle_report}


def run_verification(args):
    policy = load_policy(args.policy)
    base_policy = read(DEFAULT_EXP_POLICY)
    descriptors, sampler_spec, probe_off_info = resolve_templates(
        args.templates_root, args.template_prefix, args.probe_off_template, base_policy
    )
    host = exp.environment()
    output = args.output.resolve()
    plan_path = output / "plan.json"
    exec_path = output / "execution.json"
    start_path = output / "execution-start.json"

    if args.resume:
        plan = read(plan_path)
        state = read(exec_path)
        execution_start = read(start_path)
        if plan.get("scope") != policy["scope"] or plan.get("policy") != policy:
            raise ValueError("Existing run plan differs from practical verification policy.")
        if state.get("plan_sha256") != digest(plan_path) or execution_start["plan_sha256"] != state["plan_sha256"]:
            raise ValueError("Existing execution receipt disagrees with frozen plan.")
        existing_trials = {item["id"]: item for item in state.get("trials", [])}
        state["status"] = "running"
    else:
        output.mkdir(parents=True, exist_ok=False)
        plan = {
            "schema": 1, "scope": policy["scope"], "created_at": now(),
            "policy": policy, "policy_file": exp.fingerprint(args.policy),
            "sampler_spec": sampler_spec, "probe_off_template": probe_off_info,
            "templates": {key: {"prepared_plan": desc["prepared_plan"], "qualification_key": desc["qualification_key"], "artifact_sha256": desc["artifact_sha256"]}
                          for key, desc in descriptors.items()},
            "environment": host,
        }
        save(plan_path, plan, exclusive=True)
        started_at = now()
        plan_sha = digest(plan_path)
        execution_start = {"schema": 1, "scope": policy["scope"], "root": str(output), "plan_sha256": plan_sha, "started_at": started_at}
        save(start_path, execution_start, exclusive=True)
        state = {"schema": 1, "status": "running", "started_at": started_at, "plan_sha256": plan_sha, "trials": []}
        save(exec_path, state, exclusive=True)
        existing_trials = {}

    ordered_trials = []
    try:
        for spec in policy["schedule"]:
            trial_dir = output / spec["id"]
            if args.resume and trial_dir.exists():
                try:
                    audited = audit_single_trial(
                        trial_dir, spec, descriptors, sampler_spec, policy, base_policy, execution_start["started_at"]
                    )
                    if audited["result"]["passed"]:
                        entry = existing_trials.get(spec["id"], {
                            **spec, "status": "complete", "started_at": audited["evidence"]["started_at"],
                            "finished_at": audited["evidence"]["finished_at"],
                        })
                        entry.update(status="complete", result=audited["result"], files=trial_raw_files(trial_dir))
                        ordered_trials.append(entry)
                        print(f"Resumed passed trial {spec['id']}", flush=True)
                        continue
                except Exception as error:
                    failed_entry = existing_trials.get(spec["id"], {**spec, "status": "failed"})
                    failed_entry.update(status="failed", error=f"{type(error).__name__}: {error}")
                    ordered_trials.append(failed_entry)
                    print(f"Preserving failed existing trial {spec['id']}: {error}", flush=True)
                    continue
                failed_entry = existing_trials.get(spec["id"], {**spec, "status": "failed"})
                failed_entry.update(status="failed", result=audited["result"])
                ordered_trials.append(failed_entry)
                print(f"Preserving unqualified existing trial {spec['id']}", flush=True)
                continue

            print(f"Running {spec['id']} ({spec['role']} / {spec['mode']})", flush=True)
            trial_started = now()
            trial_record = {**spec, "status": "running", "started_at": trial_started}
            state["trials"] = ordered_trials + [trial_record]
            save(exec_path, state)

            if spec["mode"] == "plain":
                descriptor = descriptors[f"{spec['role']}_plain"]
                evidence, result = exp.collect_trial(descriptor, base_policy, trial_dir, trial_spec=spec)
                try:
                    idle = sampler.verify_idle(trial_dir / "instance", sampler_spec)
                    save(trial_dir / "spark-idle.json", idle, exclusive=True)
                except Exception as error:
                    idle = {"verified_idle": False, "error": f"{type(error).__name__}: {error}"}
                    save(trial_dir / "spark-idle.json", idle)
                    result["passed"] = False
                    result["errors"].append(idle["error"])
                    save(trial_dir / "result.json", result)
                spark_report = None
            elif spec["mode"] == "profile":
                descriptor = descriptors[f"{spec['role']}_profile"]
                evidence, result, spark_report = collect_profile_spark_trial(
                    descriptor, base_policy, sampler_spec, trial_dir, trial_spec=spec
                )
            elif spec["mode"] == "probe_off":
                evidence, result = collect_probe_off_trial(
                    args.probe_off_template, policy, trial_dir, trial_spec=spec
                )
                spark_report = None
            else:
                raise ValueError("Unsupported trial mode: " + spec["mode"])

            files = trial_raw_files(trial_dir)
            save(trial_dir / "trial-summary.json", {
                "schema": 1, "spec": spec, "status": "complete" if result["passed"] else "failed",
                "result": result, "spark_verified": spark_report.get("verified") if spark_report else None,
                "files": files,
            }, exclusive=True)
            trial_record.update(
                status="complete" if result["passed"] else "failed",
                finished_at=now(),
                result=result,
                files=files,
            )
            ordered_trials.append(trial_record)
            state["trials"] = ordered_trials
            save(exec_path, state)
            if evidence.get("cleanup", {}).get("exited") is not True:
                raise RuntimeError(f"Trial {spec['id']} JVM cleanup failed; halting sequential execution.")
        state["status"] = "complete" if all(item["status"] == "complete" for item in ordered_trials) else "failed"
    except BaseException as error:
        state.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        state["finished_at"] = now()
        save(exec_path, state)
    analysis_report = audit_run(
        output, policy_path=args.policy, templates_root=args.templates_root,
        template_prefix=args.template_prefix, probe_off_template=args.probe_off_template
    )
    save(output / "analysis.json", analysis_report, exclusive=True)
    return 0 if analysis_report["all_trials_passed"] else 2


def compare_arms(pairs, metrics):
    summary = {}
    for metric in metrics:
        before = [a[metric] for a, _ in pairs]
        after = [b[metric] for _, b in pairs]
        if any(value is None for value in before + after):
            summary[metric] = {"available": False}
            continue
        abs_deltas = [b - a for a, b in zip(before, after)]
        pct_deltas = [100.0 * (b / a - 1.0) if a > 0 else None for a, b in zip(before, after)]
        pct_ok = all(value is not None for value in pct_deltas)
        summary[metric] = {
            "available": True,
            "pairs": len(pairs),
            "baseline_values": before,
            "candidate_values": after,
            "absolute_deltas": abs_deltas,
            "percent_deltas": pct_deltas if pct_ok else None,
            "median_absolute_delta": statistics.median(abs_deltas),
            "median_percent_delta": statistics.median(pct_deltas) if pct_ok else None,
            "min_percent_delta": min(pct_deltas) if pct_ok else None,
            "max_percent_delta": max(pct_deltas) if pct_ok else None,
        }
    return summary


def spark_thread_summary(spark_report):
    if not spark_report:
        return None
    out = {}
    for bucket in ("thread_reports", "optional_thread_reports"):
        for thread_name, report in spark_report.get(bucket, {}).items():
            out[thread_name] = {
                "root_sample_weight": report["root_sample_weight"],
                "metadata_duration_ms": report["metadata"]["metadata_duration_ms"],
                "interval_ms": report["metadata"]["interval_ms"],
                "negative_residual_count": len(report["negative_self_residuals"]),
                "top_self": [
                    {"class": row["class"], "method": row["method"], "self_percent": round(row["self_percent"], 2)}
                    for row in report["ranked_self"][:8]
                ],
                "top_inclusive": [
                    {"class": row["class"], "method": row["method"], "inclusive_percent": round(row["inclusive_percent"], 2)}
                    for row in report["ranked_inclusive"][:8]
                ],
                "source_self_weights": report["source_self_weights"][:8],
            }
    return out


def audit_run(run_dir, *, policy_path=DEFAULT_POLICY, templates_root=DEFAULT_TEMPLATES_ROOT,
              template_prefix=DEFAULT_TEMPLATE_PREFIX, probe_off_template=DEFAULT_PROBE_OFF_TEMPLATE):
    run_dir = Path(run_dir).resolve(strict=True)
    plan = read(run_dir / "plan.json")
    state = read(run_dir / "execution.json")
    execution_start = read(run_dir / "execution-start.json")
    policy = load_policy(policy_path)
    base_policy = read(DEFAULT_EXP_POLICY)
    descriptors, sampler_spec, _ = resolve_templates(templates_root, template_prefix, probe_off_template, base_policy)
    errors = []
    if plan.get("policy") != policy or state.get("plan_sha256") != digest(run_dir / "plan.json"):
        errors.append("Plan or execution receipt differs from practical verification policy.")
    if execution_start["plan_sha256"] != state["plan_sha256"]:
        errors.append("Execution start receipt differs from plan SHA-256.")

    audited = {}
    process_ids = set()
    prev_finish = None
    passed_count = 0
    for spec in policy["schedule"]:
        tid = spec["id"]
        trial_dir = run_dir / tid
        if not trial_dir.is_dir():
            errors.append(f"Missing trial directory: {tid}")
            continue
        try:
            item = audit_single_trial(
                trial_dir, spec, descriptors, sampler_spec, policy, base_policy, execution_start["started_at"]
            )
            ev = item["evidence"]
            pkey = analysis.process_key(ev["process"])
            if pkey in process_ids:
                errors.append(f"Duplicate JVM creation identity in {tid}")
            process_ids.add(pkey)
            raw_start = instant(ev["run_start"]["started_at"])
            raw_finish = instant(ev["run_finish"]["finished_at"])
            if prev_finish is not None and raw_start < prev_finish:
                errors.append(f"Trial window overlaps previous trial: {tid}")
            prev_finish = raw_finish
            audited[tid] = item
            if item["result"]["passed"]:
                passed_count += 1
            else:
                errors.append(f"Trial failed qualification checks: {tid}")
        except Exception as error:
            errors.append(f"Audit error in {tid}: {type(error).__name__}: {error}")

    common_metrics = ("steady_private_bytes", "steady_working_set_bytes", "steady_heap_bytes",
                      "loading_ms", "startup_peak_working_set_bytes", "startup_peak_heap_bytes")
    profile_metrics = ("frame_p99_ms", "frame_max_ms", "gc_count", "gc_pause_total_ms",
                       "gc_pause_max_ms", "full_gc_count", "full_gc_pause_max_ms")

    comparisons = {}
    if all(spec["id"] in audited and audited[spec["id"]]["result"]["passed"] for spec in policy["schedule"]):
        m = {tid: item["result"]["metrics"] for tid, item in audited.items()}
        ab_plain = [(m["01-ab-plain-baseline"], m["01-ab-plain-candidate"]),
                    (m["02-ba-plain-baseline"], m["02-ba-plain-candidate"])]
        ab_profile = [(m["03-ab-profile-baseline"], m["03-ab-profile-candidate"]),
                      (m["04-ba-profile-baseline"], m["04-ba-profile-candidate"])]
        aa_plain = [(m["05-aa-plain-a"], m["05-aa-plain-b"])]
        inst_baseline = [
            ({"steady_private_bytes": statistics.mean([m["01-ab-plain-baseline"]["steady_private_bytes"], m["02-ba-plain-baseline"]["steady_private_bytes"]]),
              "steady_working_set_bytes": statistics.mean([m["01-ab-plain-baseline"]["steady_working_set_bytes"], m["02-ba-plain-baseline"]["steady_working_set_bytes"]]),
              "steady_heap_bytes": statistics.mean([m["01-ab-plain-baseline"]["steady_heap_bytes"], m["02-ba-plain-baseline"]["steady_heap_bytes"]]),
              "loading_ms": statistics.mean([m["01-ab-plain-baseline"]["loading_ms"], m["02-ba-plain-baseline"]["loading_ms"]])},
             {"steady_private_bytes": statistics.mean([m["03-ab-profile-baseline"]["steady_private_bytes"], m["04-ba-profile-baseline"]["steady_private_bytes"]]),
              "steady_working_set_bytes": statistics.mean([m["03-ab-profile-baseline"]["steady_working_set_bytes"], m["04-ba-profile-baseline"]["steady_working_set_bytes"]]),
              "steady_heap_bytes": statistics.mean([m["03-ab-profile-baseline"]["steady_heap_bytes"], m["04-ba-profile-baseline"]["steady_heap_bytes"]]),
              "loading_ms": statistics.mean([m["03-ab-profile-baseline"]["loading_ms"], m["04-ba-profile-baseline"]["loading_ms"]])})
        ]
        inst_candidate = [
            ({"steady_private_bytes": statistics.mean([m["01-ab-plain-candidate"]["steady_private_bytes"], m["02-ba-plain-candidate"]["steady_private_bytes"]]),
              "steady_working_set_bytes": statistics.mean([m["01-ab-plain-candidate"]["steady_working_set_bytes"], m["02-ba-plain-candidate"]["steady_working_set_bytes"]]),
              "steady_heap_bytes": statistics.mean([m["01-ab-plain-candidate"]["steady_heap_bytes"], m["02-ba-plain-candidate"]["steady_heap_bytes"]]),
              "loading_ms": statistics.mean([m["01-ab-plain-candidate"]["loading_ms"], m["02-ba-plain-candidate"]["loading_ms"]])},
             {"steady_private_bytes": statistics.mean([m["03-ab-profile-candidate"]["steady_private_bytes"], m["04-ba-profile-candidate"]["steady_private_bytes"]]),
              "steady_working_set_bytes": statistics.mean([m["03-ab-profile-candidate"]["steady_working_set_bytes"], m["04-ba-profile-candidate"]["steady_working_set_bytes"]]),
              "steady_heap_bytes": statistics.mean([m["03-ab-profile-candidate"]["steady_heap_bytes"], m["04-ba-profile-candidate"]["steady_heap_bytes"]]),
              "loading_ms": statistics.mean([m["03-ab-profile-candidate"]["loading_ms"], m["04-ba-profile-candidate"]["loading_ms"]])})
        ]
        probe_off_vs_plain = [
            ({"steady_private_bytes": statistics.mean([m["06-probe-off-01"]["steady_private_bytes"], m["06-probe-off-02"]["steady_private_bytes"]]),
              "steady_working_set_bytes": statistics.mean([m["06-probe-off-01"]["steady_working_set_bytes"], m["06-probe-off-02"]["steady_working_set_bytes"]]),
              "startup_peak_working_set_bytes": statistics.mean([m["06-probe-off-01"]["startup_peak_working_set_bytes"], m["06-probe-off-02"]["startup_peak_working_set_bytes"]]),
              "loading_ms": statistics.mean([m["06-probe-off-01"]["loading_ms"], m["06-probe-off-02"]["loading_ms"]])},
             {"steady_private_bytes": statistics.mean([m["01-ab-plain-candidate"]["steady_private_bytes"], m["02-ba-plain-candidate"]["steady_private_bytes"]]),
              "steady_working_set_bytes": statistics.mean([m["01-ab-plain-candidate"]["steady_working_set_bytes"], m["02-ba-plain-candidate"]["steady_working_set_bytes"]]),
              "startup_peak_working_set_bytes": statistics.mean([m["01-ab-plain-candidate"]["startup_peak_working_set_bytes"], m["02-ba-plain-candidate"]["startup_peak_working_set_bytes"]]),
              "loading_ms": statistics.mean([m["01-ab-plain-candidate"]["loading_ms"], m["02-ba-plain-candidate"]["loading_ms"]])})
        ]
        comparisons = {
            "ab_plain": compare_arms(ab_plain, common_metrics),
            "ab_profile_spark": compare_arms(ab_profile, common_metrics + profile_metrics),
            "ab_combined_common": compare_arms(ab_plain + ab_profile, common_metrics),
            "aa_plain_noise": compare_arms(aa_plain, ("steady_private_bytes", "steady_working_set_bytes", "steady_heap_bytes", "loading_ms")),
            "instrumentation_overhead_baseline": compare_arms(inst_baseline, ("steady_private_bytes", "steady_working_set_bytes", "steady_heap_bytes", "loading_ms")),
            "instrumentation_overhead_candidate": compare_arms(inst_candidate, ("steady_private_bytes", "steady_working_set_bytes", "steady_heap_bytes", "loading_ms")),
            "observer_and_idle_spark_overhead": compare_arms(probe_off_vs_plain, ("steady_private_bytes", "steady_working_set_bytes", "startup_peak_working_set_bytes", "loading_ms")),
        }

    trials_out = {}
    for tid, item in audited.items():
        trials_out[tid] = {
            "passed": item["result"]["passed"],
            "errors": item["result"]["errors"],
            "metrics": item["result"]["metrics"],
            "process": {"pid": item["evidence"]["process"]["pid"], "created": item["evidence"]["process"]["created"]},
            "windows": item["evidence"]["windows"],
            "spark": spark_thread_summary(item["spark"]),
        }

    return {
        "schema": 1,
        "scope": policy["scope"],
        "audited_at": now(),
        "full_48_trial_protocol_satisfied": False,
        "scheduled_trials": len(policy["schedule"]),
        "passed_trials": passed_count,
        "unique_jvms": len(process_ids),
        "all_trials_passed": (passed_count == len(policy["schedule"]) and not errors),
        "errors": errors,
        "budgets": policy["budgets"],
        "comparisons": comparisons,
        "trials": trials_out,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    p_prep = sub.add_parser("prepare-probe-off")
    p_prep.add_argument("--output", type=Path, default=DEFAULT_PROBE_OFF_TEMPLATE)
    p_prep.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p_prep.add_argument("--companion", type=Path, default=DEFAULT_COMPANION_048)
    p_prep.add_argument("--catalogue", type=Path, default=DEFAULT_CATALOGUE)
    p_prep.add_argument("--world", default="Vehicle Acceptance 1_21_1")
    p_prep.add_argument("--username", default="VehicleTest")

    p_run = sub.add_parser("run")
    p_run.add_argument("--output", type=Path, required=True)
    p_run.add_argument("--resume", action="store_true")
    p_run.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p_run.add_argument("--templates-root", type=Path, default=DEFAULT_TEMPLATES_ROOT)
    p_run.add_argument("--template-prefix", default=DEFAULT_TEMPLATE_PREFIX)
    p_run.add_argument("--probe-off-template", type=Path, default=DEFAULT_PROBE_OFF_TEMPLATE)

    p_audit = sub.add_parser("audit")
    p_audit.add_argument("--run-dir", type=Path, required=True)
    p_audit.add_argument("--output", type=Path, required=True)
    p_audit.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p_audit.add_argument("--templates-root", type=Path, default=DEFAULT_TEMPLATES_ROOT)
    p_audit.add_argument("--template-prefix", default=DEFAULT_TEMPLATE_PREFIX)
    p_audit.add_argument("--probe-off-template", type=Path, default=DEFAULT_PROBE_OFF_TEMPLATE)

    args = parser.parse_args()
    if args.action == "prepare-probe-off":
        info = prepare_probe_off(
            args.output, source=args.source, companion=args.companion,
            catalogue=args.catalogue, world=args.world, username=args.username,
        )
        print(json.dumps(info, indent=2), flush=True)
        return 0
    if args.action == "run":
        return run_verification(args)
    report = audit_run(
        args.run_dir, policy_path=args.policy, templates_root=args.templates_root,
        template_prefix=args.template_prefix, probe_off_template=args.probe_off_template,
    )
    save(args.output, report, exclusive=True)
    print(json.dumps({"all_trials_passed": report["all_trials_passed"], "passed_trials": report["passed_trials"]}, indent=2), flush=True)
    return 0 if report["all_trials_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
