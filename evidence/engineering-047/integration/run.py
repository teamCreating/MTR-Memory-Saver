"""Preserve one integrated standalone suite against frozen current tool inputs."""
import datetime as dt
import hashlib
import importlib.metadata
import json
import pathlib
import subprocess
import sys

OUTPUT = pathlib.Path(__file__).resolve().parent
ROOT = OUTPUT.parents[2]
OFFSET = dt.timezone(dt.timedelta(hours=8))


def now():
    return dt.datetime.now(OFFSET).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(value):
    (OUTPUT / "execution.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


if (OUTPUT / "execution.json").exists() or (OUTPUT / "source-snapshots").exists():
    raise SystemExit("Use a fresh integration evidence directory.")
paths = sorted((ROOT / "tools").glob("*.py")) + [
    ROOT / "config/targets.json", ROOT / "config/legacy-baselines.json",
    ROOT / "config/client-experiment.json", ROOT / "tools/probes/neutral/observer.json",
]
sources = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in paths}
command = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tools", "-p", "test_*.py", "-v"]
record = {"started_at": now(), "utc_offset": "+08:00", "status": "running", "command": command,
          "cwd": str(ROOT), "python_version": sys.version,
          "python_executable_sha256": sha(pathlib.Path(sys.executable).read_bytes()),
          "minecraft_launcher_lib_version": importlib.metadata.version("minecraft-launcher-lib"),
          "source_hashes_before": {name: sha(data) for name, data in sources.items()},
          "limits": "Standalone tool tests, including harmless Python child ownership fixtures; no Minecraft launch or v6 runtime validation."}
save(record)
snapshot = OUTPUT / "source-snapshots"
snapshot.mkdir()
for name, data in sources.items():
    destination = snapshot / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
try:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60)
    (OUTPUT / "stdout.log").write_bytes(result.stdout)
    (OUTPUT / "stderr.log").write_bytes(result.stderr)
    record.update(exit_code=result.returncode, status="passed" if result.returncode == 0 else "failed")
except subprocess.TimeoutExpired as error:
    (OUTPUT / "stdout.log").write_bytes(error.stdout or b"")
    (OUTPUT / "stderr.log").write_bytes(error.stderr or b"")
    record.update(status="failed", error="Standalone suite exceeded its 60-second execution limit.")
finally:
    current = {path.relative_to(ROOT).as_posix(): sha(path.read_bytes()) for path in paths}
    record["source_hashes_after"] = current
    record["sources_changed_during_execution"] = sorted(
        name for name in sources if sha(sources[name]) != current[name])
    if record["sources_changed_during_execution"]:
        record["status"] = "failed"
    record["finished_at"] = now()
    save(record)
print((OUTPUT / "stderr.log").read_text(encoding="utf-8", errors="replace"))
raise SystemExit(0 if record["status"] == "passed" else 1)
