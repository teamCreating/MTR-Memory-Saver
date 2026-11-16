"""Capture actual read-only machine/background context and validate a scenario."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
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
        raise ValueError("Do not overwrite actual preparation context")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


started = now()
environment = client_experiment.environment()
write(BASE / "environment.json", {"timestamp": now(), "tool_sha256": sha(Path(__file__)),
    "environment_consumer_sha256": sha(ROOT / "tools/client_experiment.py"), "observed": environment})
command = ["pwsh", "-NoProfile", "-Command", "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
    "$prepOperatingSystem=Get-CimInstance Win32_OperatingSystem; "
    "$prepPower=Get-CimInstance -Namespace root/cimv2/power -ClassName Win32_PowerPlan | Where-Object IsActive; "
    "$prepProcesses=Get-Process | Group-Object ProcessName | ForEach-Object { "
    "[ordered]@{name=$_.Name;count=$_.Count;workingSetBytes=[long](($_.Group | Measure-Object WorkingSet64 -Sum).Sum)}}; "
    "[ordered]@{windows=[ordered]@{caption=$prepOperatingSystem.Caption;version=$prepOperatingSystem.Version;"
    "build=$prepOperatingSystem.BuildNumber;architecture=$prepOperatingSystem.OSArchitecture;"
    "freePhysicalMemoryKiB=[long]$prepOperatingSystem.FreePhysicalMemory}; "
    "power=@($prepPower | Select-Object ElementName,InstanceID);"
    "backgroundProcesses=@($prepProcesses | Sort-Object name)} | ConvertTo-Json -Depth 6 -Compress"]
receipt = {"started": now(), "command": command, "cwd": str(ROOT), "source_sha256": sha(Path(__file__))}
with (BASE / "machine-context.stdout.log").open("wb") as stdout, (BASE / "machine-context.stderr.log").open("wb") as stderr:
    process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
    receipt["pid"] = process.pid
    receipt["exit_code"] = process.wait()
receipt["ended"] = now()
write(BASE / "machine-context.execution.json", receipt)
if receipt["exit_code"] != 0:
    raise ValueError("Actual machine context query failed")
machine = json.loads((BASE / "machine-context.stdout.log").read_text(encoding="utf-8-sig"))
write(BASE / "machine-context.json", machine)
policy = json.loads((ROOT / "config/client-experiment.json").read_text(encoding="utf-8-sig"))
hardware = environment["hardware"]
cpu = "; ".join(item["Name"] for item in hardware["cpus"])
gpu = "; ".join(item["Name"] + " (driver " + item["DriverVersion"] + ")" for item in hardware["gpus"])
power = "; ".join(item["ElementName"] + " " + item["InstanceID"] for item in machine["power"])
processes = ", ".join(item["name"] + "×" + str(item["count"]) for item in machine["backgroundProcesses"]
                      if item["name"].lower() in {"codex", "devenv", "msedge", "chrome", "discord", "java", "code", "explorer"})
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
        "power_mode": power,
        "background_workload": "Observed concurrent applications: " + processes + ". User work and other agents remain active; "
            "this is not a quiet dedicated benchmark machine. Background process and available-memory observations are a timestamped snapshot, "
            "not a guarantee that later trial loads are identical. No user process or power setting was changed."},
    "warmup": {"duration_seconds": policy["warmup_seconds"], "description": "After native registration and work settlement, "
               "keep the declared stationary unpaused camera for the policy warm-up, then observe the same saved route train for the measurement window. "
               "Fresh JVM and immutable copied world per qualification/trial; OS cache is warm and uncontrolled."}}
client_experiment.scenario_from_controls({"context": {"declarations": scenario}})
write(BASE / "scenario.json", scenario)
write(BASE / "context-assessment.json", {"started": started, "ended": now(), "passed": True,
    "source_sha256": sha(Path(__file__)), "scenario_sha256": sha(BASE / "scenario.json"),
    "policy_sha256": sha(ROOT / "config/client-experiment.json"), "policy_pairs": policy["pairs"],
    "planned_independent_trial_jvms": policy["pairs"] * 2 * 2 * 2,
    "schema_validation": "Existing client_experiment.scenario_from_controls accepted the exact current schema.",
    "limits": "Actual read-only machine snapshot and declared scenario only; no template launch, qualification or performance claim."})
print(json.dumps({"scenario_valid": True, "active_power_scheme": environment["active_power_scheme"],
                  "background_applications": processes, "trial_jvms": policy["pairs"] * 8}))
