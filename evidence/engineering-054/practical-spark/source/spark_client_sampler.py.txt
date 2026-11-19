"""Explicit CUA/operator coordination and independent local Spark-file auditing.

This module never sends game input or uploads data. A continuation file only
coordinates the warmup clock; the actual Spark binary is independently decoded
and checked afterwards. All comparison metrics still use native/OS/JFR sources.
"""
import copy
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from frame_diagnostics.contract import fingerprint, require
from frame_diagnostics.etw_diagnostic import run_command, write_new
from spark_profile_analysis import analyze

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config/client-samplers.json"
EXPORTER = ROOT / "tools/SparkProfileExport.java"


def read(path):
    return json.loads(Path(path).read_bytes())


def instant(text):
    result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "Sampler timestamp needs an explicit offset")
    return result


def spec_for_plan(plan, catalog_path=CATALOG):
    mods = [mod for mod in plan["mods"] if mod["role"] == "measurement"]
    if not mods:
        return None
    catalog = read(catalog_path)
    require(catalog["schema"] == 1 and len(mods) == 1, "Unsupported measurement sampler set")
    matches = [item for item in catalog["samplers"] if item["jar_sha256"] == mods[0]["sha256"]]
    require(len(matches) == 1, "Measurement JAR has no exact declared sampler protocol")
    spec = copy.deepcopy(matches[0])
    spec["filename"] = mods[0]["filename"]
    spec["catalog_sha256"] = fingerprint(catalog_path)["sha256"]
    require(all(arg in plan["extra_jvm_arguments"] for arg in spec["required_jvm_arguments"]),
            "Sampler idle/background controls were not frozen before launch")
    require(type(spec["interval_microseconds"]) is int and spec["interval_microseconds"] > 0
            and spec["interval_microseconds"] % 1000 == 0, "Unsupported execution sampling interval")
    directory = Path(spec["directory"])
    require(not directory.is_absolute() and ".." not in directory.parts, "Sampler directory must stay in the instance")
    return spec


def command(spec):
    return (f"{spec['command_prefix']} profiler start --thread * --interval {spec['interval_microseconds'] // 1000} "
            f"--force-java-sampler --timeout {spec['duration_seconds']} --save-to-file")


def request(root, spec, process, instance, stamp):
    root = Path(root)
    value = {"schema": 1, "kind": "local_spark_start_coordination", "created_at": stamp,
             "process": process, "instance": str(instance), "sampler": spec,
             "command": command(spec), "scope": "Operator coordination only; not sampling or performance evidence"}
    write_new(root / "sampler-request.json", value)
    return value


def continued(root):
    root = Path(root)
    path = root / "sampler-continue.json"
    if not path.exists():
        return False
    value = read(path)
    require(value.get("schema") == 1 and value.get("request_sha256") == fingerprint(root / "sampler-request.json")["sha256"],
            "Sampler continuation belongs to another request")
    require(instant(value["observed_at"]) >= instant(read(root / "sampler-request.json")["created_at"]),
            "Sampler continuation predates its request")
    return True


def completed_bytes(path):
    """Read a producer-closed Windows file, holding a deny-write/delete handle.

    Sharing violation means the producer still owns a writer, not corrupt data.
    This does not guess completion from file size stability.
    """
    require(os.name == "nt", "Live Spark-file publication is qualified only on Windows")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                               ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    api.CreateFileW.restype = ctypes.c_void_p
    api.GetFileSizeEx.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64)]
    api.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = api.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.get_last_error()
        if error in (2, 3, 32):
            return None
        raise ctypes.WinError(error)
    try:
        size = ctypes.c_int64()
        if not api.GetFileSizeEx(handle, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        if size.value == 0:
            return None
        require(0 < size.value <= 32 * 1024 * 1024, "Spark binary exceeds input bound")
        output = bytearray()
        while len(output) < size.value:
            amount = min(65536, size.value - len(output))
            buffer, count = ctypes.create_string_buffer(amount), ctypes.c_uint32()
            if not api.ReadFile(handle, buffer, amount, ctypes.byref(count), None):
                raise ctypes.WinError(ctypes.get_last_error())
            require(count.value > 0, "Unexpected EOF in producer-closed Spark profile")
            output.extend(buffer.raw[:count.value])
        return bytes(output)
    finally:
        api.CloseHandle(handle)


def wait_for_file(root, instance, spec, process):
    directory = Path(instance) / spec["directory"]
    deadline = time.monotonic() + spec["duration_seconds"] + spec["completion_grace_seconds"]
    while True:
        require(process.poll() is None, "Actual JVM exited before Spark publication")
        files = list(directory.glob(spec["file_glob"]))
        require(len(files) <= 1, "Multiple Spark profiles cannot substitute for the requested capture")
        if files:
            raw = completed_bytes(files[0])
            if raw is not None:
                folder = Path(root) / "spark"
                folder.mkdir(exist_ok=False)
                with (folder / "recording.sparkprofile").open("xb") as stream:
                    stream.write(raw)
                write_new(folder / "publication.json", {"source": str(files[0]), "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(), "publication": "producer-closed deny-write/delete handle",
                    "copied_at": datetime.now(timezone.utc).isoformat()})
                return folder
        require(time.monotonic() < deadline, "Timed local Spark profile did not publish within its declared bound")
        time.sleep(2)


def decode(raw, jar, java, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    require(fingerprint(raw)["bytes"] <= 32 * 1024 * 1024, "Spark input exceeds bound")
    before = fingerprint(raw)
    tool_before, jar_before = fingerprint(EXPORTER), fingerprint(jar)
    suffix = ".exe" if os.name == "nt" else ""
    receipts = {}
    for label, args in (("compile", [str(Path(java).with_name("javac" + suffix)), "--release", "17", "-encoding", "UTF-8", "-d", str(folder), str(EXPORTER)]),
                        ("export", [str(java), "-cp", str(folder) + os.pathsep + str(jar), "SparkProfileExport", str(raw)])):
        receipts[label] = run_command(args, folder, label, timeout_seconds=60)
        require(receipts[label]["exit_code"] == 0, "Actual Spark decoder helper failed: " + label)
    require(fingerprint(raw) == before and fingerprint(EXPORTER) == tool_before and fingerprint(jar) == jar_before,
            "Spark binary/JAR/decoder changed during export")
    write_new(folder / "inputs.json", {"profile": before, "spark_jar": jar_before, "decoder_source": tool_before})
    return read(folder / "export.stdout.log")


def validate(data, spec, prepared, evidence):
    metadata = data["metadata"]
    require(metadata["samplerEngine"] == spec["engine"] and metadata["samplerMode"] == spec["mode"], "Unexpected Spark engine/mode")
    require(metadata["interval"] == spec["interval_microseconds"], "Spark sampling interval differs from the frozen protocol")
    require(metadata["sources"]["spark"]["version"] == spec["spark_version"], "Spark source version differs")
    target = read(ROOT / "config/targets.json")
    require(metadata["sources"][target["modId"]]["version"] == prepared["artifact"]["version"], "Spark companion treatment differs")
    platform = metadata["platformMetadata"]
    require(platform["type"]["name"] == "CLIENT" and platform["minecraftVersion"] == target["minecraft"]
            and platform["version"] == prepared["artifact"]["neoForge"], "Spark client/loader/platform differs")
    require(metadata["threadDumper"]["type"]["name"] == "ALL", "Spark thread selection differs")
    start, end = metadata["startTime"] / 1000, metadata["endTime"] / 1000
    duration = end - start
    require(spec["duration_seconds"] <= duration <= spec["duration_seconds"] + spec["completion_grace_seconds"],
            "Spark timeout/export duration differs from the declared window")
    windows = evidence["windows"]
    require(instant(evidence["process"]["created"]).timestamp() <= start <= instant(windows["warmup"]["start"]).timestamp()
            and end >= instant(windows["steady"]["end"]).timestamp(), "Spark metadata does not enclose the actual warmup/steady window")
    derived_birth = end - metadata["systemStatistics"]["uptime"] / 1000
    require(abs(derived_birth - instant(evidence["process"]["created"]).timestamp()) <= spec["jvm_start_tolerance_seconds"],
            "Spark JVM uptime does not bind the actual process creation")
    resolved = Path(prepared["instance"]).resolve()
    instance_suffix = (resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else Path(resolved.name)).as_posix().casefold()
    vm_args = re.sub(r"/+", "/", metadata["systemStatistics"]["java"]["vmArgs"].replace("\\", "/")).casefold()
    require(instance_suffix in vm_args, "Spark JVM arguments belong to another isolated instance")
    reports = {name: analyze(data, name) for name in spec["required_threads"]}
    actual_threads = [item["name"] for item in data["threads"]]
    optional = {"MTR-memory-parse": analyze(data, "MTR-memory-parse")} if "MTR-memory-parse" in actual_threads else {}
    return {"verified": True, "sampler_id": spec["id"], "interval_microseconds": metadata["interval"],
            "start_utc": datetime.fromtimestamp(start, timezone.utc).isoformat(),
            "export_end_utc": datetime.fromtimestamp(end, timezone.utc).isoformat(),
            "actual_threads": actual_threads,
            "thread_reports": reports, "optional_thread_reports": optional,
            "metric_scope": "Execution sample diagnostics, not CPU elapsed or frame time",
            "performance_accepted": False}


def verify_idle(instance, spec):
    instance = Path(instance)
    files = list((instance / spec["directory"]).glob(spec["file_glob"]))
    require(not files, "Unexpected Spark profile captured during idle control")
    log_path = instance / "logs/latest.log"
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8-sig", errors="replace")
        require("Starting a new profiler" not in text and "Profiler is now running!" not in text,
                "Unexpected Spark profiler session started during idle control")
    return {"verified_idle": True, "sampler_id": spec["id"]}


def finish(root, prepared, evidence, spec):
    folder = Path(root) / "spark"
    jar = Path(prepared["instance"]) / "mods" / spec["filename"]
    require(fingerprint(jar)["sha256"] == spec["jar_sha256"], "Installed Spark JAR changed")
    data = decode(folder / "recording.sparkprofile", jar, prepared["java"], folder / "decode")
    result = validate(data, spec, prepared, evidence)
    result["profile"] = fingerprint(folder / "recording.sparkprofile")
    write_new(folder / "assessment.json", result)
    return result


def audit(root, prepared, evidence, spec):
    root = Path(root)
    folder = root / "spark"
    saved = read(folder / "assessment.json")
    profile = folder / "recording.sparkprofile"
    require(fingerprint(profile) == saved["profile"], "Spark raw binary changed")
    jar = Path(prepared["instance"]) / "mods" / spec["filename"]
    require(fingerprint(jar)["sha256"] == spec["jar_sha256"], "Spark decoder JAR no longer matches the frozen source")
    private = ROOT / ".cache/acceptance/spark-independent-audit" / str(uuid.uuid4())
    data = decode(profile, jar, prepared["java"], private)
    require(data == read(folder / "decode/export.stdout.log"), "Independent Spark decode differs from captured raw derivation")
    result = validate(data, spec, prepared, evidence)
    result["profile"] = fingerprint(profile)
    require(result == saved, "Spark assessment differs from raw independent reparse")
    return result
