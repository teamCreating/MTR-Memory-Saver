"""Bounded, owned external-present feasibility only; never send game input."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from native_etw import child_identity, query_session

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
EXPECTED_BINARY_SHA256 = "25fcc45da599b13c434d022c57214972b9fd64608e4820c399f41d01fb1961ba"
BINARY = Path(r"C:\Program Files\NVIDIA Corporation\FrameViewSDK\bin\PresentMon_x64.exe")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def require(value, message):
    if not value:
        raise ValueError(message)


def clock_pair():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.QueryPerformanceCounter.argtypes = [ctypes.POINTER(ctypes.c_longlong)]
    kernel.QueryPerformanceFrequency.argtypes = [ctypes.POINTER(ctypes.c_longlong)]
    before, after, frequency = [ctypes.c_longlong() for _ in range(3)]
    require(kernel.QueryPerformanceFrequency(ctypes.byref(frequency)), "QPC frequency unavailable")
    require(kernel.QueryPerformanceCounter(ctypes.byref(before)), "QPC unavailable")
    utc = now()
    require(kernel.QueryPerformanceCounter(ctypes.byref(after)), "QPC unavailable")
    return {"utc_between_qpc_reads": utc, "qpc_before": before.value, "qpc_after": after.value,
            "frequency_hz": frequency.value, "pair_span_seconds": (after.value-before.value)/frequency.value}


def execute(command, folder, label, timeout=20):
    started = clock_pair()
    receipt = {"argv": command, "cwd": str(folder), "started": now(), "start_clock": started,
               "owner": {"pid": os.getpid(), "script": str(Path(__file__)), "source_sha256": sha(Path(__file__))}}
    with (folder / (label + ".stdout.log")).open("xb") as stdout, (folder / (label + ".stderr.log")).open("xb") as stderr:
        child = subprocess.Popen(command, cwd=folder, stdout=stdout, stderr=stderr,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        receipt["helper_pid"] = child.pid
        try:
            receipt["exit_code"] = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            receipt["timeout"] = True
            # Popen owns this helper. This never targets the game or another session.
            child.terminate()
            receipt["exit_code"] = child.wait(timeout=10)
            receipt["cleanup"] = "terminated_only_owned_helper_after_timeout"
        receipt.update(ended=now(), end_clock=clock_pair(), helper_exited=child.poll() is not None)
    receipt["stdout_sha256"] = sha(folder / (label + ".stdout.log"))
    receipt["stderr_sha256"] = sha(folder / (label + ".stderr.log"))
    write(folder / (label + ".execution.json"), receipt)
    return receipt


def ps(script, folder, label):
    command = ["pwsh", "-NoProfile", "-Command", "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); " + script]
    receipt = execute(command, folder, label, timeout=35)
    require(receipt["exit_code"] == 0 and not receipt.get("timeout"), "PowerShell read failed: " + label)
    return json.loads((folder / (label + ".stdout.log")).read_text(encoding="utf-8-sig"))


def metadata(folder):
    require(sha(BINARY) == EXPECTED_BINARY_SHA256, "Installed executable hash changed")
    data = ps("$pmFile=Get-Item -LiteralPath '" + str(BINARY) + "'; "
        "$pmSignature=Get-AuthenticodeSignature -LiteralPath $pmFile.FullName; "
        "$pmPrincipal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()); "
        "@{observed_at=[DateTimeOffset]::UtcNow.ToString('o'); path=$pmFile.FullName; bytes=$pmFile.Length; "
        "file_version=$pmFile.VersionInfo.FileVersion; product_version=$pmFile.VersionInfo.ProductVersion; "
        "company=$pmFile.VersionInfo.CompanyName; signature_status=$pmSignature.Status.ToString(); "
        "signer=$pmSignature.SignerCertificate.Subject; administrator=$pmPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator); "
        "performance_log_users=$pmPrincipal.IsInRole([Security.Principal.SecurityIdentifier]::new('S-1-5-32-559'))} | ConvertTo-Json -Depth 4",
        folder, "binary-and-token")
    require(data["signature_status"] == "Valid" and data["performance_log_users"] is True, "Binary/token precondition changed")
    data["sha256"] = sha(BINARY)
    write(folder / "binary-and-token.json", data)
    shutil.copy2(BINARY, folder / BINARY.name)
    return data


def inspect_target(args, folder, label):
    result = ps(f"$pmTarget=@(Get-CimInstance Win32_Process -Filter 'ProcessId = {args.pid}' -ErrorAction Stop | "
        "ForEach-Object {@{pid=[int]$_.ProcessId; created=$_.CreationDate.ToUniversalTime().ToString('o'); "
        "executable=$_.ExecutablePath; command=$_.CommandLine}}); "
        "@{observed_at=[DateTimeOffset]::UtcNow.ToString('o'); processes=$pmTarget} | ConvertTo-Json -Depth 5", folder, label)
    require(len(result["processes"]) == 1, "Owned game is unavailable")
    target = result["processes"][0]
    launch = json.loads((args.instance / "packaged-client-launch.json").read_text(encoding="utf-8-sig"))
    plan = json.loads((args.instance / "packaged-client-plan.json").read_text(encoding="utf-8-sig"))
    require(launch["pid"] == target["pid"] == args.pid and Path(target["executable"]).resolve() == Path(plan["java"]).resolve(), "Actual game identity differs")
    require(str(args.instance.resolve()).lower() in target["command"].lower(), "Actual game directory differs")
    age = abs((datetime.fromisoformat(target["created"].replace("Z", "+00:00")) - datetime.fromisoformat(args.created.replace("Z", "+00:00"))).total_seconds())
    require(age <= 0.01, "Actual process creation does not match authorized owner")
    write(folder / (label + ".json"), result)
    return result


def capture(args, folder):
    help_dir = args.help_directory.resolve(strict=True)
    help_receipt = json.loads((help_dir / "help.execution.json").read_text(encoding="utf-8"))
    # This exact signed vendor binary prints complete --help to stderr and exits
    # 1. Preserve the first wrapper's rejected exit-zero assumption separately;
    # accept that receipt only as reviewed CLI schema, never as a capture pass.
    require(help_receipt["argv"] == [str(BINARY), "--help"] and help_receipt["exit_code"] in (0, 1)
            and help_receipt["helper_exited"] is True and not help_receipt.get("timeout"), "Help did not complete")
    text = (help_dir / "help.stdout.log").read_text(encoding="utf-8-sig") + (help_dir / "help.stderr.log").read_text(encoding="utf-8-sig")
    required = ("--process_id", "--session_name", "--output_file", "--timed", "--terminate_after_timed", "--qpc_time",
                "--no_console_stats", "--no_track_input", "--no_track_gpu")
    require(all(option in text for option in required), "Actual help does not support the reviewed command")
    require(all(section in text for section in ("Capture Target Options:", "Output Options:", "Recording Options:", "Execution Options:", "Beta Options:")), "Help schema is incomplete")
    write(folder / "help-review.json", {"binary_sha256": EXPECTED_BINARY_SHA256, "original_help_exit_code": help_receipt["exit_code"],
          "original_wrapper_failed": not json.loads((help_dir / "execution.json").read_text(encoding="utf-8"))["passed"],
          "scope": "actual_help_schema_only_not_capture_acceptance", "required_options": required,
          "help_receipt_sha256": sha(help_dir / "help.execution.json"),
          "help_stdout_sha256": sha(help_dir / "help.stdout.log"), "help_stderr_sha256": sha(help_dir / "help.stderr.log")})
    require(20 <= args.duration <= 30, "Pilot must stay within its authorized 20–30 seconds")
    for name in ("packaged-client-launch.json", "packaged-client-plan.json"):
        shutil.copy2(args.instance / name, folder / name)
    before = inspect_target(args, folder, "target-before")
    execute(["logman", "query", "-ets"], folder, "sessions-before")
    session = "mtr-present-feasibility-" + uuid.uuid4().hex
    absent = execute(["logman", "query", session, "-ets"], folder, "unique-session-before")
    require(absent["exit_code"] != 0, "Unique proposed ETW session is already present")
    command = [str(BINARY), "--process_id", str(args.pid), "--session_name", session,
               "--output_file", str(folder / "presents.csv"), "--timed", str(args.duration),
               "--terminate_after_timed", "--qpc_time", "--no_console_stats", "--no_track_input", "--no_track_gpu"]
    write(folder / "capture-intent.json", {"argv": command, "session_name": session, "duration_seconds": args.duration,
          "scope": "external_OpenGL_present_source_feasibility_only", "target_before": before,
          "not_calibration_comparison_or_gameplay_acceptance": True, "clock": clock_pair()})
    # A separate bounded query witnesses the actual session while this helper runs.
    with (folder / "capture.stdout.log").open("xb") as stdout, (folder / "capture.stderr.log").open("xb") as stderr:
        receipt = {"argv": command, "cwd": str(folder), "started": now(), "start_clock": clock_pair(),
                   "owner_pid": os.getpid(), "runner_sha256": sha(Path(__file__)), "session_name": session}
        child = subprocess.Popen(command, cwd=folder, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        receipt["helper_pid"] = child.pid
        receipt["actual_owned_helper"] = child_identity(child)
        require(Path(receipt["actual_owned_helper"]["executable"]).resolve() == BINARY.resolve(), "Owned helper image differs")
        write(folder / "capture-start.json", receipt)
        time.sleep(2)
        ps(f"$pmHelper=@(Get-CimInstance Win32_Process -Filter 'ProcessId = {child.pid}' -ErrorAction Stop | "
           "Select-Object ProcessId,CreationDate,ExecutablePath,CommandLine); "
           "@{observed_at=[DateTimeOffset]::UtcNow.ToString('o'); processes=$pmHelper} | ConvertTo-Json -Depth 5",
           folder, "owned-helper")
        execute(["logman", "query", session, "-ets"], folder, "unique-session-during")
        write(folder / "native-session-query-during.json", query_session(session))
        try:
            receipt["exit_code"] = child.wait(timeout=args.duration + 15)
        except subprocess.TimeoutExpired:
            receipt["timeout"] = True
            child.terminate()
            receipt["exit_code"] = child.wait(timeout=10)
            receipt["cleanup"] = "terminated_only_owned_presentmon_helper_after_timeout"
            execute(["logman", "stop", session, "-ets"], folder, "owned-session-timeout-cleanup")
        receipt.update(ended=now(), end_clock=clock_pair(), helper_exited=child.poll() is not None)
        receipt["actual_owned_helper_after"] = child_identity(child)
    receipt.update(stdout_sha256=sha(folder / "capture.stdout.log"), stderr_sha256=sha(folder / "capture.stderr.log"))
    write(folder / "capture.execution.json", receipt)
    execute(["logman", "query", session, "-ets"], folder, "unique-session-after")
    write(folder / "native-session-query-after.json", query_session(session))
    execute(["logman", "query", "-ets"], folder, "sessions-after")
    after = inspect_target(args, folder, "target-after")
    require(before["processes"] == after["processes"], "Target identity changed during pilot")
    require(sha(BINARY) == EXPECTED_BINARY_SHA256, "Installed executable changed during pilot")
    require(receipt["exit_code"] == 0 and not receipt.get("timeout"), "PresentMon capture failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("help", "capture"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--help-directory", type=Path)
    parser.add_argument("--instance", type=Path)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--created")
    parser.add_argument("--duration", type=int, default=25)
    parser.add_argument("--download-receipt", type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"started": now(), "argv": [sys.executable, str(Path(__file__)), *sys.argv[1:]],
               "pid": os.getpid(), "source_sha256": sha(Path(__file__)), "passed": False}
    shutil.copy2(Path(__file__), args.output / "pilot-source.py")
    shutil.copy2(BASE / "native_etw.py", args.output / "native-etw-source.py")
    try:
        if args.download_receipt:
            upstream = json.loads(args.download_receipt.read_text(encoding="utf-8"))
            require(upstream["passed"] is True and upstream["release"] == "https://github.com/GameTechDev/PresentMon/releases/tag/v2.6.0"
                    and upstream["official_asset_digest"] == "sha256:" + upstream["sha256"], "Unverified upstream download receipt")
            BINARY = Path(upstream["executable"]).resolve(strict=True)
            EXPECTED_BINARY_SHA256 = upstream["sha256"]
            require((ROOT / ".cache/acceptance/presentmon-upstream-050").resolve() in BINARY.parents, "Upstream path escaped its owned cache")
            shutil.copy2(args.download_receipt, args.output / "download.execution.json")
        metadata(args.output)
        if args.action == "help":
            result = execute([str(BINARY), "--help"], args.output, "help", timeout=10)
            help_text = (args.output / "help.stdout.log").read_text(encoding="utf-8-sig") + (args.output / "help.stderr.log").read_text(encoding="utf-8-sig")
            require(result["exit_code"] in (0, 1) and not result.get("timeout")
                    and all(section in help_text for section in ("Capture Target Options:", "Output Options:", "Execution Options:")),
                    "Actual --help did not provide complete CLI schema")
        else:
            require(args.help_directory and args.instance and args.pid and args.created, "Capture requires explicit owner and reviewed help")
            capture(args, args.output)
        receipt["passed"] = True
    except BaseException as error:
        receipt["error"] = repr(error)
        raise
    finally:
        receipt["ended"] = now()
        write(args.output / "execution.json", receipt)
    print(json.dumps({"action": args.action, "passed": True, "output": str(args.output)}))
