"""Read only this seal and its tracked engineering artifact/source references.

No original instance, JFR/MTR binary, JVM, game, imported archived tool or process
API is used. External binary hashes are read-time observations, not portable data.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def owned(root, relative):
    value = PurePosixPath(str(relative).replace("\\", "/"))
    require(not value.is_absolute() and ".." not in value.parts, "Unowned reference")
    path = root.joinpath(*value.parts).resolve()
    require(path.is_relative_to(root.resolve()), "Reference escaped root")
    return path


def verify(seal, repository):
    index = read(seal / "sha256-index.json")["files"]
    actual = {p.relative_to(seal).as_posix() for p in seal.rglob("*") if p.is_file() and p.name != "sha256-index.json"}
    require(actual == {row["path"] for row in index} and len(actual) == len(index), "Seal inventory differs")
    for row in index:
        raw = owned(seal, row["path"]).read_bytes()
        require(len(raw) == row["bytes"] and digest(raw) == row["sha256"], "Seal payload differs: " + row["path"])
    for row in read(seal / "copy-receipts.json")["files"]:
        raw = owned(seal, row["payload"]).read_bytes()
        require(row["before"] == row["after"] and len(raw) == row["before"]["bytes"] and digest(raw) == row["sha256"], "Original copy receipt differs")
    for relative, expected in read(seal / "inputs.json")["sources"].items():
        require(digest(owned(seal / "sources", relative).read_bytes()) == expected, "Frozen source pin differs")
    bindings = read(seal / "run-bindings.json")
    artifacts, input_count = {}, 0
    for row in bindings["artifact_bindings"]:
        manifest = read(owned(seal, row["manifest"]))
        jar = owned(repository, row["jar_repository_path"])
        raw = jar.read_bytes()
        require(len(raw) == row["jar_bytes"] and digest(raw) == row["jar_sha256"] == manifest["sha256"], "Portable artifact differs")
        source_root = owned(repository, row["sources_repository_path"])
        with zipfile.ZipFile(jar) as archive:
            for name, expected in manifest["inputs"].items():
                path = owned(source_root, name)
                if path.is_file():
                    value = path.read_bytes()
                elif name.startswith("src/main/resources/"):
                    value = archive.read(name.removeprefix("src/main/resources/"))
                else:
                    parts = PurePosixPath(name).parts
                    require(parts[:2] == ("build", "generated") and len(parts) >= 5, "Unresolved build input: " + name)
                    value = archive.read(PurePosixPath(*parts[4:]).as_posix())
                require(digest(value) == expected, "Artifact source/input differs: " + name)
                input_count += 1
        kind = "probe" if manifest.get("kind") == "acceptance-probe" else "companion"
        artifacts[(row["target"], kind)] = (manifest, source_root)
    for target in {key[0] for key in artifacts}:
        product, _ = artifacts[(target, "companion")]
        probe, _ = artifacts[(target, "probe")]
        require(probe["companionSha256"] == product["sha256"] and probe["mtrSha256"] == product["mtrSha256"], "Probe/product identity differs")
    external = read(seal / "external-binary-references.json")["files"]
    for row in external:
        require(row["before"] == row["after"] and row["portable_binary_in_this_seal"] is False, "External read-time guard differs")
    audit = {row["instance"]: row for row in read(seal / "audit/results.json")}
    rows = []
    for binding in bindings["runs"]:
        folder = seal / "attempts" / binding["label"]
        capture = folder / "capture"
        execution, plan, launch = (read(capture / name) for name in ("execution.json", "packaged-client-plan.json", "packaged-client-launch.json"))
        require(execution["status"] == "exited" and execution["capture_errors"] == [], "Capture did not finish cleanly")
        require(execution["pid"] == launch["pid"] == binding["pid"], "PID binding differs")
        require(execution["instance"] == plan["instance"] == binding["instance"], "Instance binding differs")
        require(execution["exit_code"] == binding["jvm_exit_code"], "JVM exit binding differs")
        require(digest((capture / "packaged-client-plan.json").read_bytes()) == launch["plan_sha256"], "Launch plan pin differs")
        require(launch["launcher_tool_sha256"] == plan["source_hash"] == digest((seal / "sources/tools/packaged_client.py").read_bytes()), "Launcher source pin differs")
        for name, expected in execution["files"].items():
            require(digest(owned(capture, name).read_bytes()) == expected, "Collector final file differs")
        for name, expected in execution["sources"].items():
            require(digest((seal / "sources/tools" / name).read_bytes()) == expected, "Collector source differs")
        argv = launch["command"]
        require(argv[argv.index("--gameDir") + 1] == binding["instance"], "Exact gameDir argument differs")
        require(argv[argv.index("--fml.neoForgeVersion") + 1] == plan["artifact"]["neoForge"], "Loader argument differs")
        marker = read(folder / "instance/vehicle-test-instance.json")
        require(marker["instance"] == binding["instance"] and marker["pid"] == binding["pid"] and marker["loader"] == plan["artifact"]["neoForge"], "Instance marker differs")
        require(digest((folder / "instance/options.txt").read_bytes()) == plan["options_sha256"], "Options pin differs")
        product, source_root = artifacts[(plan["artifact"]["target"], "companion")]
        require(all(plan["artifact"].get(k) == value for k, value in product.items()), "Prepared artifact manifest differs")
        for mod in plan["mods"]:
            seen = [r for r in external if r["role"] == binding["label"] + ":" + mod["role"]]
            require(len(seen) == 1 and seen[0]["sha256"] == mod["sha256"], "Installed mod read-time fingerprint differs")
            if mod["role"] in ("companion", "probe"):
                manifest, _ = artifacts[(plan["artifact"]["target"], mod["role"])]
                require(manifest["sha256"] == mod["sha256"], "Installed/portable artifact differs")
        log = (capture / "logs/latest.log").read_text(encoding="utf-8")
        stderr = (capture / "launch.stderr.log").read_text(encoding="utf-8")
        source = (source_root / "src/main/java/site/benli06/BinaryFingerprint.java").read_text(encoding="utf-8")
        failure = re.search(r'throw new IllegalStateException\("([^"]+)"\)', source).group(1)
        result = folder / "instance/loader-lifecycle-result.json"
        if binding["expected_outcome"] == "packaged_checks_pass":
            require(execution["exit_code"] == 0 and plan["smoke"] and not plan["expected_binary_rejection"], "Smoke policy/exit differs")
            value = read(result)
            require(value["request"] == read(folder / "instance/loader-lifecycle-request.json"), "Lifecycle request differs")
            require(value["passed"] is True and len(value["checks"]) == 24 and len(value["strict_resource_checks"]) == 18, "Packaged check inventory differs")
            require(all(v is True for group in (value["checks"], value["strict_resource_checks"]) for v in group.values()), "Packaged check failed")
            # Instance names were produced on Windows; parse its recorded separator.
            copied = seal / "audit" / (PurePosixPath(binding["instance"].replace("\\", "/")).name + ".lifecycle-result.json")
            require(copied.read_bytes() == result.read_bytes(), "Audit lifecycle copy differs")
            require("MTR memory sharing:" in log and "MTR Blockbench native snapshot capability:" in log, "Native registration/source path record absent")
            check_counts = [len(value["checks"]), len(value["strict_resource_checks"])]
        elif binding["expected_outcome"] == "expected_fingerprint_rejection":
            require(execution["exit_code"] == 1 and plan["expected_binary_rejection"] and not plan["smoke"], "Mismatch policy/exit differs")
            require(failure in stderr and "MixinInitialisationError" in stderr and "MTR memory sharing:" not in log and "Reloading ResourceManager:" not in log, "Fingerprint fatal/pre-registration boundary differs")
            require(not result.exists() and not any(m["role"] == "probe" for m in plan["mods"]), "Mismatch unexpectedly has a probe/result")
            require(next(m["sha256"] for m in plan["mods"] if m["role"] == "mtr") != product["mtrSha256"], "Mismatch fixture fingerprint is unchanged")
            check_counts = None
        else:
            require(binding["expected_outcome"] == "incomplete_no_result" and execution["exit_code"] == 0 and not result.exists(), "Earlier incomplete attempt differs")
            check_counts = None
        if binding["instance"] in audit:
            entry = audit[binding["instance"]]
            stem = PurePosixPath(binding["instance"].replace("\\", "/")).name
            summary = (seal / "audit" / (stem + ".jfr-summary.stdout.log")).read_text(encoding="utf-8")
            require(entry["jfr_summary_exit"] == 0 and (seal / "audit" / (stem + ".jfr-summary.stderr.log")).read_bytes() == b"", "Saved JFR summary failed")
            require("Event Type" in summary and re.search(r"Duration:\s+\d+ s", summary), "Saved JFR summary unreadable")
            require(entry["jfr_sha256"] == binding["jfr"]["sha256"], "On-exit JFR reference differs")
            require(entry["artifact_sha256"] == product["sha256"], "Audit artifact pin differs")
        rows.append({"capture": binding["label"], "pid": execution["pid"], "jvm_exit": execution["exit_code"], "outcome": binding["expected_outcome"], "checks": check_counts})
    initial = read(seal / "attempts" / bindings["initial_attempt"] / "capture/execution.json")
    require(initial["status"] == "launching" and "pid" not in initial and "exit_code" not in initial, "Initial incomplete evidence differs")
    parent = read(seal / "parent-reported-tool-results.json")
    require(all(row["wrapper_exit_code"] == 0 for row in parent["collector_wrappers"]), "Parent-reported wrapper transcription differs")
    return {"payloads": len(index), "artifact_input_fingerprints": input_count, "runs": rows,
            "initial_attempt_accepted": False, "jfr_binaries_portable": False,
            "scope": "Packaged component checks and expected binary rejection only; no reload/gameplay/performance acceptance."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seal", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    print(json.dumps(verify(args.seal.resolve(), args.repository.resolve()), ensure_ascii=False, indent=2))
