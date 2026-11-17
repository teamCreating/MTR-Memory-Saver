import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

root = Path.cwd()
base = Path(__file__).parent
sealed = root/'evidence/engineering-051/streamed-obj-input'
sealed.mkdir(exist_ok=False)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if digest(source) != digest(target): raise RuntimeError('Copy differs: '+str(source))
def data(path): return json.loads(path.read_bytes())
assessment = {'scope': 'Engineering and packaged-client checks for revised unpublished 0.4.8; no twenty-reload or performance acceptance',
              'sealed_at': dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
              'source_commit': subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(), 'targets': []}
for stage in ['02-final-nf248','03-final-nf265']:
    source = base/stage
    for path in source.rglob('*'):
        if path.is_file(): copy(path,sealed/'runs'/stage/path.relative_to(source))
    command=data(source/'command.json'); tests=data(source/'test-summary.json')
    if command['exit_code'] != 0 or data(source/'source-after.json')['changed']: raise RuntimeError('Build failed or drifted')
    if sum(int(x['tests']) for x in tests) != 105 or any(int(x[k]) for x in tests for k in ['failures','errors','skipped']): raise RuntimeError('Tests incomplete')
    for manifest in source.glob('*.build.json'):
        identity=data(manifest)
        if 'inputs' not in identity or 'acceptance-probe' in manifest.name: continue
        for name, expected in identity['inputs'].items():
            path=root/name
            if digest(path) != expected: raise RuntimeError('Manifest input differs: '+name)
            copy(path,sealed/'artifact-inputs'/name)
        if digest(source/identity['artifact']) != identity['sha256']: raise RuntimeError('Artifact identity differs')
    assessment['targets'].append({'stage':stage,'exit_code':0,'tests':105,'failures':0,'skipped':0,'source_drift':[]})
for path in (base/'04-string-negative').rglob('*'):
    if path.is_file(): copy(path,sealed/'string-negative'/path.relative_to(base/'04-string-negative'))
negative=data(base/'04-string-negative/command.json')
stderr=(base/'04-string-negative/stderr.log').read_text(encoding='utf-8',errors='replace')
if negative['exit_code'] != 1 or not negative['source_unchanged'] or 'java.lang.OutOfMemoryError' not in stderr or 'String.join' not in stderr: raise RuntimeError('Negative control differs')
assessment['negative_control']={'actual_exit_code':1,'string_join_oom':True,'scope':negative['scope']}
first=base/'01-targeted-failed'
for path in first.rglob('*'):
    if path.is_file() and path.suffix != '.bin': copy(path,sealed/'first-targeted-failure'/path.relative_to(first))
runtime=root/'.cache/acceptance/streamed-obj048-client-validation'
cases=[('nf248-smoke01','official-nf248-obj048-smoke01',57308,0),('nf265-smoke01','official-nf265-obj048-smoke01',62672,0),
       ('nf248-mismatch01','official-nf248-obj048-mismatch01',44564,1),('nf265-mismatch01','official-nf265-obj048-mismatch01',67416,1)]
assessment['clients']=[]
for label, name, pid, expected_exit in cases:
    capture=runtime/label; instance=root/'.cache/acceptance'/name
    execution=data(capture/'execution.json')
    if execution['status']!='exited' or execution['pid']!=pid or execution['exit_code']!=expected_exit: raise RuntimeError('Client exit differs')
    for path in capture.rglob('*'):
        if path.is_file(): copy(path,sealed/'clients'/label/'capture'/path.relative_to(capture))
    for name2 in ['loader-lifecycle-result.json','loader-lifecycle-request.json','vehicle-test-instance.json','options.txt']:
        if (instance/name2).is_file(): copy(instance/name2,sealed/'clients'/label/name2)
    if expected_exit==0:
        result=data(instance/'loader-lifecycle-result.json')
        groups=[result[key] for key in ['checks','strict_resource_checks','obj_input_checks']]
        if result['passed'] is not True or [len(group) for group in groups]!=[24,18,27] or any(value is not True for group in groups for value in group.values()): raise RuntimeError('Probe checks incomplete')
    else:
        error=(capture/'launch.stderr.log').read_text(encoding='utf-8',errors='replace')
        if 'Loaded MTR fingerprint does not match the audited build target' not in error or (instance/'loader-lifecycle-result.json').exists(): raise RuntimeError('Wrong binary was not rejected')
    jfr=instance/'acceptance.jfr'
    java=Path(data(capture/'packaged-client-plan.json')['java'])
    argv=[str(java.with_name('jfr.exe')),'summary',str(jfr)]
    actual=subprocess.run(argv,capture_output=True)
    dest=sealed/'clients'/label
    (dest/'jfr-summary.stdout.log').write_bytes(actual.stdout); (dest/'jfr-summary.stderr.log').write_bytes(actual.stderr)
    if actual.returncode: raise RuntimeError('JFR not readable')
    info={'pid':pid,'jvm_exit_code':expected_exit,'jfr_summary_argv':argv,'jfr_summary_exit':actual.returncode,'jfr_bytes':jfr.stat().st_size,'jfr_sha256':digest(jfr)}
    (dest/'jfr-check.json').write_text(json.dumps(info,indent=2)+'\n',encoding='utf-8')
    assessment['clients'].append({'case':label,**info})
for name in ['run.py','negative.py','seal.py']:
    copy(base/name,sealed/'scripts'/name)
assessment['runner_scope']='Java/build source pins are pre/post-run. Runner source copies are retained after completed invocations, not represented as pre-frozen terminal receipts.'
assessment['runtime_scope']='execution.exit_code is actual owned JVM wait; collector Python wrapper terminal codes remain parent-reported unless separately recorded. No JFR/MTR/world/dependency binary is copied.'
(sealed/'assessment.json').write_text(json.dumps(assessment,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'sealed':str(sealed),'targets':assessment['targets'],'clients':len(cases)}),flush=True)
