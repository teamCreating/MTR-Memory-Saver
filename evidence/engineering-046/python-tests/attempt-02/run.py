"""Capture final standalone regressions without overwriting the earlier suite."""
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys

OUTPUT = pathlib.Path(__file__).resolve().parent
ROOT = OUTPUT.parents[3]
command = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py"]
sources = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in sorted((ROOT / "tools").glob("*.py"))}
execution = {"started": dt.datetime.now(dt.timezone.utc).isoformat(), "command": command,
    "python_version": sys.version, "source_hashes": {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}}
snapshot = OUTPUT / "source-snapshots"
snapshot.mkdir(exist_ok=False)
for name in ("tools/observe_packaged_client.py", "tools/test_observe_packaged_client.py"):
    (snapshot / pathlib.Path(name).name).write_bytes(sources[name])
result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60)
(OUTPUT / "stdout.log").write_bytes(result.stdout)
(OUTPUT / "stderr.log").write_bytes(result.stderr)
changed = [name for name, data in sources.items() if (ROOT / name).read_bytes() != data]
execution.update(ended=dt.datetime.now(dt.timezone.utc).isoformat(), exit_code=result.returncode,
    sources_changed_during_execution=changed)
(OUTPUT / "execution.json").write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
print(result.stderr.decode("utf-8", errors="replace"))
raise SystemExit(result.returncode or bool(changed))
