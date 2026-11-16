"""Verify only this sealed evidence tree; never read a live instance or process."""
import argparse
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode = True


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def require(value, message):
    if not value:
        raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify(base):
    index = read(base / "sha256-index.json")["files"]
    actual = {path.relative_to(base).as_posix() for path in base.rglob("*") if path.is_file()
              and path.name != "sha256-index.json" and "__pycache__" not in path.parts}
    require(actual == set(index), "Sealed payload inventory differs from its index.")
    for name, expected in index.items():
        path = (base / name).resolve(strict=True)
        require(path.is_relative_to(base), "Indexed payload escapes the seal.")
        raw = path.read_bytes()
        require(len(raw) == expected["bytes"] and sha(raw) == expected["sha256"], "Payload changed: " + name)
    dependencies = base / "sealed-dependencies"
    provenance = read(dependencies / "provenance.json")
    for name, expected in provenance["files"].items():
        raw = (dependencies / name).read_bytes()
        require(sha(raw) == expected["sha256"] and len(raw) == expected["bytes"], "Copied dependency changed: " + name)
    old_index = read(dependencies / "startup-seal-sha256-index.json")["files"]
    for name in ("native_diagnostic_review.py", "client_experiment_analysis.py", "native-diagnostic-review.json", "summary.json", "windows_snapshot_io.py"):
        require(sha((dependencies / name).read_bytes()) == old_index["capture-01/observation/" + name]["sha256"],
                "Dependency differs from the previously committed startup seal: " + name)
    live = base / "actual-read-01"
    assessment = read(live / "assessment.json")
    require(assessment["passed"] and assessment["source_sha256_before"] == assessment["source_sha256_after"], "Read-only capture did not complete unchanged.")
    for name, expected in assessment["source_sha256_before"].items():
        require(sha((live / "sources" / name).read_bytes()) == expected, "Captured source differs: " + name)
    load("windows_snapshot_io", dependencies / "windows_snapshot_io.py")
    stream = load("sealed_native_log_stream", live / "sources/tools/native_log_stream.py")
    root = live / "native-log"
    reference = assessment["reference"]
    receipt_path = root / reference["receipt"]
    require(sha(receipt_path.read_bytes()) == reference["receipt_sha256"], "Producer receipt pin differs.")
    require(sha((root / "context.json").read_bytes()) == reference["context_sha256"], "Producer context pin differs.")
    data = stream.verify_capture(root, receipt_path)
    receipt, context = read(receipt_path), read(root / "context.json")
    reconstructed = b"".join(gzip.decompress((root / part["blob"]).read_bytes()) if part["name"].endswith(".gz")
                             else (root / part["blob"]).read_bytes() for part in receipt["segments"])
    require(data == reconstructed == (live / "logical-native.log").read_bytes(), "Independent gzip reconstruction differs.")
    require(len(data) == assessment["logical_bytes"] and sha(data) == assessment["logical_sha256"], "Logical stream assessment differs.")
    anchor = (root / "anchor.bin").read_bytes()
    require(sha(anchor) == old_index["capture-01/observation/native-log-at-completion.log"]["sha256"], "Independent prior prefix witness differs.")
    require(data.startswith(anchor), "The earlier exact startup prefix was lost.")
    process, launch, plan = read(live / "actual-process.json"), read(root / "launch.json"), read(root / "plan.json")
    require(process == context["process"] == assessment["process"], "Native process identity binding differs.")
    require(launch["pid"] == process["pid"] and launch["plan_sha256"] == sha((root / "plan.json").read_bytes()), "Plan/launch identity differs.")
    require(context["plan_sha256"] == launch["plan_sha256"] and context["launch_sha256"] == sha((root / "launch.json").read_bytes()), "Context launch pins differ.")
    native = read(live / "native-observer.json")
    require(native["pid"] == process["pid"] and native["observation_errors"] == 0, "Native snapshot identity/errors differ.")
    analysis = load("sealed_log_analysis", dependencies / "client_experiment_analysis.py")
    diagnostic = load("sealed_log_diagnostic", dependencies / "native_diagnostic_review.py")
    review = read(dependencies / "native-diagnostic-review.json")
    diagnostic.validate_review(review, native["target"], root=dependencies / "proof-root")
    text = data.decode("utf-8")
    replay = diagnostic.review_diagnostics(analysis.native_diagnostics(text), text,
        [json.loads(line) for line in (live / "native-invalid-model.jsonl").read_bytes().splitlines()],
        [json.loads(line) for line in (live / "native-resource-epochs.jsonl").read_bytes().splitlines()],
        process, native["target"], review, {"start": plan["timestamp"], "end": assessment["completed_at"]}, native)
    require(replay == assessment["native_diagnostics"] == read(dependencies / "summary.json")["native_diagnostics"], "Frozen diagnostic replay differs.")
    release = base / "release-proof-02"
    config = read(live / "sources/config/native-log-reader.json")
    proof = read(release / "assessment.json")
    class_count = 0
    for target in proof["profiles"]:
        folder = release / target
        facts, actual_launch = read(folder / "profile-facts.json"), read(folder / "packaged-client-launch.json")
        profile = config["profiles"][facts["neoForge"]]
        require(facts["fml_version"] == profile["fml_version"] and facts["launch_target"] == profile["launch_target"], "Exact FML profile differs.")
        command = actual_launch["command"]
        require(command[command.index("--fml.fmlVersion") + 1] == profile["fml_version"], "Actual launch FML differs.")
        require(command[command.index("--fml.neoForgeVersion") + 1] == facts["neoForge"], "Actual launch NeoForge differs.")
        for role, expected in (("loader", profile["loader_sha256"]), ("core", profile["core_sha256"])):
            jar_info = facts["jars"][role]
            raw = (release / jar_info["blob"]).read_bytes()
            require(sha(raw) == jar_info["sha256"] == expected and len(raw) == jar_info["bytes"], "Exact released JAR differs.")
            with zipfile.ZipFile(release / jar_info["blob"]) as jar:
                if role == "loader":
                    xml = jar.read(profile["xml_member"])
                    require(sha(xml) == facts["xml_sha256"] == profile["xml_sha256"], "Module logging XML differs.")
                    stream.Layout.from_xml(xml)
                for item in proof["bytecode_proofs"][expected]:
                    value = jar.read(item["member"])
                    require(sha(value) == item["class_sha256"] and item["exit_code"] == 0, "Original javap proof differs.")
                    path = release / "classes" / expected / item["member"]
                    require(path.read_bytes() == value, "Extracted class differs from the exact release.")
                    transcript = path.with_suffix(".javap.txt")
                    require(sha(transcript.read_bytes()) == item["stdout_sha256"] and sha(transcript.with_suffix(".stderr.txt").read_bytes()) == item["stderr_sha256"], "Javap stdout/stderr pin differs.")
                    require(read(transcript.with_suffix(".execution.json")) == item, "Javap execution metadata differs.")
                    class_count += 1
    runs = {}
    for name in ("engineering-run-01", "engineering-run-02-targeted", "engineering-run-03-final"):
        folder = base / name
        execution = read(folder / "execution.json")
        require(execution["sources_unchanged"] and execution["source_sha256_before"] == execution["source_sha256_after"], "Engineering execution source changed.")
        for channel in ("stdout", "stderr"):
            require(sha((folder / (channel + ".log")).read_bytes()) == execution[channel + "_sha256"], "Original test output changed.")
        for source, expected in execution["source_sha256_before"].items():
            require(sha((folder / "sources" / source).read_bytes()) == expected, "Original test source changed.")
        output = (folder / "stderr.log").read_text(encoding="utf-8")
        tests = int(re.search(r"Ran (\d+) tests? in ", output)[1])
        runs[name] = {"tests": tests, "exit_code": execution["exit_code"]}
    require(runs["engineering-run-01"]["exit_code"] != 0, "Original failed suite was overwritten.")
    require(runs["engineering-run-03-final"]["exit_code"] == 0, "Final targeted tests failed.")
    final = read(base / "engineering-run-03-final/execution.json")["source_sha256_after"]
    for name, expected in assessment["source_sha256_before"].items():
        if name in final:
            require(final[name] == expected, "Real log validation used a different final runtime source.")
    return {"verified_at": dt.datetime.now(dt.timezone.utc).isoformat(), "passed": True,
            "index_sha256": sha((base / "sha256-index.json").read_bytes()), "payloads": len(index),
            "logical_bytes": len(data), "earlier_prefix_bytes": len(anchor), "segment_names": [s["name"] for s in receipt["segments"]],
            "native_diagnostic_replay_exact": True, "release_profiles": proof["profiles"],
            "bytecode_checks_including_shared_core_per_profile": class_count, "engineering_runs": runs,
            "scope": "Sealed-only byte/hash/CRC/identity/configuration/diagnostic replay. No live process, input, reload, route, performance or whole-game exit acceptance."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seal", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.seal.resolve(strict=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(json.dumps(result))
