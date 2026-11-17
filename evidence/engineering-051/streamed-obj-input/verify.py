import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def read(path): return json.loads(path.read_bytes())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
index=read(ROOT/'SHA256.json')
for name, item in index.items():
    path=ROOT/name
    assert path.is_file() and path.stat().st_size==item['bytes'] and sha(path)==item['sha256'], name
actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p.name!='SHA256.json' and '__pycache__' not in p.parts}
assert actual==set(index), 'Payload file set differs'
for stage in ['02-final-nf248','03-final-nf265']:
    run=ROOT/'runs'/stage
    assert read(run/'command.json')['exit_code']==0
    assert read(run/'source-after.json')['changed']==[]
    for name, expected in read(run/'source-sha256.json').items(): assert sha(run/'sources'/name)==expected, name
    suites=read(run/'test-summary.json')
    assert sum(int(x['tests']) for x in suites)==105
    assert not any(int(x[k]) for x in suites for k in ['failures','errors','skipped'])
    for name, record in read(run/'artifact-sha256.json').items():
        path=run/name
        assert path.stat().st_size==record['bytes'] and sha(path)==record['sha256'], name
    for path in run.glob('*.build.json'):
        meta=read(path)
        if 'inputs' not in meta or 'acceptance-probe' in path.name: continue
        assert sha(run/meta['artifact'])==meta['sha256']
        for name, expected in meta['inputs'].items(): assert sha(ROOT/'artifact-inputs'/name)==expected, name
negative=read(ROOT/'string-negative/command.json')
assert negative['exit_code']==1 and negative['source_unchanged'] is True
error=(ROOT/'string-negative/stderr.log').read_text(encoding='utf-8')
assert 'java.lang.OutOfMemoryError' in error and 'String.join' in error
for item in read(ROOT/'assessment.json')['clients']:
    client=ROOT/'clients'/item['case']; capture=client/'capture'
    execution=read(capture/'execution.json')
    assert execution['status']=='exited' and execution['pid']==item['pid'] and execution['exit_code']==item['jvm_exit_code']
    assert read(client/'jfr-check.json')['jfr_summary_exit']==0
    if item['jvm_exit_code']==0:
        result=read(client/'loader-lifecycle-result.json')
        assert result['passed'] is True
        groups=[result[x] for x in ['checks','strict_resource_checks','obj_input_checks']]
        assert [len(x) for x in groups]==[24,18,27]
        assert all(value is True for group in groups for value in group.values())
    else:
        assert item['jvm_exit_code']==1
        assert not (client/'loader-lifecycle-result.json').exists()
        assert 'Loaded MTR fingerprint does not match the audited build target' in (capture/'launch.stderr.log').read_text(encoding='utf-8')
print(json.dumps({'passed':True,'payloads':len(index),'scope':'Sealed engineering and four packaged JVM outcomes only; no endurance/performance pass'}))
