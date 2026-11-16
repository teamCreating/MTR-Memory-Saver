import datetime as dt,hashlib,json,os,pathlib,subprocess,sys
root=pathlib.Path.cwd();base=root/'evidence/engineering-049/observer-stop-control'
tag=sys.argv[1];args=sys.argv[2:];out=base/tag;out.mkdir(exist_ok=False)
files=['tools/observe_packaged_client.py','tools/test_observe_packaged_client.py','tools/windows_snapshot_io.py','tools/reload_before_recorder.py','tools/client_experiment_analysis.py','tools/native_diagnostic_review.py','tools/test_neutral_reload_adapter.py','tools/test_reload_before_recorder.py','config/native-observer-consumer.json','config/native-diagnostic-review.json']
hashes={}
for name in files:
 source=root/name;data=source.read_bytes();copy=out/'inputs'/name;copy.parent.mkdir(parents=True,exist_ok=True);copy.write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
for name in files[:2]:
 data=subprocess.check_output(['git','show',f'HEAD:{name}']);copy=base/'source-before'/name
 if not copy.exists():copy.parent.mkdir(parents=True,exist_ok=True);copy.write_bytes(data)
argv=[sys.executable,'-X','utf8','-m','unittest','-v',*args]
env=dict(os.environ);env['PYTHONPATH']=str(root/'tools')
start=dt.datetime.now(dt.timezone.utc).isoformat()
with (out/'stdout.log').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
 process=subprocess.Popen(argv,cwd=root,env=env,stdout=stdout,stderr=stderr)
 receipt={'argv':argv,'cwd':str(root),'pid':process.pid,'started_at':start,'python':sys.executable,'pythonpath':env['PYTHONPATH'],'input_sha256':hashes}
 (out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
 code=process.wait()
receipt.update({'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),'exit_code':code,'source_bytes_unchanged':all(hashlib.sha256((root/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())})
(out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))
print((out/'stderr.log').read_text(encoding='utf-8')[-8000:])
raise SystemExit(code)
