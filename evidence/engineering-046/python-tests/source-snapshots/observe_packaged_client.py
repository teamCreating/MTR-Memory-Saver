"""Observe a frozen packaged client without controlling game input.

The default observer reads packaged-observer.json plus separately fresh live.json
vehicle state. Reload counting pairs actual resource-epochs.jsonl starts/returns
with each epoch's settled state and excludes the initial startup. Optional external
input JSONL records contain timestamp, pid, process_created, log_offset,
method="native_f3_t", and a fresh before snapshot; real resource/registration/work
log completions must follow. This observer never performs game input.
"""
import argparse
import ctypes
from ctypes import wintypes
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import re
import subprocess
import time
import uuid

UTC = dt.timezone.utc
ZERO_COUNTERS = ("native_pending", "module_pending", "module_outstanding", "module_queued", "active_reads", "resource_in_flight", "module_failures")


def timestamp():
    return dt.datetime.now(UTC).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_snapshot(path):
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8-sig")), hashlib.sha256(raw).hexdigest()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def instant(value):
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("An observation timestamp must include a UTC offset.")
    return parsed.astimezone(UTC)


def finite_positive(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("Use a finite positive number.")
    return result


def frozen_context(instance, verify_inputs=True):
    plan_path, launch_path = instance / "packaged-client-plan.json", instance / "packaged-client-launch.json"
    plan, launch = read(plan_path), read(launch_path)
    if pathlib.Path(plan["instance"]).resolve() != instance.resolve():
        raise ValueError("Prepared instance identity differs from this directory.")
    if launch["plan_sha256"] != digest(plan_path):
        raise ValueError("The frozen plan changed after launch.")
    if not isinstance(launch["pid"], int) or launch["pid"] <= 0:
        raise ValueError("Require a valid launched process identifier.")
    if not launch["command"] or pathlib.Path(launch["command"][0]).resolve() != pathlib.Path(plan["java"]).resolve():
        raise ValueError("Launch executable differs from the prepared Java runtime.")
    if verify_inputs:
        for item in plan["mods"]:
            if digest(instance / "mods" / item["filename"]) != item["sha256"]:
                raise ValueError("A launched mod differs from the frozen input.")
        for item in plan["packs"]:
            if digest(instance / "resourcepacks" / item["filename"]) != item["sha256"]:
                raise ValueError("A launched pack differs from the frozen input.")
    # Options/world naturally advance after launch; their launch-time hashes are
    # preserved in the verified plan instead of treating later saves as tampering.
    instant(launch["timestamp"])
    return plan, launch


def windows_arguments(command):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = (wintypes.HLOCAL,)
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not pointer:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [pointer[index] for index in range(count.value)]
    finally:
        kernel.LocalFree(ctypes.cast(pointer, wintypes.HLOCAL))


def verify_process_identity(plan, launch, process, arguments):
    if process["pid"] != launch["pid"] or pathlib.Path(process["executable"]).resolve() != pathlib.Path(plan["java"]).resolve():
        raise ValueError("The actual process executable/identifier differs from the launch.")
    if arguments != launch["command"]:
        raise ValueError("The actual process arguments differ from the recorded launch.")
    age = (instant(launch["timestamp"]) - instant(process["created"])).total_seconds()
    if not -5 <= age <= 30:
        raise ValueError("The process start time does not match this launch; possible reused PID.")


class ProcessMemory(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("page_fault_count", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ("peak_working_set", "working_set", "quota_peak_paged_pool", "quota_paged_pool",
        "quota_peak_nonpaged_pool", "quota_nonpaged_pool", "pagefile_usage", "peak_pagefile_usage", "private_usage")]


class WindowsProcess:
    def __init__(self, plan, launch):
        if os.name != "nt":
            raise ValueError("This process observer requires Windows.")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        self.kernel.GetExitCodeProcess.restype = wintypes.BOOL
        self.kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self.psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD)
        self.psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        self.handle = self.kernel.OpenProcess(0x0410, False, launch["pid"])
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            result = subprocess.run(["pwsh", "-NoProfile", "-Command",
                f"$observedProcess = Get-CimInstance Win32_Process -Filter 'ProcessId = {launch['pid']}'; "
                "if ($null -eq $observedProcess) { throw 'Launched process is absent' }; "
                "@{pid=[int]$observedProcess.ProcessId; executable=$observedProcess.ExecutablePath; "
                "created=$observedProcess.CreationDate.ToUniversalTime().ToString('o'); command=$observedProcess.CommandLine} | ConvertTo-Json -Compress"],
                capture_output=True, text=True, check=True, timeout=20)
            self.identity = json.loads(result.stdout)
            verify_process_identity(plan, launch, self.identity, windows_arguments(self.identity["command"]))
            self.created = self.creation_time()
            if abs((instant(self.created) - instant(self.identity["created"])).total_seconds()) > 1:
                raise ValueError("The opened process handle does not match the inspected process.")
        except BaseException:
            self.close()
            raise

    def creation_time(self):
        created, exited, kernel, user = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(self.handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
            raise ctypes.WinError(ctypes.get_last_error())
        value = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return (dt.datetime(1601, 1, 1, tzinfo=UTC) + dt.timedelta(microseconds=value // 10)).isoformat()

    def sample(self):
        exit_code = wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(exit_code)):
            raise ctypes.WinError(ctypes.get_last_error())
        if exit_code.value != 259:
            return {"running": False, "exit_code": exit_code.value}
        if self.creation_time() != self.created:
            raise ValueError("Observed process creation identity changed.")
        counters = ProcessMemory()
        counters.cb = ctypes.sizeof(counters)
        if not self.psapi.GetProcessMemoryInfo(self.handle, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"running": True, "working_set": counters.working_set, "private_usage": counters.private_usage,
                "peak_working_set_since_process_start": counters.peak_working_set, "page_fault_count": counters.page_fault_count}

    def close(self):
        if getattr(self, "handle", None):
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def state_observation(path, now, last_stamp, freshness, expected_count, require_world, unpaused, vehicle_path=None, expected_pid=None, expected_declarations=None):
    observation = {"path": str(path), "verified": False, "failures": [], "missing": []}
    try:
        original_state, state_hash = read_snapshot(path)
        state = original_state
        observation["raw_state"] = original_state
        if "shared_blockbench" in original_state:
            if expected_pid is not None and original_state.get("pid") != expected_pid:
                observation["failures"].append("observer_process_identity_mismatch")
            blockbench = original_state["shared_blockbench"]
            heap = original_state.get("heap", {})
            state = {"timestamp": original_state["timestamp"], "registered_count": original_state.get("registered_count"),
                "model_parsing_complete": original_state.get("native_settled"), "heap_used": heap.get("used_bytes"),
                "heap_max": heap.get("max_bytes"), "paused": original_state.get("paused"),
                "screen": "game" if original_state.get("in_world") is True and original_state.get("screen") is None else original_state.get("screen"),
                "runtime_counters": {"native_pending": original_state.get("native_pending"), "module_pending": blockbench.get("pending"),
                    "module_outstanding": blockbench.get("outstanding"), "module_queued": blockbench.get("queued"), "active_reads": original_state.get("active_read_permits"), "resource_in_flight": original_state.get("resource_epochs", {}).get("in_flight"), "module_failures": blockbench.get("failures")},
                "resource_epochs": original_state.get("resource_epochs", {}), "game_time": original_state.get("game_time")}
            if original_state.get("schema_version") == 2:
                workspace = original_state.get("text_workspace")
                state["text_workspace"] = workspace
                if not isinstance(workspace, dict):
                    observation["missing"].append("text_workspace")
                else:
                    for name in ("budget_bytes", "used_bytes", "peak_bytes", "waiting"):
                        if name not in workspace or workspace[name] is None:
                            observation["missing"].append("text_workspace." + name)
                        elif type(workspace[name]) is not int:
                            observation["failures"].append("invalid_text_workspace_counter." + name)
                    if all(type(workspace.get(name)) is int for name in ("budget_bytes", "used_bytes", "peak_bytes", "waiting")):
                        if not (workspace["budget_bytes"] > 0 and 0 <= workspace["used_bytes"] <= workspace["peak_bytes"] <= workspace["budget_bytes"] and workspace["waiting"] >= 0):
                            observation["failures"].append("invalid_text_workspace_bounds")
                        if workspace["used_bytes"] != 0 or workspace["waiting"] != 0:
                            observation["failures"].append("text_workspace_not_settled")
            if require_world and vehicle_path:
                try:
                    vehicle_state, vehicle_hash = read_snapshot(vehicle_path)
                    observation["raw_vehicle_state"] = vehicle_state
                    observation["vehicle_state_sha256"] = vehicle_hash
                    vehicle_age = (now - instant(vehicle_state["timestamp"])).total_seconds()
                    observation["vehicle_state_age_seconds"] = vehicle_age
                    if not -2 <= vehicle_age <= freshness:
                        observation["failures"].append("stale_or_future_vehicle_state")
                    state["vehicles"] = vehicle_state.get("vehicles", [])
                    vehicle_expected = expected_declarations if expected_declarations is not None else expected_count
                    if vehicle_state.get("registered_count") != vehicle_expected:
                        observation["failures"].append("vehicle_state_declaration_count_mismatch")
                except (OSError, ValueError, KeyError, TypeError) as error:
                    observation["failures"].append("unavailable_vehicle_state: " + str(error))
        stamp = instant(state["timestamp"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        observation["failures"].append("unavailable_or_invalid_state: " + str(error))
        return observation, last_stamp
    observation["state"] = state
    observation["state_sha256"] = state_hash
    age = (now - stamp).total_seconds()
    observation["age_seconds"] = age
    if not -2 <= age <= freshness:
        observation["failures"].append("stale_or_future_state")
    if state["timestamp"] == last_stamp:
        observation["failures"].append("state_did_not_advance")
    for name in ("registered_count", "model_parsing_complete", "heap_used", "heap_max"):
        if name not in state or state[name] is None:
            observation["missing"].append(name)
    if expected_count is not None and state.get("registered_count") != expected_count:
        observation["failures"].append("registration_count_mismatch")
    if state.get("model_parsing_complete") is not True:
        observation["failures"].append("native_parsing_not_complete")
    if require_world:
        if "screen" not in state:
            observation["missing"].append("screen")
        elif state["screen"] != "game":
            observation["failures"].append("not_in_game_screen")
        if not state.get("vehicles"):
            observation["failures"].append("no_observed_route_vehicle")
    if unpaused:
        if "paused" not in state or state["paused"] is None:
            observation["missing"].append("paused")
        elif state["paused"] is not False:
            observation["failures"].append("client_paused")
    counters = state.get("runtime_counters", {})
    for name in ZERO_COUNTERS:
        if name not in counters or counters[name] is None:
            observation["missing"].append("runtime_counters." + name)
        elif type(counters[name]) is not int or counters[name] != 0:
            observation["failures"].append("unsettled_counter." + name)
    observation["verified"] = not observation["failures"] and not observation["missing"]
    return observation, state["timestamp"]


class RouteWindows:
    """Distribute actual same-ID progress observations across the whole route run."""
    def __init__(self, duration, count, minimum_displacement, interval, freshness):
        if not math.isfinite(duration) or duration <= 0 or type(count) is not int or count < 2:
            raise ValueError("Distributed route observation requires positive duration and at least two windows.")
        if not math.isfinite(minimum_displacement) or minimum_displacement <= 0:
            raise ValueError("Use a positive minimum per-window progress displacement.")
        if not math.isfinite(interval) or interval <= 0 or not math.isfinite(freshness) or freshness <= 0:
            raise ValueError("Use positive finite sampling and freshness intervals.")
        self.duration, self.minimum_displacement = duration, minimum_displacement
        self.maximum_gap = interval + freshness
        self.windows = []
        self.previous = {}
        for index in range(count):
            start, end = duration * index / count, duration * (index + 1) / count
            self.windows.append({"index": index, "start_seconds": start, "end_seconds": end,
                "coverage_tolerance_seconds": min((end-start)/4, self.maximum_gap),
                "sample_count": 0, "eligible_sample_count": 0, "first_elapsed_seconds": None,
                "last_elapsed_seconds": None, "first_timestamp": None, "last_timestamp": None,
                "maximum_observed_gap_seconds": 0, "same_id_pair_count": 0,
                "observed_progress_displacement": {}})

    def policy(self):
        return {"duration_seconds": self.duration, "window_count": len(self.windows),
            "minimum_window_progress_displacement": self.minimum_displacement,
            "maximum_sampling_gap_seconds": self.maximum_gap,
            "windows": [{key: value[key] for key in ("index", "start_seconds", "end_seconds", "coverage_tolerance_seconds")} for value in self.windows],
            "motion_evidence": "Positive absolute railProgress displacement between eligible observations of the same vehicle ID inside each window.",
            "limits": "Sampled route motion does not establish doors, arrivals, visual rendering or unsampled continuity."}

    def add(self, elapsed, observation):
        index = min(len(self.windows)-1, max(0, int(elapsed*len(self.windows)/self.duration)))
        window = self.windows[index]
        current, invalid, duplicates = {}, [], set()
        state = observation.get("state", {})
        vehicles = state.get("vehicles", [])
        if not isinstance(vehicles, list):
            invalid.append({"reason": "invalid_vehicle_list"})
            vehicles = []
        for vehicle in vehicles:
            if not isinstance(vehicle, dict):
                invalid.append({"reason": "invalid_vehicle_record"})
                continue
            identifier, progress = vehicle.get("id"), vehicle.get("railProgress")
            if type(identifier) not in (int, str) or type(progress) not in (int, float) or not math.isfinite(progress):
                invalid.append({"vehicle_id": identifier, "reason": "missing_or_invalid_id_or_progress"})
            elif identifier in current or identifier in duplicates:
                duplicates.add(identifier)
                current.pop(identifier, None)
                invalid.append({"vehicle_id": identifier, "reason": "duplicate_vehicle_id"})
            else:
                current[identifier] = progress
        eligible = observation.get("verified") is True and bool(current) and not invalid and elapsed <= self.duration+self.maximum_gap
        record = {"index": index, "eligible": eligible, "eligible_vehicle_count": len(current),
            "invalid_trajectory_records": invalid, "same_id_progress_displacements": []}
        window["sample_count"] += 1
        if window["last_elapsed_seconds"] is not None:
            gap = elapsed-window["last_elapsed_seconds"]
            window["maximum_observed_gap_seconds"] = max(window["maximum_observed_gap_seconds"], gap)
        if window["first_elapsed_seconds"] is None:
            window["first_elapsed_seconds"] = elapsed
            window["first_timestamp"] = state.get("timestamp")
        window["last_elapsed_seconds"], window["last_timestamp"] = elapsed, state.get("timestamp")
        if eligible:
            window["eligible_sample_count"] += 1
            previous = self.previous.get(index)
            if previous is not None and 0 < elapsed-previous["elapsed"] <= self.maximum_gap:
                for identifier in current.keys() & previous["vehicles"].keys():
                    displacement = abs(current[identifier]-previous["vehicles"][identifier])
                    if not math.isfinite(displacement):
                        continue
                    window["same_id_pair_count"] += 1
                    key = type(identifier).__name__ + ":" + str(identifier)
                    window["observed_progress_displacement"][key] = window["observed_progress_displacement"].get(key, 0)+displacement
                    record["same_id_progress_displacements"].append({"vehicle_id": identifier,
                        "previous_elapsed_seconds": previous["elapsed"], "elapsed_seconds": elapsed,
                        "previous_progress": previous["vehicles"][identifier], "progress": current[identifier],
                        "absolute_progress_displacement": displacement})
            self.previous[index] = {"elapsed": elapsed, "vehicles": current}
        else:
            self.previous.pop(index, None)
        return record

    def summary(self):
        results = []
        for window in self.windows:
            result = dict(window)
            tolerance = window["coverage_tolerance_seconds"]
            result["coverage_verified"] = window["sample_count"] >= 2 and window["eligible_sample_count"] == window["sample_count"] and \
                window["first_elapsed_seconds"] <= window["start_seconds"]+tolerance and \
                window["last_elapsed_seconds"] >= window["end_seconds"]-tolerance and \
                window["maximum_observed_gap_seconds"] <= self.maximum_gap
            result["motion_verified"] = any(value >= self.minimum_displacement for value in window["observed_progress_displacement"].values())
            result["passed"] = result["coverage_verified"] and result["motion_verified"]
            results.append(result)
        return {"passed": all(window["passed"] for window in results), "windows": results}


BLOCKING_DIAGNOSTICS = ("Failed to decode resource", "Failed to parse Blockbench model", "Failed to parse OBJ model",
    "Resource text exceeds", "OutOfMemoryError", "Resource reload failed", "Failed to initialize mod containers", "Mixin apply failed")


def native_diagnostics(log):
    lines = log.decode("utf-8", errors="replace").splitlines()
    blocking = [{"line": index+1, "text": line} for index, line in enumerate(lines) if any(token in line for token in BLOCKING_DIAGNOSTICS)]
    other_errors = [{"line": index+1, "text": line} for index, line in enumerate(lines)
        if "/ERROR]" in line and "MinecraftTransitRailway" in line and not any(token in line for token in BLOCKING_DIAGNOSTICS)]
    return {"blocking": blocking, "other_mtr_error_lines_requiring_review": other_errors}


START = b"Reloading ResourceManager:"
REGISTERED = re.compile(rb"Loaded (\d+) vehicles and completed door movement validation")
WORK = re.compile(rb"MTR memory sharing: (\d+) requests, (\d+) path hits, (\d+) unique parses, (\d+) failures, (\d+) pending, (\d+) outstanding, (\d+) queued")


def reload_evidence(log, events, launch, process_created, expected_count, expected_declarations=None):
    results, consumed_end = [], 0
    for event in events:
        record = {"event": event, "verified": False, "failures": []}
        try:
            offset = event["log_offset"]
            if type(offset) is not int or offset < consumed_end or offset < 0 or offset >= len(log):
                raise ValueError("Reload event offset is outside new, distinct log evidence.")
            if event["pid"] != launch["pid"] or instant(event["process_created"]) != instant(process_created):
                raise ValueError("Reload event belongs to another process.")
            if event["method"] != "native_f3_t":
                raise ValueError("An actual native F3+T input record is required.")
            before = event["before"]
            in_game = before.get("screen") == "game" or (before.get("screen") is None and before.get("in_world") is True)
            parsed = before.get("native_settled", before.get("model_parsing_complete"))
            if not in_game or before.get("paused") is not False or parsed is not True:
                raise ValueError("Reload event lacks a loaded, unpaused before snapshot.")
            if before.get("registered_count") != expected_count:
                raise ValueError("Reload event starts from a different catalogue.")
            event_time, before_time = instant(event["timestamp"]), instant(before["timestamp"])
            if not 0 <= (event_time - before_time).total_seconds() <= 15 or event_time < instant(launch["timestamp"]):
                raise ValueError("Reload input/before evidence is not fresh for this launch.")
            start = log.find(START, offset)
            if start < 0:
                raise ValueError("No new ResourceManager reload follows the input.")
            next_start = log.find(START, start + len(START))
            stop = len(log) if next_start < 0 else next_start
            diagnostics = native_diagnostics(log[start:stop])
            if diagnostics["blocking"]:
                raise ValueError("Resource decoding/native parsing diagnostics reject this reload.")
            registered = REGISTERED.search(log, start, stop)
            work = WORK.search(log, start, stop)
            if not registered or not work:
                raise ValueError("Native registration and module-work completion are missing.")
            if (expected_declarations is not None and int(registered.group(1)) != expected_declarations) or any(int(work.group(index)) for index in (4, 5, 6, 7)):
                raise ValueError("Reload registration/counters did not settle successfully.")
            consumed_end = max(registered.end(), work.end())
            record.update(verified=True, resource_start_offset=start, native_registration_offset=registered.start(),
                          declared_vehicle_count=int(registered.group(1)), module_report_offset=work.start(), completion_end_offset=consumed_end)
        except (KeyError, TypeError, ValueError) as error:
            record["failures"].append(str(error))
        results.append(record)
    return results


def native_epoch_evidence(events, observations, baseline_sequence, launch, process_created):
    """Match real reload calls to their own post-return settled observations."""
    starts, returns, results = {}, {}, []
    for event in events:
        if event.get("pid") != launch["pid"]:
            continue
        sequence = event.get("sequence")
        if type(sequence) is not int or sequence <= baseline_sequence:
            continue
        collection = starts if event.get("phase") == "start" else returns if event.get("phase") == "return" else None
        if collection is not None:
            collection.setdefault(sequence, []).append(event)
    for sequence in sorted(set(starts) | set(returns)):
        record = {"sequence": sequence, "verified": False, "failures": []}
        try:
            if len(starts.get(sequence, [])) != 1 or len(returns.get(sequence, [])) != 1:
                raise ValueError("A unique actual reload start and return are required.")
            start, returned = starts[sequence][0], returns[sequence][0]
            if instant(start["timestamp"]) < instant(launch["timestamp"]) or instant(returned["timestamp"]) < instant(start["timestamp"]):
                raise ValueError("Reload timestamps do not belong to this launch/order.")
            if not start.get("render_thread") or not returned.get("render_thread"):
                raise ValueError("Reload did not run on the observed render thread.")
            if start["thread_id"] != returned["thread_id"] or returned["monotonic_nanos"] < start["monotonic_nanos"]:
                raise ValueError("Reload call identity/order differs at return.")
            next_starts = [item[0]["monotonic_nanos"] for key, item in starts.items() if key > sequence]
            next_start = min(next_starts) if next_starts else math.inf
            settled = [item for item in observations if item.get("verified") and
                item.get("raw_state", {}).get("resource_epochs", {}).get("last_completed_sequence") == sequence and
                returned["monotonic_nanos"] <= item.get("raw_state", {}).get("monotonic_nanos", -1) < next_start]
            if not settled:
                raise ValueError("This returned epoch has no fresh settled snapshot before the next reload.")
            record.update(verified=True, start=start, returned=returned, settled_timestamp=settled[0]["state"]["timestamp"],
                          settled_state_sha256=settled[0]["state_sha256"])
        except (ValueError, KeyError, TypeError) as error:
            record["failures"].append(str(error))
        results.append(record)
    return results


def consecutive_reloads(records):
    longest = current = 0
    previous_sequence = None
    for record in records:
        sequence = record.get("sequence")
        contiguous = previous_sequence is None or sequence is None or sequence == previous_sequence + 1
        current = current + 1 if record["verified"] and contiguous else 1 if record["verified"] else 0
        longest = max(longest, current)
        previous_sequence = sequence
    return longest


def full_reload_evidence(log, inputs, epochs, observations, baseline_sequence, launch, process_created, expected_count, expected_declarations):
    """Require external native input, full ResourceManager work and settled MTR epoch."""
    if expected_declarations is None:
        raise ValueError("Full resource validation requires a separate expected declaration count.")
    logs = reload_evidence(log, inputs, launch, process_created, expected_count, expected_declarations)
    native = native_epoch_evidence(epochs, observations, baseline_sequence, launch, process_created)
    used_sequences, results = set(), []
    for index, record in enumerate(logs):
        record["scope"] = "full_resource_manager_native_f3_t"
        try:
            if not record["verified"]:
                raise ValueError("The input has no verified full resource/registration log completion.")
            event, receipt = inputs[index], inputs[index]["input"]
            if receipt.get("succeeded") is not True or receipt.get("method") != "native_f3_t" or not receipt.get("provider"):
                raise ValueError("Actual external native input confirmation is missing.")
            issued, confirmed = instant(receipt["issued_at"]), instant(receipt["confirmed_at"])
            if issued < instant(event["timestamp"]) or confirmed < issued or (issued-instant(event["before"]["timestamp"])).total_seconds() > 15:
                raise ValueError("External input confirmation/before timing is invalid or stale.")
            next_issued = instant(inputs[index+1]["input"]["issued_at"]) if index+1 < len(inputs) else dt.datetime.max.replace(tzinfo=UTC)
            before_sequence = event["before"]["resource_epochs"]["last_completed_sequence"]
            candidates = [item for item in native if item["verified"] and item["sequence"] not in used_sequences and
                item["sequence"] > before_sequence and issued <= instant(item["start"]["timestamp"]) < next_issued and
                instant(item["settled_timestamp"]) < next_issued]
            if len(candidates) != 1:
                raise ValueError("Input must map to one distinct returned, settled native epoch before the next input.")
            item = candidates[0]
            used_sequences.add(item["sequence"])
            record.update(sequence=item["sequence"], native_epoch=item, verified=True)
        except (KeyError, TypeError, ValueError) as error:
            record["verified"] = False
            record["failures"].append(str(error))
        results.append(record)
    return results


def capture_reload_before(instance, output, expected_count):
    """Save an immutable before record; this performs no game input."""
    instance, output = pathlib.Path(instance).resolve(), pathlib.Path(output).resolve()
    if output.exists():
        raise ValueError("Use a fresh external input before-record path.")
    plan, launch = frozen_context(instance, verify_inputs=False)
    process = WindowsProcess(plan, launch)
    try:
        if not process.sample()["running"]:
            raise ValueError("The launched process has exited.")
        path = instance / "game-probe/packaged-observer.json"
        observed, _ = state_observation(path, dt.datetime.now(UTC), None, 15, expected_count, False, True, expected_pid=launch["pid"])
        if not observed["verified"]:
            raise ValueError("Before state is not fresh and settled: " + json.dumps(observed["failures"] + observed["missing"]))
        before = observed["raw_state"]
        if before.get("in_world") is not True or before.get("screen") is not None:
            raise ValueError("Actual game screen is required before external reload input.")
        record = {"schema_version": 1, "event_id": str(uuid.uuid4()), "timestamp": timestamp(), "pid": launch["pid"],
            "process_created": process.created, "method": "native_f3_t", "log_offset": (instance / "logs/latest.log").stat().st_size,
            "before": before, "before_state_sha256": observed["state_sha256"], "plan_sha256": launch["plan_sha256"]}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record
    finally:
        process.close()


def confirm_reload_input(before_path, events_path, receipt):
    """Append caller-confirmed native input while preserving the before record."""
    before_path, events_path = pathlib.Path(before_path), pathlib.Path(events_path)
    record = read(before_path)
    if type(receipt.get("succeeded")) is not bool or receipt.get("method") != "native_f3_t" or not receipt.get("provider"):
        raise ValueError("Provide the actual external native input result, including failed attempts.")
    issued, confirmed = instant(receipt["issued_at"]), instant(receipt["confirmed_at"])
    if issued < instant(record["timestamp"]) or confirmed < issued:
        raise ValueError("Actual input receipt timestamps are out of order.")
    if events_path.exists() and any(json.loads(line).get("event_id") == record["event_id"] for line in events_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()):
        raise ValueError("This actual input has already been recorded.")
    record.update(input=receipt, before_record_sha256=digest(before_path))
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")
        stream.flush()
    return record


def gpu_process_paths(paths, pid):
    # The Windows GPU instance identity includes the PID. Query that process
    # directly so a retired, unrelated wildcard instance cannot invalidate it.
    return [path.replace("(*)", "(pid_" + str(pid) + "_*)") for path in paths]


def auxiliary(plan, launch, gpu_paths, nmt):
    result = {}
    if gpu_paths:
        queried_paths = gpu_process_paths(gpu_paths, launch["pid"])
        payload = {"paths": queried_paths, "pid": launch["pid"]}
        script = "$gpuRequest = [Console]::In.ReadToEnd() | ConvertFrom-Json; "                  "$gpuSample = Get-Counter -Counter @($gpuRequest.paths) -ErrorAction Stop; "                  "@($gpuSample.CounterSamples | Where-Object { $_.InstanceName.StartsWith('pid_' + $gpuRequest.pid + '_') } | "                  "Select-Object Path,InstanceName,CookedValue,Status,Timestamp) | ConvertTo-Json -Depth 3 -Compress"
        try:
            sampled = subprocess.run(["pwsh", "-NoProfile", "-Command", script], input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=20)
            if sampled.returncode:
                result["gpu"] = {"paths": gpu_paths, "queried_paths": queried_paths, "available": False,
                    "exit_code": sampled.returncode, "raw_stdout": sampled.stdout, "raw_stderr": sampled.stderr,
                    "error": "GPU counter query exited with code " + str(sampled.returncode)}
                values = None
            else:
                values = json.loads(sampled.stdout) if sampled.stdout.strip() else []
            if values is not None:
                values = [values] if isinstance(values, dict) else values
                names = {path.rsplit(chr(92), 1)[-1].casefold() for path in gpu_paths}
                found = {item.get("Path", "").rsplit(chr(92), 1)[-1].casefold() for item in values}
                available = bool(values) and names.issubset(found) and all(item.get("Status") in (0, 1) and math.isfinite(item.get("CookedValue", math.nan)) for item in values)
                totals = {}
                for item in values:
                    counter = item.get("Path", "").rsplit(chr(92), 1)[-1]
                    totals[counter] = totals.get(counter, 0) + item.get("CookedValue", 0)
                result["gpu"] = {"paths": gpu_paths, "queried_paths": queried_paths, "samples": values,
                    "totals_by_counter": totals, "available": available, "exit_code": sampled.returncode,
                    "raw_stdout": sampled.stdout, "raw_stderr": sampled.stderr}
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            result["gpu"] = {"available": False, "error": str(error)}
    if nmt:
        java = pathlib.Path(plan["java"])
        jcmd = java.with_name("jcmd.exe")
        try:
            sampled = subprocess.run([str(jcmd), str(launch["pid"]), "VM.native_memory", "summary", "scale=KB"], capture_output=True, text=True, timeout=20)
            total = re.search(r"Total: reserved=(\d+)KB, committed=(\d+)KB", sampled.stdout)
            result["nmt"] = {"available": sampled.returncode == 0 and total is not None, "exit_code": sampled.returncode,
                             "stdout": sampled.stdout, "stderr": sampled.stderr}
            if total:
                result["nmt"].update(reserved_bytes=int(total.group(1))*1024, committed_bytes=int(total.group(2))*1024)
        except (OSError, subprocess.SubprocessError) as error:
            result["nmt"] = {"available": False, "error": str(error)}
    return result


def observe(args):
    instance, output = args.instance.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError("Use a fresh observation output directory.")
    output.mkdir(parents=True)
    source_bytes = pathlib.Path(__file__).read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    (output / "observer-source.py").write_bytes(source_bytes)
    process = None
    try:
        plan, launch = frozen_context(instance)
        process = WindowsProcess(plan, launch)
        duration, interval, freshness = args.duration, args.interval, args.freshness_seconds
        route_windows = RouteWindows(duration, args.route_windows, args.minimum_window_progress_displacement, interval, freshness) if args.mode == "route" else None
        route_policy = route_windows.policy() if route_windows else None
        route_policy_hash = None
        if route_policy:
            route_policy_bytes = (json.dumps(route_policy, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            (output / "route-window-policy.json").write_bytes(route_policy_bytes)
            route_policy_hash = hashlib.sha256(route_policy_bytes).hexdigest()
        observation_policy = {"duration": duration, "interval": interval, "freshness_seconds": freshness,
            "stable_seconds": args.stable_seconds, "expected_count": args.expected_count, "expected_declarations": args.expected_declarations,
            "require_world": args.require_world or args.mode == "route", "unpaused": args.unpaused or args.mode == "route",
            "required_zero_counters": ZERO_COUNTERS, "require_reloads": args.require_reloads, "gpu_counter_paths": list(args.gpu_counter),
            "nmt": args.nmt, "auxiliary_interval": args.auxiliary_interval, "route_windows": route_policy,
            "sampling_cadence": "future phase-aligned deadlines; missed slots are skipped without catch-up",
            "gpu_query_paths": gpu_process_paths(args.gpu_counter, launch["pid"]),
            "route_window_policy_sha256": route_policy_hash}
    except Exception as preflight_error:
        if process is not None:
            process.close()
        (output / "samples.jsonl").write_text("", encoding="utf-8")
        summary = {"timestamp": timestamp(), "status": "preflight_failed", "passed": False, "error": str(preflight_error),
            "instance": str(instance), "mode": args.mode, "source_sha256": source_hash, "current_source_sha256": digest(pathlib.Path(__file__)),
            "source_changed_during_observation": digest(pathlib.Path(__file__)) != source_hash,
            "samples_sha256": digest(output / "samples.jsonl"),
            "plan_sha256": digest(instance / "packaged-client-plan.json") if (instance / "packaged-client-plan.json").exists() else None,
            "launch_sha256": digest(instance / "packaged-client-launch.json") if (instance / "packaged-client-launch.json").exists() else None}
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "preflight_failed", "passed": False, "summary": str(output / "summary.json")}), flush=True)
        return 1
    state_path = args.state_file.resolve() if args.state_file else instance / "game-probe/packaged-observer.json"
    vehicle_path = args.vehicle_state_file.resolve() if args.vehicle_state_file else instance / "game-probe/live.json"
    epoch_path = args.epoch_events.resolve() if args.epoch_events else instance / "game-probe/resource-epochs.jsonl"
    epoch_observations, baseline_sequence = [], None
    started, start_clock = timestamp(), time.monotonic()
    stable_since, last_stamp, prior_valid = None, None, False
    count, valid, missing, failures, peaks, vehicle_motion = 0, 0, set(), set(), {}, False
    previous_game_time, game_time_advanced, previous_clock = None, False, None
    auxiliary_available = {"gpu": 0, "nmt": 0}
    auxiliary_attempted = {"gpu": 0, "nmt": 0}
    auxiliary_peaks = {}
    status, error = "duration_complete", None
    interval_end, last_auxiliary = start_clock, -math.inf
    try:
        with (output / "samples.jsonl").open("x", encoding="utf-8") as stream:
            while True:
                now_clock, now = time.monotonic(), dt.datetime.now(UTC)
                memory = process.sample()
                sample = {"timestamp": now.isoformat(), "elapsed_seconds": now_clock-start_clock, "process": memory}
                if not memory["running"]:
                    status = "process_exited"
                    if route_windows:
                        sample["route_window"] = route_windows.add(sample["elapsed_seconds"], {"verified": False})
                        sample["route_window"]["policy_sha256"] = route_policy_hash
                    stream.write(json.dumps(sample) + "\n"); stream.flush()
                    break
                state, last_stamp = state_observation(state_path, now, last_stamp, freshness,
                    args.expected_count, args.require_world or args.mode == "route", args.unpaused or args.mode == "route", vehicle_path, launch["pid"], args.expected_declarations)
                if previous_clock is not None and now_clock-previous_clock > interval+freshness:
                    state["verified"] = False
                    state["failures"].append("observation_gap_exceeded")
                previous_clock = now_clock
                sample["observation"] = state
                if route_windows:
                    sample["route_window"] = route_windows.add(sample["elapsed_seconds"], state)
                    sample["route_window"]["policy_sha256"] = route_policy_hash
                    if any(pair["absolute_progress_displacement"] > 0 for pair in sample["route_window"]["same_id_progress_displacements"]):
                        vehicle_motion = True
                if now_clock-last_auxiliary >= args.auxiliary_interval:
                    sample["auxiliary"] = auxiliary(plan, launch, args.gpu_counter, args.nmt)
                    last_auxiliary = now_clock
                    for name, value in sample["auxiliary"].items():
                        auxiliary_available[name] += int(value.get("available", False))
                        auxiliary_attempted[name] += 1
                        if value.get("available"):
                            metrics = value.get("totals_by_counter", {}) if name == "gpu" else {key: value[key] for key in ("reserved_bytes", "committed_bytes") if key in value}
                            for key, amount in metrics.items():
                                metric = name + "." + key
                                auxiliary_peaks[metric] = max(auxiliary_peaks.get(metric, 0), amount)
                stream.write(json.dumps(sample, ensure_ascii=False) + "\n"); stream.flush()
                count += 1; valid += int(state["verified"])
                missing.update(state["missing"]); failures.update(state["failures"])
                for name in ("working_set", "private_usage"):
                    peaks[name] = max(peaks.get(name, 0), memory[name])
                current = state.get("state", {})
                if baseline_sequence is None and state["verified"] and current.get("resource_epochs"):
                    baseline_sequence = current["resource_epochs"].get("last_completed_sequence", 0)
                if args.require_reloads and state["verified"]:
                    epoch_observations.append(state)
                if args.mode == "reloads" and baseline_sequence is not None and epoch_path.exists():
                    try:
                        epoch_events = [json.loads(line) for line in epoch_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
                        input_events = [json.loads(line) for line in args.reload_events.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
                        current_reloads = full_reload_evidence((instance / "logs/latest.log").read_bytes(), input_events, epoch_events,
                            epoch_observations, baseline_sequence, launch, process.created, args.expected_count, args.expected_declarations)
                        if consecutive_reloads(current_reloads) >= args.require_reloads:
                            status = "reloads_verified"
                            break
                    except (OSError, ValueError):
                        pass
                if isinstance(current.get("heap_used"), (int, float)):
                    peaks["heap_used"] = max(peaks.get("heap_used", 0), current["heap_used"])
                game_time = current.get("game_time")
                if state["verified"] and type(game_time) is int:
                    if prior_valid and previous_game_time is not None and game_time > previous_game_time:
                        game_time_advanced = True
                    previous_game_time = game_time
                if state["verified"]:
                    stable_since = stable_since if stable_since is not None else now_clock
                else:
                    stable_since = None
                prior_valid = state["verified"]
                elapsed = now_clock-start_clock
                if args.mode == "startup" and stable_since is not None and now_clock-stable_since >= args.stable_seconds:
                    status = "settled"
                    break
                if elapsed >= duration:
                    break
                current_clock = time.monotonic()
                # Missed sampling slots remain gaps in the raw evidence; do not
                # manufacture catch-up observations against one probe snapshot.
                interval_end = start_clock + (math.floor((current_clock-start_clock)/interval)+1)*interval
                delay = min(max(0, interval_end-current_clock), max(0, start_clock+duration-current_clock))
                time.sleep(delay)
    except KeyboardInterrupt:
        status, error = "interrupted", "Observer interrupted; recorded samples are preserved."
    except Exception as observed_error:
        status, error = "observation_failed", str(observed_error)
    finally:
        process.close()
    ended, elapsed = timestamp(), time.monotonic()-start_clock
    log_path = instance / "logs/latest.log"
    log_bytes = log_path.read_bytes() if log_path.exists() else b""
    (output / "native-log-at-completion.log").write_bytes(log_bytes)
    diagnostics = native_diagnostics(log_bytes)
    declaration_counts = [int(match.group(1)) for match in REGISTERED.finditer(log_bytes)]
    input_bytes = args.reload_events.read_bytes() if args.reload_events and args.reload_events.exists() else b""
    epoch_bytes = epoch_path.read_bytes() if epoch_path.exists() else b""
    if args.reload_events:
        (output / "external-input-events-at-completion.jsonl").write_bytes(input_bytes)
    if epoch_path.exists():
        (output / "native-epoch-events-at-completion.jsonl").write_bytes(epoch_bytes)
    reloads = []
    if args.require_reloads and args.reload_events and epoch_path.exists() and baseline_sequence is not None:
        try:
            events = [json.loads(line) for line in input_bytes.decode("utf-8-sig").splitlines() if line.strip()]
            epoch_events = [json.loads(line) for line in epoch_bytes.decode("utf-8-sig").splitlines() if line.strip()]
            reloads = full_reload_evidence(log_bytes, events, epoch_events, epoch_observations, baseline_sequence,
                launch, process.created, args.expected_count, args.expected_declarations)
        except (OSError, ValueError) as observed_error:
            failures.add("full_reload_evidence_unavailable: " + str(observed_error))
    verified_reloads = sum(item["verified"] for item in reloads)
    route_results = route_windows.summary() if route_windows else None
    if args.mode == "startup":
        passed = status == "settled"
    elif args.mode == "reloads":
        passed = status == "reloads_verified"
    else:
        passed = status == "duration_complete" and count > 1 and valid == count and elapsed >= duration and vehicle_motion and game_time_advanced and route_results["passed"]
        if not route_results["passed"]:
            failures.add("distributed_route_windows_unverified")
    passed = passed and consecutive_reloads(reloads) >= args.require_reloads
    if not log_path.exists():
        passed = False
        failures.add("native_log_unavailable")
    if args.mode == "startup" and (not declaration_counts or (args.expected_declarations is not None and declaration_counts[-1] != args.expected_declarations)):
        passed = False
        failures.add("native_registration_declaration_log_missing_or_mismatched")
    if diagnostics["blocking"]:
        passed = False
        failures.add("native_resource_decode_or_parse_diagnostics")
    for name in ("gpu", "nmt"):
        if auxiliary_attempted[name] and auxiliary_available[name] != auxiliary_attempted[name]:
            passed = False
            failures.add("requested_" + name + "_observation_unavailable")
    current_source_hash = digest(pathlib.Path(__file__)) if pathlib.Path(__file__).exists() else None
    summary = {"started": started, "ended": ended, "elapsed_seconds": elapsed, "status": status, "passed": passed,
        "error": error, "mode": args.mode, "instance": str(instance), "plan_sha256": digest(instance / "packaged-client-plan.json"),
        "launch_sha256": digest(instance / "packaged-client-launch.json"), "process_identity": process.identity,
        "process_created": process.created, "policy": observation_policy, "route_window_evidence": route_results,
        "sample_count": count, "verified_sample_count": valid, "missing_observation_fields": sorted(missing),
        "observed_failures": sorted(failures), "sampled_peaks_bytes": peaks, "observed_vehicle_motion": vehicle_motion, "observed_game_time_advanced": game_time_advanced,
        "auxiliary_available_samples": auxiliary_available, "auxiliary_attempted_samples": auxiliary_attempted, "auxiliary_sampled_peaks": auxiliary_peaks, "verified_reload_count": verified_reloads, "longest_verified_reload_run": consecutive_reloads(reloads), "reload_evidence": reloads,
        "samples_sha256": digest(output / "samples.jsonl"), "source_sha256": source_hash, "current_source_sha256": current_source_hash,
        "source_changed_during_observation": current_source_hash != source_hash,
        "log_sha256_at_completion": hashlib.sha256(log_bytes).hexdigest(), "native_diagnostics": diagnostics, "native_registration_declaration_counts": declaration_counts,
        "reload_events_sha256": hashlib.sha256(input_bytes).hexdigest() if args.reload_events else None,
        "native_epoch_events_sha256": hashlib.sha256(epoch_bytes).hexdigest() if epoch_path.exists() else None, "baseline_completed_epoch_sequence": baseline_sequence,
        "limits": ["Sampled peaks may miss brief peaks. Missing or stale state cannot pass settlement or route observation.",
            "Route evidence requires every sampled state to be fresh, in-game, explicitly unpaused and settled, plus same-ID railProgress displacement in every frozen time window. It does not establish doors, arrivals, visual rendering or unsampled continuity.",
            "Reload counts require distinct real log starts/registration/work completion and externally recorded native input, not repeated polling.",
            "NMT includes Java heap and does not account for all driver/third-party native allocations. OS private usage minus heap is not reported as native memory.",
            "GPU counters are driver/OS observations. Frame and GC distributions require the separate raw JFR/GC analysis.",
            "CIM identity verification, sampling and optional jcmd/PowerShell GPU queries add instrumentation overhead; pair matching controls."]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "passed": passed, "samples": count, "summary": str(output / "summary.json")}), flush=True)
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("startup", "route", "reloads"))
    parser.add_argument("--instance", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--state-file", type=pathlib.Path)
    parser.add_argument("--vehicle-state-file", type=pathlib.Path)
    parser.add_argument("--epoch-events", type=pathlib.Path)
    parser.add_argument("--expected-count", type=int, required=True, help="Distinct registered ID count in the native observer.")
    parser.add_argument("--expected-declarations", type=int, help="Separate declared-vehicle list count in the native registration log.")
    parser.add_argument("--duration", type=finite_positive, default=300)
    parser.add_argument("--interval", type=finite_positive, default=5)
    parser.add_argument("--stable-seconds", type=finite_positive, default=60)
    parser.add_argument("--freshness-seconds", type=finite_positive, default=15)
    parser.add_argument("--route-windows", type=int, default=3, help="Equal-duration windows; every window must contain eligible same-ID motion and sampling coverage.")
    parser.add_argument("--minimum-window-progress-displacement", type=finite_positive, default=0.01,
        help="Minimum observed absolute railProgress displacement for one vehicle ID inside every route window.")
    parser.add_argument("--require-world", action="store_true")
    parser.add_argument("--unpaused", action="store_true")
    parser.add_argument("--reload-events", type=pathlib.Path)
    parser.add_argument("--require-reloads", type=int, default=0)
    parser.add_argument("--gpu-counter", action="append", default=[], help="Explicit local GPU Process Memory counter paths; repeat per counter.")
    parser.add_argument("--nmt", action="store_true", help="Observe enabled JVM NativeMemoryTracking through read-only jcmd summaries.")
    parser.add_argument("--auxiliary-interval", type=finite_positive, default=60)
    args = parser.parse_args()
    if args.expected_count <= 0 or args.require_reloads < 0 or (args.expected_declarations is not None and args.expected_declarations <= 0):
        parser.error("Require positive native ID/declaration counts and a nonnegative reload count.")
    if args.route_windows < 2:
        parser.error("Distributed route validation requires at least two windows.")
    if args.mode == "reloads" and not args.require_reloads:
        parser.error("Reload observation requires a positive consecutive reload count.")
    if args.require_reloads and (not args.reload_events or args.expected_declarations is None):
        parser.error("Full reload validation requires actual --reload-events input records and --expected-declarations.")
    return observe(args)


if __name__ == "__main__":
    raise SystemExit(main())
