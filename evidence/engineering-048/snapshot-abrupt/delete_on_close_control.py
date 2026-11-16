"""Record actual JDK FileChannel DELETE_ON_CLOSE behavior across an owned Runtime.halt."""
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "delete-on-close-control-shared-reader"
sys.path.insert(0, str(HERE.parents[2] / "tools"))
from windows_snapshot_io import read_snapshot_bytes
JDK = pathlib.Path("C:/Users/ben_l/Saved Games/Yuuniverse 1.20.1 Shenyang/porting-output/work/tools/jdk21/jdk-21.0.11+10")
SOURCE = HERE / "DeleteOnCloseControl.java"
OUT.mkdir(exist_ok=False)
CLASSES = OUT / "classes"
CLASSES.mkdir()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


result = {"started": stamp(), "passed": False, "source_sha256": sha(SOURCE),
          "scope": "JDK-only candidate-design feasibility; packaged0.4.6 remains unchanged."}


def save():
    (OUT / "execution.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


save()
try:
    command = [str(JDK / "bin/javac.exe"), "-proc:none", "--release", "21", "-d", str(CLASSES), str(SOURCE)]
    compiled = subprocess.run(command, capture_output=True, timeout=60)
    result["compile"] = {"command": command, "exit_code": compiled.returncode}
    (OUT / "compile.stdout.log").write_bytes(compiled.stdout)
    (OUT / "compile.stderr.log").write_bytes(compiled.stderr)
    if compiled.returncode:
        raise RuntimeError("Control compilation failed")
    result["classes"] = {path.name: sha(path) for path in CLASSES.glob("*.class")}
    command = [str(JDK / "bin/java.exe"), "-Xmx64m", "-cp", str(CLASSES), "DeleteOnCloseControl", str(OUT)]
    result["command"] = command
    with (OUT / "stdout.log").open("wb") as stdout, (OUT / "stderr.log").open("wb") as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        result["pid"] = child.pid
        save()
        try:
            deadline = time.monotonic() + 40
            while not (OUT / "ready.txt").exists():
                if child.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Control did not become ready")
                time.sleep(0.01)
            ready = dict(line.split("=", 1) for line in (OUT / "ready.txt").read_text().splitlines())
            if int(ready["pid"]) != child.pid or int(ready["bytes"]) <= 0 or ready["roundtrip"] != "true":
                raise ValueError("Actual channel control was not verified")
            path = OUT / "owned-channel-snapshot.utf16"
            result["before_halt"] = {"timestamp": stamp(), "ready": ready, "path_visible": path.exists(),
                "listed_names": sorted(item.name for item in OUT.iterdir()), "running": child.poll() is None}
            if path.exists():
                result["before_halt"]["disk_bytes"] = path.stat().st_size
                actual = read_snapshot_bytes(path)
                expected = ("ab\u03b1\u4e2d\U0001f686\0" * 5000).encode("utf-16-be")
                if actual != expected:
                    raise ValueError("Independent UTF-16 disk bytes differ")
                result["before_halt"]["sha256"] = hashlib.sha256(actual).hexdigest()
                result["before_halt"]["independent_utf16_bytes_equal"] = True
            save()
            (OUT / "halt-after-observation").write_text("Halt only the ready control JVM.\n")
            result["exit_code"] = child.wait(timeout=20)
        finally:
            if child.poll() is None:
                child.kill()
                result["failure_cleanup"] = {"owned_pid": child.pid, "exit_code": child.wait(timeout=10)}
    result["after_halt"] = {"snapshot_exists": path.exists(), "shutdown_hook_ran": (OUT / "shutdown-hook-ran").exists(),
                            "listed_names": sorted(item.name for item in OUT.iterdir())}
    if result["exit_code"] != 75 or path.exists() or result["after_halt"]["shutdown_hook_ran"]:
        raise ValueError("OS-owned deletion on abrupt exit did not pass")
    if sha(SOURCE) != result["source_sha256"]:
        raise ValueError("Control source changed")
    result.update(passed=True, ended=stamp())
    save()
    print(json.dumps({"passed": True, "exit_code": result["exit_code"], "snapshot_after_halt": path.exists()}))
except BaseException as error:
    result.update(error=repr(error), ended=stamp())
    save()
    raise
