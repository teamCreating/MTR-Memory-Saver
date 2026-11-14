"""Capture this incomplete observation before interrupting its observer only."""
import datetime as dt
import json
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTPUT = pathlib.Path(__file__).resolve().parent
EXPORT = OUTPUT / "export"
EXPORT.mkdir(exist_ok=False)
INSTANCE = ROOT / ".cache/acceptance/official-nf248-full-native-046-profile"
OBSERVATION = ROOT / ".cache/acceptance/official-nf248-full-native-046-route-observation-attempt-02"
plan = json.loads((INSTANCE / "packaged-client-plan.json").read_text(encoding="utf-8"))
launch = json.loads((INSTANCE / "packaged-client-launch.json").read_text(encoding="utf-8"))
java = pathlib.Path(plan["java"])
execution = {"timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "pid": launch["pid"], "commands": []}


def run(name, args):
    result = subprocess.run(args, capture_output=True, timeout=60)
    (EXPORT / (name + ".stdout.log")).write_bytes(result.stdout)
    (EXPORT / (name + ".stderr.log")).write_bytes(result.stderr)
    execution["commands"].append({"name": name, "command": args, "exit_code": result.returncode})
    (EXPORT / "capture-execution.json").write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
    if result.returncode:
        raise RuntimeError(name + " failed; do not interrupt the observer or stop the JVM")


run("jfr-check", [str(java.with_name("jcmd.exe")), str(launch["pid"]), "JFR.check", "verbose=true"])
recording = OUTPUT / "partial-route.jfr"
native_recording = INSTANCE / "route-attempt-02.jfr"
run("jfr-dump", [str(java.with_name("jcmd.exe")), str(launch["pid"]), "JFR.dump", "name=acceptance", "filename=" + native_recording.name])
shutil.copyfile(native_recording, recording)
run("jfr-summary", [str(java.with_name("jfr.exe")), "summary", str(recording)])
run("nmt", [str(java.with_name("jcmd.exe")), str(launch["pid"]), "VM.native_memory", "summary", "scale=KB"])
for name in ("packaged-client-plan.json", "packaged-client-launch.json", "acceptance-gc.log", "logs/latest.log", "game-probe/packaged-observer.json", "game-probe/live.json", "game-probe/resource-epochs.jsonl"):
    shutil.copyfile(INSTANCE / name, OUTPUT / pathlib.Path(name).name)
checkpoint = OUTPUT / "live-observation-checkpoint"
checkpoint.mkdir(exist_ok=False)
for source in OBSERVATION.iterdir():
    if source.is_file():
        shutil.copyfile(source, checkpoint / source.name)
execution["recording_verified"] = True
execution["jvm_stopped"] = False
execution["observer_interruption_safe_to_attempt"] = True
(EXPORT / "capture-execution.json").write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
print(json.dumps(execution))
