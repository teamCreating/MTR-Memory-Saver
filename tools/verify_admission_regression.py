"""Compile an independent admission audit against historical and current source bytes."""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES = [f"src/main/java/site/benli06/{name}.java" for name in
           ("ReadAdmission", "GenerationWorkCache", "BoundedTextCache")]
AUDIT = ROOT / "tools/acceptance/java/AdmissionGenerationAudit.java"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=pathlib.Path, required=True)
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Use a fresh evidence directory.")
    java = args.java_home / "bin" / "java.exe"
    javac = args.java_home / "bin" / "javac.exe"
    baseline = subprocess.check_output(["git", "rev-parse", args.baseline_ref], cwd=ROOT, text=True).strip()
    output.mkdir(parents=True)
    report = {"timestamp": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
              "baseline_commit": baseline, "scope": "Java core only; no client or Mixin acceptance",
              "audit_sha256": sha(AUDIT.read_bytes()), "trials": {}}
    for label in ("baseline", "candidate"):
        trial = output / label
        trial.mkdir()
        inputs = {}
        for relative in SOURCES:
            data = (subprocess.check_output(["git", "show", f"{baseline}:{relative}"], cwd=ROOT)
                    if label == "baseline" else (ROOT / relative).read_bytes())
            (trial / pathlib.Path(relative).name).write_bytes(data)
            inputs[relative] = sha(data)
        command = [str(javac), "-d", str(trial), *map(str, trial.glob("*.java")), str(AUDIT)]
        compile_result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (trial / "compile.log").write_text(compile_result.stdout + compile_result.stderr, encoding="utf-8")
        if compile_result.returncode:
            raise RuntimeError(f"{label} audit compilation failed")
        run = subprocess.run([str(java), "-Xmx3G", "-cp", str(trial), "site.benli06.audit.AdmissionGenerationAudit"],
                             capture_output=True, text=True, timeout=60)
        (trial / "process.log").write_text(run.stdout + run.stderr, encoding="utf-8")
        if run.returncode:
            raise RuntimeError(f"{label} audit process failed")
        result = json.loads(run.stdout)
        report["trials"][label] = {"source_sha256": inputs, "result": result,
                                    "process_log_sha256": sha((trial / "process.log").read_bytes())}
    old, new = (report["trials"][label]["result"] for label in ("baseline", "candidate"))
    report["passed"] = (old["model_waiter_rejected"] is False and old["model_stale_reads"] == 1
                        and old["text_waiter_rejected_before_owner_exit"] is False and old["text_stale_reads"] == 1
                        and new["model_waiter_rejected"] is True and new["model_stale_reads"] == 0
                        and new["text_waiter_rejected_before_owner_exit"] is True and new["text_stale_reads"] == 0
                        and old["cleanup_verified"] is True and new["cleanup_verified"] is True)
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise RuntimeError("The historical defect did not fail or the current repair did not pass.")


if __name__ == "__main__":
    main()
