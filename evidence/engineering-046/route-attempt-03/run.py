"""Fresh two-hour route observation; preserve commands, failures and complete JFR."""
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTPUT = pathlib.Path(__file__).resolve().parent
INSTANCE = ROOT / ".cache/acceptance/official-nf248-full-native-046-profile"
OBSERVATION = OUTPUT / "observation"
EXECUTION = OUTPUT / "execution.json"
if EXECUTION.exists() or OBSERVATION.exists():
    raise SystemExit("Use a fresh route attempt; do not overwrite prior evidence.")
plan = json.loads((INSTANCE / "packaged-client-plan.json").read_text(encoding="utf-8"))
launch = json.loads((INSTANCE / "packaged-client-launch.json").read_text(encoding="utf-8"))
java = pathlib.Path(plan["java"])
execution = {"started": dt.datetime.now(dt.timezone.utc).isoformat(), "status": "starting",
             "pid": launch["pid"], "commands": [], "jvm_stopped": False,
             "source_sha256": hashlib.sha256((ROOT / "tools/observe_packaged_client.py").read_bytes()).hexdigest(),
             "limits": "Live-existing-client durability observation, not an independent performance trial. No reload inputs during the frozen window. Background build activity remains part of this desktop environment. Visual/boarding and pending native diagnostics are separate gates."}


def save():
    EXECUTION.write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")


def command(name, arguments, timeout=60):
    entry = {"name": name, "command": arguments, "started": dt.datetime.now(dt.timezone.utc).isoformat()}
    execution["commands"].append(entry)
    save()
    try:
        result = subprocess.run(arguments, capture_output=True, timeout=timeout)
        (OUTPUT / (name + ".stdout.log")).write_bytes(result.stdout)
        (OUTPUT / (name + ".stderr.log")).write_bytes(result.stderr)
        entry.update(exit_code=result.returncode, ended=dt.datetime.now(dt.timezone.utc).isoformat())
        save()
        if result.returncode:
            raise RuntimeError(name + " failed; retain the client and all evidence")
        return result
    except BaseException as error:
        entry["error"] = repr(error)
        save()
        raise


save()
try:
    command("jfr-check-before", [str(java.with_name("jcmd.exe")), str(launch["pid"]), "JFR.check", "verbose=true"])
    started = command("jfr-start", [str(java.with_name("jcmd.exe")), str(launch["pid"]), "JFR.start",
        "name=route03", "settings=profile", "disk=true", "maxsize=0"])
    if b"Started recording" not in started.stdout:
        raise RuntimeError("Jcmd exit zero did not confirm a new recording")
    arguments = [sys.executable, "-X", "utf8", str(ROOT / "tools/observe_packaged_client.py"), "route",
        "--instance", str(INSTANCE), "--output", str(OBSERVATION), "--expected-count", "1091",
        "--expected-declarations", "1092", "--duration", "7200", "--interval", "5",
        "--stable-seconds", "60", "--freshness-seconds", "15", "--route-windows", "3",
        "--minimum-window-progress-displacement", "0.01", "--require-world", "--unpaused",
        "--gpu-counter", r"\GPU Process Memory(*)\Shared Usage",
        "--gpu-counter", r"\GPU Process Memory(*)\Dedicated Usage", "--nmt",
        "--auxiliary-interval", "60", "--auxiliary-shutdown-seconds", "45"]
    execution["observer_command"] = arguments
    with (OUTPUT / "observer.stdout.log").open("wb") as stdout, (OUTPUT / "observer.stderr.log").open("wb") as stderr:
        process = subprocess.Popen(arguments, stdout=stdout, stderr=stderr)
        execution.update(status="observing", observer_pid=process.pid)
        save()
        result = process.wait()
    execution["observer_exit_code"] = result
    execution["status"] = "exporting"
    save()
    recording = INSTANCE / "route-attempt-03-complete.jfr"
    command("jfr-check-after", [str(java.with_name("jcmd.exe")), str(launch["pid"]), "JFR.check", "verbose=true"])
    command("jfr-dump", [str(java.with_name("jcmd.exe")), str(launch["pid"]), "JFR.dump", "name=route03", "filename=" + recording.name])
    command("jfr-summary", [str(java.with_name("jfr.exe")), "summary", str(recording)])
    command("jfr-stop", [str(java.with_name("jcmd.exe")), str(launch["pid"]), "JFR.stop", "name=route03"])
    import shutil
    shutil.copyfile(recording, OUTPUT / "route.jfr")
    for relative in ("packaged-client-plan.json", "packaged-client-launch.json", "acceptance-gc.log",
                     "logs/latest.log", "game-probe/packaged-observer.json", "game-probe/live.json", "game-probe/resource-epochs.jsonl"):
        shutil.copyfile(INSTANCE / relative, OUTPUT / pathlib.Path(relative).name)
    execution.update(status="observed_pass" if result == 0 else "observed_failure", ended=dt.datetime.now(dt.timezone.utc).isoformat())
    save()
    raise SystemExit(result)
except BaseException as error:
    if isinstance(error, SystemExit):
        raise
    execution.update(status="failed", error=repr(error), ended=dt.datetime.now(dt.timezone.utc).isoformat())
    save()
    raise
