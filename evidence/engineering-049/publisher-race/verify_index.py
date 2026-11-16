"""Read-only verification of the sealed publisher engineering evidence."""
import hashlib
import json
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
inventory = json.loads((root / "sha256-index.json").read_text(encoding="utf-8"))
for name, expected in inventory["files"].items():
    file = root / name
    data = file.read_bytes()
    assert len(data) == expected["bytes"], name
    assert hashlib.sha256(data).hexdigest() == expected["sha256"], name

base = root / "sealed-01"
for target in ("official-nf248", "official-nf265"):
    output = base / target
    manifest = json.loads((output / f"mtr-native-observer-{target}-1.0.3.build.json").read_text())
    candidate = output / manifest["artifact"]
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == manifest["sha256"]
    for name, digest in manifest["inputs"].items():
        assert hashlib.sha256((base / "source" / name).read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(output / "reference-1.0.2.jar") as before, zipfile.ZipFile(candidate) as after:
        assert set(before.namelist()) == set(after.namelist())
        for name in ("META-INF/MANIFEST.MF", "META-INF/neoforge.mods.toml", "mtr-native-observer-target.json"):
            assert before.read(name).replace(b"1.0.2", b"1.0.3") == after.read(name)
        for name in after.namelist():
            if name.endswith(".class") and not name.startswith("dev/abenli/probeio/"):
                assert before.read(name) == after.read(name), name
    suites = [ET.parse(file).getroot() for file in (output / "junit").glob("TEST-*.xml")]
    assert sum(int(suite.get("tests")) for suite in suites) == 27
    assert sum(int(suite.get(field)) for suite in suites for field in ("failures", "errors", "skipped")) == 0

print(json.dumps({"verified_payloads": len(inventory["files"]), "official_targets": 2,
                  "tests_per_target": 27, "scope": "Probe engineering only"}))
