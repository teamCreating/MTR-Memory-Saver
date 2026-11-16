"""Record an actual independent verification invocation and its complete output."""

import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
folder = Path(__file__).resolve().parent
verifier = folder / "verify.py"
receipt = folder / "verification-execution.json"
assert not receipt.exists()
argv = [sys.executable, "-X", "utf8", str(verifier), "--sealed", str(folder / "sealed-02"),
        "--output", str(folder / "verification-confirmation.json")]
report = {"argv": argv, "started": dt.datetime.now(dt.timezone.utc).isoformat(),
          "verifier_sha256": hashlib.sha256(verifier.read_bytes()).hexdigest()}
receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
completed = subprocess.run(argv, capture_output=True, timeout=60)
for label, raw in (("stdout", completed.stdout), ("stderr", completed.stderr)):
    path = folder / ("verification." + label + ".log")
    path.write_bytes(raw)
    report[label + "_sha256"] = hashlib.sha256(raw).hexdigest()
report.update(ended=dt.datetime.now(dt.timezone.utc).isoformat(), exit_code=completed.returncode)
receipt.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report))
raise SystemExit(completed.returncode)
