"""Verify exact abrupt-exit receipts and keep audit success separate from product cleanup."""
import datetime as dt
import hashlib
import json
import pathlib
import zipfile

OUT = pathlib.Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


targets = []
for target in ("official-nf248", "official-nf265"):
    directory = OUT / target
    execution = read(directory / "execution.json")
    identity = execution["artifact_identity"]
    assert execution["passed"] and not execution["product_cleanup_after_halt"]
    assert not execution["later_read_reclaims_prior_residue"]
    artifact = directory / identity["artifact"]
    assert sha(artifact) == identity["sha256"]
    trials = execution["trials"]
    assert [row["exit_code"] for row in trials] == [0, 74, 0, 74, 0]
    assert len({row["pid"] for row in trials}) == 5
    for row in trials:
        if row["mode"] == "halt":
            assert row["halt_bypassed_cleanup_confirmed"]
            path = pathlib.Path(row["observed_before_halt"]["snapshot"])
            assert sha(path) == row["observed_before_halt"]["sha256"]
        else:
            assert row["normal_cleanup_confirmed"] and row["before"] == row["after"]
    with zipfile.ZipFile(artifact) as archive:
        payloads = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()
                    if name.endswith(".class") and name.startswith(tuple("site/benli06/" + name for name in
                        ("SegmentedResourceText", "ReadAdmission", "TextWorkspace")))}
    targets.append({"target": target, "artifact": artifact.relative_to(OUT).as_posix(), "sha256": sha(artifact),
        "version": identity["version"], "child_processes": [row["pid"] for row in trials],
        "exit_codes": [row["exit_code"] for row in trials], "reader_class_payloads": payloads,
        "retained_abrupt_snapshots": [{"bytes": row["observed_before_halt"]["bytes"],
            "sha256": row["observed_before_halt"]["sha256"]} for row in trials if row["mode"] == "halt"]})
assert targets[0]["reader_class_payloads"] == targets[1]["reader_class_payloads"]
control = read(OUT / "delete-on-close-control-shared-reader/execution.json")
assert control["passed"] and control["exit_code"] == 75
assert control["before_halt"]["disk_bytes"] == 70000
assert control["before_halt"]["independent_utf16_bytes_equal"]
assert not control["after_halt"]["snapshot_exists"] and not control["after_halt"]["shutdown_hook_ran"]
save(OUT / "assessment.json", {"timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
    "utc_offset": "+08:00", "audit_observations_verified": True, "product_cleanup_after_halt": False,
    "targets": targets, "delete_on_close_feasibility_verified": True,
    "feasibility_scope": "Actual Windows/JDK-only channel, not patched product",
    "disk_full_executed": False, "disk_full_capability_inspection": "disk-full-capabilities.json",
    "product_source_changed": False, "proposed_follow_up": "proposal.md",
    "limits": ["A terminated JVM has no surviving admission statistics to measure; no zero counters are invented.",
               "Two abrupt spills accumulate two files per target; normal restart preserves earlier residues and other owners.",
               "No shared-temp sweep, volume allocation, filesystem fill or product patch was performed.",
               "The failed first feasibility control remains separate; its reader denied delete sharing."]})
save(OUT / "sha256.json", [{"path": path.relative_to(OUT).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}
    for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "sha256.json" and "__pycache__" not in path.parts])
print(json.dumps({"targets": 2, "owned_product_jvms": 10, "abrupt_residues": 4,
                  "delete_on_close_control_passed": True, "product_cleanup_after_halt": False}))
