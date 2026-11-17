"""Copy only the previously frozen original 0.4.7 Java inputs, not live source."""
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BACKUP = ROOT / ".cache/acceptance/owned049d-oom-diagnostics/product-source-047"
OUTPUT = HERE / "capture-01/product-source-047"
OUTPUT.mkdir(exist_ok=False)
plan = json.loads((HERE / "capture-01/recorder/packaged-client-plan.json").read_bytes())
receipt_raw = (BACKUP / "source-receipt.json").read_bytes()
receipt = json.loads(receipt_raw)
if receipt["artifact_sha256"] != plan["artifact"]["sha256"]:
    raise ValueError("Original Java backup belongs to another artifact.")
expected = {name: digest for name, digest in plan["artifact"]["inputs"].items() if name.endswith(".java")}
if {row["path"] for row in receipt["files"]} != set(expected):
    raise ValueError("Original Java source inventory differs from the artifact inputs.")
(OUTPUT / "source-receipt.json").write_bytes(receipt_raw)
copies = []
for row in receipt["files"]:
    source, target = BACKUP / row["path"], OUTPUT / row["path"]
    if not source.resolve().is_relative_to(BACKUP.resolve()) or not target.resolve().is_relative_to(OUTPUT.resolve()):
        raise ValueError("Original source path escapes its declared backup.")
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected[row["path"]] or actual != row["sha256"] or len(raw) != row["bytes"] or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("Previously frozen original Java source differs: " + row["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(raw)
    copies.append({"path": row["path"], "source": str(source), "started_at": started,
        "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "bytes": len(raw), "sha256": actual})
(OUTPUT / "copy-receipts.json").write_text(json.dumps({"scope": "Post-run copies of the parent-frozen exact 0.4.7 Java backup; no live source read or runtime modification.", "copies": copies}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"original_java_files": len(copies), "bytes": sum(row["bytes"] for row in copies), "artifact_sha256": receipt["artifact_sha256"]}))
