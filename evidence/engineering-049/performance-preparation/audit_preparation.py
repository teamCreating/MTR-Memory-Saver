"""Independently recheck prepared templates without launching or mutating a client."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import client_experiment as experiment
import packaged_client as packaged
from client_experiment_analysis import schedule, validate_policy


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit():
    receipt = read(BASE / "preparation.execution.json")
    frozen = read(BASE / "descriptors.json")
    policy = read(BASE / "source/config/client-experiment.json")
    validate_policy(policy)
    require(receipt["passed"] is True and receipt["launched_game_jvms"] == 0,
            "Original preparation did not finish without game launches")
    require(sha(BASE / "prepare_templates.py") == receipt["runner_sha256"], "Preparation runner changed")
    require(len(receipt["commands"]) == len(frozen), "Incomplete preparation command ledger")
    sources = {}
    for name, digest in receipt["source_sha256"].items():
        require(sha(BASE / "source" / name) == digest, "Frozen source changed: " + name)
        sources[name] = {"recorded_sha256": digest, "current_sha256": sha(ROOT / name)}
        require(sources[name]["current_sha256"] == digest, "Current preparation source changed: " + name)
    require(sha(ROOT / "config/client-experiment.json") == sha(BASE / "source/config/client-experiment.json"),
            "Current policy differs from frozen policy")
    current = {}
    groups = []
    for command in receipt["commands"]:
        key = command["group"]
        descriptor = frozen[key]
        instance = Path(command["instance"])
        plan = instance / "packaged-client-plan.json"
        require(command["exit_code"] == 0 and command["verified_unlaunched"] is True,
                "Preparation command failed or was already launched: " + key)
        require(not (instance / "packaged-client-launch.json").exists(), "Template has been launched: " + key)
        require(not (instance / "logs").exists(), "Template contains execution logs: " + key)
        require(sha(plan) == command["plan_sha256"] == sha(BASE / "plans" / (key + ".json")),
                "Plan does not match original receipt/sealed copy: " + key)
        current[key] = experiment.prepared_descriptor(plan, descriptor["role"], descriptor["instrumentation"], policy)
        require(current[key] == descriptor, "Independent descriptor differs: " + key)
        for path in (instance / ".prepared-controls").iterdir():
            require(sha(path) == sha(BASE / "plans" / key / ".prepared-controls" / path.name),
                    "Sealed control differs: " + str(path))
        plan_data = read(plan)
        require(len(plan_data["packs"]) == len(current[key]["controls"]["packs"]),
                "Pack control count mismatch: " + key)
        mods = []
        for item in plan_data["mods"]:
            if item["role"] in ("companion", "observer"):
                sealed = BASE / "artifacts" / item["filename"]
                require(sha(sealed) == item["sha256"], "Sealed artifact differs: " + str(sealed))
                mods.append({"role": item["role"], "filename": item["filename"], "sha256": item["sha256"]})
        groups.append({"group": key, "plan_sha256": sha(plan), "controls_sha256": command["controls_sha256"],
                       "packs": len(plan_data["packs"]), "mods": mods,
                       "qualification_key": descriptor["qualification_key"], "unlaunched": True})
        print(json.dumps({"verified": key, "unlaunched": True}), flush=True)
    experiment.validate_groups(current)
    source_context = read(BASE / "preparation-context.json")
    source = Path(source_context["source"])
    actual_world = packaged.inventory(source / "saves" / source_context["world_name"])
    require(actual_world == read(BASE / "source-world-inventory.json"), "Source world changed since preparation")
    require(experiment.canonical_sha(actual_world) == source_context["source_world_sha256"], "Source world digest differs")
    for name, field in (("vehicle-test-instance.json", "source_marker_sha256"),
                        ("options.txt", "source_options_sha256"), ("usercache.json", "source_usercache_sha256")):
        require(sha(source / name) == source_context[field], "Source input changed: " + name)
    original_environment = read(BASE / "environment.json")
    current_environment = experiment.environment()
    return {"started_from_receipt": receipt["started"], "passed": True,
            "scope": "Preparation integrity only; no client was launched or qualified by this audit.",
            "groups": groups, "sources": sources,
            "source_world_unchanged": True, "policy_trial_jvms": len(schedule(policy)),
            "current_host_snapshot": current_environment,
            "original_host_snapshot_time": original_environment["timestamp"],
            "hardware_power_identity_unchanged": current_environment == original_environment["observed"],
            "background_workload": "Original process counts are historical observations, not current controls. Qualification and every trial must independently freeze/recheck host identity and retain all noise/failures.",
            "pending": ["Four actual current qualification JVMs", "Frozen 48-trial plan after qualifications",
                        "48 scheduled fresh-JVM trials and independent analysis", "Observer-off overhead calibration",
                        "New artifact full-pack/reload/gameplay/endurance acceptance", "NF265 separate full-client experiment"],
            "performance_accepted": False}


if __name__ == "__main__":
    output = Path(sys.argv[1]).resolve()
    require(not output.exists(), "Do not overwrite an audit receipt")
    result = {"started": datetime.now(timezone.utc).isoformat(), "source_sha256": sha(Path(__file__)),
              "command": [sys.executable, str(Path(__file__).resolve()), str(output)], "passed": False}
    try:
        result.update(audit())
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        result["ended"] = datetime.now(timezone.utc).isoformat()
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
