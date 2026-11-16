"""Seal this small preparation evidence directory; never inspect or launch a client."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


output = BASE / "SHA256SUMS.json"
require(not output.exists(), "Do not overwrite a sealed index")
context = read(BASE / "context-assessment.json")
require(sha(BASE / "scenario.json") == context["scenario_sha256"], "Scenario changed")
require(sha(BASE / "complete_scenario.py") == context["source_sha256"], "Scenario builder changed")
require(sha(BASE / "source/config/client-experiment.json") == context["policy_sha256"], "Policy changed")
for manifest in (BASE / "artifacts").glob("*.build.json"):
    identity = read(manifest)
    require(sha(manifest.with_suffix("").with_suffix(".jar")) == identity.get("sha256", identity.get("output_sha256")),
            "Artifact manifest mismatch: " + str(manifest))
for proof in read(BASE / "source/config/native-diagnostic-review.json")["proofs"]:
    require(sha(BASE / "source" / proof["path"]) == proof["sha256"], "Native proof changed")
audit = read(BASE / "independent-audit-01.json")
require(audit["passed"] is True and audit["performance_accepted"] is False, "Missing scoped audit")
require(sha(BASE / "audit_preparation.py") == audit["source_sha256"], "Audit source changed")
files = {path.relative_to(BASE).as_posix(): {"sha256": sha(path), "bytes": path.stat().st_size}
         for path in sorted(BASE.rglob("*")) if path.is_file() and path != output}
with output.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump({"schema": 1, "timestamp": datetime.now(timezone.utc).isoformat(), "files": files,
               "scope": "Preparation records and independent read-only audit; no runtime/performance pass."},
              stream, indent=2, ensure_ascii=False)
    stream.write("\n")
print(json.dumps({"sealed_files": len(files), "bytes": sum(item["bytes"] for item in files.values()),
                  "performance_accepted": False}))
