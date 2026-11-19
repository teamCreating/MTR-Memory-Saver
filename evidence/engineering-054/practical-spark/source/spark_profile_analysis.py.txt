"""Analyze locally exported spark protobuf data without inventing CPU/frame time.

Input comes from SparkProfileExport.java using the audited spark JAR's own
generated decoder. Flat child references and the explicit timeWindows ordering
are authoritative. Sample weights include waiting states unless the capture
explicitly excluded them; percentages are not measured process CPU durations.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path


def require(value, message):
    if not value:
        raise ValueError(message)


def weights(values, size):
    require(isinstance(values, list) and len(values) == size, "Sample weights do not align with explicit timeWindows")
    require(all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in values), "Invalid sample weight")
    return values


def references(values, size):
    require(isinstance(values, list) and len(set(values)) == len(values), "Duplicate child references")
    require(all(type(x) is int and 0 <= x < size for x in values), "Child reference outside flat node pool")
    return values


def analyze(data, thread_name, top=15):
    require(type(top) is int and 1 <= top <= 100, "Invalid ranking bound")
    metadata = data["metadata"]
    require(metadata["samplerMode"]["name"] == "EXECUTION", "Allocation/other profiles need their own metric interpretation")
    interval = metadata["interval"]
    require(type(interval) is int and interval > 0, "Missing execution interval in microseconds")
    start, end = metadata["startTime"], metadata["endTime"]
    require(type(start) is int and type(end) is int and 0 < start < end, "Invalid profile metadata time bounds")
    windows = data["timeWindows"]
    require(windows and all(type(x) is int for x in windows) and len(set(windows)) == len(windows), "Invalid explicit time windows")
    selected = [thread for thread in data["threads"] if thread["name"] == thread_name]
    require(len(selected) == 1, "Requested thread must match exactly once; no fallback thread is selected")
    thread = selected[0]
    nodes = thread["children"]
    require(nodes, "Requested thread has no stack samples")
    roots = references(thread["childrenRefs"], len(nodes))
    require(roots, "Requested thread has no explicit roots")
    weights(thread["times"], len(windows))
    children, parent = [], {}
    for index, node in enumerate(nodes):
        weights(node["times"], len(windows))
        refs = references(node["childrenRefs"], len(nodes))
        children.append(refs)
        for child in refs:
            require(child not in parent, "Flat sample node has multiple parents")
            parent[child] = index
    require(not any(root in parent for root in roots), "Root sample has a parent/cycle")
    visited = set()
    pending = list(roots)
    while pending:
        index = pending.pop()
        require(index not in visited, "Cycle/shared sample node in flat tree")
        visited.add(index)
        pending.extend(children[index])
    require(len(visited) == len(nodes), "Orphan sample nodes are not silently ignored")
    root_by_window = [sum(nodes[root]["times"][window] for root in roots) for window in range(len(windows))]
    require(all(math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6) for a, b in zip(root_by_window, thread["times"])),
            "Root and thread sample weights disagree")
    total = sum(root_by_window)
    require(total > 0, "Requested thread has zero sample weight")
    results = []
    negative_residuals = []
    source_totals = Counter()
    for index, node in enumerate(nodes):
        inclusive = sum(node["times"])
        residuals = [node["times"][window] - sum(nodes[child]["times"][window] for child in children[index])
                     for window in range(len(windows))]
        for window, value in enumerate(residuals):
            if value < -1e-6:
                negative_residuals.append({"node": index, "window": windows[window], "residual": value})
        own = sum(max(0, value) for value in residuals)
        item = {"index": index, "class": node["className"], "method": node["methodName"],
                "inclusive_sample_weight": inclusive, "self_sample_weight": own,
                "inclusive_percent": inclusive * 100 / total, "self_percent": own * 100 / total}
        results.append(item)
        source = data.get("classSources", {}).get(node["className"], "<unattributed>")
        source_totals[source] += own

    def ranked(field):
        output = sorted(results, key=lambda item: (-item[field], item["index"]))[:top]
        for item in output:
            index, path = item["index"], []
            while True:
                node = nodes[index]
                path.append(node["className"] + "." + node["methodName"])
                if index not in parent:
                    break
                index = parent[index]
            item["path"] = list(reversed(path))
        return output

    return {"scope": "Spark execution stack diagnostics; not performance acceptance", "thread": thread_name,
            "metadata": {"start_utc": datetime.fromtimestamp(start / 1000, timezone.utc).isoformat(),
                         "export_end_utc": datetime.fromtimestamp(end / 1000, timezone.utc).isoformat(),
                         "metadata_duration_ms": end - start, "interval_microseconds": interval,
                         "interval_ms": interval / 1000, "engine": metadata["samplerEngine"],
                         "mode": metadata["samplerMode"]},
            "explicit_time_windows": windows, "root_sample_weight": total,
            "weight_semantics": "Spark execution sample weights; includes waits when capture did not exclude them; not CPU elapsed or frame time",
            "window_sample_weights": dict(zip(map(str, windows), root_by_window)),
            "world_statistics_semantics": "Raw signed Spark snapshots; negative counts are unavailable, and load-time warnings/freshness need separate log review",
            "raw_world_statistics": data["timeWindowStatistics"],
            "negative_self_residuals": negative_residuals,
            "ranked_inclusive": ranked("inclusive_sample_weight"), "ranked_self": ranked("self_sample_weight"),
            "source_self_weights": [{"source": source, "self_sample_weight": value, "percent": value * 100 / total}
                                    for source, value in source_totals.most_common(top)],
            "performance_accepted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--thread", required=True)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()
    require(args.input.stat().st_size <= 128 * 1024 * 1024, "Decoded JSON exceeds input bound")
    data = json.loads(args.input.read_bytes())
    print(json.dumps(analyze(data, args.thread, args.top), ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
