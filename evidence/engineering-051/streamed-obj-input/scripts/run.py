import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

stage, target, *tasks = sys.argv[1:]
root = Path.cwd()
output = Path(__file__).parent / stage
output.mkdir(exist_ok=False)
env = os.environ.copy()
env['JAVA_HOME'] = r'C:\Users\ben_l\Saved Games\Yuuniverse 1.20.1 Shenyang\porting-output\work\tools\jdk21\jdk-21.0.11+10'
env['PATH'] = env['JAVA_HOME'] + r'\bin;' + env['PATH']
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name, value):
    (output / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
paths = sorted(set(Path('src').rglob('*.java')) | set(Path('tools/probes').rglob('*.java'))
               | set(Path('tools/acceptance/java').glob('*.java'))
               | {Path('build.gradle'), Path('gradle.properties'), Path('config/targets.json')})
before = {path.as_posix(): sha(path) for path in paths}
for path in paths:
    copied = output / 'sources' / path
    copied.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, copied)
save('source-sha256.json', before)
argv = ['gradlew.bat', '--no-daemon', '-Ptarget=' + target, *tasks]
record = {'argv': argv, 'cwd': str(root), 'started_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'JAVA_HOME': env['JAVA_HOME']}
save('command.json', record)
with (output / 'stdout.log').open('wb') as stdout, (output / 'stderr.log').open('wb') as stderr:
    actual = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr)
record.update(exit_code=actual.returncode, ended_at=dt.datetime.now(dt.timezone.utc).isoformat())
save('command.json', record)
tests = []
for path in sorted(Path('build/test-results/test').glob('TEST-*.xml')):
    copied = output / 'junit' / path.name
    copied.parent.mkdir(exist_ok=True)
    shutil.copyfile(path, copied)
    suite = ET.parse(path).getroot()
    tests.append({key: suite.get(key) for key in ['name', 'tests', 'failures', 'errors', 'skipped']})
save('test-summary.json', tests)
changed = [path.as_posix() for path in paths if sha(path) != before[path.as_posix()]]
save('source-after.json', {'changed': changed})
artifacts = {}
version = next(line.split('=', 1)[1] for line in Path('gradle.properties').read_text().splitlines() if line.startswith('modVersion='))
for path in sorted(Path('build/libs').glob('mtr-memory-saver-' + target + '-' + version + '*')):
    if path.suffix not in {'.jar', '.json'}: continue
    shutil.copyfile(path, output / path.name)
    artifacts[path.name] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
save('artifact-sha256.json', artifacts)
print(json.dumps({'target': target, 'exit_code': actual.returncode, 'changed': changed,
                  'tests': sum(int(x['tests']) for x in tests), 'failures': sum(int(x['failures']) for x in tests),
                  'skipped': sum(int(x['skipped']) for x in tests), 'output': str(output), 'artifacts': artifacts}), flush=True)
if actual.returncode:
    print((output/'stdout.log').read_text(encoding='utf-8', errors='replace')[-12000:])
    print((output/'stderr.log').read_text(encoding='utf-8', errors='replace')[-12000:])
sys.exit(actual.returncode or bool(changed))
