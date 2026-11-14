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


def frozen_context(instance):
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


def state_observation(path, now, last_stamp, freshness, expected_count, require_world, unpaused, vehicle_path=None, expected_pid=None):
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
                    if vehicle_state.get("registered_count") != expected_count:
                        observation["failures"].append("vehicle_state_registration_mismatch")
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


START = b"Reloading ResourceManager:"
REGISTERED = re.compile(rb"Loaded (\d+) vehicles and completed door movement validation")
WORK = re.compile(rb"MTR memory sharing: (\d+) requests, (\d+) path hits, (\d+) unique parses, (\d+) failures, (\d+) pending, (\d+) outstanding, (\d+) queued")


def reload_evidence(log, events, launch, process_created, expected_count):
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
            if before.get("screen") != "game" or before.get("paused") is not False or before.get("model_parsing_complete") is not True:
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
            registered = REGISTERED.search(log, start, stop)
            work = WORK.search(log, start, stop)
            if not registered or not work:
                raise ValueError("Native registration and module-work completion are missing.")
            if int(registered.group(1)) != expected_count or any(int(work.group(index)) for index in (4, 5, 6, 7)):
                raise ValueError("Reload registration/counters did not settle successfully.")
            consumed_end = max(registered.end(), work.end())
            record.update(verified=True, resource_start_offset=start, native_registration_offset=registered.start(),
                          module_report_offset=work.start(), completion_end_offset=consumed_end)
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


def auxiliary(plan, launch, gpu_paths, nmt):
    result = {}
    if gpu_paths:
        payload = {"paths": gpu_paths, "pid": launch["pid"]}
        script = "$gpuRequest = [Console]::In.ReadToEnd() | ConvertFrom-Json; "                  "$gpuSample = Get-Counter -Counter @($gpuRequest.paths) -ErrorAction Stop; "                  "@($gpuSample.CounterSamples | Where-Object { $_.InstanceName.StartsWith('pid_' + $gpuRequest.pid + '_') } | "                  "Select-Object Path,InstanceName,CookedValue,Status,Timestamp) | ConvertTo-Json -Depth 3 -Compress"
        try:
            sampled = subprocess.run(["pwsh", "-NoProfile", "-Command", script], input=json.dumps(payload), capture_output=True, text=True, check=True, timeout=20)
            values = json.loads(sampled.stdout) if sampled.stdout.strip() else []
            values = [values] if isinstance(values, dict) else values
            names = {path.rsplit(chr(92), 1)[-1].casefold() for path in gpu_paths}
            found = {item.get("Path", "").rsplit(chr(92), 1)[-1].casefold() for item in values}
            available = bool(values) and names.issubset(found) and all(item.get("Status") in (0, 1) and math.isfinite(item.get("CookedValue", math.nan)) for item in values)
            totals = {}
            for item in values:
                counter = item.get("Path", "").rsplit(chr(92), 1)[-1]
                totals[counter] = totals.get(counter, 0) + item.get("CookedValue", 0)
            result["gpu"] = {"paths": gpu_paths, "samples": values, "totals_by_counter": totals, "available": available, "raw_stderr": sampled.stderr}
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
    try:
        plan, launch = frozen_context(instance)
        process = WindowsProcess(plan, launch)
    except Exception as preflight_error:
        (output / "samples.jsonl").write_text("", encoding="utf-8")
        summary = {"timestamp": timestamp(), "status": "preflight_failed", "passed": False, "error": str(preflight_error),
            "instance": str(instance), "mode": args.mode, "source_sha256": digest(pathlib.Path(__file__)),
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
    stable_since, last_stamp, previous_state, prior_valid = None, None, None, False
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
                    stream.write(json.dumps(sample) + "\n"); stream.flush()
                    break
                state, last_stamp = state_observation(state_path, now, last_stamp, args.freshness_seconds,
                    args.expected_count, args.require_world or args.mode == "route", args.unpaused or args.mode == "route", vehicle_path, launch["pid"])
                if previous_clock is not None and now_clock-previous_clock > args.interval+args.freshness_seconds:
                    state["verified"] = False
                    state["failures"].append("observation_gap_exceeded")
                previous_clock = now_clock
                sample["observation"] = state
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
                        current_reloads = native_epoch_evidence(epoch_events, epoch_observations, baseline_sequence, launch, process.created)
                        if consecutive_reloads(current_reloads) >= args.require_reloads:
                            status = "reloads_verified"
                            break
                    except (OSError, ValueError):
                        pass
                if isinstance(current.get("heap_used"), (int, float)):
                    peaks["heap_used"] = max(peaks.get("heap_used", 0), current["heap_used"])
                vehicles = current.get("vehicles", [])
                motion = [(vehicle.get("id"), vehicle.get("railProgress")) for vehicle in vehicles]
                if state["verified"] and prior_valid and previous_state is not None and motion != previous_state:
                    vehicle_motion = True
                game_time = current.get("game_time")
                if state["verified"] and type(game_time) is int:
                    if prior_valid and previous_game_time is not None and game_time > previous_game_time:
                        game_time_advanced = True
                    previous_game_time = game_time
                if state["verified"]:
                    stable_since = stable_since if stable_since is not None else now_clock
                else:
                    stable_since = None
                previous_state, prior_valid = motion, state["verified"]
                elapsed = now_clock-start_clock
                if args.mode == "startup" and stable_since is not None and now_clock-stable_since >= args.stable_seconds:
                    status = "settled"
                    break
                if elapsed >= args.duration:
                    break
                interval_end += args.interval
                delay = min(max(0, interval_end-time.monotonic()), max(0, start_clock+args.duration-time.monotonic()))
                time.sleep(delay)
    except KeyboardInterrupt:
        status, error = "interrupted", "Observer interrupted; recorded samples are preserved."
    except Exception as observed_error:
        status, error = "observation_failed", str(observed_error)
    finally:
        process.close()
    ended, elapsed = timestamp(), time.monotonic()-start_clock
    log_path = instance / "logs/latest.log"
    reloads = []
    if args.reload_events:
        try:
            events = [json.loads(line) for line in args.reload_events.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            reloads = reload_evidence(log_path.read_bytes(), events, launch, process.created, args.expected_count)
        except (OSError, ValueError) as observed_error:
            failures.add("reload_evidence_unavailable: " + str(observed_error))
    if args.require_reloads and epoch_path.exists() and baseline_sequence is not None:
        try:
            epoch_events = [json.loads(line) for line in epoch_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            reloads = native_epoch_evidence(epoch_events, epoch_observations, baseline_sequence, launch, process.created)
        except (OSError, ValueError) as observed_error:
            failures.add("native_epoch_evidence_unavailable: " + str(observed_error))
    verified_reloads = sum(item["verified"] for item in reloads)
    if args.mode == "startup":
        passed = status == "settled"
    elif args.mode == "reloads":
        passed = status == "reloads_verified"
    else:
        passed = status == "duration_complete" and count > 1 and valid == count and elapsed >= args.duration and vehicle_motion and game_time_advanced
    passed = passed and consecutive_reloads(reloads) >= args.require_reloads
    for name in ("gpu", "nmt"):
        if auxiliary_attempted[name] and auxiliary_available[name] != auxiliary_attempted[name]:
            passed = False
            failures.add("requested_" + name + "_observation_unavailable")
    summary = {"started": started, "ended": ended, "elapsed_seconds": elapsed, "status": status, "passed": passed,
        "error": error, "mode": args.mode, "instance": str(instance), "plan_sha256": digest(instance / "packaged-client-plan.json"),
        "launch_sha256": digest(instance / "packaged-client-launch.json"), "process_identity": process.identity,
        "process_created": process.created, "policy": {"duration": args.duration, "interval": args.interval, "freshness_seconds": args.freshness_seconds,
            "stable_seconds": args.stable_seconds, "expected_count": args.expected_count, "require_world": args.require_world or args.mode == "route",
            "unpaused": args.unpaused or args.mode == "route", "required_zero_counters": ZERO_COUNTERS, "require_reloads": args.require_reloads,
            "gpu_counter_paths": args.gpu_counter, "nmt": args.nmt, "auxiliary_interval": args.auxiliary_interval},
        "sample_count": count, "verified_sample_count": valid, "missing_observation_fields": sorted(missing),
        "observed_failures": sorted(failures), "sampled_peaks_bytes": peaks, "observed_vehicle_motion": vehicle_motion, "observed_game_time_advanced": game_time_advanced,
        "auxiliary_available_samples": auxiliary_available, "auxiliary_attempted_samples": auxiliary_attempted, "auxiliary_sampled_peaks": auxiliary_peaks, "verified_reload_count": verified_reloads, "longest_verified_reload_run": consecutive_reloads(reloads), "reload_evidence": reloads,
        "samples_sha256": digest(output / "samples.jsonl"), "source_sha256": digest(pathlib.Path(__file__)),
        "log_sha256_at_completion": digest(log_path) if log_path.exists() else None,
        "reload_events_sha256": digest(args.reload_events) if args.reload_events and args.reload_events.exists() else None,
        "native_epoch_events_sha256": digest(epoch_path) if epoch_path.exists() else None, "baseline_completed_epoch_sequence": baseline_sequence,
        "limits": ["Sampled peaks may miss brief peaks. Missing or stale state cannot pass settlement or route observation.",
            "Route evidence requires every sampled state to be fresh, in-game, explicitly unpaused and settled, plus vehicle-state change; it does not establish unsampled continuity.",
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
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--duration", type=finite_positive, default=300)
    parser.add_argument("--interval", type=finite_positive, default=5)
    parser.add_argument("--stable-seconds", type=finite_positive, default=60)
    parser.add_argument("--freshness-seconds", type=finite_positive, default=15)
    parser.add_argument("--require-world", action="store_true")
    parser.add_argument("--unpaused", action="store_true")
    parser.add_argument("--reload-events", type=pathlib.Path)
    parser.add_argument("--require-reloads", type=int, default=0)
    parser.add_argument("--gpu-counter", action="append", default=[], help="Explicit local GPU Process Memory counter paths; repeat per counter.")
    parser.add_argument("--nmt", action="store_true", help="Observe enabled JVM NativeMemoryTracking through read-only jcmd summaries.")
    parser.add_argument("--auxiliary-interval", type=finite_positive, default=60)
    args = parser.parse_args()
    if args.expected_count <= 0 or args.require_reloads < 0 or (args.mode == "reloads" and not args.require_reloads):
        parser.error("Require positive catalogue count and a positive reload count for reload observation.")
    return observe(args)


if __name__ == "__main__":
    raise SystemExit(main())
