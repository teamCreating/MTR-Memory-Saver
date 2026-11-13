"""Summarize exact JFR windows, distinguishing frame intervals, tick spans and GC pauses."""
import argparse
import collections
import datetime as dt
import json
import math
import pathlib
import re
import subprocess
import os
import hashlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

def read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

def save_json(path, value):
    pathlib.Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

def digest(path):
    with pathlib.Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def duration(value):
    match = re.fullmatch(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?', value)
    if not match:
        raise ValueError('Unsupported ISO duration: ' + value)
    return sum(float(v or 0) * factor for v, factor in zip(match.groups(), (3600, 60, 1)))


def stats(values):
    if not values:
        return {'count': 0}
    ordered = sorted(values)
    def quantile(p):
        index = (len(ordered) - 1) * p
        low = math.floor(index)
        return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (index - low)
    return {'count': len(values), 'mean': sum(values) / len(values), 'p50': quantile(.5),
            'p95': quantile(.95), 'p99': quantile(.99), 'max': ordered[-1], 'sum': sum(values)}


def method(frame):
    m = frame['method']
    return m['type']['name'].replace('/', '.') + '.' + m['name']


def summarize(events, start, end):
    chosen = [e for e in events if start <= dt.datetime.fromisoformat(e['values']['startTime']) < end]
    groups = collections.defaultdict(list)
    for e in chosen:
        groups[e['type']].append(e['values'])
    frames = [v['intervalMs'] for v in groups['mtrtest.ClientFrame']
              if v['inWorld'] and not v['paused'] and v['screen'] == 'game'
              and dt.datetime.fromisoformat(v['startTime']) - dt.timedelta(milliseconds=v['intervalMs']) >= start]
    ticks = [duration(v['duration']) * 1000 for v in groups['mtrtest.ServerTick']]
    pauses = [duration(v['duration']) * 1000 for v in groups['jdk.GCPhasePause']]
    gc = groups['jdk.GarbageCollection']
    cpu = [v['jvmUser'] + v['jvmSystem'] for v in groups['jdk.CPULoad']]
    allocations = collections.Counter()
    leaf, inclusive, threads = collections.Counter(), collections.Counter(), collections.Counter()
    by_thread = collections.defaultdict(collections.Counter)
    by_engine = {}
    for kind in ('jdk.ExecutionSample', 'jdk.NativeMethodSample'):
        engine_leaf, engine_inclusive = collections.Counter(), collections.Counter()
        for v in groups[kind]:
            stack = (v.get('stackTrace') or {}).get('frames', [])
            if not stack:
                continue
            names = [method(f) for f in stack]
            thread = (v.get('sampledThread') or {}).get('javaName') or '<unnamed>'
            leaf[names[0]] += 1
            by_thread[thread][names[0]] += 1
            inclusive.update(set(names))
            threads[thread] += 1
            engine_leaf[names[0]] += 1
            engine_inclusive.update(set(names))
        by_engine[kind] = {'sample_count_with_stack': sum(engine_leaf.values()),
                           'leaf': engine_leaf.most_common(30), 'inclusive': engine_inclusive.most_common(30)}
    for v in groups['jdk.ObjectAllocationSample']:
        allocations[v['objectClass']['name'].replace('/', '.')] += v['weight']
    return {'start': start.isoformat(), 'end': end.isoformat(), 'seconds': (end-start).total_seconds(),
            'event_counts': {k: len(v) for k,v in groups.items()},
            'game_frame_interval_ms': stats(frames),
            'effective_fps_from_intervals': len(frames) * 1000 / sum(frames) if frames else None,
            'frames_over_50ms': sum(v > 50 for v in frames), 'frames_over_100ms': sum(v > 100 for v in frames),
            'server_tick_event_span_ms': stats(ticks), 'gc_pause_ms': stats(pauses),
            'gc_causes': dict(collections.Counter((v['name'] + ': ' + v['cause']) for v in gc)),
            'gc_events': [{'start': v['startTime'], 'name': v['name'], 'cause': v['cause'],
                           'duration_seconds': duration(v['duration']),
                           'pause_seconds': duration(v['sumOfPauses'])} for v in gc],
            'jvm_cpu_fraction_of_machine': stats(cpu), 'sampled_threads': threads.most_common(15),
            'sampled_leaf_methods': leaf.most_common(25), 'sampled_inclusive_methods': inclusive.most_common(25),
            'sampled_leaf_by_thread': {k: v.most_common(12) for k,v in by_thread.items()},
            'samples_by_event_type': by_engine,
            'allocation_sample_weight_by_class': allocations.most_common(20),
            'virtual_thread_pinned_events': len(groups['jdk.VirtualThreadPinned']),
            'sampled_heap_used_bytes': stats([v['heapUsed'] for v in groups['jdk.GCHeapSummary']])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recording', type=pathlib.Path, required=True)
    p.add_argument('--jfr', type=pathlib.Path, required=True)
    p.add_argument('--json-library', type=pathlib.Path, required=True, help='MTR JAR supplying shaded Gson for the streaming exporter.')
    p.add_argument('--windows', type=pathlib.Path, required=True)
    p.add_argument('--output', type=pathlib.Path, required=True)
    p.add_argument('--export', type=pathlib.Path, required=True)
    args = p.parse_args()
    if args.output.exists() or args.export.exists():
        p.error('Use fresh outputs.')
    exporter = ROOT / 'tools/acceptance/java/ExportPerformanceJfr.java'
    build = ROOT / 'build/acceptance/performance-jfr-exporter' / digest(exporter)
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(args.jfr.with_name('javac.exe' if os.name == 'nt' else 'javac')), '-proc:none', '--release', '21', '-classpath',
                    str(args.json_library), '-d', str(build), str(exporter)], check=True)
    subprocess.run([str(args.jfr.with_name('java.exe' if os.name == 'nt' else 'java')), '-Xmx512m', '-cp',
                    str(build) + os.pathsep + str(args.json_library), 'site.benli06.audit.ExportPerformanceJfr',
                    str(args.recording), str(args.export)], check=True)
    data = read_json(args.export)['recording']['events']
    windows = read_json(args.windows)
    summary = {'recording_sha256': digest(args.recording), 'windows_sha256': digest(args.windows),
               'analyzer_sha256': digest(__file__), 'export_sha256': digest(args.export),
               'exporter_sha256': digest(exporter), 'json_library_sha256': digest(args.json_library),
               'event_count': len(data), 'windows': {},
               'limits': ['Frame intervals are CPU render-loop intervals including pacing, not GPU presentation times.',
                          'Tick spans cover NeoForge event hooks, not full authoritative MSPT; no TPS derived from them.',
                          'Execution/NativeMethod sample counts are statistical observations, not exact CPU milliseconds.',
                          'Allocation weights estimate allocation traffic, not retained heap.',
                          'JFR profile and observation instrumentation add overhead; no uninstrumented control.']}
    for name, window in windows.items():
        summary['windows'][name] = summarize(data, dt.datetime.fromisoformat(window['start']),
                                            dt.datetime.fromisoformat(window['end']))
    save_json(args.output, summary)
    print(json.dumps({name: {k: v[k] for k in ['effective_fps_from_intervals', 'game_frame_interval_ms',
                     'gc_pause_ms', 'server_tick_event_span_ms']} for name,v in summary['windows'].items()}), flush=True)


if __name__ == '__main__':
    main()
