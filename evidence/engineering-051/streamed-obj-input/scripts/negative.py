import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path.cwd()
output = Path(__file__).parent / '04-string-negative'
output.mkdir(exist_ok=False)
pins = json.loads((output.parent/'02-final-nf248/source-sha256.json').read_bytes())
def unchanged():
    return all(hashlib.sha256(Path(name).read_bytes()).hexdigest() == value for name, value in pins.items())
if not unchanged(): raise RuntimeError('Frozen Java/build inputs changed')
env = os.environ.copy()
env['JAVA_HOME'] = r'C:\Users\ben_l\Saved Games\Yuuniverse 1.20.1 Shenyang\porting-output\work\tools\jdk21\jdk-21.0.11+10'
env['PATH'] = env['JAVA_HOME'] + r'\bin;' + env['PATH']
argv = ['gradlew.bat', '--no-daemon', '-Ptarget=official-nf248', 'streamingObjInputAudit', '-PobjAuditMode=string',
        '-PobjAuditDirectory=' + str(output/'text')]
record = {'argv': argv, 'started_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'scope': 'One full-String negative allocation control; no JUnit test task or game launched'}
with (output/'stdout.log').open('wb') as stdout, (output/'stderr.log').open('wb') as stderr:
    actual = subprocess.run(argv, env=env, stdout=stdout, stderr=stderr)
record.update(exit_code=actual.returncode, ended_at=dt.datetime.now(dt.timezone.utc).isoformat(), source_unchanged=unchanged())
(output/'command.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps(record), flush=True)
print((output/'stdout.log').read_text(encoding='utf-8', errors='replace')[-2500:])
print((output/'stderr.log').read_text(encoding='utf-8', errors='replace')[-5000:])
sys.exit(actual.returncode)
