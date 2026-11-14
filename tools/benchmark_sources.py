"""Plan, execute and audit a frozen, paired real-input source-work experiment."""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import subprocess
import sys
import zipfile

from source_experiment_analysis import METRICS, analyze

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'tools/acceptance/java/SourceLookupBenchmark.java'
SCHEMA = 1
INJECTED_ENV = ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS', 'CLASSPATH')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value, *, exclusive=False):
    content = json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + '\n'
    path = Path(path)
    if exclusive:
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
    else:
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(content, encoding='utf-8', newline='\n')
        temporary.replace(path)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def fingerprint(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def environment():
    injected = {key: os.environ[key] for key in INJECTED_ENV if os.environ.get(key)}
    if injected:
        raise ValueError('Remove JVM-injecting environment variables before planning/running: ' + ', '.join(injected))
    return {'system': platform.platform(), 'machine': platform.machine(),
            'processor': platform.processor(), 'node': platform.node(), 'cpu_count': os.cpu_count()}


def heap_bytes(value):
    match = re.fullmatch(r'([1-9][0-9]*)([kmg]?)', value.lower())
    if not match:
        raise ValueError('Invalid heap size: ' + value)
    return int(match[1]) * 1024 ** ('', 'k', 'm', 'g').index(match[2])


def validate_policy(policy):
    required = {'schema', 'hypothesis', 'pairs', 'minimum_pairs', 'seed', 'confidence', 'heap', 'initial_heap',
                'warmup_epochs', 'epochs', 'queries', 'timeout_seconds', 'primary', 'guardrails', 'aa_tolerance_percent'}
    if set(policy) != required or policy['schema'] != SCHEMA:
        raise ValueError('Unknown/missing experiment policy fields or schema.')
    for key in ('pairs', 'minimum_pairs', 'warmup_epochs', 'epochs', 'queries', 'timeout_seconds'):
        if type(policy[key]) is not int or policy[key] < 1:
            raise ValueError('Expected positive integer: ' + key)
    if type(policy['seed']) is not int or not isinstance(policy['hypothesis'], str) or not policy['hypothesis'].strip():
        raise ValueError('Seed and hypothesis must be explicit.')
    if not isinstance(policy['confidence'], (int, float)) or not .5 < policy['confidence'] < 1:
        raise ValueError('Confidence must be between .5 and 1.')
    if heap_bytes(policy['initial_heap']) > heap_bytes(policy['heap']):
        raise ValueError('Initial heap exceeds maximum heap.')
    primary = policy['primary']
    if set(primary) != {'metric', 'minimum_reduction_percent'} or primary['metric'] not in METRICS:
        raise ValueError('Invalid primary endpoint.')
    if not policy['guardrails'] or not policy['aa_tolerance_percent']:
        raise ValueError('Guardrails and A/A tolerances are required.')
    if not {primary['metric'], *policy['guardrails']} <= set(policy['aa_tolerance_percent']):
        raise ValueError('A/A tolerances must cover the primary endpoint and every guardrail.')
    for group in (policy['guardrails'], policy['aa_tolerance_percent'],
                  {primary['metric']: primary['minimum_reduction_percent']}):
        for metric, value in group.items():
            if metric not in METRICS or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError('Invalid metric/tolerance: ' + metric)
    if not 0 < primary['minimum_reduction_percent'] < 100:
        raise ValueError('Primary reduction must be strictly between 0 and 100 percent.')


def schedule(policy):
    """Randomize blocks; balance AB/BA and plain/profile order within each stratum."""
    rng = random.Random(policy['seed'])
    starts = {(comparison, probe): rng.randrange(2) for comparison in ('ab', 'aa') for probe in ('plain', 'profile')}
    probe_starts = {comparison: rng.randrange(2) for comparison in ('ab', 'aa')}
    trials = []
    for pair in range(1, policy['pairs'] + 1):
        comparisons = ['ab', 'aa']
        rng.shuffle(comparisons)
        for comparison in comparisons:
            probes = ['plain', 'profile']
            if (pair + probe_starts[comparison]) % 2:
                probes.reverse()
            for probe in probes:
                arms = ['a', 'b']
                if (pair + starts[comparison, probe]) % 2:
                    arms.reverse()
                for arm in arms:
                    mode = 'candidate' if comparison == 'ab' and arm == 'b' else 'baseline'
                    trials.append({'id': f'{pair:03d}-{comparison}-{probe}-{arm}', 'pair': pair,
                                   'comparison': comparison, 'instrumentation': probe, 'arm': arm, 'mode': mode})
    return trials


def input_controls(jobs_path):
    jobs_path = Path(jobs_path).resolve()
    jobs = read(jobs_path)
    if not isinstance(jobs, list) or not jobs:
        raise ValueError('Expected a nonempty input job array.')
    archives, controls = {}, []
    for job in jobs:
        archive = Path(job['archive'])
        if not archive.is_absolute():
            archive = jobs_path.parent / archive
        archive = archive.resolve(strict=True)
        model = job['model']
        if any(char in str(archive) + model for char in '\t\r\n'):
            raise ValueError('Input paths cannot contain tabs/newlines.')
        if archive not in archives:
            archives[archive] = fingerprint(archive)
        with zipfile.ZipFile(archive) as source:
            if sum(entry.filename == model for entry in source.infolist()) != 1:
                raise ValueError('Input member missing or ambiguous: ' + model)
            content = source.read(model)
        if hashlib.sha256(content).hexdigest() != job['sha256']:
            raise ValueError('Input entry fingerprint mismatch: ' + model)
        # Valid UTF-8 roundtrips exactly, without either measured digest implementation.
        # Invalid UTF-8 replacement semantics belong to the separate codec audit.
        content.decode('utf-8', errors='strict')
        controls.append({'archive': str(archive), 'model': model,
                         'sha256': job['sha256'], 'bytes': len(content)})
    return controls, list(archives.values())


def oracle(inputs, epochs, queries):
    values = ''.join(job['sha256'] for job in inputs).encode('ascii')
    digest = hashlib.sha256()
    for _ in range(epochs * queries):
        digest.update(values)
    return digest.hexdigest()


def compatible_targets(identities):
    # Version is the treatment; every other target field must match, including
    # future additions, so a new loader/ABI cannot silently enter the comparison.
    controls = [{key: value for key, value in identity.items() if key != 'version'}
                for identity in identities.values()]
    if not controls[0] or any(value != controls[0] for value in controls[1:]):
        raise ValueError('Artifact target metadata differs; choose the same MTR/loader preset.')
    return controls[0]


def make_plan(args):
    policy = read(args.policy)
    if args.pairs is not None:
        policy['pairs'] = args.pairs
    validate_policy(policy)
    host = environment()
    suffix = '.exe' if os.name == 'nt' else ''
    java = fingerprint(args.java_home / 'bin' / ('java' + suffix))
    javac = fingerprint(args.java_home / 'bin' / ('javac' + suffix))
    runtime = [fingerprint(args.java_home / 'release'), fingerprint(args.java_home / 'lib/modules'),
               fingerprint(args.java_home / ('bin/server/jvm.dll' if os.name == 'nt' else 'lib/server/libjvm.so'))]
    version = subprocess.check_output([java['path'], '-version'], stderr=subprocess.STDOUT, text=True)
    if not re.search(r'version "21[.\"]', version):
        raise ValueError('This driver requires the audited Java 21 runtime.')
    inputs, archives = input_controls(args.jobs)
    artifacts = {mode: fingerprint(getattr(args, mode)) for mode in ('baseline', 'candidate')}
    identities = {}
    for mode, item in artifacts.items():
        with zipfile.ZipFile(item['path']) as jar:
            identities[mode] = json.loads(jar.read('mtr-memory-target.json'))
    target = compatible_targets(identities)
    sources = [fingerprint(path) for path in (DRIVER, Path(__file__), Path(__file__).with_name('source_experiment_analysis.py'))]
    plan = {'schema': SCHEMA, 'created_at': now(), 'scope': 'source_lookup_microbenchmark',
            'policy': policy, 'environment': host, 'environment_notes': args.environment_notes,
            'java': java, 'javac': javac, 'java_runtime': runtime, 'java_version': version,
            'artifacts': artifacts, 'artifact_metadata': identities, 'target': target, 'sources': sources,
            'inputs': inputs, 'archives': archives, 'jobs': fingerprint(args.jobs),
            'heap_bytes': heap_bytes(policy['heap']), 'schedule': schedule(policy),
            'expected_result_sha256': oracle(inputs, policy['epochs'], policy['queries']),
            'expected_warmup_sha256': oracle(inputs, policy['warmup_epochs'], policy['queries']),
            'jvm_arguments': ['-Xms' + policy['initial_heap'], '-Xmx' + policy['heap'], '-XX:+UseG1GC'],
            'cache_state': 'Real-input warm-up in each fresh JVM, then application caches cleared. OS file cache uncontrolled/warm; not cold disk.'}
    args.output.mkdir(parents=True, exist_ok=False)
    save(args.output / 'plan.json', plan, exclusive=True)
    print(str((args.output / 'plan.json').resolve()), flush=True)


def verify_inputs(plan):
    if environment() != plan['environment']:
        raise ValueError('Machine identity differs from frozen plan.')
    for item in [*plan['artifacts'].values(), *plan['archives'], *plan['sources'],
                 plan['java'], plan['javac'], *plan['java_runtime']]:
        if fingerprint(item['path']) != item:
            raise ValueError('Frozen input changed: ' + item['path'])


def validate_plan(plan):
    if plan['schema'] != SCHEMA or plan['scope'] != 'source_lookup_microbenchmark':
        raise ValueError('Unsupported plan.')
    validate_policy(plan['policy'])
    if plan['schedule'] != schedule(plan['policy']):
        raise ValueError('Schedule differs from the declared design.')
    for field, epochs in [('expected_result_sha256', plan['policy']['epochs']),
                          ('expected_warmup_sha256', plan['policy']['warmup_epochs'])]:
        if plan[field] != oracle(plan['inputs'], epochs, plan['policy']['queries']):
            raise ValueError('Invalid independent oracle.')


def run_plan(path):
    path = path.resolve(strict=True)
    plan = read(path)
    validate_plan(plan)
    verify_inputs(plan)
    root = path.parent
    state_path = root / 'execution.json'
    state = {'plan_sha256': sha(path), 'started_at': now(), 'status': 'running', 'trials': []}
    save(state_path, state, exclusive=True)
    try:
        tsv = root / 'inputs.tsv'
        tsv_text = ''.join(job['archive'] + '\t' + job['model'] + '\n' for job in plan['inputs'])
        tsv.write_text(tsv_text, encoding='utf-8', newline='\n')
        classes = root / 'classes'
        compile_command = [plan['javac']['path'], '--release', '21', '-proc:none', '-d', str(classes),
                           '-cp', plan['artifacts']['candidate']['path'], str(DRIVER)]
        with (root / 'compile.log').open('x', encoding='utf-8') as log:
            subprocess.run(compile_command, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
        state['compile_command'] = compile_command
        state['compiled_classes'] = [fingerprint(file) for file in sorted(classes.rglob('*.class'))]
        policy = plan['policy']
        for spec in plan['schedule']:
            if sha(path) != state['plan_sha256']:
                raise ValueError('Plan edited after experiment started.')
            verify_inputs(plan)
            for item in state['compiled_classes']:
                if fingerprint(item['path']) != item:
                    raise ValueError('Compiled harness changed during experiment.')
            if sha(tsv) != hashlib.sha256(tsv_text.encode('utf-8')).hexdigest():
                raise ValueError('Workload TSV changed during experiment.')
            trial_dir = root / spec['id']
            trial_dir.mkdir(exist_ok=False)
            output, recording = trial_dir / 'result.json', trial_dir / 'recording.jfr'
            command = [plan['java']['path'], *plan['jvm_arguments']]
            if spec['instrumentation'] == 'profile':
                # Relative filename avoids interpreting Windows path commas as JFR options.
                command += ['-XX:StartFlightRecording=filename=recording.jfr,settings=profile,dumponexit=true',
                            '-Xlog:gc*:stdout:time,uptime,level,tags']
            command += ['-cp', str(classes) + os.pathsep + plan['artifacts']['candidate']['path'],
                        'site.benli06.audit.SourceLookupBenchmark', spec['mode'], plan['artifacts'][spec['mode']]['path'],
                        str(tsv), str(policy['epochs']), str(policy['queries']), str(output),
                        str(policy['warmup_epochs']), spec['instrumentation']]
            trial = {**spec, 'status': 'running', 'started_at': now(), 'command': command}
            state['trials'].append(trial)
            save(state_path, state)
            print('Measuring ' + spec['id'], flush=True)
            try:
                with (trial_dir / 'process.log').open('x', encoding='utf-8') as log:
                    completed = subprocess.run(command, cwd=trial_dir, stdout=log, stderr=subprocess.STDOUT,
                                               timeout=policy['timeout_seconds'])
                trial['returncode'] = completed.returncode
                if completed.returncode:
                    raise RuntimeError('JVM exited with code ' + str(completed.returncode))
                trial['result'] = read(output)
                if spec['instrumentation'] == 'profile' and not recording.is_file():
                    raise ValueError('Requested recording missing.')
                trial['status'] = 'complete'
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                trial['status'] = 'failed'
                trial['error'] = type(error).__name__ + ': ' + str(error)
            finally:
                trial['finished_at'] = now()
                trial['files'] = [fingerprint(file) for file in sorted(trial_dir.iterdir()) if file.is_file()]
                save(state_path, state)
        verify_inputs(plan)
        if sha(path) != state['plan_sha256']:
            raise ValueError('Plan edited during experiment.')
        state['status'] = 'complete' if all(t['status'] == 'complete' for t in state['trials']) else 'failed'
    except BaseException as error:
        state['status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed'
        state['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        state['finished_at'] = now()
        save(state_path, state)
    report = audit(path)
    save(root / 'analysis.json', report, exclusive=True)
    print(json.dumps({'status': report['status'], 'gates': report.get('gates', {}), 'report': str(root / 'analysis.json')}), flush=True)
    return 2 if report['status'] in ('invalid', 'fail') else 0


def audit(path):
    plan, state = read(path), read(path.parent / 'execution.json')
    validate_plan(plan)
    errors = []
    if state['plan_sha256'] != sha(path):
        errors.append('Plan fingerprint mismatch.')
    for trial in state['trials']:
        if trial.get('status') != 'complete':
            continue
        files = {Path(item['path']).name: item for item in trial.get('files', [])}
        required = {'process.log', 'result.json'}
        if trial['instrumentation'] == 'profile':
            required.add('recording.jfr')
        if not required <= files.keys():
            errors.append('Missing raw evidence: ' + trial['id'])
        for item in files.values():
            if not Path(item['path']).is_file() or sha(item['path']) != item['sha256']:
                errors.append('Changed/missing evidence: ' + item['path'])
        if 'result.json' in files:
            try:
                if read(files['result.json']['path']) != trial['result']:
                    errors.append('Result differs from raw file: ' + trial['id'])
            except (OSError, ValueError):
                errors.append('Unreadable result: ' + trial['id'])
    report = analyze(plan, state)
    if errors:
        report.update(status='invalid', performance_accepted=False, integrity_errors=errors)
    return {**report, 'plan_sha256': sha(path), 'execution_sha256': sha(path.parent / 'execution.json'),
            'analyzer_sha256': sha(Path(__file__).with_name('source_experiment_analysis.py'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prepare = sub.add_parser('plan', help='Freeze identities, policy and all trial orders before measurements.')
    for name in ('java-home', 'baseline', 'candidate', 'jobs', 'output'):
        prepare.add_argument('--' + name, type=Path, required=True)
    prepare.add_argument('--policy', type=Path, default=ROOT / 'config/source-experiment.json')
    prepare.add_argument('--pairs', type=int, help='Pilot override; does not lower minimum evidence for acceptance.')
    prepare.add_argument('--environment-notes', required=True, help='Power mode, background workload and known confounders.')
    for action in ('run', 'analyze'):
        command = sub.add_parser(action)
        command.add_argument('--plan', type=Path, required=True)
        if action == 'analyze':
            command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'plan':
        make_plan(args)
    elif args.action == 'run':
        return run_plan(args.plan)
    else:
        report = audit(args.plan.resolve())
        save(args.output, report, exclusive=True)
        print(json.dumps({'status': report['status'], 'gates': report.get('gates', {})}), flush=True)
        return 2 if report['status'] in ('invalid', 'fail') else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
