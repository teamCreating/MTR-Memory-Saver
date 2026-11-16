"""Record an actual sealed-only verifier execution, preserving every failed run."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SEALED = HERE.parent / "neutral103-startup"
OUTPUT = HERE / (sys.argv[1] if len(sys.argv) > 1 else "run-01")
OUTPUT.mkdir(parents=True, exist_ok=False)
verifier = HERE / "verify_startup.py"
command = [sys.executable, "-X", "utf8", str(verifier), "--sealed", str(SEALED),
           "--output", str(OUTPUT / "verification-result.json")]
(OUTPUT / "verifier-source.py").write_bytes(verifier.read_bytes())
(OUTPUT / "runner-source.py").write_bytes(Path(__file__).read_bytes())
started, clock = dt.datetime.now(dt.timezone.utc).isoformat(), time.monotonic()
result = subprocess.run(command, cwd=HERE, capture_output=True)
(OUTPUT / "stdout.log").write_bytes(result.stdout)
(OUTPUT / "stderr.log").write_bytes(result.stderr)
receipt = {"started_at": started, "ended_at": dt.datetime.now(dt.timezone.utc).isoformat(),
           "elapsed_seconds": time.monotonic()-clock, "argv": command, "cwd": str(HERE), "exit_code": result.returncode,
           "verifier_sha256": hashlib.sha256((OUTPUT / "verifier-source.py").read_bytes()).hexdigest(),
           "runner_sha256": hashlib.sha256((OUTPUT / "runner-source.py").read_bytes()).hexdigest(),
           "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(), "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
           "scope": "Actual independent sealed-only verification execution; not a game launch or original observer exit receipt."}
(OUTPUT / "execution.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"exit_code": result.returncode, "output": str(OUTPUT)}))
raise SystemExit(result.returncode)
