"""Index the completed snapshot-I/O observations and their exact source bytes."""
import datetime as dt
import hashlib
import json
import pathlib
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTPUT = pathlib.Path(__file__).resolve().parent
assessment = {"timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
              "version": "0.4.6", "scope": "Official beta.2 snapshot I/O verification; product sources and JAR bytes unchanged",
              "java_tests": {}, "windows_packaged_reader_audits": {}}
for target in ("official-nf248", "official-nf265"):
    suites = [ET.parse(path).getroot() for path in (OUTPUT / (target + "-junit")).glob("*.xml")]
    counts = {key: sum(int(suite.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}
    if counts != {"tests": 66, "failures": 0, "errors": 0, "skipped": 0}:
        raise ValueError("Unexpected completed core test results: " + target + " " + repr(counts))
    assessment["java_tests"][target] = counts
    audit = "windows-lock-" + target.removeprefix("official-")
    result = json.loads((OUTPUT / audit / "result.json").read_text(encoding="utf-8"))
    execution = json.loads((OUTPUT / audit / "execution.json").read_text(encoding="utf-8"))
    if not result["passed"] or not execution["passed"] or result["lock_exit_code"] or result["remaining_snapshot_files"]:
        raise ValueError("Actual Windows observation did not pass: " + target)
    assessment["windows_packaged_reader_audits"][target] = {
        "passed": True, "artifact_sha256": execution["artifact_identity"]["sha256"],
        "deletion_error": result["deletion_error_type"], "snapshot_retained_on_error": True,
        "active_read_scopes": result["active_read_scopes"], "lock_exit_code": result["lock_exit_code"],
        "fixture_cleanup_after_unlock": result["fixture_cleanup_after_unlock"], "result": audit + "/result.json"}
assessment["new_headless_cases"] = ["snapshot output write and same-path cache retry", "snapshot output close",
    "snapshot restoration read", "snapshot deletion retaining real file", "original write with suppressed deletion failure"]
assessment["limits"] = ["Forwarding java.nio fixtures inject exact snapshot operation failures without filling the user's disk.",
    "Actual Windows audit runs the unchanged packaged reader, not a Minecraft/NeoForge client.",
    "Failed deletion retains a file and reports failure; successful test-owned cleanup after unlocking is not automatic product recovery.",
    "Real disk-full, abrupt JVM exit and automatic stale-snapshot recovery remain separate coverage."]
(OUTPUT / "assessment.json").write_text(json.dumps(assessment, indent=2) + "\n", encoding="utf-8")
paths = [path for path in OUTPUT.rglob("*") if path.is_file() and "binary" not in path.parts and path.name != "sha256.json"]
source_paths = [ROOT / "src/test/java/site/benli06/SnapshotFilesystemFailureTest.java",
    ROOT / "src/test/java/site/benli06/SnapshotFaultFileSystem.java",
    ROOT / "tools/acceptance/java/WindowsSnapshotFileLockAudit.java", ROOT / "tools/acceptance/fixtures/hold_snapshot.ps1",
    ROOT / "tools/acceptance/snapshot_windows_audit.py"]
index = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
         for path in sorted(paths + source_paths)}
(OUTPUT / "sha256.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
print(json.dumps(assessment))
