"""Independent whole-client evidence and paired, predeclared performance decisions.

Only independent JVM trials are replicates. Missing observations stay unavailable;
no sample or failed trial is removed to improve a performance decision.
"""
import datetime as dt
import hashlib
import math
import random
import re
import statistics

MODES = ("plain", "profile")
ROLES = ("baseline", "candidate")
COMMON_METRICS = {"loading_ms", "startup_peak_working_set_bytes", "startup_peak_heap_bytes",
                  "steady_private_bytes", "steady_working_set_bytes", "steady_heap_bytes"}
PROFILE_METRICS = {"frame_p99_ms", "frame_max_ms", "gc_count", "gc_pause_total_ms",
                   "gc_pause_max_ms", "full_gc_count", "full_gc_pause_max_ms"}
METRICS = COMMON_METRICS | PROFILE_METRICS


def native_diagnostics(text):
    """Keep all errors; native diagnostics cannot be excused by registration counts."""
    blocking = re.compile(r"Invalid model|OutOfMemoryError|MixinInitialisationError|Mixin apply failed|Resource text exceeds|Resource reload failed|Failed to initialize mod containers|(?:failed|unable|could not) to (?:decode|parse|load|read).*(?:model|resource)|(?:model|resource).*(?:decode|parse) (?:error|failure)|\bFATAL\b", re.IGNORECASE)
    severity = re.compile(r"\bERROR\b")
    mtr = re.compile(r"MinecraftTransitRailway|\[MTR\]|org\.mtr\b|mtr_memory_sharing|site\.benli06", re.IGNORECASE)
    native, other = [], []
    for number, line in enumerate(text.splitlines(), 1):
        entry = {"line": number, "text": line}
        if blocking.search(line) or (severity.search(line) and mtr.search(line)):
            native.append(entry)
        elif severity.search(line):
            other.append(entry)
    return {"scanned": True, "unreviewed_native": native, "other_errors_requiring_contextual_review": other}


def client_log_completeness(raw, samples, instance):
    errors = []
    first_line = raw.splitlines()[0] if raw.splitlines() else b""
    if b"cpw.mods.modlauncher.Launcher/MODLAUNCHER" not in first_line or b"ModLauncher running: args" not in first_line or str(instance).encode("utf-8") not in first_line:
        errors.append("Raw client log lacks this exact isolated client's startup header.")
    previous, count = 0, 0
    for sample in samples:
        witness = sample.get("client_log_witness")
        if witness is None:
            continue  # Logger initialization can follow the earliest startup poll.
        count += 1
        size, expected = witness.get("bytes"), witness.get("sha256")
        if type(size) is not int or not previous <= size <= len(raw) or hashlib.sha256(raw[:size]).hexdigest() != expected:
            errors.append("Client log was truncated, rotated or changed after its captured prefix.")
        if type(size) is int:
            previous = size
    if not count:
        errors.append("No actual client log prefix observations were captured.")
    return {"passed": not errors, "errors": errors, "bytes": len(raw), "prefix_witness_count": count}


def instant(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Evidence timestamps require an explicit UTC offset.")
    return parsed.astimezone(dt.timezone.utc)


def finite(value, *, positive=False):
    return (not isinstance(value, bool) and isinstance(value, (int, float)) and
            math.isfinite(value) and (value > 0 if positive else value >= 0))


def process_key(process):
    if type(process.get("pid")) is not int or process["pid"] <= 0:
        raise ValueError("Invalid actual process identifier.")
    return process["pid"], instant(process["created"]).isoformat()


def execution_window_errors(evidence, expected_trial=None, experiment_started=None):
    """Raw producer receipts, rather than edited execution summaries, bound a JVM."""
    errors = []
    try:
        start, finish = evidence["run_start"], evidence["run_finish"]
        scope = "official_client_performance_trial" if expected_trial is not None else "official_current_client_qualification"
        if start["scope"] != scope or finish["scope"] != scope or start["trial_spec"] != expected_trial:
            errors.append("Raw attempt/trial scope or scheduled identity differs.")
        if start["root"] != finish["root"] or start["root"] != evidence["capture_root"] or start["qualification_key"] != evidence["qualification_key"]:
            errors.append("Raw run receipts belong to another capture directory/qualification.")
        if finish["start_sha256"] != evidence["run_start_sha256"]:
            errors.append("Raw finish does not bind the captured start receipt.")
        if process_key(finish["process"]) != process_key(evidence["process"]):
            errors.append("Raw run finish belongs to another actual JVM.")
        started, finished = instant(start["started_at"]), instant(finish["finished_at"])
        created, captured = instant(evidence["process"]["created"]), instant(evidence["process"]["captured_at"])
        launched = instant(evidence["launch"]["timestamp"])
        completed = instant(evidence["measurement_completed_at"])
        cleanup = instant(evidence["cleanup"]["timestamp"])
        if evidence["started_at"] != start["started_at"] or evidence["finished_at"] != finish["finished_at"]:
            errors.append("Observation times differ from raw attempt/trial receipts.")
        if finish["measurement_completed_at"] != evidence["measurement_completed_at"] or finish["cleanup"] != evidence["cleanup"]:
            errors.append("Endpoint/cleanup differs from the raw run finish.")
        if not started <= created <= launched <= captured <= completed <= cleanup <= finished:
            errors.append("Actual process creation/capture/endpoint falls outside its raw execution window.")
        if experiment_started is not None and instant(experiment_started) > started:
            errors.append("Raw trial predates the actual experiment execution start.")
    except (KeyError, ValueError, TypeError, AttributeError):
        errors.append("Missing/invalid raw execution receipts or actual process timestamps.")
    return errors


def validate_policy(policy):
    required = {"schema", "hypothesis", "pairs", "minimum_pairs", "seed", "confidence", "neutral_probe_off_calibration",
                "startup_timeout_seconds", "warmup_seconds", "measurement_seconds", "sample_interval_seconds",
                "maximum_sample_gap_seconds", "snapshot_freshness_seconds", "jfr_boundary_tolerance_seconds",
                "primary", "guardrails", "aa_equivalence", "instrumentation_equivalence"}
    if set(policy) != required or type(policy["schema"]) is not int or policy["schema"] != 1:
        raise ValueError("Unknown/missing client experiment policy fields or schema.")
    if not isinstance(policy["hypothesis"], str) or not policy["hypothesis"].strip():
        raise ValueError("An explicit hypothesis is required.")
    if policy["neutral_probe_off_calibration"] != "required_before_uninstrumented_claim":
        raise ValueError("Neutral observer overhead calibration cannot be waived by this protocol.")
    for field in ("pairs", "minimum_pairs"):
        if type(policy[field]) is not int or policy[field] < 6 or policy[field] % 2:
            raise ValueError(field + " must be an even integer of at least six for balanced independent pairs.")
    if policy["pairs"] < policy["minimum_pairs"] or type(policy["seed"]) is not int:
        raise ValueError("Insufficient scheduled pairs or invalid seed.")
    if not finite(policy["confidence"], positive=True) or not .5 < policy["confidence"] < 1:
        raise ValueError("Invalid confidence.")
    for field in required:
        if field.endswith("_seconds") and not finite(policy[field], positive=True):
            raise ValueError("Expected finite positive duration: " + field)
    if policy["maximum_sample_gap_seconds"] < policy["sample_interval_seconds"]:
        raise ValueError("Sample gap budget is smaller than the sample interval.")
    if policy["measurement_seconds"] < 3 * policy["sample_interval_seconds"]:
        raise ValueError("Measurement window must contain at least three sampling intervals.")
    if not isinstance(policy["primary"], dict) or any(not isinstance(policy[field], list) for field in ("guardrails", "aa_equivalence", "instrumentation_equivalence")):
        raise ValueError("Endpoint groups must have their documented object/array types.")
    endpoints = [policy["primary"], *policy["guardrails"], *policy["aa_equivalence"]]
    if not policy["guardrails"] or not policy["aa_equivalence"] or not policy["instrumentation_equivalence"]:
        raise ValueError("Guardrails, A/A and instrumentation equivalence budgets are mandatory.")
    for endpoint in endpoints:
        if not isinstance(endpoint, dict) or set(endpoint) != {"metric", "instrumentation", "unit", "limit"}:
            raise ValueError("Unknown/missing endpoint fields.")
        if endpoint["instrumentation"] not in MODES or endpoint["metric"] not in METRICS:
            raise ValueError("Unknown endpoint metric or instrumentation.")
        if endpoint["instrumentation"] == "plain" and endpoint["metric"] in PROFILE_METRICS:
            raise ValueError("JFR endpoints are unavailable in plain trials.")
        if endpoint["unit"] not in ("absolute", "percent") or isinstance(endpoint["limit"], bool) or not isinstance(endpoint["limit"], (int, float)) or not math.isfinite(endpoint["limit"]):
            raise ValueError("Invalid endpoint budget.")
    if policy["primary"]["limit"] >= 0 or (policy["primary"]["unit"] == "percent" and policy["primary"]["limit"] <= -100):
        raise ValueError("Primary endpoint requires a positive improvement.")
    for group in (policy["guardrails"], policy["aa_equivalence"]):
        keys = [(e["instrumentation"], e["metric"], e["unit"]) for e in group]
        if len(keys) != len(set(keys)) or any(e["limit"] < 0 for e in group):
            raise ValueError("Duplicate endpoint or negative guardrail/equivalence tolerance.")
    budgets = {(e["instrumentation"], e["metric"], e["unit"]) for e in policy["aa_equivalence"]}
    if not {(e["instrumentation"], e["metric"], e["unit"]) for e in [policy["primary"], *policy["guardrails"]]} <= budgets:
        raise ValueError("A/A budgets must cover every primary/guardrail endpoint in its own mode and unit.")
    seen = set()
    for endpoint in policy["instrumentation_equivalence"]:
        if set(endpoint) != {"metric", "unit", "limit"} or endpoint["metric"] not in COMMON_METRICS or endpoint["unit"] not in ("absolute", "percent") or not finite(endpoint["limit"]):
            raise ValueError("Invalid instrumentation equivalence endpoint.")
        if endpoint["metric"] in seen:
            raise ValueError("Duplicate instrumentation equivalence endpoint.")
        seen.add(endpoint["metric"])


def schedule(policy):
    """Seeded blocking with equally many AB/BA, AA labels and mode orders."""
    validate_policy(policy)
    rng = random.Random(policy["seed"])
    starts = {(comparison, mode): rng.randrange(2) for comparison in ("aa", "ab") for mode in MODES}
    mode_starts = {comparison: rng.randrange(2) for comparison in ("aa", "ab")}
    result = []
    for pair in range(1, policy["pairs"] + 1):
        comparisons = ["aa", "ab"]
        rng.shuffle(comparisons)
        for comparison in comparisons:
            modes = list(MODES)
            if (pair + mode_starts[comparison]) % 2:
                modes.reverse()
            for mode in modes:
                arms = ["a", "b"]
                if (pair + starts[comparison, mode]) % 2:
                    arms.reverse()
                for arm in arms:
                    role = "candidate" if comparison == "ab" and arm == "b" else "baseline"
                    result.append({"id": f"{pair:03d}-{comparison}-{mode}-{arm}", "pair": pair,
                                   "comparison": comparison, "instrumentation": mode, "arm": arm, "role": role})
    return result


def median_interval(values, confidence):
    ordered = sorted(values)
    count = len(ordered)
    indices = [k for k in range(1, count // 2 + 1)
               if 2 * sum(math.comb(count, j) for j in range(k)) / 2 ** count <= 1 - confidence + 1e-12]
    if not indices:
        return None
    index = max(indices)
    return [ordered[index - 1], ordered[count - index]]


def paired_summary(pairs, metric, unit, confidence):
    before = [a[metric] for a, _ in pairs]
    after = [b[metric] for _, b in pairs]
    absolute = [b - a for a, b in zip(before, after)]
    values = absolute if unit == "absolute" else [100 * (b / a - 1) if a > 0 else None for a, b in zip(before, after)]
    available = bool(values) and all(value is not None for value in values)
    return {"pairs": len(pairs), "unit": unit, "baseline_values": before, "candidate_values": after,
            "absolute_deltas": absolute, "deltas": values,
            "median_delta": statistics.median(values) if available else None,
            "median_interval": median_interval(values, confidence) if available else None}


def decision(summary, limit, minimum_pairs, *, equivalence=False):
    interval = summary["median_interval"]
    if summary["pairs"] < minimum_pairs or interval is None:
        return "inconclusive"
    lower, upper = interval
    if equivalence:
        if lower >= -limit and upper <= limit:
            return "pass"
        if upper < -limit or lower > limit:
            return "fail"
    elif upper <= limit:
        return "pass"
    elif lower > limit:
        return "fail"
    return "inconclusive"


def duration_seconds(value):
    if finite(value):
        return float(value) / 1_000_000_000  # JFR JSON numeric durations use nanoseconds.
    match = re.fullmatch(r"PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?", str(value))
    if not match or not any(part is not None for part in match.groups()):
        raise ValueError("Invalid JFR ISO duration: " + str(value))
    return sum(float(part or 0) * multiplier for part, multiplier in zip(match.groups(), (3600, 60, 1)))


def percentile(values, quantile):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("No observations for percentile.")
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def jfr_metrics(events, window, coverage, tolerance, maximum_gap):
    """Count complete GC events; reject events/pauses straddling phase boundaries."""
    start, end = map(instant, (window["start"], window["end"]))
    errors, frames, collections, pauses = [], [], {}, []
    invalid_gc, invalid_pause = False, False
    try:
        covered_start, covered_end = map(instant, (coverage["start"], coverage["end"]))
        if covered_start > start + dt.timedelta(seconds=tolerance) or covered_end < end:
            errors.append("JFR does not cover the complete measurement window.")
        if coverage.get("readable") is not True:
            errors.append("JFR readability was not established.")
    except (KeyError, ValueError, TypeError):
        errors.append("Missing/invalid JFR coverage.")
    for event in events:
        kind, values = event.get("type"), event.get("values", {})
        try:
            stamp = instant(values["startTime"])
            duration = duration_seconds(values["duration"] if kind in ("jdk.GarbageCollection", "jdk.GCPhasePause") else values.get("duration", "PT0S"))
            finish = stamp + dt.timedelta(seconds=duration)
            if kind in ("jdk.GarbageCollection", "jdk.GCPhasePause") and ((stamp < start < finish) or (stamp < end < finish)):
                errors.append("GC event crosses a measurement boundary; window is incomplete.")
            if not start <= stamp <= end:
                continue
            if kind == "mtrtest.ClientFrame":
                if values.get("inWorld") is not True or values.get("paused") is not False or values.get("screen") != "game":
                    errors.append("Profile frame observed outside unpaused world.")
                interval = values.get("intervalMs")
                if not finite(interval, positive=True):
                    errors.append("Invalid frame interval.")
                else:
                    frames.append((stamp, float(interval)))
            elif kind == "jdk.GarbageCollection":
                identity = values["gcId"]
                if identity in collections:
                    errors.append("Duplicate GC identifier.")
                collections[identity] = values["name"]
            elif kind == "jdk.GCPhasePause":
                pauses.append((values["gcId"], duration * 1000))
        except (KeyError, ValueError, TypeError, OverflowError):
            errors.append("Invalid required JFR event: " + str(kind))
            invalid_gc = invalid_gc or kind == "jdk.GarbageCollection"
            invalid_pause = invalid_pause or kind == "jdk.GCPhasePause"
    if not frames:
        errors.append("No unpaused in-world frame events.")
    else:
        stamps = [start, *sorted(stamp for stamp, _ in frames), end]
        if any((b - a).total_seconds() > maximum_gap for a, b in zip(stamps, stamps[1:])):
            errors.append("Frame events do not continuously cover the measurement window.")
    if any(identity not in collections for identity, _ in pauses):
        errors.append("GC pause has no matching complete collection event.")
    # This protocol freezes UseG1GC. A G1 full collection is named G1Full by JDK 21.
    full_ids = {identity for identity, name in collections.items() if name == "G1Full"}
    missing_full_pauses = full_ids - {identity for identity, _ in pauses}
    if missing_full_pauses:
        errors.append("Full GC lacks a complete matching observed pause event.")
    values = [value for _, value in frames]
    pause_unavailable = bool(missing_full_pauses) or invalid_gc or invalid_pause
    metrics = {"frame_p99_ms": percentile(values, .99) if values else None,
               "frame_max_ms": max(values) if values else None,
               "gc_count": None if invalid_gc else len(collections), "gc_pause_total_ms": None if pause_unavailable else sum(value for _, value in pauses),
               "gc_pause_max_ms": None if pause_unavailable else max((value for _, value in pauses), default=0),
               "full_gc_count": None if invalid_gc else len(full_ids),
               "full_gc_pause_max_ms": None if pause_unavailable else max((value for identity, value in pauses if identity in full_ids), default=0)}
    return metrics, errors


def native_snapshot_errors(snapshot, process, stamp, freshness, scenario, *, require_scene=True):
    errors = []
    if snapshot.get("schema_version") != 1 or snapshot.get("probe_kind") != "official-native-observer":
        errors.append("Unrecognized neutral observer.")
    if snapshot.get("pid") != process["pid"]:
        errors.append("Neutral observer PID differs from actual process.")
    try:
        if abs((instant(snapshot["process_created"]) - instant(process["created"])).total_seconds()) > 1:
            errors.append("Neutral observer process creation identity differs.")
        age = (instant(stamp) - instant(snapshot["observed_at"])).total_seconds()
        if not -1 <= age <= freshness:
            errors.append("Neutral snapshot is stale or future dated.")
    except (KeyError, ValueError, TypeError, AttributeError):
        errors.append("Missing/invalid neutral process or observation time.")
    expected = scenario["expected_registration"]
    if snapshot.get("registered_count") != expected["distinct_ids"] or snapshot.get("registered_declarations") != expected["declarations"]:
        errors.append("Native registration differs from frozen pack catalogue.")
    epochs = snapshot.get("resource_epochs")
    if type(snapshot.get("native_pending")) is not int or snapshot.get("native_pending") != 0 or snapshot.get("native_settled") is not True or not isinstance(epochs, dict) or type(epochs.get("in_flight")) is not int or epochs.get("in_flight") != 0:
        errors.append("Native resource work is not settled.")
    if snapshot.get("observation_errors") != 0:
        errors.append("Independent observer reported observation errors.")
    capabilities = snapshot.get("capabilities")
    if not isinstance(capabilities, dict) or any(capabilities.get(field) is not True for field in ("native_pending", "registration_counts", "native_epochs", "heap", "world", "train_state", "cache_state")):
        errors.append("Required independent native capabilities are unavailable.")
    heap = snapshot.get("heap")
    if not isinstance(heap, dict) or not finite(heap.get("used_bytes")) or not finite(heap.get("max_bytes"), positive=True) or heap.get("used_bytes", math.inf) > heap.get("max_bytes", -1):
        errors.append("Invalid independent heap observation.")
    if not require_scene:
        return errors
    observation = scenario["observation"]
    if observation["require_world"] and snapshot.get("in_world") is not True:
        errors.append("Client is outside frozen world.")
    if observation["require_unpaused"] and snapshot.get("paused") is not False:
        errors.append("Client is paused.")
    if snapshot.get("screen") is not None:
        errors.append("Client screen differs from the frozen unobstructed game camera.")
    world, camera = snapshot.get("world"), scenario["camera"]
    if not isinstance(world, dict) or world.get("dimension") != camera["dimension"] or not isinstance(world.get("player"), dict):
        errors.append("Observed world dimension/player differs from frozen camera.")
    else:
        player = world["player"]
        try:
            distance = math.sqrt(sum((player[axis] - camera["player"][axis]) ** 2 for axis in ("x", "y", "z")))
            angle = max(abs((player[axis] - camera["player"][axis] + 180) % 360 - 180) for axis in ("yaw", "pitch"))
            if not math.isfinite(distance) or not math.isfinite(angle) or distance > camera["maximum_position_error"] or angle > camera["maximum_angle_error"]:
                errors.append("Observed camera pose exceeds frozen tolerances.")
        except (KeyError, TypeError, ValueError, OverflowError):
            errors.append("Observed camera pose is unavailable.")
    if observation["require_train"]:
        train_state = snapshot.get("train_state")
        vehicles = train_state.get("vehicles", []) if isinstance(train_state, dict) else []
        if not isinstance(train_state, dict) or train_state.get("available") is not True or not vehicles:
            errors.append("Required native train state is unavailable.")
        elif not any(vehicle.get("route_id") in scenario["route"]["route_ids"] and
                     (not scenario["route"]["vehicle_ids"] or vehicle.get("id") in scenario["route"]["vehicle_ids"]) for vehicle in vehicles):
            errors.append("No actual train matches the frozen route/vehicle identities.")
    return errors


def assess_observation(evidence, policy, scenario, instrumentation):
    """Recompute phase metrics from preserved neutral snapshots and OS samples."""
    errors, metrics = [], {metric: None for metric in METRICS}
    errors.extend(execution_window_errors(evidence, evidence.get("run_start", {}).get("trial_spec")))
    diagnostics = evidence.get("client_diagnostics")
    if evidence.get("client_log_completeness", {}).get("passed") is not True:
        errors.append("Complete startup-to-observation client log was not established.")
    if not isinstance(diagnostics, dict) or diagnostics.get("scanned") is not True or not isinstance(diagnostics.get("unreviewed_native"), list) or not isinstance(diagnostics.get("other_errors_requiring_contextual_review"), list):
        errors.append("Complete native/client log diagnostic scan is unavailable.")
    elif diagnostics["unreviewed_native"]:
        errors.append("Unreviewed native/client diagnostics require attribution before qualification.")
    try:
        process = evidence["process"]
        created = instant(process["created"])
        windows = evidence["windows"]
        native_end = instant(windows["startup"]["end"])
        warm_start, warm_end = map(instant, (windows["warmup"]["start"], windows["warmup"]["end"]))
        start, end = map(instant, (windows["steady"]["start"], windows["steady"]["end"]))
        completed_at = instant(evidence["measurement_completed_at"])
        if not end <= completed_at <= end + dt.timedelta(seconds=policy["maximum_sample_gap_seconds"]) or evidence.get("measurement_process_running") is not True:
            errors.append("Actual owned JVM measurement endpoint was not completed/confirmed.")
        if not created < native_end <= warm_start < warm_end == start < end:
            errors.append("Invalid startup/warmup/steady ordering.")
        if abs((warm_end - warm_start).total_seconds() - policy["warmup_seconds"]) > .05 or abs((end - start).total_seconds() - policy["measurement_seconds"]) > .05:
            errors.append("Phase durations differ from frozen policy.")
        if (warm_start - created).total_seconds() > policy["startup_timeout_seconds"]:
            errors.append("Native startup exceeds timeout.")
        if type(process["pid"]) is not int or process["pid"] <= 0:
            errors.append("Invalid process identifier.")
    except (KeyError, ValueError, TypeError, AttributeError):
        return {"passed": False, "errors": ["Missing/invalid process or phase windows."], "metrics": metrics}
    epochs = evidence.get("epochs", [])
    initial = []
    for event in epochs:
        if event.get("pid") != process["pid"]:
            errors.append("Native epoch belongs to another process.")
            continue
        try:
            if abs((instant(event["process_created"]) - created).total_seconds()) > 1:
                errors.append("Native epoch process creation identity differs.")
            stamp = instant(event["timestamp"])
            if created <= stamp <= native_end:
                initial.append(event)
            elif native_end < stamp <= end:
                errors.append("Unexpected native reload during frozen measurement.")
        except (KeyError, TypeError, ValueError, AttributeError):
            errors.append("Invalid native epoch timestamp.")
    starts = [event for event in initial if event.get("phase") == "start"]
    returns = [event for event in initial if event.get("phase") == "return"]
    if not starts or len(starts) != len(returns) or len({event.get("sequence") for event in starts}) != len(starts):
        errors.append("Initial native HEAD/RETURN evidence is missing or ambiguous.")
    else:
        for head in starts:
            tail = [event for event in returns if event.get("sequence") == head.get("sequence")]
            if len(tail) != 1 or instant(head["timestamp"]) > instant(tail[0]["timestamp"]):
                errors.append("Unpaired/out-of-order native epoch.")
    samples = evidence.get("samples", [])
    stamps, postload, steady, startup = [], [], [], []
    previous = None
    snapshots_seen = set()
    for sample in samples:
        try:
            stamp = instant(sample["observed_at"])
            if previous is not None and stamp <= previous:
                errors.append("Sample timestamps do not strictly advance.")
            previous = stamp
            if not created <= stamp <= end:
                errors.append("Sample falls outside the frozen observation window.")
            os_state = sample.get("os", {})
            if os_state.get("running") is not True:
                errors.append("Actual JVM was unavailable during observation.")
            for field in ("private_usage", "working_set", "peak_working_set_since_process_start"):
                if not finite(os_state.get(field), positive=True):
                    errors.append("Unavailable/invalid OS memory: " + field)
            snapshot = sample.get("native")
            if stamp <= native_end:
                startup.append(sample)
            if warm_start <= stamp <= end:
                postload.append(sample)
                errors.extend(sample.get("errors", []))
                if sample.get("client_log_witness") is None:
                    errors.append("Postload client log prefix observation is unavailable.")
                if not isinstance(snapshot, dict):
                    errors.append("Missing postload neutral snapshot.")
                else:
                    errors.extend(native_snapshot_errors(snapshot, process, sample["observed_at"], policy["snapshot_freshness_seconds"], scenario))
                    identity = snapshot.get("observed_at")
                    if identity in snapshots_seen:
                        errors.append("Postload neutral snapshot did not advance.")
                    snapshots_seen.add(identity)
            if start <= stamp <= end:
                stamps.append(stamp)
                steady.append(sample)
        except (KeyError, ValueError, TypeError, AttributeError):
            errors.append("Malformed observation sample.")
    for left, right in ((warm_start, start), (start, end)):
        phase_stamps = [left, *[instant(sample["observed_at"]) for sample in postload if left <= instant(sample["observed_at"]) <= right], right]
        if len(phase_stamps) < 3 or any((b - a).total_seconds() > policy["maximum_sample_gap_seconds"] for a, b in zip(phase_stamps, phase_stamps[1:])):
            errors.append("Incomplete postload phase sampling coverage.")
    if not startup or not steady:
        errors.append("Startup or steady phase lacks actual samples.")
    else:
        # The startup anchor is the first settled snapshot following native RETURN.
        at_anchor = [sample for sample in samples if instant(sample["observed_at"]) == native_end]
        if not at_anchor or not isinstance(at_anchor[0].get("native"), dict):
            errors.append("Native completion anchor has no actual settled snapshot.")
        elif native_snapshot_errors(at_anchor[0]["native"], process, at_anchor[0]["observed_at"], policy["snapshot_freshness_seconds"], scenario, require_scene=False):
            errors.append("Native completion anchor is not qualified.")
        elif returns and instant(at_anchor[0]["native"]["observed_at"]) < max(instant(event["timestamp"]) for event in returns):
            errors.append("Settled snapshot precedes native RETURN.")
        try:
            metrics.update(loading_ms=(native_end - created).total_seconds() * 1000,
                startup_peak_working_set_bytes=max(s["os"]["peak_working_set_since_process_start"] for s in startup),
                startup_peak_heap_bytes=max(s["native"]["heap"]["used_bytes"] for s in startup if isinstance(s.get("native"), dict)),
                steady_private_bytes=statistics.median(s["os"]["private_usage"] for s in steady),
                steady_working_set_bytes=statistics.median(s["os"]["working_set"] for s in steady),
                steady_heap_bytes=statistics.median(s["native"]["heap"]["used_bytes"] for s in steady))
        except (KeyError, ValueError, TypeError):
            errors.append("Required phase metrics are unavailable.")
    minimum_motion = scenario["observation"]["minimum_train_displacement"]
    if minimum_motion > 0:
        progresses = {}
        for sample in steady:
            snapshot = sample.get("native") or {}
            state = snapshot.get("train_state") or {}
            for vehicle in state.get("vehicles", []):
                value = vehicle.get("rail_progress")
                if vehicle.get("route_id") in scenario["route"]["route_ids"] and (not scenario["route"]["vehicle_ids"] or vehicle.get("id") in scenario["route"]["vehicle_ids"]) and finite(value):
                    progresses.setdefault(vehicle.get("id"), []).append(value)
        if not any(len(values) >= 2 and max(values) - min(values) >= minimum_motion for values in progresses.values()):
            errors.append("Actual route train displacement is below the frozen minimum.")
    if instrumentation == "profile":
        profile, profile_errors = jfr_metrics(evidence.get("jfr_events", []), windows["steady"], evidence.get("jfr_coverage", {}),
                                               policy["jfr_boundary_tolerance_seconds"], policy["maximum_sample_gap_seconds"])
        metrics.update(profile)
        errors.extend(profile_errors)
        try:
            if instant(evidence["jfr_coverage"]["start"]) > created + dt.timedelta(seconds=policy["jfr_boundary_tolerance_seconds"]):
                errors.append("JFR omits process startup.")
        except (KeyError, ValueError, TypeError, AttributeError):
            errors.append("Missing startup JFR coverage.")
    elif evidence.get("jfr_events") or evidence.get("jfr_coverage"):
        errors.append("Plain trial unexpectedly contains JFR instrumentation.")
    required = COMMON_METRICS | (PROFILE_METRICS if instrumentation == "profile" else set())
    if any(not finite(metrics[metric]) for metric in required):
        errors.append("Required endpoint metric is unavailable.")
    if evidence.get("status") != "complete" or evidence.get("cleanup", {}).get("exited") is not True:
        errors.append("Observation or owned-process cleanup is incomplete.")
    return {"passed": not errors, "errors": errors, "metrics": metrics,
            "unavailable_metrics": sorted(metric for metric, value in metrics.items() if value is None),
            "phases": windows, "sample_count": len(samples),
            "loading_anchor": evidence.get("loading_anchor"),
            "client_diagnostics": diagnostics,
            "client_log_completeness": evidence.get("client_log_completeness"),
            "loading_resolution": "First captured settled snapshot; native sample time and external capture delay remain explicit, not a continuous native completion measurement."}


def analyze(plan, execution):
    policy = plan["policy"]
    validate_policy(policy)
    expected = schedule(policy)
    errors = []
    if plan.get("schedule") != expected:
        errors.append("Frozen schedule differs from the declared counterbalanced design.")
    actual = execution.get("trials", [])
    if [trial.get("id") for trial in actual] != [spec["id"] for spec in expected]:
        errors.append("Recorded trial order/completeness differs from frozen schedule.")
    indexed, passed = {}, 0
    previous_raw_finish = None
    process_ids = set()
    qualifier_ids = set()
    try:
        if set(plan["qualification_processes"]) != {role + "_" + mode for role in ROLES for mode in MODES}:
            raise ValueError("Missing current qualification process identities.")
        qualifier_ids = {process_key(value) for value in plan["qualification_processes"].values()}
        if len(qualifier_ids) != 4:
            errors.append("The four qualification groups did not use distinct actual JVMs.")
    except (KeyError, ValueError, TypeError, AttributeError):
        errors.append("Current qualification actual process identities are unavailable.")
    for trial in actual:
        identity = trial.get("id")
        if identity in indexed:
            errors.append("Duplicate trial identity: " + str(identity))
        indexed[identity] = trial
    for spec in expected:
        trial = indexed.get(spec["id"])
        if trial is None:
            errors.append("Missing trial: " + spec["id"])
            continue
        for field, value in spec.items():
            if trial.get(field) != value:
                errors.append("Changed trial treatment/control: " + spec["id"])
        evidence = trial.get("evidence", {})
        process = evidence.get("process", {})
        try:
            identity = process_key(process)
        except (ValueError, KeyError, TypeError, AttributeError):
            identity = None
        if identity is None or identity in process_ids:
            errors.append("Trials do not have distinct actual JVM creation identities: " + spec["id"])
        if identity in qualifier_ids:
            errors.append("Qualification JVM reused as a scheduled performance replicate: " + spec["id"])
        process_ids.add(identity)
        errors.extend(execution_window_errors(evidence, spec, execution.get("started_at")))
        try:
            raw_start = instant(evidence["run_start"]["started_at"])
            raw_finish = instant(evidence["run_finish"]["finished_at"])
            if not instant(execution["started_at"]) <= instant(trial["started_at"]) <= raw_start <= raw_finish <= instant(trial["finished_at"]) <= instant(execution["finished_at"]):
                errors.append("Trial/execution summaries do not contain the raw actual execution window: " + spec["id"])
            if previous_raw_finish is not None and raw_start < previous_raw_finish:
                errors.append("Actual trial windows overlap or run outside the frozen order: " + spec["id"])
            previous_raw_finish = max(previous_raw_finish, raw_finish) if previous_raw_finish is not None else raw_finish
        except (KeyError, ValueError, TypeError, AttributeError):
            errors.append("Actual trial chronology is unavailable: " + spec["id"])
        key = spec["role"] + "_" + spec["instrumentation"]
        if trial.get("qualification_key") != plan["prepared"][key]["qualification_key"]:
            errors.append("Trial artifact/control/probe qualification differs: " + spec["id"])
        result = assess_observation(evidence, policy, plan["scenario"], spec["instrumentation"])
        trial["recomputed_result"] = result
        if trial.get("status") != "complete" or not result["passed"]:
            errors.append("Failed/unqualified trial: " + spec["id"])
        else:
            passed += 1
    denominator = {"scheduled_trials": len(expected), "recorded_trials": len(actual),
                   "passed_trials": passed, "failed_or_missing_trials": len(expected) - passed,
                   "scheduled_pairs_per_stratum": policy["pairs"]}
    if execution.get("status") != "complete":
        errors.append("Experiment did not complete.")
    if errors:
        return {"status": "invalid", "performance_accepted": False, "errors": errors, "failure_denominator": denominator}
    summaries, gates = {}, {}

    def pairs(comparison, mode):
        result = []
        for pair in range(1, policy["pairs"] + 1):
            arms = {spec["arm"]: indexed[spec["id"]]["recomputed_result"]["metrics"] for spec in expected
                    if spec["pair"] == pair and spec["comparison"] == comparison and spec["instrumentation"] == mode}
            result.append((arms["a"], arms["b"]))
        return result

    def add(name, data, endpoint, equivalence):
        summary = paired_summary(data, endpoint["metric"], endpoint["unit"], policy["confidence"])
        summaries[name] = summary
        gates[name] = decision(summary, endpoint["limit"], policy["minimum_pairs"], equivalence=equivalence)

    for endpoint in policy["aa_equivalence"]:
        name = "aa_" + endpoint["instrumentation"] + "_" + endpoint["metric"]
        add(name, pairs("aa", endpoint["instrumentation"]), endpoint, True)
    for label, endpoints in (("primary", [policy["primary"]]), ("guardrail", policy["guardrails"])):
        for endpoint in endpoints:
            add(label + "_" + endpoint["instrumentation"] + "_" + endpoint["metric"], pairs("ab", endpoint["instrumentation"]), endpoint, False)
    for role, arm in (("baseline", "a"), ("candidate", "b")):
        data = []
        for pair in range(1, policy["pairs"] + 1):
            modes = {spec["instrumentation"]: indexed[spec["id"]]["recomputed_result"]["metrics"] for spec in expected
                     if spec["comparison"] == "ab" and spec["pair"] == pair and spec["arm"] == arm}
            data.append((modes["plain"], modes["profile"]))
        for endpoint in policy["instrumentation_equivalence"]:
            add("instrumentation_" + role + "_" + endpoint["metric"], data, endpoint, True)
    status = "fail" if "fail" in gates.values() else "pass" if set(gates.values()) == {"pass"} else "inconclusive"
    return {"status": "inconclusive" if status == "pass" else status, "performance_accepted": False,
            "instrumented_comparison_status": status, "instrumented_performance_accepted": status == "pass",
            "pending_gates": ["neutral_probe_off_calibration"], "gates": gates,
            "paired_summaries": summaries, "failure_denominator": denominator, "confidence": policy["confidence"],
            "method": "Exact binomial sign-test inversion for paired median deltas; predeclared pointwise intervals. No exclusions or extra sample replicates.",
            "limits": ["A/A and instrumentation must establish equivalence within frozen budgets.",
                       "Fresh JVM/world copies use uncontrolled warm OS file cache; this is not a cold-disk claim.",
                       "Native/heap/OS/JFR observations do not establish geometry, doors or boarding correctness.",
                       "Neutral observation runs in both modes; instrumentation comparison measures added JFR and GC logging.",
                       "Neutral observer allocation and native registry/cache traversal overhead remains uncalibrated; no uninstrumented-client performance acceptance.",
                       "Host drift/correlation can remain despite seeded counterbalancing."]}
