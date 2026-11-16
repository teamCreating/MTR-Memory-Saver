import datetime as dt,hashlib,json,os,pathlib,subprocess,sys
root=pathlib.Path.cwd();base=root/'evidence/engineering-049/observer-stop-control';out=base/'head-realtime-control-01';out.mkdir(exist_ok=False)
before=base/'source-before/tools'
names=['test_background_auxiliary_keeps_sampling_while_provider_is_blocked','test_background_auxiliary_missing_failed_or_exception_result_still_rejects','test_interrupted_main_sampling_preserves_accepted_auxiliary_result','test_interruption_after_completion_poll_preserves_unaccounted_result','test_interruption_after_submission_preserves_request_and_attempt_count','test_shutdown_completion_is_explicit_and_does_not_extend_route_window']
code="import hashlib,json,unittest,observe_packaged_client as observer,test_observe_packaged_client as tests;from pathlib import Path;print(json.dumps({'observer':observer.__file__,'observer_sha256':hashlib.sha256(Path(observer.__file__).read_bytes()).hexdigest(),'tests':tests.__file__}),flush=True);unittest.main(module=None,verbosity=2)"
argv=[sys.executable,'-X','utf8','-c',code,*['test_observe_packaged_client.ObservationTest.'+name for name in names]]
env=dict(os.environ);env['PYTHONPATH']=os.pathsep.join((str(before),str(root/'tools')))
started=dt.datetime.now(dt.timezone.utc).isoformat()
with (out/'stdout.log').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
 process=subprocess.Popen(argv,cwd=root,env=env,stdout=stdout,stderr=stderr)
 receipt={'argv':argv,'cwd':str(root),'pid':process.pid,'started_at':started,'pythonpath':env['PYTHONPATH'],'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in before.glob('*.py')}}
 (out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');result=process.wait()
receipt.update({'exit_code':result,'finished_at':dt.datetime.now(dt.timezone.utc).isoformat()})
(out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt));print((out/'stdout.log').read_text(encoding='utf-8'));print((out/'stderr.log').read_text(encoding='utf-8'))
