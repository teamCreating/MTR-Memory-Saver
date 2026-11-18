"""Strict, offline evidence checks. Presents are not native render-loop or CPU metrics."""
import codecs
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import io
import math
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET


SCHEMA = 1
EVENT_NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"
REQUIRED_COLUMNS = ("Application", "ProcessID", "SwapChainAddress", "PresentRuntime", "TimeInQPC", "MsBetweenPresents")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(path):
    digest, count = hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            count += len(block)
    return {"bytes": count, "sha256": digest.hexdigest()}


def timestamp(value):
    require(isinstance(value, str), "Timestamp must retain its original ISO text")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "Timestamp needs an explicit UTC offset")
    return result


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, label + " must be an integer")
    return value


def identity(value):
    integer(value["pid"], "PID", 1)
    timestamp(value["created"])
    require(isinstance(value["executable"], str) and value["executable"], "Executable is missing")
    require(isinstance(value["command"], str) and value["command"], "Actual command is missing")
    return {"pid": value["pid"], "created": timestamp(value["created"]).astimezone(timezone.utc).isoformat(),
            "executable": value["executable"], "command": value["command"]}


def validate_window(window):
    frequency = integer(window["frequency_hz"], "QPC frequency", 1)
    for label in ("start", "end"):
        pair = window[label]
        integer(pair["qpc_before"], label + " QPC")
        integer(pair["qpc_after"], label + " QPC")
        require(pair["qpc_before"] <= pair["qpc_after"], "QPC bracket is reversed")
        timestamp(pair["utc_between_qpc_reads"])
    require(window["start"]["qpc_after"] < window["end"]["qpc_before"], "Capture QPC window is empty/reversed")
    require(timestamp(window["start"]["utc_between_qpc_reads"]) < timestamp(window["end"]["utc_between_qpc_reads"]), "UTC window is reversed")
    utc_elapsed = (timestamp(window["end"]["utc_between_qpc_reads"]) - timestamp(window["start"]["utc_between_qpc_reads"])).total_seconds()
    qpc_elapsed = (window["end"]["qpc_before"] - window["start"]["qpc_after"]) / frequency
    bracket_width = sum((window[key]["qpc_after"] - window[key]["qpc_before"]) / frequency for key in ("start", "end"))
    require(abs(utc_elapsed - qpc_elapsed) <= 1 + bracket_width, "UTC/QPC relation drift exceeds one second plus recorded brackets")
    return frequency


def text_bytes(raw):
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def inspect_csv(path, target, window, maximum_gap_seconds=5, maximum_bytes=32 * 1024 * 1024):
    """Validate the pinned 2.6 explicit v1/QPC schema without metric aliases."""
    frequency = validate_window(window)
    identity(target)
    require(type(maximum_gap_seconds) in (int, float) and math.isfinite(maximum_gap_seconds) and maximum_gap_seconds > 0, "Invalid coverage-gap budget")
    result = {"exists": path is not None and Path(path).is_file(), "columns": None, "rows": 0,
              "chains": {}, "errors": [], "present_records_available": False, "window_covered": False}
    if not result["exists"]:
        result["errors"].append("No CSV file; helper exit0 is not data availability")
        return result
    source = fingerprint(path)
    result["source"] = {"path": str(Path(path).resolve()), **source}
    if source["bytes"] > maximum_bytes:
        result["errors"].append("CSV exceeds the bounded offline parser input")
        return result
    chains = defaultdict(list)
    try:
        with Path(path).open("rb") as stream:
            reader = csv.DictReader(io.StringIO(text_bytes(stream.read(maximum_bytes + 1))))
        columns = reader.fieldnames
        require(columns and len(columns) == len(set(columns)), "Missing/duplicate CSV header")
        result["columns"] = columns
        require(all(name in columns for name in REQUIRED_COLUMNS), "Unsupported CSV schema; no legacy/v2 aliases are inferred")
        for row in reader:
            result["rows"] += 1
            require(None not in row and all(value is not None for value in row.values()), "Malformed CSV row width")
            require(re.fullmatch(r"[0-9]+", row["ProcessID"]) and int(row["ProcessID"]) == target["pid"], "CSV contains another or invalid process PID")
            require(re.fullmatch(r"[0-9]+", row["TimeInQPC"]), "Missing/invalid raw present QPC")
            qpc = int(row["TimeInQPC"])
            require(window["start"]["qpc_before"] <= qpc <= window["end"]["qpc_after"], "Present QPC is outside the recorded capture bracket")
            chain = row["SwapChainAddress"]
            require(re.fullmatch(r"0x[0-9a-fA-F]+", chain), "Invalid swap-chain address")
            require(row["Application"] and row["PresentRuntime"], "Missing application/runtime identity")
            interval = float(row["MsBetweenPresents"])
            require(math.isfinite(interval) and interval > 0, "Missing/nonpositive present interval")
            previous = chains[chain]
            require(not previous or qpc > previous[-1][0], "Present QPC must advance within each swap chain")
            previous.append((qpc, row["PresentRuntime"], interval))
        require(result["rows"] >= 2, "Fewer than two target present records")
        for chain, values in chains.items():
            stamps = [window["start"]["qpc_before"], *[x[0] for x in values], window["end"]["qpc_after"]]
            max_gap = max((b - a) / frequency for a, b in zip(stamps, stamps[1:]))
            result["chains"][chain] = {"rows": len(values), "first_qpc": values[0][0], "last_qpc": values[-1][0],
                "present_runtime_values": sorted({x[1] for x in values}), "maximum_observed_gap_seconds": max_gap,
                "window_covered": len(values) >= 2 and max_gap <= maximum_gap_seconds}
        result["present_records_available"] = any(x["rows"] >= 2 for x in result["chains"].values())
        result["window_covered"] = bool(result["chains"]) and all(x["window_covered"] for x in result["chains"].values())
    except (ValueError, UnicodeError, csv.Error) as error:
        result["errors"].append(str(error))
        result["present_records_available"] = result["window_covered"] = False
    require(fingerprint(path) == source, "CSV changed during inspection")
    return result


def inspect_headers(path, target, maximum_bytes=256 * 1024 * 1024, maximum_events=2_000_000):
    """Count event HEADER writer PIDs, not payload process IDs or presents."""
    identity(target)
    result = {"events": 0, "header_writer_pid_counts": {}, "providers": {}, "errors": [],
              "timestamp_semantics": "System/TimeCreated UTC, not inferred raw QPC", "target_presents_claim": False}
    source = fingerprint(path)
    require(source["bytes"] <= maximum_bytes, "XML exceeds the bounded offline parser input")
    result["source"] = {"path": str(Path(path).resolve()), **source}
    with Path(path).open("rb") as stream:
        raw = stream.read(maximum_bytes + 1)
    declarations = text_bytes(raw).upper()
    require("<!DOCTYPE" not in declarations and "<!ENTITY" not in declarations, "XML entity/DTD declarations are unsupported")
    providers, writers = {}, Counter()
    try:
        for _, element in ET.iterparse(io.BytesIO(raw), events=("end",)):
            if element.tag != EVENT_NS + "Event":
                continue
            result["events"] += 1
            require(result["events"] <= maximum_events, "Event count exceeds the parser budget")
            system = element.find(EVENT_NS + "System")
            require(system is not None, "Event System header is missing")
            provider = system.find(EVENT_NS + "Provider")
            execution = system.find(EVENT_NS + "Execution")
            event_id = system.findtext(EVENT_NS + "EventID")
            when = system.find(EVENT_NS + "TimeCreated")
            require(provider is not None and provider.get("Guid"), "Provider GUID missing; names are not substituted")
            guid = str(uuid.UUID(provider.get("Guid").strip("{}")))
            require(execution is not None and re.fullmatch(r"[0-9]+", execution.get("ProcessID", "")), "Header writer ProcessID missing")
            require(event_id is not None and re.fullmatch(r"[0-9]+", event_id), "EventID missing")
            require(when is not None, "Event timestamp is missing")
            stamp = when.get("SystemTime")
            timestamp(stamp)
            writer = execution.get("ProcessID")
            writers[writer] += 1
            bucket = providers.setdefault(guid, {"events": 0, "header_writer_pid_counts": {}, "event_id_counts": {}, "first_utc": stamp, "last_utc": stamp})
            bucket["events"] += 1
            bucket["header_writer_pid_counts"][writer] = bucket["header_writer_pid_counts"].get(writer, 0) + 1
            bucket["event_id_counts"][event_id] = bucket["event_id_counts"].get(event_id, 0) + 1
            if timestamp(stamp) < timestamp(bucket["first_utc"]): bucket["first_utc"] = stamp
            if timestamp(stamp) > timestamp(bucket["last_utc"]): bucket["last_utc"] = stamp
            element.clear()
        require(result["events"] > 0, "No recognized Event/System headers")
    except (ValueError, ET.ParseError) as error:
        result["errors"].append(str(error))
    result["providers"], result["header_writer_pid_counts"] = providers, dict(writers)
    result["target_header_writer_events"] = writers[str(target["pid"])]
    result["all_headers_decoded"] = not result["errors"]
    require(fingerprint(path) == source, "XML changed during inspection")
    return result


def decision(target_before, target_after, window, csv_report, header_report, stop_receipt):
    """Availability is a narrower outcome than a qualified sampling/calibration window."""
    validate_window(window)
    same = identity(target_before) == identity(target_after)
    counters = stop_receipt.get("counters")
    loss_known = (stop_receipt.get("status") == 0 and stop_receipt.get("operation") == "owned_session_stop" and counters is not None
                  and bool(window.get("session_guid")) and stop_receipt.get("guid") == window["session_guid"]
                  and bool(window.get("session_name")) and stop_receipt.get("session_name") == window["session_name"])
    lost = any(integer(counters[key], key) != 0 for key in ("EventsLost", "LogBuffersLost", "RealTimeBuffersLost")) if loss_known else None
    available = same and not csv_report["errors"] and csv_report["present_records_available"]
    return {"schema": SCHEMA, "target_identity_equal": same, "data_source_available": available,
        "sampling_window_ready": available and csv_report["window_covered"] and header_report["all_headers_decoded"] and loss_known and not lost,
        "whole_owned_session_loss_known": loss_known, "whole_owned_session_loss_observed": lost,
        "native_frame_p99_ms": None, "process_cpu_seconds": None, "gc_pause_total_ms": None,
        "metric_semantics": "External present records only; neither native render-loop frames nor process CPU/GC",
        "opengl_identification": "Not inferred from PresentRuntime=Other or header writer PIDs",
        "calibration_accepted": False, "performance_accepted": False}
