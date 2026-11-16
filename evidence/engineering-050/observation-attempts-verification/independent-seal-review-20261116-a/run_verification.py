"""Persist actual verifier argv, timestamps, return code, and raw output."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

base = Path(__file__).resolve().parent
root = base.parent.parent / "observation-attempts"
run_name = "execution-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
output = base / run_name
verifier = base / "verify_sealed_attempts.py"
argv = [sys.executable, str(verifier), "--sealed-root", str(root), "--output", str(output)]
started = dt.datetime.now(dt.timezone.utc).isoformat()
counter = time.perf_counter()
completed = subprocess.run(argv, cwd=base, capture_output=True, check=False)
elapsed = time.perf_counter() - counter
ended = dt.datetime.now(dt.timezone.utc).isoformat()
# A pre-output failure must remain visible and retained, too.
output.mkdir(parents=True, exist_ok=True)
for name, raw in (("stdout.txt", completed.stdout), ("stderr.txt", completed.stderr)):
    with (output/name).open("xb") as stream:
        stream.write(raw)
receipt = {"started_at": started, "ended_at": ended, "elapsed_seconds": elapsed,
    "argv": argv, "cwd": str(base), "exit_code": completed.returncode,
    "runner_argv": sys.argv, "python_executable": sys.executable, "python_version": sys.version,
    "verifier_sha256": hashlib.sha256(verifier.read_bytes()).hexdigest(),
    "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
    "original_evidence_receipt": False, "scope": "Actual execution receipt for independent external verifier only"}
with (output/"execution-receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
sys.stdout.buffer.write(completed.stdout)
sys.stderr.buffer.write(completed.stderr)
print(json.dumps({"execution_receipt": str(output/"execution-receipt.json"), "exit_code": completed.returncode}))
raise SystemExit(completed.returncode)
