"""Read original rollover inputs once and retain exact bytes for offline controls."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import windows_snapshot_io

folder = Path(__file__).resolve().parent / "actual-inputs"
folder.mkdir(parents=True, exist_ok=False)
instance = ROOT / ".cache/acceptance/official-nf248-owned-049c"
paths = [(instance / "logs/2026-11-16-1.log.gz", "2026-11-16-1.log.gz"),
         (instance / "logs/latest.log", "latest-prefix.log"),
         (ROOT / "evidence/engineering-050/neutral103-startup/capture-01/observation/native-log-at-completion.log", "startup-prefix.log"),
         (instance / "packaged-client-plan.json", "plan.json"), (instance / "packaged-client-launch.json", "launch.json")]
receipts = []
for path, name in paths:
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    with windows_snapshot_io.open_snapshot(path) as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(before.st_size)
        after = os.fstat(stream.fileno())
    assert len(raw) == before.st_size and after.st_size >= before.st_size
    (folder / name).write_bytes(raw)
    receipts.append({"source": str(path), "file": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                     "started_at": started, "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "handle_file_id": [before.st_dev, before.st_ino], "source_size_before": before.st_size, "source_size_after": after.st_size})
(folder / "read-receipts.json").write_text(json.dumps({"files": receipts}, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"captured_inputs": len(receipts)}))
