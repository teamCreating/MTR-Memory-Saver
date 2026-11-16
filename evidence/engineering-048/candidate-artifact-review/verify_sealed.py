"""Verify the sealed audit inventory without using its comparison implementation."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile


base = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
assert not out.exists(), "Refusing to overwrite verification evidence"
index = json.loads((base / "SHA256SUMS.json").read_text(encoding="utf-8"))
actual_files = {path.relative_to(base).as_posix() for path in base.rglob("*")
                if path.is_file() and path.name != "SHA256SUMS.json"}
assert actual_files == set(index), "Sealed file inventory differs"
for name, expected in index.items():
    assert hashlib.sha256((base / name).read_bytes()).hexdigest() == expected, name

report = json.loads((base / "assessment.json").read_text(encoding="utf-8"))
assert report["passed"] is True
assert report["source_fingerprints_before"] == report["source_fingerprints_after"]
for name, expected in report["source_fingerprints_before"].items():
    assert hashlib.sha256((base / "inputs" / name).read_bytes()).hexdigest() == expected, name

verified_targets = []
for target in report["targets"]:
    with zipfile.ZipFile(base / "inputs" / target["reference"]["jar"]) as old_zip:
        with zipfile.ZipFile(base / "inputs" / target["candidate"]["jar"]) as new_zip:
            old_names = {name for name in old_zip.namelist() if not name.endswith("/")}
            new_names = {name for name in new_zip.namelist() if not name.endswith("/")}
            assert old_names == new_names
            assert len(target["members"]) == len(new_names)
            assert {member["name"] for member in target["members"]} == new_names
            actual_changed = []
            for member in target["members"]:
                name = member["name"]
                old, new = old_zip.read(name), new_zip.read(name)
                assert hashlib.sha256(old).hexdigest() == member["reference_sha256"]
                assert hashlib.sha256(new).hexdigest() == member["candidate_sha256"]
                assert len(old) == member["reference_bytes"]
                assert len(new) == member["candidate_bytes"]
                assert (old == new) == member["unchanged"]
                if old != new:
                    actual_changed.append(name)
            assert sorted(actual_changed) == target["payload_comparison"]["changed"]
            verified_targets.append({"target": target["target"],
                                     "verified_member_payloads": len(new_names)})

result = {"timestamp": datetime.now(timezone.utc).isoformat(), "passed": True,
          "scope": "Recomputed every sealed file and archived ZIP member digest; no original workspace artifacts or audit module were loaded",
          "sealed_files": len(index),
          "source_fingerprints": len(report["source_fingerprints_before"]),
          "targets": verified_targets, "argv": sys.argv,
          "python": sys.executable}
out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
