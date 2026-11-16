"""Repeat and freeze the candidate build with explicit execution receipts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
OUT = EVIDENCE / "build-replay"
JAVA = Path(r"C:\Users\ben_l\Saved Games\Yuuniverse 1.20.1 Shenyang\porting-output\work\tools\jdk21\jdk-21.0.11+10")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(value):
    (OUT / "execution.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(exist_ok=False)
    env = os.environ.copy()
    env["JAVA_HOME"] = str(JAVA)
    env["PATH"] = str(JAVA / "bin") + os.pathsep + env["PATH"]
    record = {
        "started": stamp(), "passed": False, "commands": [],
        "purpose": "New actual executions with explicit argv/time/exit receipts; initial raw logs are preserved separately.",
        "java_home": str(JAVA), "java_sha256": sha(JAVA / "bin/java.exe"),
        "runner_sha256": sha(Path(__file__).resolve()),
    }
    write(record)
    try:
        for target in ("official-nf248", "official-nf265"):
            frozen = EVIDENCE / target
            manifests = list(frozen.glob("*.build.json"))
            assert len(manifests) == 1
            manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
            assert manifest["target"] == target
            version = manifest["version"]
            assert sha(frozen / manifest["artifact"]) == manifest["sha256"]
            trial = OUT / target
            trial.mkdir()
            command = [str(ROOT / "gradlew.bat"), "test", "jar", "buildManifest", "verifyRelease",
                       f"-Ptarget={target}", f"-PmodVersion={version}", "--rerun-tasks", "--console=plain"]
            receipt = {"target": target, "command": command, "cwd": str(ROOT), "started": stamp()}
            record["commands"].append(receipt)
            write(record)
            with (trial / "stdout.log").open("wb") as stdout, (trial / "stderr.log").open("wb") as stderr:
                process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
                receipt["pid"] = process.pid
                write(record)
                receipt["exit_code"] = process.wait()
            receipt["ended"] = stamp()
            write(record)
            assert receipt["exit_code"] == 0, receipt
            artifact = ROOT / "build/libs" / manifest["artifact"]
            receipt["artifact_sha256"] = sha(artifact)
            assert receipt["artifact_sha256"] == manifest["sha256"]
            built_manifest = artifact.with_suffix(".build.json")
            assert built_manifest.read_bytes() == manifests[0].read_bytes()
            shutil.copy2(artifact, trial / artifact.name)
            shutil.copy2(built_manifest, trial / built_manifest.name)
            totals = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
            (trial / "junit").mkdir()
            xmls = list((ROOT / "build/test-results/test").glob("TEST-*.xml"))
            assert xmls
            for path in xmls:
                shutil.copy2(path, trial / "junit" / path.name)
                attrs = ET.parse(path).getroot().attrib
                for key in totals:
                    totals[key] += int(attrs[key])
            receipt["junit"] = totals
            assert totals == {"tests": 73, "failures": 0, "errors": 0, "skipped": 0}, totals
            receipt["manifest_byte_identical"] = True
            receipt["passed"] = True
            write(record)
        record["passed"] = True
    finally:
        record["ended"] = stamp()
        write(record)
    print(json.dumps({"passed": record["passed"], "targets": [{"target": row["target"], "sha256": row["artifact_sha256"], "junit": row["junit"]} for row in record["commands"]]}))


if __name__ == "__main__":
    main()
