"""Cross-check and seal the already-completed owned-channel evidence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
TARGETS = ("official-nf248", "official-nf265")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copied(source, destination, expected=None):
    data = source.read_bytes()
    if expected is not None:
        assert hashlib.sha256(data).hexdigest() == expected, source
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        assert destination.read_bytes() == data, destination
    else:
        destination.write_bytes(data)


def junit(directory):
    totals = dict(tests=0, failures=0, errors=0, skipped=0)
    files = sorted(directory.glob("TEST-*.xml"))
    assert len(files) == 10, directory
    for path in files:
        attributes = ET.parse(path).getroot().attrib
        for key in totals:
            totals[key] += int(attributes[key])
    assert totals == dict(tests=73, failures=0, errors=0, skipped=0), totals
    return totals


def jar_source(url):
    value = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    if len(value) > 2 and value.startswith("/") and value[2] == ":":
        value = value[1:]
    return Path(value).resolve()


def main():
    replay = read(BASE / "build-replay/execution.json")
    assert replay["passed"] and len(replay["commands"]) == 2
    assert sha(BASE / "build_replay.py") == replay["runner_sha256"]
    assessment = {"timestamp": datetime.now(timezone.utc).isoformat(), "passed": False,
                  "targets": [], "abrupt": [], "large_text": [], "input_freeze": {}}
    manifests = {}
    for target, receipt in zip(TARGETS, replay["commands"], strict=True):
        manifest_path, = (BASE / target).glob("*.build.json")
        manifest = read(manifest_path)
        manifests[target] = manifest
        assert receipt["passed"] and receipt["target"] == target and receipt["exit_code"] == 0
        assert f"-PmodVersion={manifest['version']}" in receipt["command"]
        assert "--rerun-tasks" in receipt["command"]
        assert receipt["started"] < receipt["ended"]
        candidate = BASE / target / manifest["artifact"]
        assert sha(candidate) == manifest["sha256"] == receipt["artifact_sha256"]
        replay_dir = BASE / "build-replay" / target
        assert sha(replay_dir / candidate.name) == manifest["sha256"]
        assert (replay_dir / manifest_path.name).read_bytes() == manifest_path.read_bytes()
        for relative, expected in manifest["inputs"].items():
            copied(ROOT / relative, BASE / "inputs" / relative, expected)
        old_dir = BASE.parent / "snapshot-abrupt" / target
        old_manifest = read(old_dir / "artifact.build.json")
        old = old_dir / old_manifest["artifact"]
        assert sha(old) == old_manifest["sha256"]
        with zipfile.ZipFile(old) as before, zipfile.ZipFile(candidate) as after:
            names = {name for name in before.namelist() if not name.endswith("/")}
            assert names == {name for name in after.namelist() if not name.endswith("/")}
            changed = sorted(name for name in names if before.read(name) != after.read(name))
            classes = sorted(name for name in names if name.endswith(".class"))
            changed_classes = [name for name in changed if name.endswith(".class")]
            assert changed_classes == ["site/benli06/SegmentedResourceText$Snapshot.class", "site/benli06/SegmentedResourceText.class"]
            metadata = [name for name in changed if not name.endswith(".class")]
            assert len(metadata) == 3
            for name in metadata:
                assert before.read(name).replace(old_manifest["version"].encode(), manifest["version"].encode()) == after.read(name), name
        assessment["targets"].append({"target": target, "artifact": candidate.relative_to(BASE).as_posix(),
            "sha256": manifest["sha256"], "initial_junit": junit(BASE / target / "junit"),
            "replayed_junit": junit(replay_dir / "junit"), "manifest_input_count": len(manifest["inputs"]),
            "jar_members": len(names), "class_count": len(classes), "changed_members": changed,
            "unchanged_classes": len(classes) - len(changed_classes), "metadata_only_version_changes": True,
            "old_artifact_sha256": old_manifest["sha256"], "reproduced_identical_jar_and_manifest": True})

    source_paths = {path.relative_to(ROOT).as_posix() for path in (ROOT / "src/test").rglob("*") if path.is_file()}
    source_paths.update({"gradle.properties", "tools/acceptance/java/AbruptSnapshotAudit.java",
        "tools/acceptance/java/LargeTextWorkspaceAudit.java", "tools/acceptance/snapshot_abrupt_audit.py",
        "tools/acceptance/README.md", "tools/windows_snapshot_io.py",
        "evidence/engineering-046/text-workspace/attempt-02/plan.json"})
    for relative in sorted(source_paths):
        copied(ROOT / relative, BASE / "inputs" / relative)
    verified_inputs = {}
    for name, expected_removed in (("abrupt-nf248", True), ("abrupt-nf265", True), ("old-reader-control", False)):
        directory = BASE / name
        execution = read(directory / "execution.json")
        assert execution["passed"] and execution["product_cleanup_after_halt"] == expected_removed
        assert execution["expected_cleanup"] == ("removed" if expected_removed else "retained")
        assert len(execution["trials"]) == 5
        for filename, expected in execution["inputs"].items():
            if filename not in verified_inputs:
                assert sha(filename) == expected, filename
                verified_inputs[filename] = expected
        for relative, expected in execution["classes"].items():
            assert sha(directory / "classes" / relative) == expected
        assert sha(directory / "AbruptSnapshotAudit.java") == sha(ROOT / "tools/acceptance/java/AbruptSnapshotAudit.java")
        assert sha(directory / "snapshot_abrupt_audit.py") == sha(ROOT / "tools/acceptance/snapshot_abrupt_audit.py")
        halts = []
        sentinel = execution["trials"][0]["before"]
        assert len(sentinel) == 1
        for trial in execution["trials"]:
            assert trial["pid"] > 0 and trial["started"] < trial["ended"]
            assert sentinel[0] in trial["after"]
            if trial["mode"] == "normal":
                result = read(directory / trial["name"] / "result.json")
                assert result["passed"] and result["pid"] == trial["pid"]
                assert trial["exit_code"] == 0 and trial["normal_cleanup_confirmed"]
                assert result["active_reads"] == 0 and result["workspace_statistics"][1] == 0
                continue
            ready = read(directory / trial["name"] / "spill-ready.json")
            observed = trial["observed_before_halt"]
            assert ready["pid"] == trial["pid"] and observed["child_running"]
            assert sha(jar_source(ready["reader_code_source"])) == execution["artifact_identity"]["sha256"]
            assert ready["reader_code_source"] == ready["admission_code_source"]
            assert observed["snapshot"] == ready["snapshot"] and observed["bytes"] == ready["snapshot_bytes"]
            assert trial["exit_code"] == 74 and trial["halt_bypassed_cleanup_confirmed"]
            assert trial["snapshot_removed_after_halt"] == expected_removed
            assert ready["active_read_scopes"] == 1
            assert not (directory / trial["name"] / "shutdown-hook-ran").exists()
            assert not (directory / trial["name"] / "caller-stream-closed").exists()
            if trial["mode"] == "wait":
                assert observed["bytes"] == ready["expected_utf16_bytes"] == 90008
                assert ready["source_bytes_remaining"] == 0
                assert observed["workspace_statistics"] == [240000, 120000, 240000, 1]
            else:
                assert 0 < observed["bytes"] == 65536 < ready["expected_utf16_bytes"]
                assert ready["source_bytes_remaining"] == 9007
                assert observed["workspace_statistics"][1] == 0
            if not expected_removed:
                assert sha(Path(ready["snapshot"])) == observed["sha256"]
            halts.append({"name": trial["name"], "pid": trial["pid"], "bytes": observed["bytes"],
                          "sha256": observed["sha256"], "removed": expected_removed})
        final = execution["residue_after_two_halts"]
        inventory = [{"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted((directory / "owned-tmp").iterdir())]
        assert inventory == final
        assert len(final) == (1 if expected_removed else 3)
        assessment["abrupt"].append({"directory": name, "target": execution["artifact_identity"]["target"],
            "version": execution["artifact_identity"]["version"], "normal_controls": 3, "halts": halts,
            "sentinel_preserved": True, "product_cleanup_after_halt": expected_removed})

    large = read(BASE / "large-text/execution.json")
    assert large["passed"] and len(large["trials"]) == 4
    for filename, expected in large["inputs"].items():
        if filename not in verified_inputs:
            assert sha(filename) == expected, filename
            verified_inputs[filename] = expected
    for relative, expected in large["classes"].items():
        assert sha(BASE / "large-text/classes" / relative) == expected
    copied(ROOT / "tools/acceptance/java/LargeTextWorkspaceAudit.java", BASE / "large-text/LargeTextWorkspaceAudit.java")
    for trial in large["trials"]:
        result = read(BASE / "large-text" / trial["output"])
        assert trial["passed"] and result["passed"]
        assert trial["artifact_sha256"] == manifests[trial["target"]]["sha256"]
        assert result["source_sha256"] == result["candidate_input_sha256"] == result["candidate_utf8_sha256"]
        assert result["oracle_decoded_utf16_units"] == result["candidate_decoded_utf16_units"] == 102035449
        assert result["active_read_scopes"] == 0 and not result["remaining_snapshot_files"]
        assert result["workspace_statistics"][1] == result["workspace_statistics"][3] == 0
        assert result["max_heap_bytes"] == 3 * 1024 ** 3 and result["snapshot_observed"]
        assert len(result["synthetic_controls"]) == 8
        assert all(item["native_equal"] and item["snapshot_observed"] for item in result["synthetic_controls"])
        raw_classes = (BASE / "large-text" / Path(trial["output"]).parent / "class-load.log").read_text(encoding="utf-8")
        for name, url in trial["actual_reader_class_sources"].items():
            assert f"site.benli06.{name} source: {url}" in raw_classes
            assert sha(jar_source(url)) == trial["artifact_sha256"]
        assessment["large_text"].append({"target": trial["target"], "mode": trial["mode"],
            "decoded_utf16_units": result["candidate_decoded_utf16_units"], "utf8_sha256": result["candidate_utf8_sha256"],
            "synthetic_controls": 8, "max_heap_bytes": result["max_heap_bytes"], "ownership_released": True})

    for path in sorted((BASE / "inputs").rglob("*")):
        if path.is_file():
            assessment["input_freeze"][path.relative_to(BASE / "inputs").as_posix()] = sha(path)
    assessment.update(passed=True, checked_execution_input_count=len(verified_inputs),
        boundaries=["Controlled Runtime.halt is not a game crash or power-loss test.",
                    "Actual filesystem-full, gameplay, resource reload, full route and performance acceptance remain separate.",
                    "Initial full logs lack structured command receipts; the separate replay has actual receipts.",
                    "The initial targeted log predates the final persistent-zero retirement test.",
                    "The old-reader audit passes expected retained-residue behavior, not cleanup acceptance.",
                    "V6 remains paused."])
    write(BASE / "assessment.json", assessment)
    index = [{"path": path.relative_to(BASE).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}
             for path in sorted(BASE.rglob("*"))
             if path.is_file() and path.name != "sha256.json" and "__pycache__" not in path.parts]
    write(BASE / "sha256.json", index)
    print(json.dumps({"passed": True, "indexed_files": len(index), "frozen_inputs": len(assessment["input_freeze"]),
                      "total_bytes": sum(item["bytes"] for item in index)}))


if __name__ == "__main__":
    main()
