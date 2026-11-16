"""Preserve an unfinished diagnostic run without inventing its missing exit receipt."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
INSTANCE = ROOT / ".cache/acceptance/official-nf248-owned-049b"
COLLECTOR = ROOT / ".cache/acceptance/capture-owned-049b"


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def preserve(source, destination, receipts):
    started = now()
    before = {"sha256": sha(source), "bytes": source.stat().st_size}
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(not destination.exists(), "Do not overwrite retained evidence")
    shutil.copy2(source, destination)
    actual = {"sha256": sha(destination), "bytes": destination.stat().st_size}
    after = {"sha256": sha(source), "bytes": source.stat().st_size}
    require(before == actual == after, "Original changed during preservation: " + str(source))
    receipts.append({"source": str(source), "destination": destination.relative_to(BASE).as_posix(),
                     "started": started, "ended": now(), **actual, "source_unchanged_during_copy": True})
    return actual


def resolve(relative, expected):
    for prefix in (ROOT, ROOT / "evidence/engineering-049/release/source",
                   ROOT / "evidence/engineering-049/release/inputs",
                   ROOT / "evidence/engineering-049/publisher-race/sealed-01/source",
                   ROOT / "evidence/engineering-049/performance-preparation/source"):
        path = prefix / relative
        if path.is_file() and sha(path) == expected:
            return path
    raise ValueError("No exact recorded source resolves: " + relative)


def seal(output):
    copies = []
    for source in sorted(COLLECTOR.rglob("*")):
        if source.is_file():
            preserve(source, output / "collector" / source.relative_to(COLLECTOR), copies)
    for relative in ("packaged-client-plan.json", "packaged-client-launch.json", "vehicle-test-instance.json",
                     "options.txt", "usercache.json", "usernamecache.json", "launch.stdout.log", "launch.stderr.log",
                     "acceptance-gc.log", "acceptance.jfr"):
        preserve(INSTANCE / relative, output / "instance" / relative, copies)
    for folder in ("logs", "game-probe"):
        for source in sorted((INSTANCE / folder).rglob("*")):
            if source.is_file():
                preserve(source, output / "instance" / source.relative_to(INSTANCE), copies)
    plan = read(output / "instance/packaged-client-plan.json")
    launch = read(output / "instance/packaged-client-launch.json")
    original = read(output / "collector/execution.json")
    require(original["status"] == "observing" and "ended" not in original and "exit_code" not in original,
            "Original collector now has a terminal receipt; reassess this task")
    require(original["pid"] == launch["pid"], "Original collector and launch PID differ")
    require(sha(output / "instance/packaged-client-plan.json") == launch["plan_sha256"], "Launch plan differs")
    require(sha(output / "collector/packaged-client-plan.json") == launch["plan_sha256"], "Collector plan differs")
    require(sha(output / "collector/packaged-client-launch.json") == sha(output / "instance/packaged-client-launch.json"),
            "Collector launch differs")
    pid = launch["pid"]
    script = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); " \
        f"$retrospectivePid={pid}; " \
        "$retrospectiveProcess=@(Get-CimInstance Win32_Process -Filter \"ProcessId = $retrospectivePid\" -ErrorAction Stop | " \
        "Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine); " \
        "$retrospectiveCollectors=@(Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" -ErrorAction Stop | " \
        "Where-Object {$_.CommandLine -match 'capture_diagnostic_client.py' -and $_.CommandLine -match 'capture-owned-049b'} | " \
        "Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine); " \
        "@{observed_at=[DateTimeOffset]::UtcNow.ToString('o'); target_pid=$retrospectivePid; " \
        "process_records=$retrospectiveProcess; matching_collectors=$retrospectiveCollectors} | ConvertTo-Json -Depth 5"
    command = ["pwsh", "-NoProfile", "-Command", script]
    execution = {"started": now(), "command": command, "cwd": str(ROOT)}
    process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    execution["helper_pid"] = process.pid
    stdout, stderr = process.communicate(timeout=40)
    execution.update(ended=now(), exit_code=process.returncode,
                     stdout_sha256=hashlib.sha256(stdout).hexdigest(), stderr_sha256=hashlib.sha256(stderr).hexdigest())
    (output / "current-process.stdout.log").write_bytes(stdout)
    (output / "current-process.stderr.log").write_bytes(stderr)
    write(output / "current-process.execution.json", execution)
    require(process.returncode == 0, "Actual retrospective CIM query failed")
    current = json.loads(stdout.decode("utf-8-sig"))
    require(not current["process_records"] and not current["matching_collectors"], "Old PID or collector is currently present")
    write(output / "current-process.json", current)
    artifact_sources = []
    for entry in plan["mods"]:
        if entry["role"] not in ("companion", "observer"):
            continue
        source = INSTANCE / "mods" / entry["filename"]
        require(sha(source) == entry["sha256"], "Installed artifact differs from original plan")
        preserve(source, output / "artifacts" / source.name, copies)
        manifest = ROOT / "evidence/engineering-049/performance-preparation/artifacts" / source.with_suffix(".build.json").name
        identity = read(manifest)
        require(identity["sha256"] == entry["sha256"], "Manifest differs from installed artifact")
        preserve(manifest, output / "artifacts" / manifest.name, copies)
        for relative, expected in identity["inputs"].items():
            resolved = resolve(relative, expected)
            destination = output / "artifact-sources" / entry["role"] / relative
            preserve(resolved, destination, copies)
            artifact_sources.append({"role": entry["role"], "relative_path": relative, "sha256": expected,
                                     "resolved_from": str(resolved), "sealed_path": destination.relative_to(BASE).as_posix()})
    for name, expected in original["sources"].items():
        source = resolve("tools/" + name, expected)
        preserve(source, output / "collector-sources/tools" / name, copies)
    preserve(Path(__file__), output / "source/seal_unfinished.py", copies)
    snapshots = []
    with (output / "collector/native-snapshots.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            snapshots.append(json.loads(line))
    require(snapshots, "No actual native snapshots retained")
    first, last = snapshots[0], snapshots[-1]
    for item in snapshots:
        require(item["snapshot"]["pid"] == pid, "Retained snapshot from another PID")
    final = read(output / "instance/game-probe/native-observer.json")
    require(final == last["snapshot"], "Last collector snapshot differs from final published snapshot")
    require((output / "instance/acceptance.jfr").stat().st_size == 0, "JFR no longer empty; assess new bytes separately")
    write(output / "copy-receipts.json", copies)
    write(output / "source-resolutions.json", artifact_sources)
    assessment = {"scope": "retrospective_unfinished_diagnostic_run_observation", "observed_at": current["observed_at"],
        "pid": pid, "process_created_from_native_snapshot": final["process_created"],
        "status": "unfinished_at_retrospective_observation", "pid_currently_absent": True,
        "matching_collector_currently_absent": True, "original_collector_status": original["status"],
        "exit_code": None, "exit_time": None, "termination_cause": "unknown", "normal_exit_verified": False,
        "interruption_action_observed": False, "native_snapshot_records": len(snapshots),
        "first_capture": first["captured_at"], "last_capture": last["captured_at"],
        "last_native_observation": last["snapshot"]["observed_at"],
        "last_native_state": {name: final[name] for name in ("paused", "in_world", "screen", "registered_count",
            "registered_declarations", "native_pending", "native_settled", "resource_epochs", "observation_errors")},
        "empty_jfr": {"bytes": 0, "sha256": sha(output / "instance/acceptance.jfr"), "readable_recording": False},
        "sealed_companion_and_observer_manifest_inputs": len(artifact_sources),
        "limits": ["No exit status, exact exit time or stopping action can be reconstructed from process absence.",
                   "Original observing receipt is unchanged; its empty capture_errors is not a completed-run certification.",
                   "The last published snapshot and retained prefix do not establish error-free behavior after that observation.",
                   "Native registration/caches are observations only, not full gameplay, reload, endurance or performance acceptance.",
                   "Source-world, resource archives, MTR JAR and JDK/runtime/library bytes were not freshly rehashed; original plan declarations are retained.",
                   "No original game/world, process or source file was changed by sealing; the separate running 049c was not accessed."]}
    write(output / "assessment.json", assessment)
    return assessment


if __name__ == "__main__":
    output = BASE / sys.argv[1]
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"started": now(), "command": [sys.executable, str(Path(__file__).resolve()), sys.argv[1]],
               "pid": os.getpid(), "source_sha256": sha(Path(__file__)), "passed": False}
    try:
        result = seal(output)
        receipt.update(passed=True, scope=result["scope"])
    except BaseException as error:
        receipt["error"] = repr(error)
        raise
    finally:
        receipt["ended"] = now()
        write(output / "sealing.execution.json", receipt)
    files = {path.relative_to(BASE).as_posix(): {"sha256": sha(path), "bytes": path.stat().st_size}
             for path in sorted(output.rglob("*")) if path.is_file()}
    write(output / "SHA256SUMS.json", {"schema": 1, "timestamp": now(), "files": files})
    print(json.dumps({"preserved_files": len(files), "status": result["status"], "exit_code": None,
                      "normal_exit_verified": False}))
