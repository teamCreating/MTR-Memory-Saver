"""Complete the historical startup seal; use sealed payloads only, never a game."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
SEALED = HERE.parent / "full-load-startup"
OUTPUT = HERE / "run-01"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def execute(name, output):
    command = [sys.executable, "-X", "utf8", str(SEALED / "verify_sealed.py"),
               "--sealed", str(SEALED), "--output", str(output)]
    started, clock = now(), time.monotonic()
    result = subprocess.run(command, capture_output=True)
    receipt = {"started_at": started, "ended_at": now(), "elapsed_seconds": time.monotonic()-clock,
               "command": command, "exit_code": result.returncode,
               "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
               "stderr_sha256": hashlib.sha256(result.stderr).hexdigest()}
    (OUTPUT / (name+".stdout.log")).write_bytes(result.stdout)
    (OUTPUT / (name+".stderr.log")).write_bytes(result.stderr)
    (OUTPUT / (name+".execution.json")).write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    if result.returncode:
        raise RuntimeError(name+" verification failed; raw receipt and streams preserved")
    return receipt


def main():
    OUTPUT.mkdir(parents=True, exist_ok=False)
    originals = {path.relative_to(SEALED).as_posix(): {"sha256": sha(path), "bytes": path.stat().st_size}
                 for path in sorted(SEALED.rglob("*")) if path.is_file()}
    (OUTPUT / "original-inventory.json").write_text(json.dumps({"files": originals}, indent=2)+"\n", encoding="utf-8")
    for name in ("verify_sealed.py", "README.md"):
        (OUTPUT / name).write_bytes((SEALED / name).read_bytes())
    result_path, index_path = SEALED / "verification-result.json", SEALED / "sha256-index.json"
    assert not result_path.exists() and not index_path.exists(), "Seal outputs must be fresh"
    execute("core", result_path)
    index = {path.relative_to(SEALED).as_posix(): {"sha256": sha(path), "bytes": path.stat().st_size}
             for path in sorted(SEALED.rglob("*")) if path.is_file() and path != index_path}
    index_path.write_text(json.dumps({"schema": 1, "created_at": now(), "files": index}, indent=2)+"\n", encoding="utf-8")
    execute("indexed", OUTPUT / "verification-result-indexed.json")
    indexed = json.loads((OUTPUT / "verification-result-indexed.json").read_bytes())
    assert indexed["passed"] and indexed["outer_index_verified_payloads"] == len(index)
    for relative, receipt in originals.items():
        path = SEALED / relative
        assert sha(path) == receipt["sha256"] and path.stat().st_size == receipt["bytes"]
    receipt = {"completed_at": now(), "passed": True, "original_payloads_unchanged": len(originals),
               "sealed_indexed_payloads": len(index), "sealed_index_sha256": sha(index_path),
               "sealed_result_sha256": sha(result_path), "sealed_only": True,
               "scope": "Historical PID58468/neutral1.0.2 initial minute and selected DC01 side-view evidence only. No final-exit, full-run, reload, gameplay, endurance or performance expansion."}
    (OUTPUT / "assessment.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    (OUTPUT / "runner-source.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
