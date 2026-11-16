"""Exercise the assessor against copied actual receipts; never modify originals."""
from datetime import datetime, timezone
from pathlib import Path
import copy
import json
import assess


BASE = Path(__file__).resolve().parent
original_read = assess.read
faults = "runtime/official-nf248-faults/"
mismatch = "runtime/official-nf248-mismatch/"


def set_value(*fields, value):
    def mutate(node):
        for field in fields[:-1]:
            node = node[field]
        node[fields[-1]] = value
    return mutate


controls = (
    ("wrong_process_owner", faults + "packaged-client-exit.json", set_value("pid", value=1)),
    ("unowned_exit", faults + "packaged-client-exit.json", set_value("observed_with_owned_handle", value=False)),
    ("wrong_candidate", faults + "execution.json", set_value("artifact_sha256", value="0" * 64)),
    ("unsealed_runner", faults + "execution.json", set_value("runner_sha256", value="0" * 64)),
    ("failed_lifecycle", faults + "loader-lifecycle-result.json", set_value("checks", "fault_counts_settled", value=False)),
    ("leaked_workspace", faults + "loader-lifecycle-result.json", set_value("strict_resource_observations", "workspace_after", "used_bytes", value=1)),
    ("missing_real_oversize", faults + "loader-lifecycle-result.json", set_value("strict_resource_observations", "oversized", "failed_read", "bytes_read", value=1)),
    ("transplanted_fault_time", faults + "loader-lifecycle-result.json", set_value("timestamp", value="2000-01-01T00:00:00+00:00")),
    ("unrelated_original_failure", faults + "execution.json", set_value("error", value="TimeoutError('still running')")),
    ("wrong_jfr_identity", faults + "final-input-verification.json", set_value("jfr_sha256", value="0" * 64)),
    ("missing_binary_rejection", mismatch + "execution.json", set_value("passed", value=False)),
    ("wrong_binary_control", "prepare/official-nf248-mismatch/mtr-comment-control.json", set_value("member_and_metadata_bytes_unchanged", value=False)),
)
results = []
for label, relative, mutation in controls:
    def altered_read(path):
        result = original_read(path)
        if path.resolve() == (BASE / relative).resolve():
            result = copy.deepcopy(result)
            mutation(result)
        return result
    assess.read = altered_read
    try:
        assess.verify(BASE)
    except ValueError as error:
        results.append({"control": label, "rejected": True, "reason": str(error)})
    else:
        raise AssertionError("Assessor accepted altered actual receipt: " + label)
    finally:
        assess.read = original_read
output = BASE / "negative-controls.json"
if output.exists():
    raise ValueError("Do not overwrite negative-control evidence")
output.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "passed": True,
    "source_sha256": assess.sha(Path(__file__)), "assessor_sha256": assess.sha(BASE / "assess.py"),
    "controls": results, "scope": "Copied dictionaries only; original actual receipts/artifacts remain unchanged."}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"passed": True, "controls": len(results)}))
