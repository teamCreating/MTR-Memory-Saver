import datetime as dt,hashlib,json,os,pathlib,subprocess,sys
root=pathlib.Path.cwd();base=root/'evidence/engineering-050/native-process-identity';out=base/sys.argv[1];out.mkdir(exist_ok=False)
files=['tools/windows_process_identity.py','tools/observe_packaged_client.py','tools/reload_before_recorder.py','tools/client_experiment.py','tools/test_windows_process_identity.py','tools/test_observe_packaged_client.py','tools/test_neutral_reload_adapter.py','tools/test_reload_before_recorder.py','tools/test_client_experiment.py','tools/windows_snapshot_io.py']
hashes={}
for name in files:
 data=(root/name).read_bytes();copy=out/'inputs'/name;copy.parent.mkdir(parents=True,exist_ok=True);copy.write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
argv=[sys.executable,'-X','utf8','-m','unittest','-v',*sys.argv[2:]]
env=dict(os.environ);env['PYTHONPATH']=str(root/'tools');env['MTR_IDENTITY_TEST_EVIDENCE']=str(out/'owned-child')
start=dt.datetime.now(dt.timezone.utc).isoformat()
with (out/'stdout.log').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
 process=subprocess.Popen(argv,cwd=root,env=env,stdout=stdout,stderr=stderr)
 receipt={'argv':argv,'cwd':str(root),'launcher_pid':process.pid,'started_at':start,'input_sha256':hashes,'pythonpath':env['PYTHONPATH'],'child_evidence':env['MTR_IDENTITY_TEST_EVIDENCE']}
 (out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');code=process.wait()
receipt.update({'exit_code':code,'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),'all_inputs_unchanged':all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in hashes.items())})
(out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt));print((out/'stderr.log').read_text(encoding='utf-8')[-10000:]);raise SystemExit(code)
