"""Freeze current read-only startup evidence before any later reload grows it."""

import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "tools"))
from windows_snapshot_io import read_snapshot_bytes

instance = root / ".cache/acceptance/official-nf248-owned-049"
output = Path(__file__).resolve().parent / "capture-01"
output.mkdir(exist_ok=False)
report = {"started": dt.datetime.now(dt.timezone.utc).isoformat(), "instance": str(instance),
          "scope": "Live startup prefix only", "files": {}}
for relative in ("game-probe/native-observer.json", "logs/latest.log", "game-probe/native-resource-epochs.jsonl",
                 "game-probe/native-invalid-model.jsonl", "screenshots/2026-11-16_19.25.21.png",
                 "packaged-client-plan.json", "packaged-client-launch.json", "options.txt"):
    source, target = instance / relative, output / relative
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    size_before = source.stat().st_size
    raw = read_snapshot_bytes(source) if relative == "game-probe/native-observer.json" else source.read_bytes()
    ended = dt.datetime.now(dt.timezone.utc).isoformat()
    size_after = source.stat().st_size
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    report["files"][relative] = {"read_started": started, "read_ended": ended, "bytes": len(raw),
                                "source_size_before": size_before, "source_size_after": size_after,
                                "sha256": hashlib.sha256(raw).hexdigest()}
report["ended"] = dt.datetime.now(dt.timezone.utc).isoformat()
(output / "freeze.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
(output / "freeze-script.py").write_bytes(Path(__file__).read_bytes())
print(json.dumps(report))
