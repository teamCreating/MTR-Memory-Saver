"""Owned-session raw ETL diagnostic and offline decoder replay; never runs on import."""
from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from .contract import decision, fingerprint, identity, inspect_csv, inspect_headers, integer, require


ROOT = Path(__file__).resolve().parents[2]
PROFILE = Path(__file__).with_name("providers-presentmon-2.6.0.json")


def now():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def load_profile(path=PROFILE):
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    require(profile["schema"] == 1 and profile["clock"] == "perf", "Unsupported provider/clock contract")
    require(profile["profile_qualified_for_measurement"] is False, "No qualified measurement profile is implemented here")
    require(type(profile["maximum_etl_megabytes"]) is int and 1 <= profile["maximum_etl_megabytes"] <= 128, "ETL size cap must be between 1 and 128 MiB")
    guids = set()
    for provider in profile["providers"]:
        guid = str(uuid.UUID(provider["guid"]))
        require(guid not in guids, "Duplicate provider GUID")
        guids.add(guid)
        keywords = int(provider["keywords"], 0)
        require(0 <= keywords < 2**64 and 0 <= provider["level"] <= 5, "Invalid ETW level/keyword mask")
        if provider["name"] == "Microsoft-Windows-DxgKrnl":
            require(keywords != 0 and not keywords & 0x4000000000000000, "DxgKrnl Performance/all-keyword filtering is prohibited by the pinned source")
    require(guids, "No providers configured")
    return profile


def commands(folder, binary, session, pid, duration, profile, system32):
    folder, binary, system32 = Path(folder), Path(binary), Path(system32)
    # Windows 10 rejects scheduled -rf with direct -ets. The owned wrapper
    # stops this unique session in finally; -max bounds its raw file size.
    # No append/overwrite, remote computer or restart-admin flags.
    return {
        "start": [str(system32 / "logman.exe"), "create", "trace", session, "-ets", "-pf", str(folder / "providers.txt"),
                  "-o", str(folder / "raw.etl"), "-f", "bin", "-ct", "perf", "-max", str(profile["maximum_etl_megabytes"])],
        "headers": [str(system32 / "tracerpt.exe"), str(folder / "raw.etl"), "-o", str(folder / "headers.xml"), "-of", "XML",
                    "-summary", str(folder / "tracerpt-summary.txt")],
        "replay": [str(binary), "--etl_file", str(folder / "raw.etl"), "--process_id", str(pid), "--output_file", str(folder / "presents.csv"),
                   "--v1_metrics", "--qpc_time", "--no_console_stats", "--no_track_input", "--no_track_gpu"],
    }


def run_command(argv, folder, label, timeout_seconds=45):
    """Persist the actual wait result before optional hashes/post-exit metadata."""
    folder = Path(folder)
    executable = Path(argv[0]).resolve(strict=True)
    receipt = {"argv": argv, "cwd": str(folder), "started": now(), "owner_pid": os.getpid(), "timeout_seconds": timeout_seconds,
               "executable": {"path": str(executable), **fingerprint(executable)}}
    stdout, stderr = folder / (label + ".stdout.log"), folder / (label + ".stderr.log")
    with stdout.open("xb") as out, stderr.open("xb") as err:
        child = subprocess.Popen(argv, cwd=folder, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        receipt["helper_pid"] = child.pid
        metadata_error = None
        try:
            write_new(folder / (label + ".start.json"), receipt)
        except Exception as error:
            metadata_error = error  # Still wait for/clean up the Popen-owned child.
        try:
            receipt["exit_code"] = child.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            receipt["timeout"] = True
            child.terminate()  # Only this Popen-owned helper, never a target JVM.
            receipt["exit_code"] = child.wait(timeout=10)
            receipt["cleanup"] = "terminated_only_owned_helper"
        receipt.update(ended=now(), helper_exited=child.poll() is not None)
        if metadata_error is not None:
            receipt["start_receipt_error"] = repr(metadata_error)
        write_new(folder / (label + ".exit.json"), receipt)
    receipt.update(stdout=fingerprint(stdout), stderr=fingerprint(stderr))
    receipt["executable_after"] = {"path": str(executable), **fingerprint(executable)}
    write_new(folder / (label + ".execution.json"), receipt)
    require(receipt["executable"] == receipt["executable_after"], "Helper executable changed during execution")
    if metadata_error is not None:
        raise metadata_error
    return receipt


class Wnode(ctypes.Structure):
    _fields_ = [("BufferSize", ctypes.c_uint32), ("ProviderId", ctypes.c_uint32),
                ("HistoricalContext", ctypes.c_uint64), ("TimeStamp", ctypes.c_int64),
                ("Guid", ctypes.c_ubyte * 16), ("ClientContext", ctypes.c_uint32), ("Flags", ctypes.c_uint32)]


class TraceProperties(ctypes.Structure):
    _fields_ = [("Wnode", Wnode)] + [(name, ctypes.c_uint32) for name in (
        "BufferSize", "MinimumBuffers", "MaximumBuffers", "MaximumFileSize", "LogFileMode", "FlushTimer", "EnableFlags", "AgeLimit",
        "NumberOfBuffers", "FreeBuffers", "EventsLost", "BuffersWritten", "LogBuffersLost", "RealTimeBuffersLost")]
    _fields_ += [("LoggerThreadId", ctypes.c_void_p), ("LogFileNameOffset", ctypes.c_uint32), ("LoggerNameOffset", ctypes.c_uint32)]


class WindowsBackend:
    """Explicit live backend. It changes only a newly started, identity-checked session."""
    def __init__(self):
        require(os.name == "nt" and ctypes.sizeof(ctypes.c_void_p) == 8, "Only audited Windows x64 is supported")
        self.system32 = Path(os.environ["SystemRoot"]) / "System32"
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.control = ctypes.WinDLL("advapi32", use_last_error=True).ControlTraceW
        self.control.argtypes = [ctypes.c_uint64, ctypes.c_wchar_p, ctypes.POINTER(TraceProperties), ctypes.c_uint32]
        self.control.restype = ctypes.c_uint32

    @contextmanager
    def target(self, expected):
        from tools.windows_process_identity import NativeApi, query_identity
        api = NativeApi()
        api.kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        api.kernel.OpenProcess.restype = ctypes.c_void_p
        api.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = api.kernel.OpenProcess(0x1000, False, expected["pid"])
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            def observe():
                actual = query_identity(handle, api)
                require(identity(actual) == identity(expected), "Target PID/creation/image/command changed")
                return actual
            observe()
            yield observe
        finally:
            api.kernel.CloseHandle(handle)

    def clock(self):
        counter, after, frequency = (ctypes.c_int64() for _ in range(3))
        self.kernel.QueryPerformanceCounter.argtypes = [ctypes.POINTER(ctypes.c_int64)]
        self.kernel.QueryPerformanceFrequency.argtypes = [ctypes.POINTER(ctypes.c_int64)]
        require(self.kernel.QueryPerformanceFrequency(ctypes.byref(frequency)), "QPC frequency failed")
        require(self.kernel.QueryPerformanceCounter(ctypes.byref(counter)), "QPC read failed")
        utc = now()
        require(self.kernel.QueryPerformanceCounter(ctypes.byref(after)), "QPC read failed")
        return {"qpc_before": counter.value, "qpc_after": after.value, "utc_between_qpc_reads": utc, "frequency_hz": frequency.value}

    def _control(self, session, handle=0, operation=0):
        require(session.startswith("mtr-frame-diagnostic-"), "Refusing an unrelated session name")
        uuid.UUID(session.removeprefix("mtr-frame-diagnostic-"))
        require(operation in (0, 1), "Only query or owned stop is supported")
        memory = ctypes.create_string_buffer(ctypes.sizeof(TraceProperties) + 8192)
        props = ctypes.cast(memory, ctypes.POINTER(TraceProperties)).contents
        props.Wnode.BufferSize = ctypes.sizeof(memory)
        props.LoggerNameOffset = ctypes.sizeof(TraceProperties)
        props.LogFileNameOffset = ctypes.sizeof(TraceProperties) + 4096
        status = self.control(handle, session, ctypes.byref(props), operation)
        result = {"observed_at": now(), "session_name": session, "status": int(status),
                  "operation": "owned_session_stop" if operation else "session_query", "counters": None}
        if status == 0:
            result.update(guid=str(uuid.UUID(bytes_le=bytes(props.Wnode.Guid))), trace_handle=int(props.Wnode.HistoricalContext),
                counters={name: int(getattr(props, name)) for name in ("EventsLost", "LogBuffersLost", "RealTimeBuffersLost", "BuffersWritten")})
        return result

    def query(self, session):
        return self._control(session)

    def stop_owned(self, token):
        actual = self.query(token["session_name"])
        require(actual["status"] == 0 and actual["guid"] == token["guid"] and actual["trace_handle"] == token["trace_handle"], "Owned session identity changed; no stop issued")
        result = self._control(token["session_name"], token["trace_handle"], 1)
        require(result["status"] == 0 and result["guid"] == token["guid"], "Owned-session stop did not confirm identity")
        return result

    run = staticmethod(run_command)
    sleep = staticmethod(time.sleep)


def private_output(path, repo=ROOT):
    """Raw ETL/machine telemetry may only be created beneath this repo's ignored cache."""
    root = Path(repo).resolve()
    output = Path(path).absolute()
    require(not output.exists(), "Output already exists; no overwrite/retry substitution")
    require(output.is_relative_to(root / ".cache"), "Raw diagnostic output must stay in the repository .cache")
    for parent in [output.parent, *output.parents]:
        if parent.exists():
            require(not parent.is_symlink() and not (getattr(parent.lstat(), "st_file_attributes", 0) & 0x400), "Reparse-point output ancestry is unsupported")
    require(output.resolve().is_relative_to(root / ".cache"), "Output resolves outside the ignored cache")
    return output


def capture_diagnostic(output, expected, binary, duration=25, backend=None, repo=ROOT, profile_path=PROFILE):
    """One future authorized diagnostic, with no automatic retry or permission changes."""
    identity(expected)
    integer(duration, "Duration", 20)
    require(duration <= 30, "Diagnostic duration must not exceed 30 seconds")
    profile = load_profile(profile_path)
    binary = Path(binary).resolve(strict=True)
    require(fingerprint(binary)["sha256"] == profile["presentmon_sha256"], "PresentMon binary differs from the reviewed profile")
    output = private_output(output, repo)
    output.mkdir(parents=True, exist_ok=False)
    execution = {"started": now(), "owner_pid": os.getpid(), "passed": False,
                 "scope": "diagnostic capture/decoding only, not calibration or performance"}
    try:
        backend = WindowsBackend() if backend is None else backend
        report = _capture(output, expected, binary, duration, backend, profile, profile_path)
        execution["passed"] = True
        return report
    except BaseException as error:
        execution["error"] = repr(error)
        if not (output / "assessment.json").exists():
            write_new(output / "assessment.json", {"schema": 1, "data_source_available": False, "sampling_window_ready": False,
                "calibration_accepted": False, "performance_accepted": False, "failure": repr(error), "root_cause": None})
        raise
    finally:
        execution["ended"] = now()
        write_new(output / "execution.json", execution)
        files = {p.relative_to(output).as_posix(): fingerprint(p) for p in sorted(output.rglob("*")) if p.is_file()}
        write_new(output / "inventory.json", {"schema": 1, "files": files})


def _capture(output, expected, binary, duration, backend, profile, profile_path):
    session = "mtr-frame-diagnostic-" + str(uuid.uuid4())
    argv = commands(output, binary, session, expected["pid"], duration, profile, backend.system32)
    write_new(output / "intent.json", {"scope": "owned raw ETW/header/decoder availability diagnostic only", "session_name": session,
        "target": expected, "duration_seconds": duration, "commands": argv, "profile": profile,
        "profile_sha256": fingerprint(profile_path)["sha256"], "binary": fingerprint(binary),
        "sources": {name: fingerprint(Path(__file__).with_name(name))["sha256"] for name in ("contract.py", "etw_diagnostic.py")}})
    (output / "providers.txt").write_text("".join(f'{{{p["guid"]}}} {p["keywords"]} {p["level"]}\n' for p in profile["providers"]), encoding="ascii")
    token, stop, errors = None, None, []
    with backend.target(expected) as observe:
        before = observe()
        write_new(output / "target-before.json", {"observed_at": now(), "identity": before})
        absent = backend.query(session)
        write_new(output / "session-before.json", absent)
        require(absent["status"] == 4201, "Unique session was not definitively absent; no start issued")
        start_clock = backend.clock()
        try:
            start = backend.run(argv["start"], output, "start")
            token = backend.query(session)
            write_new(output / "session-started.json", token)
            require(start["exit_code"] == 0 and not start.get("timeout"), "Session start failed; no retry")
            require(token["status"] == 0 and token.get("guid") and token.get("trace_handle"), "Owned session identity unavailable")
            backend.sleep(duration)
        except Exception as error:
            errors.append(repr(error))
        finally:
            # logman can create the session before a provider enable fails.
            # Recover only the unique name proven absent before our own start.
            if token is None:
                try:
                    token = backend.query(session)
                    write_new(output / "session-start-recovery.json", token)
                except Exception as error:
                    errors.append("Partial-start identity unavailable: " + repr(error))
            if token is not None and token.get("status") == 0:
                try:
                    stop = backend.stop_owned(token)
                    write_new(output / "session-stop.json", stop)
                except Exception as error:
                    errors.append("Owned-session cleanup not confirmed: " + repr(error))
            end_clock = backend.clock()
            gone = backend.query(session)
            write_new(output / "session-after.json", gone)
            if gone["status"] != 4201:
                errors.append("Own session is not confirmed gone; do not start another diagnostic")
            after = observe()
            write_new(output / "target-after.json", {"observed_at": now(), "identity": after})
        require(start_clock["frequency_hz"] == end_clock["frequency_hz"], "QPC frequency changed")
        window = {"frequency_hz": start_clock["frequency_hz"], "start": start_clock, "end": end_clock,
                  "session_name": session, "session_guid": token.get("guid") if token else None}
        write_new(output / "window.json", window)
        require(not errors and stop is not None, "; ".join(errors) or "No confirmed owned-session stop")
    etl = output / "raw.etl"
    require(etl.is_file() and etl.stat().st_size > 0, "No nonempty raw ETL; no replay attempted")
    original_etl = fingerprint(etl)
    for label in ("headers", "replay"):
        receipt = backend.run(argv[label], output, label)
        require(receipt["exit_code"] == 0 and not receipt.get("timeout"), label + " decoder failed; preserve raw streams")
    require(fingerprint(etl) == original_etl, "ETL changed during offline decoding")
    headers = inspect_headers(output / "headers.xml", before)
    presents = inspect_csv(output / "presents.csv", before, window)
    report = decision(before, after, window, presents, headers, stop)
    report.update(csv=presents, headers=headers, etl=original_etl,
        provider_profile_qualified=profile["profile_qualified_for_measurement"],
        csv_failure_attribution="Absent CSV is unclassified; inspect retained decoder stderr. No CSV-open, driver or API cause is inferred.")
    report["sampling_window_ready"] = report["sampling_window_ready"] and profile["profile_qualified_for_measurement"]
    write_new(output / "assessment.json", report)
    return report


def inspect_bundle(folder, replay_output=None, runner=run_command, repo=ROOT):
    """Recompute from bound raw CSV/XML, not saved metric summaries."""
    folder = Path(folder).resolve()
    read = lambda name: json.loads((folder / name).read_text(encoding="utf-8"))
    inventory = read("inventory.json")
    require(inventory["schema"] == 1, "Unsupported inventory schema")
    actual = {p.relative_to(folder).as_posix(): p for p in folder.rglob("*") if p.is_file()}
    require(set(actual) == set(inventory["files"]) | {"inventory.json"}, "Bundle namespace differs from inventory")
    for name, expected in inventory["files"].items():
        require((folder / name).resolve().is_relative_to(folder), "Bundle path escapes its root")
        require(fingerprint(actual[name]) == expected, "Bundle bytes changed: " + name)
    intent, execution, window = read("intent.json"), read("execution.json"), read("window.json")
    require(execution["passed"] is True, "Capture/decoding did not complete; inspect retained failure evidence")
    for name, digest in intent["sources"].items():
        require(Path(name).name == name and fingerprint(Path(__file__).with_name(name))["sha256"] == digest, "Collector/analyzer source differs")
    require(intent["binary"]["sha256"] == intent["profile"]["presentmon_sha256"], "Unreviewed decoder identity")
    require(window["session_name"] == intent["session_name"], "Sampling window belongs to another session")
    before, after = read("target-before.json")["identity"], read("target-after.json")["identity"]
    require(identity(before) == identity(intent["target"]), "Capture target differs from its declared owner")
    for label in ("start", "headers", "replay"):
        receipt, exited = read(label + ".execution.json"), read(label + ".exit.json")
        require(receipt["argv"] == intent["commands"][label] and exited["argv"] == receipt["argv"], "Decoder/trace argv differs")
        require(receipt["exit_code"] == exited["exit_code"] == 0 and not receipt.get("timeout"), "Failed helper is not execution proof")
        require(receipt["owner_pid"] == execution["owner_pid"], "Helper belongs to another runner")
        require(receipt["executable"] == receipt["executable_after"], "Original helper identity changed")
        for stream in ("stdout", "stderr"):
            require(fingerprint(folder / f"{label}.{stream}.log") == receipt[stream], "Raw helper stream differs")
    require(read("session-after.json")["status"] == 4201, "Own session cleanup not confirmed")
    headers = inspect_headers(folder / "headers.xml", before)
    presents = inspect_csv(folder / "presents.csv", before, window)
    result = decision(before, after, window, presents, headers, read("session-stop.json"))
    result.update(csv=presents, headers=headers, etl=fingerprint(folder / "raw.etl"),
                  provider_profile_qualified=intent["profile"]["profile_qualified_for_measurement"])
    result["sampling_window_ready"] = result["sampling_window_ready"] and result["provider_profile_qualified"]
    result["serialized_present_records_available"] = result["data_source_available"]
    result["independent_raw_etl_replay_verified"] = False
    if replay_output is None:
        result["data_source_available"] = result["sampling_window_ready"] = False
        result["remaining_gate"] = "Saved CSV derivation has not been independently redecoded from raw ETL"
        return result
    replay_output = private_output(replay_output, repo)
    replay_output.mkdir(parents=True, exist_ok=False)
    raw_before = fingerprint(folder / "raw.etl")
    for label in ("headers", "replay"):
        old = read(label + ".execution.json")
        executable = Path(old["executable"]["path"])
        require({"path": str(executable), **fingerprint(executable)} == old["executable"], "Frozen decoder executable changed")
        argv = list(old["argv"])
        if label == "headers":
            argv[1] = str(folder / "raw.etl")
            for flag, name in (("-o", "headers.xml"), ("-summary", "tracerpt-summary.txt")):
                argv[argv.index(flag) + 1] = str(replay_output / name)
        else:
            require(old["executable"]["sha256"] == intent["binary"]["sha256"], "Replay binary differs from the capture's pinned PresentMon")
            argv[argv.index("--etl_file") + 1] = str(folder / "raw.etl")
            argv[argv.index("--output_file") + 1] = str(replay_output / "presents.csv")
        receipt = runner(argv, replay_output, "redecode-" + label)
        require(receipt["exit_code"] == 0 and not receipt.get("timeout"), "Independent offline decoder failed")
    require(fingerprint(folder / "raw.etl") == raw_before, "Raw ETL changed during independent replay")
    original_csv, repeated_csv = folder / "presents.csv", replay_output / "presents.csv"
    require(original_csv.is_file() == repeated_csv.is_file(), "Independent replay disagrees on CSV existence")
    if original_csv.is_file():
        require(fingerprint(original_csv) == fingerprint(repeated_csv), "Independent replay CSV bytes differ; edited/unstable derivation rejected")
    repeated_headers = inspect_headers(replay_output / "headers.xml", before)
    require({k: v for k, v in headers.items() if k != "source"} == {k: v for k, v in repeated_headers.items() if k != "source"}, "Independent header decoding differs")
    result["independent_raw_etl_replay_verified"] = True
    result["data_source_available"] = result["serialized_present_records_available"]
    write_new(replay_output / "assessment.json", result)
    return result
