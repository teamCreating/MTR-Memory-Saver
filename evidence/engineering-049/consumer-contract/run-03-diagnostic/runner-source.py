"""Run one unchanged realtime test, preserving its completed output before cleanup."""
import contextlib
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent / "run-03-diagnostic"
sys.path.insert(0, str(ROOT / "tools"))
import test_observe_packaged_client as tests


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    sources = [Path(tests.__file__), ROOT / "tools/observe_packaged_client.py"]
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    original = tests.ObservationTest.run_realtime_auxiliary
    def preserve(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        shutil.copytree(result[2], OUTPUT / "completed-observation")
        return result
    tests.ObservationTest.run_realtime_auxiliary = preserve
    name = "test_shutdown_completion_is_explicit_and_does_not_extend_route_window"
    suite = unittest.TestSuite([tests.ObservationTest(name)])
    started, clock = dt.datetime.now(dt.timezone.utc).isoformat(), time.monotonic()
    with (OUTPUT / "stdout.log").open("w", encoding="utf-8") as stdout, \
            (OUTPUT / "stderr.log").open("w", encoding="utf-8") as stderr, \
            contextlib.redirect_stdout(stdout):
        result = unittest.TextTestRunner(stream=stderr, verbosity=2).run(suite)
    after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    receipt = {"started_at": started, "ended_at": dt.datetime.now(dt.timezone.utc).isoformat(),
               "elapsed_seconds": time.monotonic()-clock, "argv": [sys.executable, *sys.argv],
               "test": name, "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "passed": result.wasSuccessful() and before == after,
               "source_sha256_before": before, "source_sha256_after": after,
               "scope": "Unchanged test and observer. The wrapper copies the completed result only after the observation returns; it changes no timing gate or asserted result."}
    (OUTPUT / "execution.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    (OUTPUT / "runner-source.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps({key: receipt[key] for key in ("passed", "tests", "failures", "errors")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
