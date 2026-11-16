"""Replay the verified 102 MB source with each exact candidate and both String representations."""
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import subprocess
import urllib.parse

OUT = pathlib.Path(__file__).resolve().parent / "large-text"
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT.mkdir(exist_ok=False)
old_plan = ROOT / "evidence/engineering-046/text-workspace/attempt-02/plan.json"
plan = json.loads(old_plan.read_text(encoding="utf-8"))
JDK = pathlib.Path("C:/Users/ben_l/Saved Games/Yuuniverse 1.20.1 Shenyang/porting-output/work/tools/jdk21/jdk-21.0.11+10")
archive = pathlib.Path(next(name for name in plan["inputs"] if name.endswith(".zip")))
commons = pathlib.Path(next(name for name in plan["inputs"] if name.endswith("commons-io-2.15.1.jar")))
mtr = pathlib.Path(next(name for name in plan["inputs"] if pathlib.Path(name).name.startswith("mtr-") and name.endswith(".jar")))
source = ROOT / "tools/acceptance/java/LargeTextWorkspaceAudit.java"
classes = OUT / "classes"
classes.mkdir()


def sha(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save():
    (OUT / "execution.json").write_text(json.dumps(execution, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


execution = {"started": stamp(), "passed": False, "historical_input_plan_sha256": sha(old_plan),
             "commands": [], "trials": [], "inputs": {str(path): sha(path) for path in (archive, commons, mtr, source, JDK / "bin/java.exe", JDK / "bin/javac.exe", pathlib.Path(__file__))}}
save()


def run(name, command, cwd=OUT):
    entry = {"name": name, "command": command, "cwd": str(cwd), "started": stamp()}
    execution["commands"].append(entry)
    save()
    result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=120)
    (cwd / (name + ".stdout.log")).write_bytes(result.stdout)
    (cwd / (name + ".stderr.log")).write_bytes(result.stderr)
    entry.update(exit_code=result.returncode, ended=stamp())
    save()
    if result.returncode:
        raise RuntimeError("Recorded child failed: " + name)


try:
    for path in (archive, commons, mtr, source):
        if sha(path) != plan["inputs"][str(path)]:
            raise ValueError("Historical reference input changed: " + str(path))
    shutil.copy2(source, OUT / source.name)
    first = ROOT / "build/libs/mtr-memory-saver-official-nf248-0.4.7.jar"
    cp = ";".join(map(str, (first, commons, mtr)))
    run("compile", [str(JDK / "bin/javac.exe"), "-proc:none", "-encoding", "UTF-8", "--release", "21", "-cp", cp, "-d", str(classes), str(source)])
    execution["classes"] = {path.relative_to(classes).as_posix(): sha(path) for path in classes.rglob("*.class")}
    if any(not name.startswith("site/benli06/LargeTextWorkspaceAudit") for name in execution["classes"]):
        raise ValueError("Unexpected audit class shadows a packaged reader")
    for target in ("official-nf248", "official-nf265"):
        artifact = ROOT / ("build/libs/mtr-memory-saver-" + target + "-0.4.7.jar")
        identity = json.loads(artifact.with_suffix(".build.json").read_text())
        if sha(artifact) != identity["sha256"] or identity["mtrSha256"] != sha(mtr):
            raise ValueError("Exact candidate/dependency identity failed")
        execution["inputs"][str(artifact)] = sha(artifact)
        for mode, flags in (("default", []), ("no-compact", ["-XX:-CompactStrings"])):
            directory = OUT / (target + "-" + mode)
            directory.mkdir()
            command = [str(JDK / "bin/java.exe"), "-Xmx3g", "-Dfile.encoding=UTF-8", *flags,
                "-Xlog:class+load=info:file=class-load.log", "-cp", ";".join(map(str, (classes, artifact, commons, mtr))),
                "site.benli06.LargeTextWorkspaceAudit", str(archive), plan["entry"], str(directory / "result.json")]
            run("audit", command, directory)
            result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
            if not result["passed"] or result["source_sha256"] != plan["entry_sha256"] or result["candidate_utf8_sha256"] != plan["entry_sha256"]:
                raise ValueError("Independent input/output text equality failed")
            if result["candidate_decoded_utf16_units"] != plan["expected_utf16_units"] or not result["snapshot_observed"]:
                raise ValueError("Expected large source/spill was not exercised")
            if result["remaining_snapshot_files"] or result["active_read_scopes"] != 0 or result["workspace_statistics"][1] != 0 or result["workspace_statistics"][3] != 0:
                raise ValueError("Snapshot/workspace ownership was not released")
            if result["max_heap_bytes"] != 3 * 1024 ** 3:
                raise ValueError("Java heap differs from the exact requested bound")
            observed = {}
            for line in (directory / "class-load.log").read_text(encoding="utf-8").splitlines():
                for name in ("SegmentedResourceText", "ReadAdmission", "TextWorkspace"):
                    marker = "site.benli06." + name + " source: "
                    if marker in line:
                        url = line.split(marker, 1)[1]
                        text = urllib.parse.unquote(urllib.parse.urlparse(url).path)
                        if text.startswith("/") and len(text) > 2 and text[2] == ":": text = text[1:]
                        if pathlib.Path(text).resolve() != artifact: raise ValueError("Class loaded from wrong artifact")
                        observed[name] = url
            if len(observed) != 3: raise ValueError("Actual class loading was not recorded")
            execution["trials"].append({"target": target, "mode": mode, "artifact_sha256": sha(artifact),
                "output": str((directory / "result.json").relative_to(OUT)), "passed": True,
                "actual_reader_class_sources": observed, "source_bytes": result["source_bytes"],
                "decoded_utf16_units": result["candidate_decoded_utf16_units"], "synthetic_controls": len(result["synthetic_controls"])})
            save()
    if any(sha(pathlib.Path(path)) != expected for path, expected in execution["inputs"].items()):
        raise ValueError("An audit input changed")
    execution.update(passed=True, ended=stamp(), limits="Standalone exact-text/ownership checks, not gameplay or client performance acceptance.")
    save()
    print(json.dumps({"passed": True, "trials": len(execution["trials"]), "decoded_units_per_trial": plan["expected_utf16_units"]}))
except BaseException as error:
    execution.update(error=repr(error), ended=stamp())
    save()
    raise
