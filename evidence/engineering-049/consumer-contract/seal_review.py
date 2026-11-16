"""Verify the retained focused runs and seal all their exact payload bytes."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    first, targeted, diagnostic = [read(ROOT / name / "execution.json") for name in
        ("run-01", "run-02-targeted", "run-03-diagnostic")]
    assert first["test_count"] == 100 and first["exit_code"] == 1
    assert targeted["test_count"] == 3 and targeted["exit_code"] == 1
    for name, receipt in (("run-01", first), ("run-02-targeted", targeted)):
        assert receipt["source_sha256_before"] == receipt["source_sha256_after"]
        assert sha(ROOT / name / "stdout.log") == receipt["stdout_sha256"]
        assert sha(ROOT / name / "stderr.log") == receipt["stderr_sha256"]
        assert sha(ROOT / name / "runner-source.py") == receipt["runner_sha256"]
    assert first["source_sha256_before"] == targeted["source_sha256_before"]
    failures = {}
    for name in ("run-01", "run-02-targeted"):
        text = (ROOT / name / "stderr.log").read_text(encoding="utf-8")
        failures[name] = re.findall(r"^FAIL: ([^\n]+)", text, re.MULTILINE)
    assert len(failures["run-01"]) == 3 and len(failures["run-02-targeted"]) == 1
    assert diagnostic["tests"] == 1 and diagnostic["passed"]
    assert diagnostic["source_sha256_before"] == diagnostic["source_sha256_after"]
    observation = ROOT / "run-03-diagnostic/completed-observation"
    summary = read(observation / "summary.json")
    assert summary["passed"] and summary["verified_sample_count"] == summary["sample_count"] == 16
    assert summary["route_window_evidence"]["passed"] and not summary["observed_failures"]
    assert summary["auxiliary_available_samples"]["nmt"] == summary["auxiliary_attempted_samples"]["nmt"] == 1
    assert summary["auxiliary_shutdown"]["worker_stopped"]
    assert not summary["auxiliary_shutdown"]["uncompleted_request_ids"]
    terminal = summary["terminal_auxiliary_events"]
    assert len(terminal) == 1 and terminal[0]["post_sampling_window"]
    assert terminal[0]["elapsed_seconds"] > summary["elapsed_seconds"] >= summary["policy"]["duration"]
    assert sha(observation / "samples.jsonl") == summary["samples_sha256"]
    assert sha(observation / "auxiliary-events.jsonl") == summary["auxiliary_events_sha256"]
    assessment = {"timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "sealed_controls_verified": True,
                  "initial_suite": {"tests": 100, "failures": failures["run-01"], "passed_tests": 97},
                  "targeted_repeat": {"tests": 3, "failures": failures["run-02-targeted"], "passed_tests": 2},
                  "retained_shutdown_diagnostic_passed": True,
                  "all_green_single_full_suite": False,
                  "original_failed_summary_available": False,
                  "production_or_existing_timing_test_changed": False,
                  "scope": "Reviewed neutral consumer contract and retained engineering controls; no actual client/reload/gameplay/performance acceptance."}
    (ROOT / "assessment.json").write_text(json.dumps(assessment, indent=2)+"\n", encoding="utf-8")
    index_path = ROOT / "sha256-index.json"
    files = {path.relative_to(ROOT).as_posix(): {"sha256": sha(path), "bytes": path.stat().st_size}
             for path in sorted(ROOT.rglob("*")) if path.is_file() and path != index_path}
    index_path.write_text(json.dumps({"files": files}, indent=2)+"\n", encoding="utf-8")
    for relative, receipt in files.items():
        assert sha(ROOT / relative) == receipt["sha256"] and (ROOT / relative).stat().st_size == receipt["bytes"]
    print(json.dumps({"sealed_controls_verified": True, "indexed_payloads": len(files)}))


if __name__ == "__main__":
    main()
