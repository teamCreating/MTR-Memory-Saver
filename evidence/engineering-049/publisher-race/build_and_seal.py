import datetime as dt, hashlib, json, os, pathlib, shutil, subprocess, xml.etree.ElementTree as ET
root=pathlib.Path.cwd()
base=root/'evidence/engineering-049/publisher-race/sealed-01'
base.mkdir(parents=True,exist_ok=False)
marker=json.loads((root.parent/'.cache/game-test/neoforge-instance/vehicle-test-instance.json').read_text(encoding='utf-8'))
java=pathlib.Path(marker['java'])
env=dict(os.environ); env['JAVA_HOME']=str(java.parent.parent)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
product={p.relative_to(root).as_posix():sha(p) for p in (root/'build/libs').glob('mtr-memory-saver-official-*-0.4.7.jar')}
(base/'product-before.json').write_text(json.dumps(product,indent=2)+'\n',encoding='utf-8')
results=[]
for target in ('official-nf248','official-nf265'):
    out=base/target;out.mkdir()
    argv=[str(root/'gradlew.bat'),'--no-daemon','--console=plain',f'-Ptarget={target}','neutralProbeJar','verifyNeutralProbe','--rerun-tasks']
    started=dt.datetime.now(dt.timezone.utc).isoformat()
    with (out/'stdout.log').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
        process=subprocess.Popen(argv,cwd=root,env=env,stdout=stdout,stderr=stderr)
        receipt={'argv':argv,'cwd':str(root),'started_at':started,'pid':process.pid,'java_home':env['JAVA_HOME'],'java_sha256':sha(java)}
        (out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        code=process.wait()
    receipt.update({'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),'exit_code':code,'stdout_sha256':sha(out/'stdout.log'),'stderr_sha256':sha(out/'stderr.log')})
    (out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    if code: raise SystemExit(f'{target} failed: {code}')
    suites=[]
    junit=out/'junit'; junit.mkdir()
    for file in sorted((root/'build/test-results/neutralProbeTest').glob('TEST-*.xml')):
        shutil.copyfile(file,junit/file.name)
        xml=ET.parse(file).getroot()
        suites.append({k:xml.attrib[k] for k in ('name','tests','failures','errors','skipped')})
    jar=root/f'build/libs/mtr-native-observer-{target}-1.0.3.jar'
    manifest=jar.with_suffix('.build.json')
    for file in (jar,manifest):shutil.copyfile(file,out/file.name)
    result={'target':target,'artifact':str(jar),'sha256':sha(jar),'manifest':str(manifest),'manifest_sha256':sha(manifest),'suites':suites}
    results.append(result)
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'target':target,'sha256':result['sha256'],'tests':sum(int(s['tests']) for s in suites),'failed':sum(int(s['failures'])+int(s['errors']) for s in suites)}),flush=True)
assert product=={p:sha(root/p) for p in product}
(base/'build-assessment.json').write_text(json.dumps({'targets':results,'product_jars_byte_unchanged':True,'scope':'Probe engineering only; no game launch, gameplay, reload or performance acceptance.'},indent=2)+'\n',encoding='utf-8')
