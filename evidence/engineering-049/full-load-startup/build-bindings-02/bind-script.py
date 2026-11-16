"""Freeze exact build receipts and inputs for the two observed installed tool JARs."""

import hashlib
import argparse
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[3]
folder = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
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
        resolution = "current"
        resolved_source = source
        if actual != expected:
            archived = root / "evidence/engineering-048/neutral-runtime-02-final/sealed-02/prefix/sources" / relative
            assert archived.is_file() and hashlib.sha256(archived.read_bytes()).hexdigest() == expected, relative
            raw = archived.read_bytes()
            resolution = "explicit_historical_exact_input"
            resolved_source = archived
        destination = target / "inputs" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        rows.append({"path": relative, "expected_sha256": expected, "current_sha256": actual, "current_matches": actual == expected,
                     "resolved_input_sha256": hashlib.sha256(raw).hexdigest(), "resolved_source": str(resolved_source),
                     "resolution": resolution, "matches": hashlib.sha256(raw).hexdigest() == expected})
    checks.append({"role": mod["role"], "artifact": name, "artifact_sha256": mod["sha256"], "inputs": rows})
(output / "assessment.json").write_text(json.dumps({"bound_manifests": checks, "all_current_inputs_match": all(r["current_matches"] for m in checks for r in m["inputs"]),
       "all_exact_inputs_resolved": all(r["matches"] for m in checks for r in m["inputs"])}, indent=2) + "\n", encoding="utf-8")
assert all(r["matches"] for m in checks for r in m["inputs"])
print(json.dumps({"bound_input_counts": {m["role"]: len(m["inputs"]) for m in checks}, "passed": True}))
