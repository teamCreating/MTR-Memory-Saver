"""Paired text/source-lookup microbenchmark; never claims native parsing or gameplay."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--jobs', type=Path, required=True, help='JSON array: archive, model, sha256.')
    parser.add_argument('--output', type=Path, required=True, help='Fresh report directory.')
    parser.add_argument('--heap', default='3g')
    parser.add_argument('--epochs', type=int, default=2)
    parser.add_argument('--queries', type=int, default=3)
    parser.add_argument('--pairs', type=int, default=3)
    args = parser.parse_args()
    if min(args.epochs, args.queries, args.pairs) < 1:
        parser.error('Workload counts must be positive.')
    args.output.mkdir(parents=True, exist_ok=False)
    jobs = json.loads(args.jobs.read_text(encoding='utf-8-sig'))
    if not jobs:
        parser.error('No input jobs.')
    controls = []
    for job in jobs:
        archive = Path(job['archive']).resolve()
        if '\t' in str(archive) or '\t' in job['model'] or '\n' in job['model']:
            parser.error('Paths cannot contain tabs/newlines.')
        with zipfile.ZipFile(archive) as source:
            content = source.read(job['model'])
        if hashlib.sha256(content).hexdigest() != job['sha256']:
            parser.error('Fixture entry fingerprint mismatch.')
        controls.append({**job, 'archive': str(archive), 'archive_sha256': sha(archive), 'bytes': len(content)})
    tsv = args.output / 'inputs.tsv'
    tsv.write_text(''.join(job['archive'] + '\t' + job['model'] + '\n' for job in controls), encoding='utf-8')
    suffix = '.exe' if os.name == 'nt' else ''
    java, javac = [str(args.java_home / 'bin' / (tool + suffix)) for tool in ('java', 'javac')]
    driver = ROOT / 'tools/acceptance/java/SourceLookupBenchmark.java'
    classes = args.output / 'classes'
    subprocess.run([javac, '--release', '21', '-d', str(classes), '-cp', str(args.candidate), str(driver)], check=True)
    runs = []
    for pair in range(args.pairs):
        for mode in (('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')):
            label = f'{pair + 1}-{mode}'
            output = args.output / (label + '.json')
            recording = args.output / (label + '.jfr')
            # Absolute JFR path avoids guessing which working directory the JVM used.
            command = [java, '-Xms512m', '-Xmx' + args.heap, '-XX:+UseG1GC',
                       f'-XX:StartFlightRecording=filename={recording.resolve()},settings=profile,dumponexit=true',
                       '-Xlog:gc*:stdout:time,uptime,level,tags', '-cp',
                       str(classes) + os.pathsep + str(args.candidate), 'site.benli06.audit.SourceLookupBenchmark',
                       mode, str(args.baseline if mode == 'baseline' else args.candidate), str(tsv),
                       str(args.epochs), str(args.queries), str(output)]
            print('Measuring ' + label, flush=True)
            with (args.output / (label + '.log')).open('w', encoding='utf-8') as log:
                subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
            result = json.loads(output.read_text())
            runs.append({**result, 'pair': pair + 1, 'jfr_sha256': sha(recording),
                         'log_sha256': sha(args.output / (label + '.log')), 'command': command})
    if len({run['result_sha256'] for run in runs}) != 1:
        raise AssertionError('Paired source lookup results differ.')
    manifest = {'timestamp': dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
                'baseline_sha256': sha(args.baseline), 'candidate_sha256': sha(args.candidate),
                'driver_sha256': sha(driver), 'runner_sha256': sha(__file__),
                'java_version': subprocess.check_output([java, '-version'], stderr=subprocess.STDOUT, text=True),
                'controls': controls, 'heap': args.heap, 'epochs': args.epochs, 'queries': args.queries,
                'runs': runs, 'limits': ['Text/source-key microbenchmark. Digest result substitutes for native parsed mesh.',
                                       'Native model parsing, GL ownership, rendering, frames and full-pack gameplay excluded.',
                                       'Allocation counts cover measured live threads; sampled heap can miss brief peaks.',
                                       'GC collection milliseconds are JVM collection counters, not exact summed pause durations.',
                                       'Explicit full GC occurs outside timed windows. JFR/probe overhead affects both runs.']}
    (args.output / 'report.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps([{k: run[k] for k in ('mode', 'pair', 'elapsed_ms', 'resource_reads', 'digest_calls', 'allocated_bytes_live_threads')} for run in runs]), flush=True)


if __name__ == '__main__':
    main()
