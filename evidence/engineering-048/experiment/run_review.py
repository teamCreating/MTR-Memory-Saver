"""Reproduce tooling controls; no Minecraft client or performance trial is started."""
import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import client_experiment as client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    java = args.java.resolve(strict=True)
    sources = [*client.SOURCES, ROOT / "tools/test_client_experiment.py", ROOT / "docs/CLIENT_EXPERIMENT.md", Path(__file__)]
    before = [client.fingerprint(path) for path in sources]
    for path in sources:
        destination = output / "source" / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    command = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tools", "-p", "test_client_experiment.py", "-v"]
    tests = subprocess.run(command, cwd=ROOT, capture_output=True)
    (output / "tests.stdout.log").write_bytes(tests.stdout)
    (output / "tests.stderr.log").write_bytes(tests.stderr)
    real_run = subprocess.run
    captures = []

    def captured_run(command, **kwargs):
        record = {"command": command, "started_at": client.now()}
        result = real_run(command, **kwargs)
        index = len(captures)
        stdout_path = output / f"jfr-command-{index:02d}.stdout.log"
        stderr_path = output / f"jfr-command-{index:02d}.stderr.log"
        stdout_path.write_text(result.stdout, encoding="utf-8", newline="\n")
        stderr_path.write_text(result.stderr, encoding="utf-8", newline="\n")
        record.update(finished_at=client.now(), returncode=result.returncode,
                      stdout=client.fingerprint(stdout_path), stderr=client.fingerprint(stderr_path))
        captures.append(record)
        return result

    parsing = []
    with mock.patch.object(client.subprocess, "run", side_effect=captured_run):
        for target in ("official-nf248", "official-nf265"):
            source = ROOT / "evidence/engineering-047/neutral-observer" / target / "final/frame-events.jfr"
            original = client.fingerprint(source)
            events, coverage = client.parse_jfr_recording(source, java)
            # The original fixture exports contain the independently emitted
            # frame/tick pair. This parser intentionally requests frame/GC only.
            saved = client.read(source.with_suffix(".json"))["recording"]["events"]
            expected = [event for event in saved if event["type"] in ("mtrtest.ClientFrame", "jdk.GarbageCollection", "jdk.GCPhasePause")]
            matching = events == expected
            corrupt = output / (target + "-truncated-control.jfr")
            corrupt.write_bytes(source.read_bytes()[:8])
            rejection = None
            try:
                client.parse_jfr_recording(corrupt, java)
            except ValueError as error:
                rejection = str(error)
            unchanged = original == client.fingerprint(source)
            parsing.append({"target": target, "source": original, "source_unchanged": unchanged,
                            "events_match_original_export": matching, "event_count": len(events), "coverage": coverage,
                            "truncated_control": client.fingerprint(corrupt), "truncated_rejection": rejection,
                            "passed": matching and unchanged and rejection is not None})
    after = [client.fingerprint(path) for path in sources]
    passed = tests.returncode == 0 and before == after and all(item["passed"] for item in parsing)
    report = {"schema": 1, "started_at": started, "finished_at": client.now(), "passed": passed,
              "scope": "Synthetic experiment controls and actual JDK parsing of existing standalone event-schema recordings; not gameplay or performance acceptance",
              "test_command": command, "test_returncode": tests.returncode,
              "java": client.fingerprint(java), "jfr": client.fingerprint(java.with_name("jfr.exe")),
              "source_before": before, "source_after": after, "source_unchanged": before == after,
              "jfr_parsing": parsing, "jfr_commands": captures,
              "remaining_gates": ["four_actual_current_client_qualification_groups", "48_actual_scheduled_trials", "neutral_observer_off_calibration"]}
    client.save(output / "assessment.json", report, exclusive=True)
    client.save(output / "sha256.json", client.raw_files(output), exclusive=True)
    print(json.dumps({"passed": passed, "tests": tests.returncode, "actual_jfr_controls": [item["passed"] for item in parsing], "source_unchanged": before == after}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
