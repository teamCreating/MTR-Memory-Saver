"""Verify only the sealed unfinished-run evidence; never read a game directory."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(sealed):
    index = read(sealed / "SHA256SUMS.json")["files"]
    actual_files = {path.relative_to(BASE).as_posix() for path in sealed.rglob("*")
                    if path.is_file() and path.name != "SHA256SUMS.json"}
    require(set(index) == actual_files, "Sealed payload inventory changed")
    for relative, item in index.items():
        path = (BASE / relative).resolve(strict=True)
        require(sealed.resolve() in path.parents, "Payload path escapes sealed directory")
        require(sha(path) == item["sha256"] and path.stat().st_size == item["bytes"], "Payload changed: " + relative)
    assessment = read(sealed / "assessment.json")
    original = read(sealed / "collector/execution.json")
    plan = read(sealed / "instance/packaged-client-plan.json")
    launch = read(sealed / "instance/packaged-client-launch.json")
    require(assessment["scope"] == "retrospective_unfinished_diagnostic_run_observation", "Wrong evidence scope")
    require(assessment["exit_code"] is None and assessment["exit_time"] is None
            and assessment["termination_cause"] == "unknown" and assessment["normal_exit_verified"] is False
            and assessment["interruption_action_observed"] is False, "Unknown exit was relabeled")
    require(original["status"] == "observing" and "exit_code" not in original and "ended" not in original,
            "Original nonterminal receipt changed")
    pid = assessment["pid"]
    require(pid == original["pid"] == launch["pid"], "Original identities differ")
    require(sha(sealed / "instance/packaged-client-plan.json") == launch["plan_sha256"], "Launch plan mismatch")
    current = read(sealed / "current-process.json")
    query = read(sealed / "current-process.execution.json")
    require(query["exit_code"] == 0 and current["target_pid"] == pid and not current["process_records"]
            and not current["matching_collectors"], "Actual process-absence query is incomplete")
    require(sha(sealed / "current-process.stdout.log") == query["stdout_sha256"]
            and sha(sealed / "current-process.stderr.log") == query["stderr_sha256"], "Query logs changed")
    require(read(sealed / "current-process.stdout.log") == current, "Query result differs from actual stdout")
    snapshots = [json.loads(line) for line in (sealed / "collector/native-snapshots.jsonl").read_text(encoding="utf-8").splitlines()]
    require(len(snapshots) == assessment["native_snapshot_records"], "Snapshot record count differs")
    require(all(item["snapshot"]["pid"] == pid for item in snapshots), "Foreign snapshot PID")
    require(snapshots[-1]["snapshot"] == read(sealed / "instance/game-probe/native-observer.json"), "Final snapshot differs")
    require(snapshots[-1]["captured_at"] == assessment["last_capture"]
            and snapshots[-1]["snapshot"]["observed_at"] == assessment["last_native_observation"], "Last observation differs")
    require((sealed / "instance/acceptance.jfr").stat().st_size == assessment["empty_jfr"]["bytes"] == 0
            and sha(sealed / "instance/acceptance.jfr") == assessment["empty_jfr"]["sha256"], "Empty recording changed")
    source_count = 0
    for entry in plan["mods"]:
        if entry["role"] not in ("companion", "observer"):
            continue
        jar = sealed / "artifacts" / entry["filename"]
        manifest = read(jar.with_suffix(".build.json"))
        require(sha(jar) == manifest["sha256"] == entry["sha256"], "Installed artifact/manifest identity differs")
        for relative, digest in manifest["inputs"].items():
            require(sha(sealed / "artifact-sources" / entry["role"] / relative) == digest, "Pinned build input differs")
            source_count += 1
    require(source_count == assessment["sealed_companion_and_observer_manifest_inputs"], "Manifest input count differs")
    for name, digest in original["sources"].items():
        require(sha(sealed / "collector-sources/tools" / name) == digest, "Original collector source differs")
    return {"passed": True, "scope": assessment["scope"], "payload_count": len(index),
            "native_snapshot_records": len(snapshots), "manifest_inputs": source_count,
            "normal_exit_verified": False, "exit_code": None, "termination_cause": "unknown",
            "gameplay_performance_or_completed_reload_acceptance": False,
            "limits": "Sealed-only integrity audit; no current game, world, pack, JDK or process reads."}


if __name__ == "__main__":
    output = BASE / sys.argv[2]
    require(not output.exists(), "Do not overwrite a verification receipt")
    result = {"started": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(), "source_sha256": sha(Path(__file__)),
              "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], "passed": False}
    try:
        result.update(verify(BASE / sys.argv[1]))
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        result["ended"] = datetime.now(timezone.utc).isoformat()
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    print(json.dumps(result))
