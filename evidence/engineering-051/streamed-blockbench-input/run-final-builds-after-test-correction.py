import os, subprocess, json, datetime, pathlib, hashlib, shutil, xml.etree.ElementTree as E
base = pathlib.Path('.cache/acceptance/streaming048-validation')
env = os.environ.copy()
env['JAVA_HOME'] = r'C:\Users\ben_l\Saved Games\Yuuniverse 1.20.1 Shenyang\porting-output\work\tools\jdk21\jdk-21.0.11+10'
env['PATH'] = env['JAVA_HOME'] + r'\bin;' + env['PATH']
version = next(x.split('=', 1)[1] for x in pathlib.Path('gradle.properties').read_text().splitlines() if x.startswith('modVersion='))
for label, target in [('06-corrected-final-nf248', 'official-nf248'), ('07-corrected-final-nf265', 'official-nf265')]:
    out = base / label
    out.mkdir(parents=True, exist_ok=False)
    source_paths = sorted(set(pathlib.Path('src').rglob('*.java')) | set(pathlib.Path('tools/probes').rglob('*.java')) | {pathlib.Path('tools/acceptance/java/StreamingBlockbenchInputAudit.java'), pathlib.Path('build.gradle'), pathlib.Path('gradle.properties'), pathlib.Path('config/targets.json')})
    hashes = {}
    for source in source_paths:
        data = source.read_bytes()
        hashes[source.as_posix()] = hashlib.sha256(data).hexdigest()
        copy = out / 'sources' / source
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(data)
    (out/'source-sha256.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf8')
    argv = ['gradlew.bat', '--no-daemon', '-Ptarget=' + target, 'test', 'verifyRelease', 'probeJar', 'probeManifest', 'streamingBlockbenchInputAudit', '-PstreamingAuditDirectory=' + str((out/'snapshot').resolve())]
    record = {'argv': argv, 'cwd': str(pathlib.Path.cwd()), 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'JAVA_HOME': env['JAVA_HOME']}
    (out/'command.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
    with (out/'stdout.log').open('wb') as stdout, (out/'stderr.log').open('wb') as stderr:
        result = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr)
    record.update(exit_code=result.returncode, ended_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/'command.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
    tests = []
    for source in sorted(pathlib.Path('build/test-results/test').glob('TEST-*.xml')):
        copy = out/'junit'/source.name
        copy.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, copy)
        root = E.parse(source).getroot()
        tests.append({k: root.get(k) for k in ['name', 'tests', 'failures', 'errors', 'skipped']})
    (out/'test-summary.json').write_text(json.dumps(tests, indent=2) + '\n', encoding='utf8')
    artifacts = {}
    for source in sorted(pathlib.Path('build/libs').glob('mtr-memory-saver-' + target + '-' + version + '*')):
        if source.suffix not in ['.jar', '.json']: continue
        shutil.copyfile(source, out/source.name)
        artifacts[source.name] = {'size': source.stat().st_size, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    (out/'artifact-sha256.json').write_text(json.dumps(artifacts, indent=2) + '\n', encoding='utf8')
    changed = [str(source) for source in source_paths if hashlib.sha256(source.read_bytes()).hexdigest() != hashes[source.as_posix()]]
    (out/'post-source-check.json').write_text(json.dumps({'changed': changed}, indent=2) + '\n', encoding='utf8')
    summary = {'target': target, 'exit_code': result.returncode, 'tests': sum(int(t['tests']) for t in tests), 'failures': sum(int(t['failures']) for t in tests), 'errors': sum(int(t['errors']) for t in tests), 'skipped': sum(int(t['skipped']) for t in tests), 'source_changed': changed, 'artifacts': artifacts}
    print(json.dumps(summary, indent=2), flush=True)
    if result.returncode or changed:
        print((out/'stdout.log').read_text(encoding='utf8', errors='replace')[-12000:], flush=True)
        print((out/'stderr.log').read_text(encoding='utf8', errors='replace')[-12000:], flush=True)
        raise SystemExit(result.returncode or 1)
