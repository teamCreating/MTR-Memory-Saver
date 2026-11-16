"""Verify native diagnostic consumer tooling without launching a client."""
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import client_experiment as client
import packaged_client
from native_diagnostic_review import validate_review


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    sources = [*client.SOURCES, *(ROOT / "tools" / name for name in
               ("test_client_experiment.py", "test_packaged_client.py", "test_native_diagnostic_review.py")),
               ROOT / "docs/CLIENT_EXPERIMENT.md", Path(__file__)]
    before = [client.fingerprint(path) for path in sources]
    for path in sources:
        destination = output / "source" / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    started = client.now()
    tests = []
    for name in ("test_native_diagnostic_review.py", "test_client_experiment.py", "test_packaged_client.py"):
        command = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tools", "-p", name, "-v"]
        result = subprocess.run(command, cwd=ROOT, capture_output=True)
        (output / (name + ".stdout.log")).write_bytes(result.stdout)
        (output / (name + ".stderr.log")).write_bytes(result.stderr)
        counts = re.findall(rb"Ran (\d+) tests?", result.stderr)
        tests.append({"command": command, "exit_code": result.returncode, "count": int(counts[-1]) if counts else None})
    matrix = client.read(ROOT / "config/targets.json")
    review = client.read(client.DIAGNOSTIC_REVIEW)
    artifacts = []
    for target in ("official-nf248", "official-nf265"):
        path = ROOT / "evidence/engineering-048/neutral-diagnostics" / ("final-" + target) / ("mtr-native-observer-" + target + "-1.0.2.jar")
        identity = {"target": target, "mtrSha256": matrix["mtr"]["official"]["sha256"], "neoForge": matrix["targets"][target]["neoForge"]}
        artifact_before = client.fingerprint(path)
        verified = packaged_client.verified_observer(path, identity, matrix)
        validate_review(review, verified["target"], root=ROOT)
        artifacts.append({"input": artifact_before, "build_manifest": client.fingerprint(path.with_suffix(".build.json")),
                          "verified_metadata": verified, "unchanged": artifact_before == client.fingerprint(path)})
    after = [client.fingerprint(path) for path in sources]
    passed = before == after and all(test["exit_code"] == 0 and test["count"] for test in tests) and all(item["unchanged"] for item in artifacts)
    report = {"schema": 1, "started_at": started, "finished_at": client.now(), "passed": passed,
              "scope": "Consumer/launcher synthetic controls and actual final observer artifact identity; no new runtime/gameplay or performance acceptance",
              "python": sys.executable, "minecraft_launcher_lib_version": importlib.metadata.version("minecraft-launcher-lib"),
              "tests": tests, "total_tests": sum(test["count"] or 0 for test in tests), "artifacts": artifacts,
              "review": client.fingerprint(client.DIAGNOSTIC_REVIEW), "source_before": before, "source_after": after,
              "source_unchanged": before == after}
    client.save(output / "assessment.json", report, exclusive=True)
    client.save(output / "sha256.json", client.raw_files(output), exclusive=True)
    print(json.dumps({"passed": bool(passed), "tests": report["total_tests"], "source_unchanged": before == after}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
