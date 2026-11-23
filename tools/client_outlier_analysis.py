"""Apply a symmetric trial-level screen and report paired sensitivity."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from client_experiment import now, save


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "config/client-outlier-analysis.json"
DEFAULT_SCHEDULE = ROOT / "config/client-practical-verification.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def fingerprint(path):
    raw = Path(path).read_bytes()
    return {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def screen(values, policy):
    if len(values) < policy["minimum_group_samples"]:
        return {"status": "insufficient_replicates", "count": len(values), "flagged": []}
    q1, _, q3 = statistics.quantiles(list(values.values()), n=4, method="inclusive")
    spread = q3 - q1
    if spread == 0:
        return {"status": "zero_iqr_unresolved", "count": len(values), "flagged": []}
    lower = q1 - policy["iqr_multiplier"] * spread
    upper = q3 + policy["iqr_multiplier"] * spread
    return {"status": "screened", "count": len(values), "q1": q1, "q3": q3,
            "lower": lower, "upper": upper,
            "flagged": [key for key, value in values.items() if value < lower or value > upper]}


def compare(pairs, trials, metrics):
    result = {}
    for metric in metrics:
        deltas = []
        for pair in pairs:
            baseline = trials[pair["baseline"]]["metrics"][metric]
            candidate = trials[pair["candidate"]]["metrics"][metric]
            deltas.append(100 * (candidate / baseline - 1))
        result[metric] = {"pairs": len(pairs), "percent_deltas": deltas,
                          "median_percent_delta": statistics.median(deltas) if deltas else None}
    return result


def analyze(assessment, schedule, policy):
    if (policy["schema"] != 1 or policy["method"] != "tukey_inclusive"
            or policy["exclusion_unit"] != "pair" or policy["group_fields"] != ["mode", "role"]
            or policy["roles"] != ["baseline", "candidate"]
            or type(policy["minimum_group_samples"]) is not int or policy["minimum_group_samples"] < 4
            or not math.isfinite(policy["iqr_multiplier"]) or policy["iqr_multiplier"] <= 0):
        raise ValueError("Unsupported outlier policy.")
    if not assessment["all_12_trials_qualified"] or assessment["errors"]:
        raise ValueError("Independent trial qualification must pass before sensitivity analysis.")
    selected = [spec for spec in schedule["schedule"] if spec["comparison"] == policy["comparison"]]
    trials = assessment["trials"]
    groups, pairs = {}, {}
    metrics = set(policy["report_metrics"]) | {policy["screen_metric"]}
    for spec in selected:
        trial = trials[spec["id"]]
        if trial["mode"] != spec["mode"] or trial["role"] != spec["role"]:
            raise ValueError("Trial treatment differs from the schedule.")
        for metric in metrics:
            value = trial["metrics"][metric]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("Sensitivity metrics must be finite positive measurements.")
        groups.setdefault((spec["mode"], spec["role"]), {})[spec["id"]] = trial["metrics"][policy["screen_metric"]]
        pair = pairs.setdefault(spec["pair"], {"id": spec["pair"], "mode": spec["mode"]})
        if pair["mode"] != spec["mode"] or spec["role"] in pair:
            raise ValueError("Pair has duplicated roles or different modes.")
        pair[spec["role"]] = spec["id"]
    if any(not all(role in pair for role in policy["roles"]) for pair in pairs.values()):
        raise ValueError("Each pair requires both treatments.")
    screening = []
    flags = set()
    for (mode, role), values in sorted(groups.items()):
        result = screen(values, policy)
        screening.append({"mode": mode, "role": role, "values": values, **result})
        flags.update(result["flagged"])
    exclusions = [pair for pair in pairs.values() if any(pair[role] in flags for role in policy["roles"])]
    excluded_ids = {pair["id"] for pair in exclusions}
    modes = {}
    for mode in sorted({pair["mode"] for pair in pairs.values()}):
        original = [pair for pair in pairs.values() if pair["mode"] == mode]
        retained = [pair for pair in original if pair["id"] not in excluded_ids]
        sensitivity = []
        if policy["leave_one_pair_out"]:
            for removed in original:
                remaining = [pair for pair in original if pair["id"] != removed["id"]]
                sensitivity.append({"removed_pair": removed["id"],
                                    "result": compare(remaining, trials, policy["report_metrics"])})
        modes[mode] = {
            "full": compare(original, trials, policy["report_metrics"]),
            "screened": compare(retained, trials, policy["report_metrics"]),
            "retained_pairs": [pair["id"] for pair in retained],
            "leave_one_pair_out": sensitivity,
        }
    return {
        "schema": 1, "analyzed_at": now(), "scope": "Post hoc paired sensitivity",
        "policy": policy, "groups": screening, "excluded_pairs": exclusions, "modes": modes,
        "external_interference_attribution": "Unavailable from these trial metrics",
        "causal_timing_conclusion": "Inconclusive under reported concurrent host workloads",
        "automatic_exclusion_applied": bool(exclusions),
        "release_acceptance_granted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = (args.assessment, args.schedule, args.policy)
    before = [fingerprint(path) for path in paths]
    result = analyze(*(read(path) for path in paths))
    if before != [fingerprint(path) for path in paths]:
        raise ValueError("Analysis inputs changed during reading.")
    result["inputs"] = before
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save(args.output, result, exclusive=True)
    print(json.dumps({"excluded_pairs": result["excluded_pairs"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
