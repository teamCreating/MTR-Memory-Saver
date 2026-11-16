"""Independently assess the retained pilot records; never read a live game or run a capture."""
from datetime import datetime, timezone
import codecs
import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(path):
    raw = path.read_bytes()
    return raw.decode("utf-16") if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else raw.decode("utf-8-sig")


def require(value, message):
    if not value:
        raise ValueError(message)


def assess():
    receipts = 0
    for path in sorted(BASE.rglob("*.execution.json")):
        item = read(path)
        if "stdout_sha256" not in item:
            continue
        label = path.name.removesuffix(".execution.json")
        require(sha(path.with_name(label + ".stdout.log")) == item["stdout_sha256"], "Stdout changed: " + str(path))
        require(sha(path.with_name(label + ".stderr.log")) == item["stderr_sha256"], "Stderr changed: " + str(path))
        require(item["helper_exited"] is True, "Owned tool was not observed exited")
        for pair in (item["start_clock"], item["end_clock"]):
            require(pair["qpc_after"] >= pair["qpc_before"] and pair["frequency_hz"] > 0, "Bad QPC/UTC witness")
        receipts += 1
    vendor = BASE / "capture-01"
    vendor_start = read(vendor / "capture-start.json")
    vendor_exit = read(vendor / "capture.execution.json")
    require(vendor_exit["exit_code"] == 1 and not vendor_exit.get("timeout"), "Vendor failure receipt changed")
    require(not list(vendor.glob("*.csv")), "Vendor output changed")
    require(read(vendor / "target-before.json")["processes"] == read(vendor / "target-after.json")["processes"], "Vendor target identity differs")
    upstream = BASE / "upstream-capture-02"
    capture = read(upstream / "capture-start.json")
    command = capture["argv"]
    require(command[command.index("--process_id") + 1] == "18796" and command[command.index("--timed") + 1] == "25", "Unexpected target/duration")
    require(command[command.index("--session_name") + 1] == capture["session_name"], "Unique session mismatch")
    require(not set(command) & {"--stop_existing_session", "--terminate_existing_session", "--restart_as_admin", "--hotkey"}, "Unexpected session/input/privilege control")
    require(not list(upstream.glob("*.csv")), "Upstream output changed")
    stdout = text(upstream / "capture.stdout.log")
    require("Started recording." in stdout and "Stopped recording." in stdout, "Original trace lifecycle output differs")
    failure = read(upstream / "execution.json")
    require(failure["passed"] is False and "31" in failure["error"], "Original wrapper error changed")
    require(not (upstream / "capture.execution.json").exists() and not (upstream / "capture-exit.json").exists(), "Missing original exit receipt was backfilled")
    helper = read(upstream / "owned-helper.stdout.log")["processes"]
    require(len(helper) == 1 and helper[0]["ProcessId"] == capture["helper_pid"] == capture["actual_owned_helper"]["pid"], "Actual helper ownership differs")
    native = read(upstream / "native-session-query-during.json")
    require(native["session_name"] == capture["session_name"] and native["status"] == 0, "Live unique session witness differs")
    require(all(native["counters"][name] == 0 for name in ("EventsLost", "LogBuffersLost", "RealTimeBuffersLost")), "Retained query-point counters differ")
    recovery = read(BASE / "upstream-recovery-01/assessment.json")
    require(recovery["helper_currently_absent"] is True and recovery["unique_session_absent"] is True, "Later cleanup observation differs")
    require(recovery["original_helper_exit_code"] is None and not (BASE / "upstream-recovery-01/only-owned-orphan-session-cleanup.execution.json").exists(), "Unexpected exit inference or session stop")
    require(read(BASE / "upstream-recovery-01/target-current.json")["processes"] == read(upstream / "target-before.json")["processes"], "Upstream target identity changed")
    download = read(BASE / "upstream-download-01/download.execution.json")
    release = read(BASE / "upstream-download-01/release-api.json")
    require(download["passed"] is True and release["tag_name"] == "v2.6.0" and release["html_url"] == download["release"], "Official release binding differs")
    asset, = [asset for asset in release["assets"] if asset["id"] == download["asset_id"]]
    require(asset["digest"] == download["official_asset_digest"] == "sha256:" + download["sha256"], "Official asset digest differs")
    for folder in ("upstream-help-01", "upstream-capture-01", "upstream-capture-02"):
        metadata = read(BASE / folder / "binary-and-token.json")
        require(metadata["signature_status"] == "Valid" and "Intel Corporation" in metadata["signer"], "Signer observation differs")
        require(sha(BASE / folder / "PresentMon-2.6.0-x64.exe") == download["sha256"], "Official captured binary differs")
    require("PresentMon 2.6.0" in text(BASE / "upstream-help-01/help.stdout.log"), "Actual help version differs")
    require(read(BASE / "upstream-capture-01/execution.json")["passed"] is False
            and not (BASE / "upstream-capture-01/capture-start.json").exists(), "Preflight failure became a capture")
    control = read(BASE / "owned-child-control-01/execution.json")
    child_exit = read(BASE / "owned-child-control-01/child-exit.json")
    require(control["passed"] is True and child_exit["exit_code"] == 7 and control["presentmon_or_minecraft_launched"] is False,
            "Ordinary owned-child control differs")
    require(control["original_api_failure_reproduced"] is True and control["exit_receipt_preserved_through_post_check"] is True,
            "Actual post-exit failure control differs")
    require(sha(BASE / "owned-child-control-01/child-exit.json") == control["exit_receipt_sha256"], "Wait receipt changed after control")
    return {"audit_passed": True, "scope": "external_OpenGL_data_source_feasibility_only", "command_receipts_verified": receipts,
        "actual_presentmon_capture_attempts": 2, "extra_upstream_preflight_only_attempts": 1,
        "target_pid": 18796, "target_before_later_after_identity_equal": True,
        "vendor": {"helper_pid": vendor_start["helper_pid"], "observed_exit_code": 1, "csv_available": False},
        "upstream": {"version_from_actual_help": "2.6.0", "helper_pid": capture["helper_pid"],
            "actual_creation": capture["actual_owned_helper"]["created"], "official_asset_sha256": download["sha256"],
            "started_and_stopped_recording_messages": True, "unique_session_observed_live": True,
            "query_point_loss_counters": native, "whole_window_loss_verified": False,
            "original_wait_exit_code": None, "original_wrapper_error": failure["error"],
            "helper_later_absent": True, "unique_session_later_absent": True, "csv_available": False},
        "csv_schema": None, "external_present_metrics": None, "native_render_loop_metrics": None,
        "capture_data_source_available": False, "calibration_accepted": False, "performance_accepted": False,
        "wrapper_owned_child_control_passed": True,
        "limits": ["Neither requested output directory contains an actual CSV; no frame schema or intervals can be certified.",
            "The exact attempted OpenGL/display path yielded no target present data; this does not prove general driver/API incompatibility.",
            "Query-point zero losses do not establish whole-window zero losses or complete target-frame coverage.",
            "The upstream wrapper failed after wait but before saving that result; its actual helper exit code remains unavailable.",
            "The separate Python child proves engineering behavior only and cannot reconstruct the PresentMon exit code.",
            "No keyboard/mouse input, permission/service changes, session-stop commands or third PresentMon capture were executed.",
            "No current game, installed binary, source world, packs, JVM libraries or source files are read by this sealed-only audit."]}


if __name__ == "__main__":
    output = BASE / sys.argv[1]
    require(not output.exists(), "Do not overwrite an assessment")
    result = {"started": datetime.now(timezone.utc).isoformat(), "source_sha256": sha(Path(__file__)), "audit_passed": False}
    try:
        result.update(assess())
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        result["ended"] = datetime.now(timezone.utc).isoformat()
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    print(json.dumps({key: result[key] for key in ("audit_passed", "capture_data_source_available", "actual_presentmon_capture_attempts", "calibration_accepted")}))
