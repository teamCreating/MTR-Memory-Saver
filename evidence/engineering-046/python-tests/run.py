"""Preserve the actual standalone regression-suite execution and source bytes."""
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

OUTPUT = pathlib.Path(__file__).resolve().parent
ROOT = OUTPUT.parents[2]
command = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py"]
execution = {"started": dt.datetime.now(dt.timezone.utc).isoformat(), "command": command,
    "python_version": sys.version, "source_hashes": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "tools").glob("*.py"))}}
result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60)
(OUTPUT / "stdout.log").write_bytes(result.stdout)
(OUTPUT / "stderr.log").write_bytes(result.stderr)
execution.update(ended=dt.datetime.now(dt.timezone.utc).isoformat(), exit_code=result.returncode)
(OUTPUT / "execution.json").write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
print(result.stderr.decode("utf-8", errors="replace"))
raise SystemExit(result.returncode)
