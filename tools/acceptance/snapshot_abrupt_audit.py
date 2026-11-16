"""Observe controlled abrupt JVM exit after real packaged-reader spill in an isolated temp directory."""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.parse
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from windows_snapshot_io import read_snapshot_bytes


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def inventory(directory):
    return [{"name": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(read_snapshot_bytes(path)).hexdigest()}
            for path in sorted(directory.iterdir()) if path.is_file()]


def code_path(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "file":
        raise ValueError("Unexpected JVM code source URI")
    name = urllib.parse.unquote(parsed.path)
    if len(name) > 2 and name[0] == "/" and name[2] == ":":
        name = name[1:]
    return pathlib.Path(name).resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", type=pathlib.Path, required=True)
    parser.add_argument("--artifact", type=pathlib.Path, required=True)
    parser.add_argument("--mtr", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--expect-cleanup", choices=("retained", "removed"), default="retained")
    args = parser.parse_args()
    java, artifact, mtr, output = (value.resolve() for value in (args.java, args.artifact, args.mtr, args.output))
    output.mkdir(parents=True, exist_ok=False)
    execution = {"started": stamp(), "passed": False, "commands": [], "trials": [],
                 "limits": "Controlled child Runtime.halt after actual disk bytes, not a game crash, power loss, disk-full or automatic cleanup pass."}
    def record():
        save(output / "execution.json", execution)
    record()
    try:
        manifest = artifact.with_suffix(".build.json")
        identity = read(manifest)
        with zipfile.ZipFile(artifact) as archive:
            embedded = json.loads(archive.read("mtr-memory-target.json"))
        if not identity["target"].startswith("official-") or embedded.get("variant") != "official":
            raise ValueError("Require an explicitly identified official packaged candidate")
        if digest(artifact) != identity["sha256"] or digest(mtr) != identity["mtrSha256"]:
            raise ValueError("Artifact or MTR dependency differs from adjacent identity")
        for name in ("version", "target", "neoForge", "mtrSha256"):
            if embedded[name] != identity[name]:
                raise ValueError("Embedded/adjacent identity mismatch: " + name)
        source = ROOT / "tools/acceptance/java/AbruptSnapshotAudit.java"
        classes = output / "classes"
        classes.mkdir()
        source_copy = output / source.name
        shutil.copy2(source, source_copy)
        shutil.copy2(pathlib.Path(__file__), output / pathlib.Path(__file__).name)
        shutil.copy2(manifest, output / "artifact.build.json")
        execution["inputs"] = {str(path): digest(path) for path in (java, java.with_name("javac.exe"), artifact, manifest, mtr, source, pathlib.Path(__file__), ROOT / "tools/windows_snapshot_io.py")}
        execution["expected_cleanup"] = args.expect_cleanup
        execution["artifact_identity"] = identity
        command = [str(java.with_name("javac.exe")), "-proc:none", "-encoding", "UTF-8", "--release", "21",
                   "-cp", str(artifact) + ";" + str(mtr), "-d", str(classes), str(source)]
        compilation = {"command": command, "started": stamp()}
        execution["commands"].append(compilation)
        record()
        completed = subprocess.run(command, capture_output=True, timeout=60)
        (output / "compile.stdout.log").write_bytes(completed.stdout)
        (output / "compile.stderr.log").write_bytes(completed.stderr)
        compilation.update(exit_code=completed.returncode, ended=stamp())
        record()
        if completed.returncode:
            raise RuntimeError("Audit compilation failed")
        execution["classes"] = {path.relative_to(classes).as_posix(): digest(path) for path in classes.rglob("*.class")}
        if any(not name.startswith("site/benli06/AbruptSnapshotAudit") for name in execution["classes"]):
            raise ValueError("Unexpected class could replace the packaged reader")
        temporary = output / "owned-tmp"
        temporary.mkdir()
        sentinel = temporary / "mtr-memory-text-existing-owner.utf16"
        sentinel.write_bytes(b"Preexisting other-owner sentinel; the reader must never sweep it.\n")
        initial = inventory(temporary)

        def trial(name, mode):
            directory = output / name
            directory.mkdir()
            before = inventory(temporary)
            command = [str(java), "-Xmx128m", "-Djava.io.tmpdir=" + str(temporary), "-cp",
                str(classes) + ";" + str(artifact) + ";" + str(mtr), "site.benli06.AbruptSnapshotAudit", mode, str(directory)]
            item = {"name": name, "mode": mode, "command": command, "started": stamp(), "before": before}
            execution["trials"].append(item)
            record()
            with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
                child = subprocess.Popen(command, stdout=stdout, stderr=stderr)
                item["pid"] = child.pid
                record()
                try:
                    if mode in ("halt", "wait"):
                        deadline = time.monotonic() + 40
                        ready_path = directory / "spill-ready.json"
                        while not ready_path.exists():
                            if child.poll() is not None or time.monotonic() > deadline:
                                raise RuntimeError("Child did not establish real spill readiness")
                            time.sleep(0.01)
                        # The child closes this small record before awaiting our signal.
                        ready = read(ready_path)
                        if ready["pid"] != child.pid or code_path(ready["reader_code_source"]) != artifact or code_path(ready["admission_code_source"]) != artifact:
                            raise ValueError("Readiness does not belong to the exact packaged reader child")
                        path = pathlib.Path(ready["snapshot"]).resolve()
                        if path.parent != temporary or path.name in {entry["name"] for entry in before}:
                            raise ValueError("Snapshot is outside owned fresh spill")
                        if path.stat().st_size <= 0 or path.stat().st_size != ready["snapshot_bytes"]:
                            raise ValueError("Actual spill bytes absent or changed while child is paused")
                        item["observed_before_halt"] = {"timestamp": stamp(), "snapshot": str(path),
                            "bytes": path.stat().st_size, "sha256": hashlib.sha256(read_snapshot_bytes(path)).hexdigest(), "child_running": child.poll() is None,
                            "workspace_statistics": ready["workspace_statistics"]}
                        try:
                            with path.open("rb") as ordinary_reader:
                                ordinary_reader.read(1)
                            item["ordinary_reader"] = {"opened_without_delete_sharing": True}
                        except PermissionError as sharing_error:
                            item["ordinary_reader"] = {"opened_without_delete_sharing": False,
                                "error": repr(sharing_error), "winerror": getattr(sharing_error, "winerror", None)}
                        if args.expect_cleanup == "removed" and item["ordinary_reader"]["opened_without_delete_sharing"]:
                            raise ValueError("Snapshot does not retain the expected Windows delete-on-close ownership")
                        if mode == "wait" and ready["workspace_statistics"][3] != 1:
                            raise ValueError("Reader was not waiting for its full text budget")
                        if mode == "halt" and (ready["source_bytes_remaining"] <= 0 or ready["snapshot_bytes"] >= ready["expected_utf16_bytes"]):
                            raise ValueError("Writing halt did not observe an incomplete snapshot with source bytes remaining")
                        record()
                        (directory / "halt-after-observation").write_text("Parent observed real snapshot bytes; halt only this audit child.\n", encoding="utf-8")
                    item["exit_code"] = child.wait(timeout=45)
                finally:
                    if child.poll() is None:
                        child.kill()
                        item["timeout_cleanup"] = {"owned_pid": child.pid, "exit_code": child.wait(timeout=10)}
                    item["ended"] = stamp()
                    item["after"] = inventory(temporary)
                    record()
            if mode in ("halt", "wait"):
                prior = item["observed_before_halt"]
                if item["exit_code"] != 74:
                    raise ValueError("Abrupt exit code differs")
                if args.expect_cleanup == "retained":
                    after = next(entry for entry in item["after"] if entry["name"] == pathlib.Path(prior["snapshot"]).name)
                    if after["bytes"] != prior["bytes"] or after["sha256"] != prior["sha256"]:
                        raise ValueError("Preserved residue differs")
                elif item["after"] != before or pathlib.Path(prior["snapshot"]).exists():
                    raise ValueError("Abrupt snapshot was not removed or another owner's files changed")
                if any((directory / name).exists() for name in ("shutdown-hook-ran", "caller-stream-closed", "result.json")):
                    raise ValueError("Halt unexpectedly ran normal cleanup")
                item["halt_bypassed_cleanup_confirmed"] = True
                item["snapshot_removed_after_halt"] = args.expect_cleanup == "removed"
            else:
                result = read(directory / "result.json")
                ready = read(directory / "spill-ready.json")
                if item["exit_code"] != 0 or not result["passed"] or item["after"] != before:
                    raise ValueError("Normal read changed prior residue or failed cleanup")
                if ready["pid"] != child.pid or code_path(ready["reader_code_source"]) != artifact:
                    raise ValueError("Normal control used a different reader")
                if not (directory / "shutdown-hook-ran").exists() or (directory / "caller-stream-closed").read_text() != "1":
                    raise ValueError("Normal cleanup controls were absent")
                item["normal_cleanup_confirmed"] = True
            record()

        trial("normal-before", "normal")
        trial("abrupt-writing", "halt")
        trial("restart-after-writing", "normal")
        trial("abrupt-waiting", "wait")
        trial("restart-after-waiting", "normal")
        final = inventory(temporary)
        expected_files = len(initial) + (2 if args.expect_cleanup == "retained" else 0)
        if len(final) != expected_files:
            raise ValueError("Unexpected final snapshot ownership")
        for entry in initial:
            if entry not in final:
                raise ValueError("An existing owner file was changed")
        if any(digest(pathlib.Path(name)) != expected for name, expected in execution["inputs"].items()):
            raise ValueError("An audit input changed during execution")
        execution.update(passed=True, ended=stamp(), residue_after_two_halts=final,
            product_cleanup_after_halt=args.expect_cleanup == "removed", later_read_reclaims_prior_residue=False,
            notes="Audit matches its explicit cleanup expectation. Later readers preserve other-owner files; no stale-temp sweep is performed.")
        record()
        print(json.dumps({"passed": True, "target": identity["target"], "abrupt_exits": 2,
            "normal_controls": 3, "retained_files": len(final), "product_cleanup_after_halt": args.expect_cleanup == "removed"}))
    except BaseException as failure:
        execution.update(passed=False, error=repr(failure), ended=stamp())
        record()
        raise


if __name__ == "__main__":
    main()
