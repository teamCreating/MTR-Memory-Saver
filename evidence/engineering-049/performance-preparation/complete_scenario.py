"""Complete declarations from preserved hardware context and supported powercfg reads."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import client_experiment


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    if path.exists():
        raise ValueError("Do not overwrite scenario or power evidence")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


environment = json.loads((BASE / "environment.json").read_text(encoding="utf-8"))["observed"]
machine = json.loads((BASE / "machine-context.json").read_text(encoding="utf-8"))
receipts = []
outputs = {}
for action in ("/getactivescheme", "/aliases"):
    command = ["powercfg", action]
    receipt = {"command": command, "started": now(), "cwd": str(ROOT)}
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    receipt["pid"] = process.pid
    stdout, stderr = process.communicate()
    receipt.update(ended=now(), exit_code=process.returncode)
    name = action.lstrip("/")
    (BASE / ("power-" + name + ".stdout.log")).write_bytes(stdout)
    (BASE / ("power-" + name + ".stderr.log")).write_bytes(stderr)
    receipt.update(stdout_sha256=hashlib.sha256(stdout).hexdigest(), stderr_sha256=hashlib.sha256(stderr).hexdigest())
    receipts.append(receipt)
    outputs[action] = stdout
    if process.returncode != 0:
        raise ValueError("Supported read-only powercfg query failed")
guid, = re.findall(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", outputs["/getactivescheme"])
guid = guid.decode("ascii").lower()
if guid != environment["active_power_scheme"]:
    raise ValueError("Active power scheme changed between actual context observations")
aliases = re.findall(rb"([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\s+(\S+)", outputs["/aliases"])
alias, = [name.decode("ascii") for identifier, name in aliases if identifier.decode("ascii").lower() == guid]
write(BASE / "power-context.json", {"timestamp": now(), "source_sha256": sha(Path(__file__)),
    "active_scheme_guid": guid, "actual_alias": alias, "commands": receipts,
    "cim_friendly_name_status": "unavailable: original remote-session access failure retained in machine-context.stderr.log"})
hardware = environment["hardware"]
cpu = "; ".join(item["Name"] for item in hardware["cpus"])
gpu = "; ".join(item["Name"] + " (driver " + item["DriverVersion"] + ")" for item in hardware["gpus"])
processes = ", ".join(item["name"] + "×" + str(item["count"]) for item in machine["backgroundProcesses"]
                      if item["name"].lower() in {"codex", "devenv", "msedge", "chrome", "discord", "java", "code", "explorer"})
policy = json.loads((ROOT / "config/client-experiment.json").read_text(encoding="utf-8-sig"))
scenario = {"schema": 1, "scenario_name": "official-nf248-native-catalogue-station-a-background-workload",
    "expected_registration": {"declarations": 1092, "distinct_ids": 1091},
    "world_name": "Vehicle Acceptance 1_21_1",
    "camera": {"dimension": "minecraft:overworld", "player": {"x": 38.5, "y": 4.0, "z": 15.5, "yaw": -180.0, "pitch": 0.0},
               "maximum_position_error": 0.1, "maximum_angle_error": 0.5},
    "route": {"description": "Observe the same native train on the saved A/B acceptance route from station A. "
              "Require that route identity, actual unpaused train state and same-train displacement; camera declarations alone are insufficient.",
              "route_ids": [1634058583976595067], "vehicle_ids": []},
    "cache_policy": "fresh_jvm_warm_os_cache",
    "observation": {"require_world": True, "require_unpaused": True, "require_train": True, "minimum_train_displacement": 0.01},
    "machine_context": {"hardware": cpu + "; RAM " + str(hardware["system"]["ram"]) + " bytes; GPU " + gpu,
        "windows": machine["windows"]["caption"] + " " + machine["windows"]["version"] + " build " + machine["windows"]["build"],
        "power_mode": "Observed powercfg alias " + alias + " (" + guid + "). CIM friendly-name read is unavailable; no scheme was changed.",
        "background_workload": "Observed concurrent applications: " + processes + ". User work and other agents remain active; "
            "this is not a quiet dedicated benchmark machine. Background process and available-memory observations are a timestamped snapshot, "
            "not a guarantee that later trial loads are identical. No user process or power setting was changed."},
    "warmup": {"duration_seconds": policy["warmup_seconds"], "description": "After native registration and work settlement, "
               "keep the declared stationary unpaused camera for the policy warm-up, then observe the same saved route train for the measurement window. "
               "Fresh JVM and immutable copied world per qualification/trial; OS cache is warm and uncontrolled."}}
client_experiment.scenario_from_controls({"context": {"declarations": scenario}})
write(BASE / "scenario.json", scenario)
write(BASE / "context-assessment.json", {"timestamp": now(), "passed": True,
    "source_sha256": sha(Path(__file__)), "scenario_sha256": sha(BASE / "scenario.json"),
    "policy_sha256": sha(ROOT / "config/client-experiment.json"), "policy_pairs": policy["pairs"],
    "planned_independent_trial_jvms": policy["pairs"] * 8,
    "schema_validation": "Existing client_experiment.scenario_from_controls accepted the exact current schema.",
    "initial_attempt": {"passed": False, "source": "capture_context.py", "reason": "CIM power friendly-name access failed; empty power declaration was strictly rejected."},
    "limits": "Read-only hardware/background snapshot and declared scenario only; no template launch, qualification or performance claim."})
print(json.dumps({"scenario_valid": True, "actual_power_alias": alias, "background_applications": processes,
                  "trial_jvms": policy["pairs"] * 8}))
