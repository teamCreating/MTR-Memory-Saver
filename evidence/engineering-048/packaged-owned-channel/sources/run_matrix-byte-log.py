"""Actual fresh packaged-client checks for the frozen owned-channel candidate."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
import zipfile

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import packaged_client as launcher
import observe_packaged_client as observer

JAVA_HOME = Path(r"C:\Users\ben_l\Saved Games\Yuuniverse 1.20.1 Shenyang\porting-output\work\tools\jdk21\jdk-21.0.11+10")
SOURCES = {"official-nf248": ROOT.parent / ".cache/game-test/nf248-official-3g",
           "official-nf265": ROOT.parent / ".cache/game-test/neoforge-instance"}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy(path, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == path.read_bytes(), target
    else:
        shutil.copy2(path, target)


def command(argv, directory, env=None):
    directory.mkdir(parents=True, exist_ok=False)
    receipt = {"command": list(map(str, argv)), "cwd": str(ROOT), "started": now(), "runner_sha256": sha(Path(__file__))}
    write(directory / "execution.json", receipt)
    with (directory / "stdout.log").open("wb") as stdout, (directory / "stderr.log").open("wb") as stderr:
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
        receipt["pid"] = process.pid
        write(directory / "execution.json", receipt)
        receipt["exit_code"] = process.wait()
    receipt["ended"] = now()
    write(directory / "execution.json", receipt)
    assert receipt["exit_code"] == 0, receipt
    return receipt


def configuration(target, mode):
    artifacts = BASE / "artifacts" / target
    manifest_path, = artifacts.glob("*.build.json")
    manifest = read(manifest_path)
    companion = artifacts / manifest["artifact"]
    probe, = artifacts.glob("*-acceptance-probe.jar")
    instance = ROOT / ".cache/acceptance" / f"{target}-{mode}-048-owned"
    return manifest, companion, probe, instance


def prepare():
    copy(Path(__file__), BASE / "sources/run_matrix.py")
    for relative in ("tools/packaged_client.py", "tools/observe_packaged_client.py", "tools/windows_snapshot_io.py",
                     "tools/legacy_identity.py", "config/targets.json", "config/legacy-baselines.json", "build.gradle"):
        copy(ROOT / relative, BASE / "sources" / relative)
    env = os.environ.copy()
    env["JAVA_HOME"] = str(JAVA_HOME)
    env["PATH"] = str(JAVA_HOME / "bin") + os.pathsep + env["PATH"]
    for target in SOURCES:
        frozen = BASE.parent / "snapshot-owned-channel" / target
        manifest_path, = frozen.glob("*.build.json")
        manifest = read(manifest_path)
        artifact = frozen / manifest["artifact"]
        assert sha(artifact) == manifest["sha256"]
        artifacts = BASE / "artifacts" / target
        copy(artifact, artifacts / artifact.name)
        copy(manifest_path, artifacts / manifest_path.name)
        command([str(ROOT / "gradlew.bat"), "probeJar", f"-Ptarget={target}",
                 f"-PmodVersion={manifest['version']}", "--rerun-tasks", "--console=plain"], BASE / "probe-build" / target, env)
        probe_name = artifact.stem + "-acceptance-probe.jar"
        copy(ROOT / "build/libs" / probe_name, artifacts / probe_name)
        inputs = {}
        for directory in (ROOT / "tools/probes/common", ROOT / "tools/probes/io/java", ROOT / f"build/generated/probe/{target}"):
            for path in sorted(directory.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    relative = path.relative_to(ROOT)
                    copy(path, BASE / "sources" / relative)
                    inputs[relative.as_posix()] = sha(path)
        write(artifacts / "probe-identity.json", {"target": target, "version": manifest["version"],
            "artifact": probe_name, "sha256": sha(artifacts / probe_name), "inputs": inputs,
            "product_compile_inputs": manifest["inputs"], "build_gradle_sha256": sha(ROOT / "build.gradle")})
    for mode in ("faults", "mismatch"):
        for target, source in SOURCES.items():
            manifest, companion, probe, instance = configuration(target, mode)
            argv = [sys.executable, str(ROOT / "tools/packaged_client.py"), "prepare", "--source", str(source),
                    "--instance", str(instance), "--companion", str(companion),
                    "--username", "VehicleTest", "--heap-mib", "3072"]
            argv.extend(["--probe", str(probe), "--smoke", "--jfr", "--faults"] if mode == "faults" else ["--expect-binary-rejection"])
            command(argv, BASE / "prepare" / f"{target}-{mode}")
            copy(instance / "packaged-client-plan.json", BASE / "prepared" / f"{target}-{mode}.json")
            assert read(instance / "packaged-client-plan.json")["artifact"]["sha256"] == manifest["sha256"]
            if mode == "mismatch":
                plan = read(instance / "packaged-client-plan.json")
                mtr, = [item for item in plan["mods"] if item["role"] == "mtr"]
                original, modified = source / "mods" / mtr["filename"], instance / "mods" / mtr["filename"]
                original_bytes, modified_bytes = original.read_bytes(), modified.read_bytes()
                with zipfile.ZipFile(original) as archive: old_comment = archive.comment
                with zipfile.ZipFile(modified) as archive: new_comment = archive.comment
                assert new_comment == b"Memory Saver isolated same-version fingerprint negative control"
                assert modified_bytes == original_bytes[:-(len(old_comment) + 2)] + len(new_comment).to_bytes(2, "little") + new_comment
                assert sha(original) == manifest["mtrSha256"] and sha(modified) != manifest["mtrSha256"]
                write(BASE / "prepare" / f"{target}-{mode}" / "mtr-comment-control.json", {
                    "original_sha256": sha(original), "modified_sha256": sha(modified),
                    "comment_only_change": True, "original_comment_hex": old_comment.hex(),
                    "modified_comment_hex": new_comment.hex(), "member_and_metadata_bytes_unchanged": True})
            print(json.dumps({"prepared": str(instance)}), flush=True)


def launch(target, mode):
    manifest, companion, probe, instance = configuration(target, mode)
    output = BASE / "runtime" / f"{target}-{mode}"
    output.mkdir(parents=True, exist_ok=False)
    active = subprocess.run(["pwsh", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" | Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Json -Depth 4"], capture_output=True, check=True)
    (output / "java-before.json").write_bytes(active.stdout)
    (output / "java-before.stderr.log").write_bytes(active.stderr)
    if active.stdout.strip():
        processes = json.loads(active.stdout)
        if isinstance(processes, dict): processes = [processes]
        assert not any("--gameDir" in row["CommandLine"] or "forgeclient" in row["CommandLine"] for row in processes), "Another game JVM is active"
    source_identity = {relative: sha(ROOT / relative) for relative in (
        "tools/packaged_client.py", "tools/observe_packaged_client.py", "tools/windows_snapshot_io.py",
        "tools/legacy_identity.py", "config/targets.json", "config/legacy-baselines.json")}
    receipt = {"target": target, "mode": mode, "started": now(), "passed": False,
        "invocation": [sys.executable, str(Path(__file__)), "launch", "--target", target, "--mode", mode],
        "launcher_api": "packaged_client.launch(SimpleNamespace(instance=instance, wait_seconds=None))",
        "source_sha256": source_identity, "runner_sha256": sha(Path(__file__)), "artifact_sha256": manifest["sha256"]}
    write(output / "execution.json", receipt)
    actual = launcher.launch(SimpleNamespace(instance=instance, wait_seconds=None))
    plan = read(instance / "packaged-client-plan.json")
    launched = read(instance / "packaged-client-launch.json")
    process = None
    try:
        process = observer.WindowsProcess(plan, launched)
        receipt["process_identity"] = {**process.identity, "handle_created": process.created}
        receipt["pid"] = actual.pid
        write(output / "execution.json", receipt)
        deadline = time.monotonic() + 600
        with (output / "process-observations.jsonl").open("w", encoding="utf-8") as samples:
            while True:
                sampled = {"timestamp": now(), **process.sample()}
                samples.write(json.dumps(sampled) + "\n")
                samples.flush()
                if not sampled["running"]:
                    receipt["exit_code"] = sampled["exit_code"]
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Owned smoke client exceeded 600 seconds; still running, do not start the next client")
                time.sleep(1)
        assert actual.wait(timeout=10) == receipt["exit_code"]
        receipt["ended"] = now()
        write(instance / "packaged-client-exit.json", {"timestamp": receipt["ended"], "running": False,
            "exit_code": receipt["exit_code"], "pid": actual.pid, "process_created": process.created,
            "launch_sha256": sha(instance / "packaged-client-launch.json"), "observed_with_owned_handle": True})
        for name in ("packaged-client-plan.json", "packaged-client-launch.json", "packaged-client-exit.json",
                     "loader-lifecycle-request.json", "loader-lifecycle-result.json", "launch.stdout.log", "launch.stderr.log", "acceptance-gc.log", "acceptance.jfr"):
            if (instance / name).exists(): copy(instance / name, output / name)
        for folder in ("logs", "crash-reports"):
            if (instance / folder).exists():
                for path in (instance / folder).rglob("*"):
                    if path.is_file(): copy(path, output / folder / path.relative_to(instance / folder))
        for item in plan["mods"]:
            assert sha(instance / "mods" / item["filename"]) == item["sha256"]
        # These native console logs need not share an encoding. Match the exact
        # ASCII diagnostic bytes without decoding or rewriting the raw evidence.
        log = b"\n".join(path.read_bytes() for path in (
            instance / "logs/latest.log", instance / "launch.stdout.log", instance / "launch.stderr.log") if path.exists())
        if mode == "faults":
            result = read(instance / "loader-lifecycle-result.json")
            assert receipt["exit_code"] == 0 and result["passed"]
            assert result["request"] == read(instance / "loader-lifecycle-request.json")
            assert len(result["checks"]) == 24 and all(value is True for value in result["checks"].values())
            assert len(result["strict_resource_checks"]) == 18 and all(value is True for value in result["strict_resource_checks"].values())
            receipt.update(lifecycle_checks=24, strict_resource_checks=18)
        else:
            assert receipt["exit_code"] == 1
            assert not (instance / "loader-lifecycle-result.json").exists()
            assert b"MixinInitialisationError: MTR Memory Saver cannot apply this build to the loaded MTR binary" in log
            assert b"Loaded MTR fingerprint does not match the audited build target" in log
            assert f"mtr_memory_sharing@{manifest['version']}/site.benli06.CompatibilityPlugin.onLoad".encode("ascii") in log
            assert not re.search(rb"\bLoaded \d+ vehicles\b", log)
            receipt["rejected_before_registration"] = True
        for relative, expected in source_identity.items():
            assert sha(ROOT / relative) == expected
        if (output / "acceptance.jfr").exists():
            command([str(JAVA_HOME / "bin/jfr.exe"), "summary", str(output / "acceptance.jfr")], output / "jfr-summary")
        receipt["passed"] = True
    except BaseException as error:
        receipt["error"] = repr(error)
        receipt["ended"] = now()
        raise
    finally:
        if process is not None: process.close()
        write(output / "execution.json", receipt)
    print(json.dumps({"target": target, "mode": mode, "pid": actual.pid, "exit_code": receipt["exit_code"], "passed": receipt["passed"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "launch"))
    parser.add_argument("--target", choices=tuple(SOURCES))
    parser.add_argument("--mode", choices=("faults", "mismatch"))
    args = parser.parse_args()
    if args.action == "prepare": prepare()
    else:
        assert args.target and args.mode
        launch(args.target, args.mode)
