"""Freeze exact build receipts and inputs for the two observed installed tool JARs."""

import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[3]
folder = Path(__file__).resolve().parent
output = folder / "build-bindings"
output.mkdir(exist_ok=False)
bindings = json.loads((folder / "assessment-03/installed-bindings.json").read_bytes())
checks = []
for mod in bindings["mods"]:
    if mod["role"] not in {"observer", "companion"}:
        continue
    name = mod["filename"]
    manifest_path = root / "build/libs" / (Path(name).stem + ".build.json")
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["sha256"] == mod["sha256"]
    target = output / mod["role"]
    target.mkdir()
    shutil.copyfile(manifest_path, target / manifest_path.name)
    rows = []
    for relative, expected in manifest["inputs"].items():
        source = root / relative
        raw = source.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        destination = target / "inputs" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        rows.append({"path": relative, "expected_sha256": expected, "actual_sha256": actual, "matches": actual == expected})
    checks.append({"role": mod["role"], "artifact": name, "artifact_sha256": mod["sha256"], "inputs": rows})
(output / "assessment.json").write_text(json.dumps({"bound_manifests": checks, "all_current_inputs_match": all(r["matches"] for m in checks for r in m["inputs"])}, indent=2) + "\n", encoding="utf-8")
assert all(r["matches"] for m in checks for r in m["inputs"])
print(json.dumps({"bound_input_counts": {m["role"]: len(m["inputs"]) for m in checks}, "passed": True}))
