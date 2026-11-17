"""Derive only packaged-check scope from the sealed four-JVM evidence."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCE = REPO / "evidence/engineering-051/streamed-obj-input"
INDEX = json.loads((SOURCE / "SHA256.json").read_bytes())


def read(name, binary=False):
    data = (SOURCE / name).read_bytes()
    expected = INDEX[name]
    assert len(data) == expected["bytes"]
    assert hashlib.sha256(data).hexdigest() == expected["sha256"], name
    return data if binary else json.loads(data)


def assessment():
    cases = []
    bindings = {}
    for short in ("nf248", "nf265"):
        for mode, suffix, exit_code in (("faults", "smoke01", 0), ("mismatch", "mismatch01", 1)):
            prefix = f"clients/{short}-{suffix}/"
            names = ["capture/execution.json", "capture/packaged-client-plan.json",
                     "capture/packaged-client-launch.json", "jfr-check.json", "jfr-summary.stdout.log"]
            execution, plan, launch, jfr = [read(prefix + n) for n in names[:4]]
            assert execution["status"] == "exited" and execution["exit_code"] == exit_code
            assert execution["pid"] == launch["pid"] == jfr["pid"]
            assert jfr["jvm_exit_code"] == exit_code and jfr["jfr_summary_exit"] == 0
            assert jfr["jfr_bytes"] > 0 and len(jfr["jfr_sha256"]) == 64
            assert b"Version:" in read(prefix + names[-1], binary=True)
            assert launch["plan_sha256"] == INDEX[prefix + names[1]]["sha256"]
            artifact = plan["artifact"]
            assert artifact["version"] == "0.4.8" and artifact["target"] == "official-" + short
            row = {"target": artifact["target"], "mode": mode, "pid": execution["pid"],
                   "exit_code": exit_code, "artifact_sha256": artifact["sha256"],
                   "plan_sha256": launch["plan_sha256"], "launch_receipt_timestamp": launch["timestamp"],
                   "jfr_sha256": jfr["jfr_sha256"], "passed": True}
            if mode == "faults":
                name = prefix + "loader-lifecycle-result.json"
                result = read(name)
                assert result["passed"] is True
                counts = {}
                for field in ("checks", "strict_resource_checks", "obj_input_checks"):
                    group = result[field]
                    assert group and all(value is True for value in group.values())
                    counts[field] = len(group)
                workspace = result["strict_resource_observations"]["workspace_after"]
                assert workspace["used_bytes"] == workspace["waiting_requests"] == 0
                row.update(lifecycle_checks=counts["checks"], strict_resource_checks=counts["strict_resource_checks"],
                           obj_input_checks=counts["obj_input_checks"], settled_workspace=True)
                names.append("loader-lifecycle-result.json")
            else:
                assert plan["expected_binary_rejection"] is True
                assert prefix + "loader-lifecycle-result.json" not in INDEX
                names += ["capture/launch.stderr.log", "capture/logs/latest.log"]
                error = read(prefix + names[-2], binary=True)
                log = read(prefix + names[-1], binary=True)
                assert b"Loaded MTR fingerprint does not match the audited build target" in error
                assert not re.search(rb"Loaded (\d+) vehicles and completed door movement validation", log)
                row["rejected_before_registration"] = True
            for name in names:
                read(prefix + name, binary=True)
                bindings[prefix + name] = INDEX[prefix + name]
            cases.append(row)
    return {"schema_version": 1, "passed": True, "cases": cases,
            "scope": "Exact-artifact packaged lifecycle, strict-resource and OBJ/MTL checks, normal shutdown, readable JFR, and incorrect-binary rejection only. This record does not certify reload endurance, complete gameplay, route duration or controlled performance.",
            "source": "evidence/engineering-051/streamed-obj-input", "source_bindings": bindings}


if __name__ == "__main__":
    value = assessment()
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    destination = HERE / "assessment.json"
    if destination.exists():
        assert destination.read_bytes() == encoded, "Saved derivative differs from original sealed inputs"
    else:
        destination.write_bytes(encoded)
    print(json.dumps({"passed": True, "cases": len(value["cases"]), "assessment_sha256": hashlib.sha256(encoded).hexdigest()}))
