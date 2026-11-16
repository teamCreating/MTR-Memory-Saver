"""Verify wait-result persistence using one ordinary owned Python child, never PresentMon."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pilot
from native_etw import child_identity

BASE = Path(__file__).resolve().parent
OUT = BASE / "owned-child-control-01"
OUT.mkdir(exist_ok=False)
receipt = {"scope": "ordinary_owned_child_wrapper_engineering_only", "started": pilot.now(),
           "source_sha256": pilot.sha(Path(__file__)), "passed": False, "presentmon_or_minecraft_launched": False}
try:
    command = [sys._base_executable, "-c", "import time; time.sleep(0.25); raise SystemExit(7)"]
    with (OUT / "child.stdout.log").open("xb") as stdout, (OUT / "child.stderr.log").open("xb") as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        before = child_identity(child)
        exit_code = child.wait(timeout=10)
        # The same sequencing as the repaired pilot: preserve wait before any
        # post-exit observation, including the original API call that can fail.
        pilot.write(OUT / "child-exit.json", {"argv": command, "pid": child.pid, "actual_owner_pid": __import__('os').getpid(),
                    "before": before, "exit_code": exit_code, "wait_completed_at": pilot.now(), "clock": pilot.clock_pair()})
        retained = pilot.sha(OUT / "child-exit.json")
        spec = importlib.util.spec_from_file_location("original_native_etw", BASE / "upstream-capture-02/native-etw-source.py")
        original = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(original)
        try:
            historical = {"returned": original.child_identity(child), "raised": False}
        except OSError as error:
            historical = {"raised": True, "error": repr(error), "winerror": error.winerror}
        pilot.write(OUT / "original-post-exit-api-control.json", historical)
        assert pilot.sha(OUT / "child-exit.json") == retained, "Wait receipt was lost/changed after post-check"
        after = child_identity(child)
        pilot.write(OUT / "repaired-post-exit.json", after)
        assert exit_code == 7 and before["pid"] == after["pid"] == child.pid
        assert before["created"] == after["created"] and after["exit_time"] is not None
        assert after["image_query_omitted_for_exited_process"] is True and after["executable"] is None
        receipt.update(passed=True, actual_pid=child.pid, actual_exit_code=exit_code,
                       original_api_failure_reproduced=historical["raised"], exit_receipt_sha256=retained,
                       exit_receipt_preserved_through_post_check=True, repaired_post_exit_times_verified=True)
    for source in (Path(__file__), BASE / "native_etw.py", BASE / "pilot.py"):
        shutil.copy2(source, OUT / (source.stem + "-source.py"))
except BaseException as error:
    receipt["error"] = repr(error)
    raise
finally:
    receipt["ended"] = pilot.now()
    pilot.write(OUT / "execution.json", receipt)
print(json.dumps(receipt))
