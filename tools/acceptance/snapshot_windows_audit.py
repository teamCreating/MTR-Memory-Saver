"""Run the real Windows deletion-lock audit against an explicitly identified packaged reader."""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", type=pathlib.Path, required=True)
    parser.add_argument("--artifact", type=pathlib.Path, required=True)
    parser.add_argument("--mtr", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    execution = {"started": dt.datetime.now(dt.timezone.utc).isoformat(), "commands": []}

    def save():
        (output / "execution.json").write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")

    def run(name, command):
        entry = {"name": name, "command": command}
        execution["commands"].append(entry)
        save()
        result = subprocess.run(command, capture_output=True, timeout=90)
        (output / (name + ".stdout.log")).write_bytes(result.stdout)
        (output / (name + ".stderr.log")).write_bytes(result.stderr)
        entry["exit_code"] = result.returncode
        save()
        if result.returncode:
            raise RuntimeError(name + " failed; preserve this attempt")

    save()
    try:
        artifact, mtr, java = args.artifact.resolve(), args.mtr.resolve(), args.java.resolve()
        identity = json.loads(artifact.with_suffix(".build.json").read_text(encoding="utf-8"))
        if not identity["target"].startswith("official-") or identity["sha256"] != digest(artifact) or identity["mtrSha256"] != digest(mtr):
            raise ValueError("Require the exact recorded official packaged artifact and MTR dependency")
        with zipfile.ZipFile(artifact) as archive:
            embedded = json.loads(archive.read("mtr-memory-target.json"))
        for key in ("target", "version", "neoForge", "mtrSha256"):
            if identity[key] != embedded[key]:
                raise ValueError("Embedded/adjacent artifact identity differs: " + key)
        source = ROOT / "tools/acceptance/java/WindowsSnapshotFileLockAudit.java"
        helper = ROOT / "tools/acceptance/fixtures/hold_snapshot.ps1"
        classes = output / "classes"
        classes.mkdir()
        execution.update(artifact_identity=identity, input_hashes={str(path): digest(path) for path in
            (artifact, mtr, java, java.with_name("javac.exe"), source, helper, pathlib.Path(__file__))})
        save()
        run("compile", [str(java.with_name("javac.exe")), "-proc:none", "-encoding", "UTF-8", "--release", "21",
            "-cp", str(artifact) + ";" + str(mtr), "-d", str(classes), str(source)])
        execution["compiled_class_hashes"] = {str(path.relative_to(classes)): digest(path) for path in classes.rglob("*.class")}
        save()
        run("audit", [str(java), "-Xmx256m", "-cp", str(classes) + ";" + str(artifact) + ";" + str(mtr),
            "site.benli06.WindowsSnapshotFileLockAudit", str(output / "data"), str(helper), str(output / "result.json")])
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        if not result.get("passed") or result.get("lock_exit_code") != 0 or result.get("remaining_snapshot_files"):
            raise ValueError("Actual result or helper ownership did not pass")
        if any(digest(pathlib.Path(path)) != sha for path, sha in execution["input_hashes"].items()):
            raise ValueError("An input changed during the audit")
        execution.update(passed=True, ended=dt.datetime.now(dt.timezone.utc).isoformat())
        save()
        print(json.dumps({"passed": True, "result": str(output / "result.json")}))
    except BaseException as error:
        execution.update(passed=False, error=repr(error), ended=dt.datetime.now(dt.timezone.utc).isoformat())
        save()
        raise


if __name__ == "__main__":
    main()
