"""Validate live native diagnostic attribution while retaining every raw error.

Only the reviewed official generated default-rail fallback is classified. This
does not establish rendering, interaction correctness or zero performance cost.
"""
import copy
import datetime as dt
import hashlib
from pathlib import Path
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def instant(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "Diagnostic timestamps require a UTC offset.")
    return result.astimezone(dt.timezone.utc)


def positive_int(value):
    return type(value) is int and value > 0


def validate_review(review, metadata, *, root=None):
    require(review.get("schema") == 1 and review.get("id") == "official-generated-default-rail",
            "Unsupported native diagnostic review.")
    require(type(metadata.get("diagnostics_schema")) is int and metadata["diagnostics_schema"] == 1
            and metadata.get("diagnostics_path") == "game-probe/native-invalid-model.jsonl",
            "Observer lacks the supported live diagnostic contract.")
    require(metadata.get("probe_kind") == "official-native-observer" and metadata.get("variant") == "official",
            "Diagnostic review requires the independent official observer.")
    for field in ("mtrSha256", "mtrVersion", "minecraft"):
        require(review["target"][field] == metadata[field], "Diagnostic review target differs: " + field)
    contract = review["contract"]
    require(contract["model_resource"] == contract["texture_resource"] == "" and contract["flip_texture_v"] is False
            and type(contract["calls_per_completed_epoch"]) is int and contract["calls_per_completed_epoch"] == 1,
            "Review may only classify the observed empty default-rail construction.")
    require(contract["native_call_chain"] == [
        {"class": "org.mtr.resource.VehicleModel", "method": "getModelLoaderBase", "descriptor": "(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;Z)Lorg/mtr/model/ModelLoaderBase;"},
        {"class": "org.mtr.resource.RailResource", "method": "<init>", "descriptor": "(Ljava/lang/String;Ljava/lang/String;Lorg/mtr/resource/ResourceProvider;)V"},
        {"class": "org.mtr.client.CustomResourceLoader", "method": "reload", "descriptor": "()V"}],
        "Review does not identify the exact native default-rail call chain.")
    require(contract["returned_loader_class"] == "org.mtr.model.BlockbenchModelLoader",
            "Review changes the observed native fallback type.")
    require(contract["logger"] == "MinecraftTransitRailway"
            and contract["log_template"] == "[{}] Invalid model!"
            and contract["texture_identifier"] == "mtr:textures/block/transparent.png",
            "Review changes the pinned official native diagnostic.")
    require(review.get("proofs") and isinstance(review["proofs"], list), "Native review lacks source/runtime proof fingerprints.")
    if root is not None:
        root = Path(root).resolve(strict=True)
        for proof in review["proofs"]:
            path = (root / proof["path"]).resolve(strict=True)
            require(root in path.parents and path.is_file(), "Diagnostic proof escapes its repository.")
            require(hashlib.sha256(path.read_bytes()).hexdigest() == proof["sha256"], "Native diagnostic proof changed: " + proof["path"])
    return contract


def native_chain(event):
    frames = event["stack"]
    require(isinstance(frames, list), "Diagnostic stack is unavailable.")
    factory = next((index for index, frame in enumerate(frames)
                    if frame.get("class") == "org.mtr.resource.VehicleModel" and frame.get("method") == "getModelLoaderBase"), None)
    require(factory is not None, "Diagnostic stack lacks its native factory.")
    chain = frames[factory:factory + 3]
    require(len(chain) == 3, "Diagnostic native call chain is incomplete.")
    require(all(type(frame.get("bytecode_index")) is int and frame["bytecode_index"] >= 0 for frame in chain),
            "Diagnostic native callsite indices are unavailable.")
    return chain


def review_diagnostics(raw_diagnostics, log_text, events, epochs, process, metadata, review, window, final_snapshot):
    """Return raw diagnostics plus fail-closed, per-run reviewed classification."""
    result = copy.deepcopy(raw_diagnostics)
    result["reviewed_native"] = []
    assessment = {"passed": False, "review_id": review.get("id"), "errors": [], "calls": [],
                  "scope": "Live known official-default diagnostic attribution; rendering and performance impact remain separate"}
    result["native_attribution"] = assessment
    try:
        contract = validate_review(review, metadata)
        created = instant(process["created"])
        start, finish = instant(window["start"]), instant(window["end"])
        require(start <= created <= finish, "Diagnostic run window excludes its actual JVM.")
        require(positive_int(process["pid"]), "Diagnostic actual JVM PID is invalid.")
        epoch_pairs = {}
        for row in epochs:
            require(row["pid"] == process["pid"] and abs((instant(row["process_created"]) - created).total_seconds()) <= 1,
                    "Native diagnostic epoch belongs to another JVM.")
            identity = row["sequence"]
            require(positive_int(identity) and row["phase"] in ("start", "return"), "Invalid native epoch identity/phase.")
            pair = epoch_pairs.setdefault(identity, {})
            require(row["phase"] not in pair, "Duplicate native epoch phase.")
            pair[row["phase"]] = row
        require(epoch_pairs and all(set(pair) == {"start", "return"} for pair in epoch_pairs.values()),
                "Live attribution requires complete paired native epochs.")
        for pair in epoch_pairs.values():
            head, tail = pair["start"], pair["return"]
            require(start <= instant(head["timestamp"]) <= instant(tail["timestamp"]) <= finish,
                    "Native diagnostic epoch falls outside the actual run.")
            require(type(head["monotonic_nanos"]) is int and type(tail["monotonic_nanos"]) is int
                    and head["monotonic_nanos"] <= tail["monotonic_nanos"], "Native diagnostic epoch monotonic time is invalid.")
            require(positive_int(head["thread_id"]) and head["thread_id"] == tail["thread_id"]
                    and head["thread"] == tail["thread"] and head["render_thread"] is tail["render_thread"] is True,
                    "Native diagnostic epoch thread identity differs.")
        require(events and events[0]["phase"] == "installed", "Missing native diagnostic installation receipt.")
        require(sum(row["phase"] == "installed" for row in events) == 1, "Diagnostic installation receipt is duplicated.")
        previous_nanos, previous_time = None, None
        pending, completed, epoch_counts = {}, set(), dict.fromkeys(epoch_pairs, 0)
        calls = []
        native_created = None
        for sequence, row in enumerate(events, 1):
            require(type(row["schema_version"]) is int and row["schema_version"] == 1 and row["probe_kind"] == "official-native-observer"
                    and positive_int(row["sequence"]) and row["sequence"] == sequence, "Diagnostic schema/sequence is invalid, missing or reordered.")
            require(row["pid"] == process["pid"] and abs((instant(row["process_created"]) - created).total_seconds()) <= 1,
                    "Diagnostic event belongs to another actual JVM.")
            if native_created is None:
                native_created = instant(row["process_created"])
            require(instant(row["process_created"]) == native_created, "Diagnostic native process identity changed.")
            require(row["target"] == metadata, "Diagnostic event metadata differs from the frozen observer.")
            require(type(row["observation_errors"]) is int and row["observation_errors"] == 0, "Native diagnostic observation failed.")
            moment, nanos = instant(row["timestamp"]), row["monotonic_nanos"]
            require(type(nanos) is int and start <= created <= moment <= finish, "Diagnostic event time lies outside its run.")
            require((previous_nanos is None or nanos >= previous_nanos) and (previous_time is None or moment >= previous_time),
                    "Diagnostic time order regressed.")
            previous_nanos, previous_time = nanos, moment
            if row["phase"] == "installed":
                continue
            identity, epoch_id = row["call_id"], row["epoch_id"]
            require(positive_int(identity) and positive_int(epoch_id) and epoch_id in epoch_pairs, "Diagnostic call has no observed native epoch.")
            head, tail = epoch_pairs[epoch_id]["start"], epoch_pairs[epoch_id]["return"]
            require(instant(head["timestamp"]) <= moment <= instant(tail["timestamp"]), "Diagnostic event falls outside its native epoch.")
            require(head["monotonic_nanos"] <= nanos <= tail["monotonic_nanos"], "Diagnostic monotonic time falls outside its native epoch.")
            require(positive_int(row["thread_id"]) and row["thread_id"] == head["thread_id"] and row["thread"] == head["thread"] and row["render_thread"] is True,
                    "Diagnostic call does not run on its native epoch thread.")
            require(positive_int(row["native_factory_nesting"]) and positive_int(row["native_reload_nesting"])
                    and row["native_reload_nesting"] == head["nesting"], "Diagnostic native invocation depth differs from its epoch.")
            require(all(row[field] == contract[field] for field in ("model_resource", "texture_resource", "flip_texture_v"))
                    and type(row["flip_texture_v"]) is bool, "Diagnostic native factory arguments are not the reviewed empty defaults.")
            chain = native_chain(row)
            require([{key: frame[key] for key in ("class", "method", "descriptor")} for frame in chain] == contract["native_call_chain"],
                    "Diagnostic callsite is not the reviewed native default-rail chain.")
            if row["phase"] == "before_native_invalid_log":
                require(identity not in pending and identity not in completed, "Diagnostic call identity is duplicated.")
                require(not any(event["thread_id"] == row["thread_id"] for event in pending.values()), "An earlier diagnostic call on this thread is still pending.")
                pending[identity] = row
            elif row["phase"] == "native_fallback_return":
                require(identity in pending, "Diagnostic return has no matching native log call.")
                before = pending.pop(identity)
                require(all(row[field] == before[field] for field in ("epoch_id", "thread_id", "thread", "model_resource", "texture_resource", "flip_texture_v", "native_factory_nesting", "native_reload_nesting"))
                        and chain[1:] == native_chain(before)[1:],
                        "Diagnostic return belongs to another native invocation.")
                require(row["returned_loader_class"] == contract["returned_loader_class"], "Native fallback returned another loader.")
                completed.add(identity)
                epoch_counts[epoch_id] += 1
                calls.append({"call_id": identity, "epoch_id": epoch_id, "before_sequence": before["sequence"], "return_sequence": sequence,
                              "thread_id": row["thread_id"], "thread": row["thread"], "started_at": before["timestamp"], "returned_at": row["timestamp"],
                              "native_call_chain": chain, "model_resource": row["model_resource"], "texture_resource": row["texture_resource"],
                              "returned_loader_class": row["returned_loader_class"]})
            else:
                raise ValueError("Unknown native diagnostic event phase.")
        require(not pending, "A native invalid-model call has no observed fallback return.")
        require(all(count == contract["calls_per_completed_epoch"] for count in epoch_counts.values()),
                "Native default diagnostic count differs from the reviewed count per completed epoch.")
        require(final_snapshot["pid"] == process["pid"] and instant(final_snapshot["process_created"]) == native_created
                and previous_time <= instant(final_snapshot["observed_at"]) <= finish,
                "Final native diagnostic snapshot is stale or belongs to another JVM.")
        counters = final_snapshot["native_model_diagnostics"]
        require(all(type(counters.get(field)) is int for field in ("started", "completed", "in_flight", "observation_errors"))
                and counters["started"] == counters["completed"] == len(calls)
                and type(final_snapshot["observation_errors"]) is int
                and counters["in_flight"] == counters["observation_errors"] == final_snapshot["observation_errors"] == 0,
                "Final native diagnostic counters show missing, pending or failed observations.")
        message = contract["log_template"].format(contract["texture_identifier"])
        pattern = re.compile(r"^\[[^\]\r\n]+\]\s+\[(?P<thread>[^\]\r\n]+)/ERROR\]\s+\[" + re.escape(contract["logger"]) + r"/\]:\s+" + re.escape(message) + r"\s*$")
        all_invalid = [row for row in raw_diagnostics["unreviewed_native"] if "Invalid model" in row["text"]]
        require(len(all_invalid) == len(calls), "Raw native invalid-model count differs from the complete live trace.")
        for call, log in zip(calls, all_invalid):
            matched = pattern.fullmatch(log["text"])
            require(matched is not None and matched.group("thread") == call["thread"], "Raw native diagnostic logger/message/thread differs from its live call.")
            require(log_text.splitlines()[log["line"] - 1] == log["text"], "Diagnostic line differs from the full raw log.")
            call["log"] = log
        lines = {call["log"]["line"] for call in calls}
        require(len(lines) == len(calls), "Native diagnostic log line was reused.")
        result["reviewed_native"] = [{**call["log"], "classification": "official_generated_default_rail", "call_id": call["call_id"], "epoch_id": call["epoch_id"]} for call in calls]
        result["unreviewed_native"] = [row for row in raw_diagnostics["unreviewed_native"] if row["line"] not in lines]
        assessment.update(passed=True, calls=calls, captured_events=len(events), completed_epochs=len(epoch_pairs))
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as error:
        assessment["errors"].append(type(error).__name__ + ": " + str(error))
    return result
