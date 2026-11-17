"""Unit-test factory: exercise real stream logic without real loader dependencies."""
import json
from pathlib import Path
import native_log_stream as logs


def header(instance):
    return "[synthetic timestamp] [main/INFO] [cpw.mods.modlauncher.Launcher/MODLAUNCHER]: ModLauncher running: args [--gameDir, "+str(instance)+"]\n"


def fixture_stream(instance, plan, launch, output, process, *, prefix_witness=None, declared_instance=None):
    instance = Path(instance)
    plan_path, launch_path = instance / "packaged-client-plan.json", instance / "packaged-client-launch.json"
    context = {"schema": 1, "instance": str(declared_instance or instance), "process": process,
               "plan_sha256": logs.sha(plan_path.read_bytes() if plan_path.exists() else logs.canonical(plan)),
               "launch_sha256": logs.sha(launch_path.read_bytes() if launch_path.exists() else logs.canonical(launch)),
               "scope": "Synthetic test context; loader-profile selection is tested separately."}
    return logs.NativeLogStream(instance, logs.Layout("logs/latest.log", "logs/%d{yyyy-MM-dd}-%i.log.gz", "min", 1, 99),
                                output, context, json.loads(logs.REVIEW_FILE.read_bytes()), prefix_witness=prefix_witness)
