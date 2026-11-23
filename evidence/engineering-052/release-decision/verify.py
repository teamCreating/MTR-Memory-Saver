"""Verify the selected candidate assets and the explicit performance hold."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
def read(p): return json.loads(p.read_bytes())
def sha(raw): return hashlib.sha256(raw).hexdigest()
index = read(HERE / "SHA256.json")["files"]
actual = {p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file()}
assert actual == set(index) | {"SHA256.json"}
for name, expected in index.items():
    data = (HERE / name).read_bytes()
    assert len(data) == expected["bytes"] and sha(data) == expected["sha256"], name
decision = read(HERE / "decision.json")
assert decision["release_status"] == "held" and decision["release_accepted"] is False
assert decision["aa_trials_executed"] == decision["ab_trials_executed"] == 0
assert decision["controlled_performance"] == "inconclusive_not_measured"
assert read(REPO / "evidence/engineering-052/revised048-reload20/assessment.json")["verified_reload_count"] == 20
cases = read(REPO / "evidence/engineering-052/revised048-packaged-delivery/assessment.json")["cases"]
for bundle in decision["candidate_bundles"]:
    archive = HERE / "final-bundles/assets" / bundle["bundle"]
    assert sha(archive.read_bytes()) == bundle["bundle_sha256"]
    assert archive.with_suffix(".zip.sha256").read_text(encoding="utf-8") == bundle["bundle_sha256"] + "  " + archive.name + "\n"
    target_cases = [c for c in cases if c["target"] == bundle["target"]]
    assert len(target_cases) == 2 and all(c["passed"] is True and c["artifact_sha256"] == bundle["jar_sha256"] for c in target_cases)
    with zipfile.ZipFile(archive) as files:
        artifact = f"mtr-memory-saver-{bundle['target']}-0.4.8.jar"
        assert sha(files.read(artifact)) == bundle["jar_sha256"]
        validation = json.loads(files.read("docs/VALIDATION.json"))
        assert validation["status"] == "verified-packaged-scope" and validation["cases"] == target_cases
    assert read(HERE / "final-bundles" / bundle["target"] / "build.execution.json")["exit_code"] == 0
for step in ("checksums", "verify-assets"):
    assert read(HERE / "final-bundles" / (step + ".execution.json"))["exit_code"] == 0
print(json.dumps({"verified_bundles": len(decision["candidate_bundles"]), "release_status": "held", "performance_accepted": False}))
