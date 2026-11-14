"""Predeclared paired decisions, with exact distribution-free median intervals."""
import math
import statistics
import datetime as dt


METRICS = {
    'elapsed_ms', 'allocated_bytes_live_threads', 'resource_reads', 'digest_calls',
    'gc_count', 'gc_collection_ms', 'sampled_peak_heap_bytes',
    'post_release_full_gc_heap_bytes',
}


def median_interval(values, confidence):
    """Invert the binomial sign test; never invent a finite small-sample interval."""
    ordered = sorted(values)
    n = len(ordered)
    if not n:
        return None
    indices = [k for k in range(1, n // 2 + 1)
               if 2 * sum(math.comb(n, j) for j in range(k)) / 2 ** n <= 1 - confidence + 1e-12]
    if not indices:
        return None  # The requested interval extends beyond the observed range.
    k = max(indices)
    return [ordered[k - 1], ordered[n - k]]


def paired_summary(pairs, metric, confidence):
    baseline = [a[metric] for a, _ in pairs]
    candidate = [b[metric] for _, b in pairs]
    deltas = [b - a for a, b in zip(baseline, candidate)]
    # A zero reference is meaningful in absolute units, but has no percent ratio.
    relative = [100 * (b / a - 1) if a > 0 else None for a, b in zip(baseline, candidate)]
    valid = bool(relative) and all(v is not None for v in relative)
    return {
        'pairs': len(pairs), 'baseline_values': baseline, 'candidate_values': candidate,
        'absolute_deltas': deltas, 'relative_deltas_percent': relative,
        'baseline_median': statistics.median(baseline) if baseline else None,
        'candidate_median': statistics.median(candidate) if candidate else None,
        'median_absolute_delta': statistics.median(deltas) if deltas else None,
        'median_relative_delta_percent': statistics.median(relative) if valid else None,
        'median_relative_interval_percent': median_interval(relative, confidence) if valid else None,
    }


def decision(summary, limit, minimum_pairs, *, equivalence=False):
    interval = summary['median_relative_interval_percent']
    if summary['pairs'] < minimum_pairs or interval is None:
        return 'inconclusive'
    low, high = interval
    if equivalence:
        if low >= -limit and high <= limit:
            return 'pass'
        if high < -limit or low > limit:
            return 'fail'
    else:
        if high <= limit:
            return 'pass'
        if low > limit:
            return 'fail'
    return 'inconclusive'


def analyze(plan, state):
    """All scheduled trials count. Failed/missing pairs prevent acceptance."""
    policy = plan['policy']
    expected = {trial['id']: trial for trial in plan['schedule']}
    actual = state.get('trials', [])
    errors = []
    if [t.get('id') for t in actual] != list(expected):
        errors.append('Recorded trial order differs from frozen schedule.')
    indexed = {}
    for trial in actual:
        key = trial.get('id')
        if key not in expected or key in indexed:
            errors.append('Unexpected or duplicate trial: ' + str(key))
        indexed[key] = trial
    for key, spec in expected.items():
        trial = indexed.get(key)
        if not trial or trial.get('status') != 'complete':
            errors.append('Missing or failed trial: ' + key)
            continue
        result = trial.get('result', {})
        if trial.get('returncode') != 0:
            errors.append('Unsuccessful JVM exit: ' + key)
        for field in ('pair', 'comparison', 'instrumentation', 'arm', 'mode'):
            if trial.get(field) != spec[field]:
                errors.append('Trial control differs from plan (' + field + '): ' + key)
        try:
            times = [dt.datetime.fromisoformat(result[field]) for field in ('warmup_start', 'warmup_end', 'start', 'end')]
            if any(value.tzinfo is None for value in times) or not times[0] < times[1] <= times[2] < times[3]:
                errors.append('Invalid warm-up/measurement windows: ' + key)
        except (KeyError, TypeError, ValueError):
            errors.append('Missing/invalid timestamp: ' + key)
        if result.get('mode') != spec['mode']:
            errors.append('Incorrect implementation mode: ' + key)
        if result.get('result_sha256') != plan['expected_result_sha256']:
            errors.append('Independent result oracle mismatch: ' + key)
        if result.get('warmup_result_sha256') != plan['expected_warmup_sha256']:
            errors.append('Warm-up result oracle mismatch: ' + key)
        if result.get('max_heap_bytes') != plan['heap_bytes']:
            errors.append('Effective heap differs from plan: ' + key)
        if result.get('instrumentation') != spec['instrumentation']:
            errors.append('Incorrect instrumentation: ' + key)
        for metric in METRICS:
            value = result.get(metric)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                errors.append('Invalid metric ' + metric + ': ' + key)
        for field in ('warmup_epochs', 'epochs', 'queries'):
            if result.get(field) != policy[field]:
                errors.append('Workload differs from plan (' + field + '): ' + key)
        expected_hashes = len(plan['inputs']) * policy['epochs']
        if spec['mode'] == 'baseline':
            expected_hashes *= policy['queries']
        if result.get('digest_calls') != expected_hashes:
            errors.append('Unexpected digest count: ' + key)
    if state.get('status') != 'complete':
        errors.append('Experiment did not complete: ' + state.get('status', 'missing'))
    if errors:
        return {'status': 'invalid', 'errors': errors, 'scheduled_trials': len(expected),
                'recorded_trials': len(actual), 'performance_accepted': False}

    groups = {}
    for comparison in ('ab', 'aa'):
        for instrumentation in ('plain', 'profile'):
            pairs = []
            for number in range(1, policy['pairs'] + 1):
                arms = {spec['arm']: indexed[key]['result'] for key, spec in expected.items()
                        if spec['comparison'] == comparison and spec['instrumentation'] == instrumentation
                        and spec['pair'] == number}
                pairs.append((arms['a'], arms['b']))
            groups[comparison + '_' + instrumentation] = {
                metric: paired_summary(pairs, metric, policy['confidence']) for metric in sorted(METRICS)}

    gates = {}
    for instrumentation in ('plain', 'profile'):
        for metric, tolerance in policy['aa_tolerance_percent'].items():
            gates['aa_' + instrumentation + '_' + metric] = decision(
                groups['aa_' + instrumentation][metric], tolerance, policy['minimum_pairs'], equivalence=True)
    primary = policy['primary']
    # Allocations are observed in both modes, elapsed timing uses the plain arm.
    gates['primary'] = decision(groups['ab_plain'][primary['metric']],
                                -primary['minimum_reduction_percent'], policy['minimum_pairs'])
    for metric, tolerance in policy['guardrails'].items():
        gates['guardrail_' + metric] = decision(groups['ab_plain'][metric], tolerance, policy['minimum_pairs'])

    overhead = {}
    for arm in ('a', 'b'):
        pairs = []
        for number in range(1, policy['pairs'] + 1):
            by_probe = {spec['instrumentation']: indexed[key]['result'] for key, spec in expected.items()
                        if spec['comparison'] == 'ab' and spec['arm'] == arm and spec['pair'] == number}
            pairs.append((by_probe['plain'], by_probe['profile']))
        overhead[arm] = paired_summary(pairs, 'elapsed_ms', policy['confidence'])
    status = 'fail' if 'fail' in gates.values() else ('pass' if set(gates.values()) == {'pass'} else 'inconclusive')
    return {'status': status, 'performance_accepted': status == 'pass', 'gates': gates,
            'groups': groups, 'jfr_and_gc_logging_overhead': overhead,
            'confidence': policy['confidence'],
            'method': 'Paired percent deltas; median interval from exact binomial sign-test inversion. '
                      'Pointwise intervals, not simultaneous multi-metric confidence. No outlier removal.',
            'limits': ['A/A must demonstrate equivalence within the frozen tolerances; absence of significance is not equivalence.',
                       'Independent JVM pairs are the experimental units; queries, samples and epochs are not extra replicates.',
                       'Sequential host measurements can remain correlated despite blocked counterbalancing.',
                       'Plain mode retains allocation/heap observation; overhead measures added JFR and GC logging only.',
                       'Source-work microbenchmark only; whole-game loading, Full-GC pauses, GL and frames are unmeasured.']}
