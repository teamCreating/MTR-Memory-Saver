"""Read-only capture of an existing JVM; attribution is not gameplay acceptance."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from client_experiment_analysis import native_diagnostics
from native_diagnostic_review import review_diagnostics, validate_review
from windows_snapshot_io import read_snapshot_bytes


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read(path):
    return json.loads(path.read_bytes())


def capture(instance, output, pid):
    instance = instance.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=False)
    (output / "capture-script.py").write_bytes(Path(__file__).read_bytes())
    report = {"schema": 1, "scope": "Live startup prefix and native diagnostic attribution only; no gameplay or performance acceptance",
              "capture_started": now(), "instance": str(instance), "pid": pid, "status": "capturing"}
    write(output / "capture.json", report)

    def copy(relative, *, source_root=instance, destination=None):
        source = source_root / relative
        target = output / (destination or relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        return target

    def process_receipt(label):
        # The only shell interpolation is the validated integer PID. This queries
        # Win32_Process; it sends no input, attach, stop or management request.
        command = ("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
                   f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | "
                   "Select-Object ProcessId,ExecutablePath,CommandLine,@{Name='CreatedUtc';"
                   "Expression={$_.CreationDate.ToUniversalTime().ToString('o')}} | ConvertTo-Json -Depth 4")
        result = subprocess.run(["pwsh", "-NoProfile", "-Command", command], capture_output=True, check=True)
        (output / f"process-{label}.stdout.json").write_bytes(result.stdout)
        (output / f"process-{label}.stderr.log").write_bytes(result.stderr)
        raw = json.loads(result.stdout)
        assert raw["ProcessId"] == pid
        return {"pid": raw["ProcessId"], "created": raw["CreatedUtc"],
                "executable": raw["ExecutablePath"], "command_line": raw["CommandLine"], "captured_at": now()}

    try:
        process = process_receipt("before")
        write(output / "process.json", process)
        plan = read(copy(Path("packaged-client-plan.json")))
        launch = read(copy(Path("packaged-client-launch.json")))
        assert launch["pid"] == pid and launch["plan_sha256"] == digest(output / "packaged-client-plan.json")
        assert Path(plan["instance"]).resolve() == instance
        copy(Path("options.txt"))
        sources = ["tools/client_experiment_analysis.py", "tools/native_diagnostic_review.py", "tools/windows_snapshot_io.py",
                   "tools/packaged_client.py", "config/native-diagnostic-review.json"]
        report["consumer_sources"] = {}
        for relative in sources:
            target = copy(Path(relative), source_root=ROOT, destination="sources/" + relative)
            report["consumer_sources"][relative] = digest(target)
        report["launcher_source_matches_receipt"] = report["consumer_sources"]["tools/packaged_client.py"] == launch["launcher_tool_sha256"]
        report["options_match_plan_at_capture"] = digest(output / "options.txt") == plan["options_sha256"]
        report["mods"] = []
        for item in plan["mods"]:
            actual = digest(instance / "mods" / item["filename"])
            assert actual == item["sha256"], item["filename"]
            report["mods"].append({**item, "actual_sha256": actual})
        assert {p.name for p in (instance / "mods").glob("*.jar")} == {item["filename"] for item in plan["mods"]}
        report["packs"] = []
        for item in plan["packs"]:
            installed, source = digest(instance / "resourcepacks" / item["filename"]), digest(item["source"])
            assert installed == source == item["sha256"], item["filename"]
            report["packs"].append({**item, "installed_sha256": installed, "source_sha256": source})
        observer = next(item for item in plan["mods"] if item["role"] == "observer")
        with zipfile.ZipFile(instance / "mods" / observer["filename"]) as jar:
            metadata_bytes = jar.read("mtr-native-observer-target.json")
            (output / "observer-target.json").write_bytes(metadata_bytes)
            metadata = json.loads(metadata_bytes)
            report["observer_classes"] = {name: hashlib.sha256(jar.read(name)).hexdigest()
                                          for name in jar.namelist() if name.endswith(".class")}
        build_path = Path("evidence/engineering-048/neutral-diagnostics/final-official-nf248/mtr-native-observer-official-nf248-1.0.2.build.json")
        build = read(copy(build_path, source_root=ROOT, destination="observer-build.json"))
        assert build["sha256"] == observer["sha256"]
        report["observer_source_checks"] = []
        for relative, expected in build["inputs"].items():
            target = copy(Path(relative), source_root=ROOT, destination="sources/" + relative)
            actual = digest(target)
            report["observer_source_checks"].append({"path": relative, "expected": expected, "actual": actual, "matches": actual == expected})
        client = instance / "libraries/net/neoforged/neoforge" / metadata["neoForge"] / ("neoforge-" + metadata["neoForge"] + "-client.jar")
        report["patched_client"] = {"path": str(client), "sha256": digest(client), "classes": {}}
        with zipfile.ZipFile(client) as jar:
            for name in ("net/minecraft/client/KeyboardHandler.class", "net/minecraft/client/Minecraft.class"):
                report["patched_client"]["classes"][name] = hashlib.sha256(jar.read(name)).hexdigest()
        snapshots = []
        distinct_times = set()
        deadline = time.monotonic() + 15
        while len(distinct_times) < 3 and time.monotonic() < deadline:
            raw = read_snapshot_bytes(instance / "game-probe/native-observer.json")
            (output / f"snapshot-{len(snapshots) + 1:02d}.json").write_bytes(raw)
            snapshots.append({"captured_at": now(), "snapshot": json.loads(raw)})
            distinct_times.add(snapshots[-1]["snapshot"]["observed_at"])
            time.sleep(0.5)
        report["stream_captures"] = {}
        for relative in ("logs/latest.log", "game-probe/native-invalid-model.jsonl", "game-probe/native-resource-epochs.jsonl"):
            started = now()
            target = copy(Path(relative))
            report["stream_captures"][relative] = {"started": started, "ended": now(), "bytes": target.stat().st_size, "sha256": digest(target)}
        final_bytes = read_snapshot_bytes(instance / "game-probe/native-observer.json")
        (output / "final-snapshot.json").write_bytes(final_bytes)
        final_snapshot = json.loads(final_bytes)
        snapshots.append({"captured_at": now(), "snapshot": final_snapshot})
        write(output / "snapshot-receipts.json", snapshots)
        assert len(distinct_times) >= 3, "Snapshots did not advance within the capture deadline."
        moments = [row["snapshot"]["monotonic_nanos"] for row in snapshots]
        assert moments == sorted(moments), "Snapshot time regressed."
        for row in snapshots:
            state = row["snapshot"]
            assert state["pid"] == pid and state["native_settled"] and state["native_pending"] == 0
            assert state["resource_epochs"]["in_flight"] == 0 and state["observation_errors"] == 0
        after = process_receipt("after")
        assert all(after[key] == process[key] for key in ("pid", "created", "executable", "command_line"))
        window = {"start": plan["timestamp"], "end": now()}
        write(output / "run-window.json", window)
        log_text = (output / "logs/latest.log").read_text(encoding="utf-8")
        events = [json.loads(line) for line in (output / "game-probe/native-invalid-model.jsonl").read_bytes().splitlines()]
        epochs = [json.loads(line) for line in (output / "game-probe/native-resource-epochs.jsonl").read_bytes().splitlines()]
        review = read(output / "sources/config/native-diagnostic-review.json")
        validate_review(review, metadata, root=ROOT)
        result = review_diagnostics(native_diagnostics(log_text), log_text, events, epochs, process, metadata, review, window, final_snapshot)
        write(output / "diagnostic-review.json", result)
        report.update(status="captured", capture_ended=now(), attribution_passed=result["native_attribution"]["passed"],
                      snapshot_count=len(snapshots), final_observed_at=final_snapshot["observed_at"])
        write(output / "capture.json", report)
        print(json.dumps({"status": report["status"], "pid": pid, "attribution": result["native_attribution"],
                          "unreviewed_native": result["unreviewed_native"], "other_errors": result["other_errors_requiring_contextual_review"]}, indent=2))
    except BaseException as error:
        report.update(status="failed", capture_ended=now(), failure=repr(error))
        write(output / "capture.json", report)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    args = parser.parse_args()
    assert args.pid > 0
    capture(args.instance, args.output, args.pid)
