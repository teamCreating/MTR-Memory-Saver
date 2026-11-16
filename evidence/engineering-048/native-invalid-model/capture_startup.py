"""Preserve the first diagnostic startup prefix and its exact early probe source."""
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
INSTANCE = ROOT / ".cache/acceptance/official-nf248-neutral-048"
sys.path.insert(0, str(ROOT / "tools"))
from analyze_native_model_trace import digest
from windows_snapshot_io import read_snapshot_bytes


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    snapshot = OUT / "startup-prefix"
    snapshot.mkdir(exist_ok=False)
    receipt = {"captured_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
               "instance": str(INSTANCE), "scope": "Live startup prefix, not completed client acceptance", "files": {}}
    for relative in ("packaged-client-plan.json", "packaged-client-launch.json", "logs/latest.log",
                     "game-probe/native-invalid-model.jsonl", "game-probe/native-observer.json", "config/mtr.json",
                     "mods/mtr-model-trace-official-nf248-1.0.0.jar"):
        source = INSTANCE / relative
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = read_snapshot_bytes(source) if relative.endswith("native-observer.json") else source.read_bytes()
        destination.write_bytes(raw)
        receipt["files"][relative] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    write(snapshot / "capture.json", receipt)
    arguments = [sys.executable, "-X", "utf8", str(ROOT / "tools/analyze_native_model_trace.py"),
                 "--trace", str(snapshot / "game-probe/native-invalid-model.jsonl"),
                 "--log", str(snapshot / "logs/latest.log"), "--plan", str(snapshot / "packaged-client-plan.json"),
                 "--launch", str(snapshot / "packaged-client-launch.json"),
                 "--probe", str(snapshot / "mods/mtr-model-trace-official-nf248-1.0.0.jar"),
                 "--native-snapshot", str(snapshot / "game-probe/native-observer.json"), "--output", str(snapshot / "attribution.json")]
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True)
    (snapshot / "analysis.stdout.log").write_bytes(result.stdout)
    (snapshot / "analysis.stderr.log").write_bytes(result.stderr)
    write(snapshot / "analysis-execution.json", {"argv": arguments, "exit_code": result.returncode})
    if result.returncode:
        raise RuntimeError("Attribution failed; preserve the prefix and inspect analysis logs")

    source_snapshot = OUT / "early-probe-source"
    source_snapshot.mkdir(exist_ok=False)
    manifest = json.loads((OUT / "build-nf248/mtr-model-trace-official-nf248-1.0.0.build.json").read_bytes())
    source_inputs = {}
    for relative, expected in manifest["inputs"].items():
        source = ROOT / relative
        if relative == "build.gradle":
            raw = subprocess.run(["git", "show", "HEAD:build.gradle"], cwd=ROOT, capture_output=True, check=True).stdout
        else:
            raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise RuntimeError("Source bytes differ from final original build input: " + relative)
        # The launched artifact was copied before final TAIL refinement; preserve its original RETURN source.
        if relative.endswith("/InvalidModelTraceMixin.java"):
            assert raw.count(b'@At("TAIL")') == 1
            raw = raw.replace(b'@At("TAIL")', b'@At("RETURN")')
        destination = source_snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        source_inputs[relative] = hashlib.sha256(raw).hexdigest()
    shutil.copyfile(INSTANCE / "mods/mtr-model-trace-official-nf248-1.0.0.jar", source_snapshot / "launched.jar")
    write(source_snapshot / "source-reconstruction.json", {
        "timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
        "launched_jar_sha256": digest(source_snapshot / "launched.jar"),
        "inputs": source_inputs,
        "reconstruction": "Only final TAIL annotation changed back to original RETURN. Other sources verify against the final pre-launch build manifest. Class payload reproducibility is checked separately."})


if __name__ == "__main__":
    main()
