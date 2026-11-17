"""Synthetic diagnostic controls extracted from the historical regression suite."""
import copy
import datetime as dt
import json

import client_experiment_analysis as analysis
import native_diagnostic_review as review_tool
from minecraft_testkit import ROOT


def fixture(process=None, epochs=None):
    review = json.loads((ROOT / "config/native-diagnostic-review.json").read_text(encoding="utf-8"))
    process = copy.deepcopy(process or {"pid": 111, "created": "2026-11-15T00:00:00+00:00"})
    created = review_tool.instant(process["created"])
    stamp = lambda value: (created + dt.timedelta(seconds=value)).isoformat()
    epochs = copy.deepcopy(epochs or [{"pid": process["pid"], "process_created": process["created"], "sequence": 1,
                                      "phase": phase, "timestamp": stamp(value)} for phase, value in (("start", .5), ("return", 1.5))])
    for event in epochs:
        event.update(thread_id=1, thread="Render thread", render_thread=True, nesting=1)
        event["monotonic_nanos"] = int((review_tool.instant(event["timestamp"]) - created).total_seconds() * 1e9)
    metadata = {**review["target"], "schema_version": 1, "target": "official-nf248", "variant": "official",
                "probe_kind": "official-native-observer", "observer_version": "1.0.2", "neoForge": "21.1.248",
                "diagnostics_schema": 1, "diagnostics_path": "game-probe/native-invalid-model.jsonl",
                "snapshot_path": "game-probe/native-observer.json", "epochs_path": "game-probe/native-resource-epochs.jsonl"}
    stack = [{**frame, "line": index + 1, "bytecode_index": 100 + index} for index, frame in enumerate(review["contract"]["native_call_chain"])]
    events = []
    for index, (phase, seconds) in enumerate((("installed", .2), ("before_native_invalid_log", .8), ("native_fallback_return", 1)), 1):
        events.append({"schema_version": 1, "probe_kind": "official-native-observer", "sequence": index,
                       "phase": phase, "target": metadata, "pid": process["pid"], "process_created": process["created"],
                       "timestamp": stamp(seconds), "monotonic_nanos": int(seconds * 1e9), "observation_errors": 0,
                       "call_id": None if index == 1 else 1, "epoch_id": None if index == 1 else 1,
                       "thread_id": 1, "thread": "Render thread", "render_thread": True,
                       "native_factory_nesting": 1, "native_reload_nesting": 1,
                       "model_resource": "", "texture_resource": "", "flip_texture_v": False,
                       "returned_loader_class": "org.mtr.model.BlockbenchModelLoader" if index == 3 else None,
                       "stack": copy.deepcopy(stack)})
    window = {"start": process["created"], "end": stamp(11)}
    snapshot = {"pid": process["pid"], "process_created": process["created"], "observed_at": stamp(10), "observation_errors": 0,
                "native_model_diagnostics": {"started": 1, "completed": 1, "in_flight": 0, "observation_errors": 0}}
    log = "[15Nov2026 00:00:00.800] [Render thread/ERROR] [MinecraftTransitRailway/]: [mtr:textures/block/transparent.png] Invalid model!\n"
    return {"review": review, "metadata": metadata, "events": events, "epochs": epochs, "process": process,
            "window": window, "snapshot": snapshot, "log": log}


def evaluate(case):
    return review_tool.review_diagnostics(analysis.native_diagnostics(case["log"]), case["log"], case["events"], case["epochs"],
        case["process"], case["metadata"], case["review"], case["window"], case["snapshot"])
