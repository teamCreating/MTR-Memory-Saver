"""Recompile the original diagnostic sources and compare every launched class byte."""
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import zipfile

OUT = pathlib.Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    source = OUT / "early-probe-source"
    output = OUT / "early-rebuild"
    output.mkdir(exist_ok=False)
    plan = json.loads((OUT / "startup-prefix/packaged-client-plan.json").read_bytes())
    instance = pathlib.Path(plan["instance"])
    mtr = next(instance / "mods" / item["filename"] for item in plan["mods"] if item["role"] == "mtr")
    libraries = sorted((instance / "libraries").rglob("*.jar"))
    sources = sorted((source / "tools/diagnostics/native-model-trace/java").rglob("*.java"))
    command = [str(pathlib.Path(plan["java"]).with_name("javac.exe")), "--release", "21", "-g:source,lines",
               "-encoding", "UTF-8", "-proc:none", "-Xlint:unchecked", "-cp", ";".join(map(str, [mtr, *libraries])),
               "-d", str(output / "classes"), *map(str, sources)]
    result = subprocess.run(command, capture_output=True)
    (output / "javac.stdout.log").write_bytes(result.stdout)
    (output / "javac.stderr.log").write_bytes(result.stderr)
    report = {"timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
              "argv": command, "exit_code": result.returncode,
              "source_files": {str(path.relative_to(source)): sha(path.read_bytes()) for path in sources},
              "classpath": {str(path): sha(path.read_bytes()) for path in [mtr, *libraries]}, "comparisons": []}
    if result.returncode == 0:
        with zipfile.ZipFile(source / "launched.jar") as jar:
            expected = {name for name in jar.namelist() if name.endswith(".class")}
            actual = {str(path.relative_to(output / "classes")).replace("\\", "/") for path in (output / "classes").rglob("*.class")}
            report["class_sets_equal"] = actual == expected
            for name in sorted(expected & actual):
                original = jar.read(name)
                current = (output / "classes" / name).read_bytes()
                report["comparisons"].append({"class": name, "launched_sha256": sha(original), "rebuilt_sha256": sha(current), "equal": current == original})
    report["passed"] = report.get("class_sets_equal", False) and all(row["equal"] for row in report["comparisons"])
    (output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("exit_code", "passed")}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
