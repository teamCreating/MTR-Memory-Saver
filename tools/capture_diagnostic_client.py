"""Own a prepared diagnostic JVM and retain native observations through real exit.

This is functional evidence collection, not whole-client performance acceptance.
Create an ``export-request`` file in the output to request a live JFR dump. Exit
the game normally after an export succeeds. No stop/kill is sent by this tool.
"""
import argparse
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import time
from types import SimpleNamespace

import packaged_client as client
from windows_snapshot_io import read_snapshot_bytes


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def capture(instance, output):
    instance, output = instance.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan = client.read(instance / "packaged-client-plan.json")
    report = {"scope": "diagnostic client; no performance or full gameplay acceptance",
              "started": now(), "instance": str(instance), "status": "launching",
              "sources": {name: client.digest(pathlib.Path(__file__).parent / name)
                          for name in ("capture_diagnostic_client.py", "packaged_client.py", "windows_snapshot_io.py")},
              "exports": [], "capture_errors": []}
    def save():
        client.write(output / "execution.json", report)
    save()
    process = client.launch(SimpleNamespace(instance=instance, wait_seconds=None))
    report.update(pid=process.pid, status="observing")
    for name in ("packaged-client-plan.json", "packaged-client-launch.json"):
        shutil.copyfile(instance / name, output / name)
    save()
    last = None
    with (output / "native-snapshots.jsonl").open("x", encoding="utf-8") as stream:
        while process.poll() is None:
            snapshot = instance / "game-probe/native-observer.json"
            if snapshot.is_file():
                try:
                    raw = read_snapshot_bytes(snapshot)
                    if raw != last:
                        data = json.loads(raw)
                        stream.write(json.dumps({"captured_at": now(), "snapshot": data}) + "\n")
                        stream.flush()
                        last = raw
                except (OSError, ValueError) as error:
                    report["capture_errors"].append({"at": now(), "error": repr(error)})
                    save()
            request = output / "export-request"
            if request.exists():
                sequence = len(report["exports"]) + 1
                request.rename(output / f"export-request-{sequence:02d}")
                entry = {"started": now(), "status": "running", "commands": []}
                report["exports"].append(entry)
                save()
                java = pathlib.Path(plan["java"])
                recording = instance / f"diagnostic-{sequence:02d}.jfr"
                commands = [
                    ("dump", [str(java.with_name("jcmd.exe")), str(process.pid), "JFR.dump", "name=acceptance", "filename=" + recording.name]),
                    ("summary", [str(java.with_name("jfr.exe")), "summary", str(recording)])]
                try:
                    for label, arguments in commands:
                        result = subprocess.run(arguments, cwd=instance, capture_output=True, timeout=60)
                        (output / f"export-{sequence:02d}-{label}.stdout.log").write_bytes(result.stdout)
                        (output / f"export-{sequence:02d}-{label}.stderr.log").write_bytes(result.stderr)
                        entry["commands"].append({"argv": arguments, "exit_code": result.returncode})
                        save()
                        if result.returncode != 0 or not recording.is_file():
                            raise RuntimeError("JFR " + label + " failed")
                    entry.update(status="readable", recording=str(recording), sha256=client.digest(recording))
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                    entry.update(status="failed", error=repr(error))
                entry["ended"] = now()
                save()
            time.sleep(1)
    report.update(status="exited", exit_code=process.wait(), ended=now())
    for relative in ("logs/latest.log", "launch.stdout.log", "launch.stderr.log", "acceptance-gc.log",
                     "game-probe/native-observer.json", "game-probe/native-resource-epochs.jsonl",
                     "game-probe/native-invalid-model.jsonl"):
        source = instance / relative
        if source.is_file():
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    report["files"] = {str(p.relative_to(output)): client.digest(p) for p in output.rglob("*")
                       if p.is_file() and p.name != "execution.json"}
    save()
    print(json.dumps({"pid": process.pid, "exit_code": report["exit_code"], "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    capture(args.instance, args.output)
