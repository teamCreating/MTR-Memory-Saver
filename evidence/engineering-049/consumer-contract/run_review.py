"""Freeze and execute focused consumer engineering controls; never launch a game."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent / (sys.argv[1] if len(sys.argv) > 1 else "run-01")
SOURCES = (
    "tools/observe_packaged_client.py", "tools/reload_before_recorder.py",
    "tools/windows_snapshot_io.py", "config/native-observer-consumer.json",
    "tools/test_neutral_reload_adapter.py", "tools/test_reload_before_recorder.py",
    "tools/test_observe_packaged_client.py", "tools/test_windows_snapshot_io.py",
    "tools/client_experiment_analysis.py", "tools/native_diagnostic_review.py",
    "config/native-diagnostic-review.json",
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    before = {}
    for relative in SOURCES:
        raw = (ROOT / relative).read_bytes()
        copy = OUTPUT / "sources" / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(raw)
        before[relative] = sha(raw)
    tests = sys.argv[2:] or ["test_neutral_reload_adapter", "test_reload_before_recorder",
                            "test_observe_packaged_client", "test_windows_snapshot_io"]
    command = [sys.executable, "-X", "utf8", "-m", "unittest", "-v", *tests]
    started, clock = now(), time.monotonic()
    result = subprocess.run(command, cwd=ROOT / "tools", capture_output=True)
    ended, elapsed = now(), time.monotonic()-clock
    (OUTPUT / "stdout.log").write_bytes(result.stdout)
    (OUTPUT / "stderr.log").write_bytes(result.stderr)
    summary = re.search(rb"Ran (\d+) tests? in", result.stderr)
    after = {relative: sha((ROOT / relative).read_bytes()) for relative in SOURCES}
    receipt = {"started_at": started, "ended_at": ended, "elapsed_seconds": elapsed,
               "command": command, "cwd": str(ROOT / "tools"), "exit_code": result.returncode,
               "test_count": int(summary[1]) if summary else None,
               "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr),
               "source_sha256_before": before, "source_sha256_after": after,
               "runner_sha256": sha(Path(__file__).read_bytes()),
               "passed": result.returncode == 0 and before == after and summary is not None,
               "scope": "Engineering controls only. Generated epochs/receipts do not award actual reload, gameplay or performance acceptance."}
    (OUTPUT / "execution.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    (OUTPUT / "runner-source.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps({key: receipt[key] for key in ("passed", "exit_code", "test_count", "elapsed_seconds")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
