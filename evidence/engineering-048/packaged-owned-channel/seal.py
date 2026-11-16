"""Inventory and independently rehash exact packaged evidence bytes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


EXCLUDED = {"SHA256SUMS.json", "sealed-verification.json"}


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_file() and relative not in EXCLUDED and "__pycache__" not in path.parts:
            with path.open("rb") as stream:
                result[relative] = {"bytes": path.stat().st_size,
                                    "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "verify"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.root.resolve()
    actual = inventory(root)
    output = root / ("SHA256SUMS.json" if args.action == "capture" else "sealed-verification.json")
    if output.exists():
        raise ValueError("Do not overwrite the immutable evidence inventory/result")
    if args.action == "capture":
        result = {"timestamp": datetime.now(timezone.utc).isoformat(), "files": actual,
                  "excluded_from_cycle": sorted(EXCLUDED)}
    else:
        expected = json.loads((root / "SHA256SUMS.json").read_text(encoding="utf-8"))["files"]
        if actual != expected:
            raise ValueError("Evidence inventory/file content differs from the sealed record")
        result = {"timestamp": datetime.now(timezone.utc).isoformat(), "passed": True,
                  "payload_files": len(actual), "all_lengths_and_sha256_matched": True,
                  "inventory_sha256": hashlib.sha256((root / "SHA256SUMS.json").read_bytes()).hexdigest(),
                  "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"action": args.action, "payload_files": len(actual), "passed": True}))
