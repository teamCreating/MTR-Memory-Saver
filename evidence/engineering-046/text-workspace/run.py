"""Exact packaged-candidate source equivalence checks; not a client performance trial."""
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess

root = pathlib.Path(__file__).resolve().parents[3]
output = pathlib.Path(__file__).resolve().parent / "attempt-02"
output.mkdir(parents=True, exist_ok=False)
java_home = pathlib.Path("C:/Users/ben_l/.gradle/jdks/eclipse_adoptium-21-amd64-windows.2")
java, javac = java_home / "bin/java.exe", java_home / "bin/javac.exe"
candidate = root / "build/libs/mtr-memory-saver-official-nf248-0.4.6.jar"
reference = json.loads((root / "evidence/engineering-045/large-text-reference/assessment.json").read_text(encoding="utf-8"))
commons = pathlib.Path(reference["runtime"]["commons_io_path"])
mtr = pathlib.Path(reference["sources"][0]["path"])
largest = reference["over_default_limit"][0]
archive = pathlib.Path(reference["sources"][largest["source_index"]]["path"])
source = root / "tools/acceptance/java/LargeTextWorkspaceAudit.java"
classes = root / ".cache/acceptance/text-workspace-046-attempt02-classes"
classes.mkdir(parents=True, exist_ok=False)
classpath = os.pathsep.join(map(str, (candidate, commons, mtr)))

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def save(name, value):
    (output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

plan = {"timestamp": datetime.datetime.now().astimezone().isoformat(), "scope": __doc__,
        "candidate_sha256": digest(candidate), "candidate": str(candidate), "heap": "3g",
        "entry": largest["resource"], "entry_sha256": largest["sha256"],
        "expected_utf16_units": largest["decoded_utf16_units"],
        "inputs": {str(path): digest(path) for path in (pathlib.Path(__file__), source, java, javac, commons, mtr, archive)},
        "modes": ["default_compact_strings", "compact_strings_disabled"]}
save("plan.json", plan)
shutil.copyfile(source, output / source.name)
commands = []

def run(name, command):
    result = subprocess.run(command, cwd=root, capture_output=True)
    (output / (name + ".stdout.log")).write_bytes(result.stdout)
    (output / (name + ".stderr.log")).write_bytes(result.stderr)
    commands.append({"name": name, "command": list(map(str, command)), "exit_code": result.returncode})
    save("execution.json", commands)
    if result.returncode:
        raise RuntimeError(f"{name} failed with {result.returncode}; raw output preserved")

run("compile", [str(javac), "-proc:none", "-encoding", "UTF-8", "-cp", classpath, "-d", str(classes), str(source)])
for name, flags in (("default", []), ("no-compact", ["-XX:-CompactStrings"])):
    run(name, [str(java), "-Xmx3g", "-Dfile.encoding=UTF-8", *flags, "-cp", str(classes) + os.pathsep + classpath,
               "site.benli06.LargeTextWorkspaceAudit", str(archive), largest["resource"], str(output / (name + ".json"))])
    report = json.loads((output / (name + ".json")).read_text(encoding="utf-8"))
    if report.get("passed") is not True:
        raise RuntimeError(f"{name} did not pass")
if digest(candidate) != plan["candidate_sha256"] or any(digest(pathlib.Path(path)) != fingerprint for path, fingerprint in plan["inputs"].items()):
    raise RuntimeError("Inputs changed during the audit")
save("assessment.json", {"timestamp": datetime.datetime.now().astimezone().isoformat(), "passed": True,
                         "scope": __doc__, "candidate_sha256": plan["candidate_sha256"], "modes": plan["modes"],
                         "limits": "Decoded bytes/characters, native-decoder controls, workspace and stream ownership; no native OBJ geometry, GPU or whole-client performance conclusion."})
print(json.dumps({"passed": True, "output": str(output), "candidate_sha256": plan["candidate_sha256"]}))
