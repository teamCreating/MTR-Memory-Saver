"""Run focused engineering checks with frozen inputs and actual subprocess receipts."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent / (sys.argv[1] if len(sys.argv) > 1 else "engineering-run-01")
OUTPUT.mkdir(parents=True, exist_ok=False)
sources = ["tools/native_log_stream.py", "config/native-log-reader.json", "tools/observe_packaged_client.py",
           "tools/reload_before_recorder.py", "tools/client_experiment.py", "tools/log_stream_test_support.py",
           "tools/test_native_log_stream.py", "tools/test_observe_packaged_client.py", "tools/test_reload_before_recorder.py",
           "tools/test_neutral_reload_adapter.py", "tools/test_client_experiment.py"]
hashes = {}
for name in sources:
    raw = (ROOT / name).read_bytes()
    copy = OUTPUT / "sources" / name
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes(raw)
    hashes[name] = hashlib.sha256(raw).hexdigest()
tests = sys.argv[2:] or ["test_native_log_stream", "test_reload_before_recorder", "test_neutral_reload_adapter",
                        "test_observe_packaged_client", "test_client_experiment"]
command = [sys.executable, "-X", "utf8", "-m", "unittest", "-v", *tests]
started, clock = dt.datetime.now(dt.timezone.utc).isoformat(), time.monotonic()
result = subprocess.run(command, cwd=ROOT / "tools", capture_output=True)
(OUTPUT / "stdout.log").write_bytes(result.stdout)
(OUTPUT / "stderr.log").write_bytes(result.stderr)
after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
receipt = {"started_at": started, "ended_at": dt.datetime.now(dt.timezone.utc).isoformat(),
           "elapsed_seconds": time.monotonic()-clock, "argv": command, "cwd": str(ROOT / "tools"), "exit_code": result.returncode,
           "source_sha256_before": hashes, "source_sha256_after": after, "sources_unchanged": hashes == after,
           "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(), "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
           "scope": "Engineering only. No game input, resource reload, route or performance acceptance."}
(OUTPUT / "execution.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
(OUTPUT / "runner-source.py").write_bytes(Path(__file__).read_bytes())
print(json.dumps({"exit_code": result.returncode, "sources_unchanged": hashes == after, "output": str(OUTPUT)}))
raise SystemExit(result.returncode if hashes == after else 2)
