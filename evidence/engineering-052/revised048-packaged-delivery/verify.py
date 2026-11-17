"""Offline validation of the selected delivery seal and original four JVMs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


index = json.loads((HERE / "SHA256.json").read_bytes())["files"]
actual = {p.relative_to(HERE).as_posix() for p in HERE.rglob("*") if p.is_file()}
assert actual == set(index) | {"SHA256.json"}
for name, expected in index.items():
    raw = (HERE / name).read_bytes()
    assert len(raw) == expected["bytes"] and sha(raw) == expected["sha256"], name
spec = importlib.util.spec_from_file_location("packaged_delivery_048", HERE / "derive.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
derived = module.assessment()
assert derived == json.loads((HERE / "assessment.json").read_bytes())
config = json.loads((REPO / "config/delivery-evidence.json").read_bytes())
records = [r for r in config["records"] if r["version"] == "0.4.8"]
assert len(records) == 2 and len({r["target"] for r in records}) == 2
for record in records:
    assert REPO / record["assessment"] == HERE / "assessment.json"
    assert record["assessmentSha256"] == sha((HERE / "assessment.json").read_bytes())
    cases = [r for r in derived["cases"] if r["target"] == record["target"]]
    assert len(cases) == 2 and {c["mode"] for c in cases} == {"faults", "mismatch"}
    assert all(c["passed"] is True and c["artifact_sha256"] == record["artifactSha256"] for c in cases)
    build = HERE / "build-checks" / record["target"]
    assert json.loads((build / "execution.json").read_bytes())["exit_code"] == 0
    asset = HERE / "build-checks/assets" / f"mtr-memory-saver-{record['target']}-0.4.8.zip"
    assert asset.with_suffix(".zip.sha256").read_text(encoding="utf-8") == sha(asset.read_bytes()) + "  " + asset.name + "\n"
    with zipfile.ZipFile(asset) as archive:
        validation = json.loads(archive.read("docs/VALIDATION.json"))
        assert validation["status"] == "verified-packaged-scope"
        assert validation["cases"] == cases and validation["scope"] == derived["scope"]
        assert validation["artifactSha256"] == record["artifactSha256"]
        assert validation["assessmentSha256"] == record["assessmentSha256"]
        artifact = f"mtr-memory-saver-{record['target']}-0.4.8.jar"
        assert sha(archive.read(artifact)) == record["artifactSha256"]
for action in ("checksums", "verify-assets"):
    assert json.loads((HERE / "build-checks" / (action + ".execution.json")).read_bytes())["exit_code"] == 0
print(json.dumps({"passed": True, "payloads": len(index), "cases": len(derived["cases"]),
                  "scope": "Packaged delivery only; no endurance or performance acceptance"}))
