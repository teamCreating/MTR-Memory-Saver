"""Offline replay of the sealed full twenty-reload session."""
import hashlib, importlib.util, json, sys
from pathlib import Path, PureWindowsPath
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
def read(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def check(v,msg):
 if not v:raise ValueError(msg)
def rows(p):return [json.loads(x) for x in p.read_bytes().splitlines() if x]
def verify():
 index=read(HERE/'SHA256.json')['files'];actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file()}
 check(actual==set(index)|{'SHA256.json'},'Payload namespace differs')
 for n,v in index.items():
  b=(HERE/n).read_bytes();check(len(b)==v['bytes'] and sha(b)==v['sha256'],'Payload differs: '+n)
 for v in read(HERE/'read-receipts.json')['reads']:
  b=(HERE/v['destination']).read_bytes();check(len(b)==v['bytes'] and sha(b)==v['sha256'] and v['before_mtime_ns']==v['after_mtime_ns'],'Read-time copy differs')
 sys.path.insert(0,str(HERE/'operators'));import wait_reload_ready as core
 spec=importlib.util.spec_from_file_location('sealed_producer',HERE/'operators/sealed_producer.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 core.ROOT=HERE/'proof-root';rec=HERE/'recorder';obs=HERE/'observer';summary=read(obs/'summary.json');binding=read(HERE/'closure-bindings.json')
 with helper.create_producer(core,HERE) as p:
  check(p.plan['artifact']['version']=='0.4.8' and p.plan['artifact']['target']=='official-nf265','Candidate target/version differs')
  check(p.plan['heap_mib']==3072 and p.plan['initial_heap_mib']==512 and '-Xmx3072M' in p.launch['jvm_arguments'] and '-Xms512M' in p.launch['jvm_arguments'],'Frozen heap differs')
  check(len(p.plan['packs'])==16 and len({x['filename'] for x in p.plan['packs']})==16,'Full sixteen-pack scope differs')
  check(p.context['expected_registration']=={'distinct_ids':1091,'declarations':1092},'Native catalogue registration scope differs')
  journal_raw=(rec/'journal.jsonl').read_bytes();journal=p.rec.verify_journal(journal_raw);end=read(rec/'session-end.json')
  check(end['status']=='stopped' and end['process_handle_closed'] and end['journal_sha256']==sha(journal_raw),'Recorder did not close cleanly')
  check(journal[-1]['event']['kind']=='stopped','Recorder journal lacks terminal close')
  inputs=p.rec.input_events(rec);check(len(inputs)==20 and all(e['record_status']=='selected' and e['input']['succeeded'] is True for e in inputs),'Twenty literal inputs required')
  check((rec/'inputs.jsonl').read_bytes()==(obs/'external-input-events-at-completion.jsonl').read_bytes(),'Input exports differ')
  for n,e in enumerate(inputs,1):
   ui_path=HERE/'ui'/f'reload-{n:03d}.json';ui=read(ui_path)
   check(sha(ui_path.read_bytes())==e['external_receipt_sha256'],'UI receipt differs')
   check(ui['succeeded'] is True and ui['method']=='native_f3_t' and ui==e['input'],'UI method/receipt differs')
  raw=(obs/'samples.jsonl').read_bytes();samples=p.rec.json_lines(raw);observations=[x['observation'] for x in samples if x.get('observation',{}).get('verified')]
  check(sha(raw)==summary['samples_sha256'] and len(samples)==summary['sample_count'] and len(observations)==summary['verified_sample_count'],'Sample inventory differs')
  check(all(x['process']['running'] for x in samples),'Main consumer observed an exit')
  baseline=observations[0]['state']['resource_epochs']['last_completed_sequence'];check(baseline==summary['baseline_completed_epoch_sequence']==2,'Recorded post-calibration baseline differs')
  ref=summary['native_log_stream'];check(sha((obs/'native-log'/ref['receipt']).read_bytes())==ref['receipt_sha256'],'Completion receipt differs')
  log=p.logs.verify_capture(obs/'native-log',obs/'native-log'/ref['receipt']);check(log==(obs/'native-log-at-completion.log').read_bytes() and sha(log)==summary['log_sha256_at_completion'],'Completion log differs')
  epochs=rows(obs/'native-epoch-events-at-completion.jsonl');diagnostics=rows(obs/'native-diagnostic-events-at-completion.jsonl')
  def replay(log,events,ep,di,eligible,finish):
   return p.observer.neutral_reload_evidence(log,events,ep,di,eligible,baseline,p.launch,p.context['process'],p.context['expected_registration']['distinct_ids'],p.context['expected_registration']['declarations'],p.metadata,p.review,p.plan['timestamp'],finish)
  results,review=replay(log,inputs,epochs,diagnostics,observations,summary['ended'])
  check(results==summary['reload_evidence'] and review==summary['native_diagnostics'],'Full canonical replay differs')
  check(summary['status']=='reloads_verified' and summary['passed'] is True and summary['verified_reload_count']==summary['longest_verified_reload_run']==20,'Main consumer did not accept twenty')
  check(len(results)==20 and all(x['verified'] for x in results) and [x['sequence'] for x in results]==list(range(3,23)),'Reload sequence is incomplete')
  check([x['sequence'] for x in epochs if x['phase']=='start']==list(range(1,23)) and [x['sequence'] for x in epochs if x['phase']=='return']==list(range(1,23)),'Native epochs contain missing or extra pairs')
  check(not review['unreviewed_native'] and review['native_attribution']['passed'],'Unreviewed native errors remain')
  for field in ['native_log_source_sha256','neutral_source_sha256']:
   for original,expected in summary[field].items():check(sha((obs/PureWindowsPath(original).name).read_bytes())==expected,'Consumer dependency differs')
  check(not summary['source_changed_during_observation'] and not summary['neutral_sources_changed'] and not summary['native_log_sources_changed'],'Source drift recorded')
  check(summary['source_sha256']==summary['current_source_sha256']==sha((obs/'observer-source.py').read_bytes()),'Main consumer source pin differs')
  check(summary['auxiliary_shutdown']['worker_stopped'] and not summary['auxiliary_shutdown']['uncompleted_request_ids'],'Main auxiliary work did not close')
  for number in binding['retained_record_numbers']:
   folder=rec/'records'/f'{number:08d}'
   for item in rows(folder/'raw-evidence.jsonl'):
    b=p.rec.owned_path(rec,item['path']).read_bytes();check(len(b)==item['bytes'] and sha(b)==item['sha256'],'Closed raw record differs')
   record=read(folder/'before.json');ref=record['native_log_stream'];closed=p.logs.verify_capture(rec/'native-log',rec/'native-log'/ref['receipt'])
   check(closed==p.rec.owned_path(rec,record['raw_files']['client-log-prefix.log']).read_bytes(),'Record log closure differs')
  histories=[]
  for item in binding['histories']:
   n=item['number'];folder=HERE/'waiters'/f'{n:03d}';saved=read(folder/'result.json');execution=read(folder/'execution.json')
   check(saved['status']=='ready' and execution['returned_exit_code']==0 and execution['source_sha256']==sha((HERE/'operators/wait_reload_ready.py').read_bytes())==sha((folder/'waiter-source.py').read_bytes()),'Original waiter source/result differs')
   sample_receipt=next(x for x in saved['read_receipts'] if PureWindowsPath(x['path']).name=='samples.jsonl');prefix=raw[:sample_receipt['bytes']];check(sha(prefix)==sample_receipt['sha256'],'Original sample prefix differs')
   local=p.rec.json_lines(prefix);eligible=[x['observation'] for x in local if x.get('observation',{}).get('verified')];record=read(rec/'records'/f"{item['record_number']:08d}"/'before.json');ref=record['native_log_stream'];local_log=p.logs.verify_capture(rec/'native-log',rec/'native-log'/ref['receipt'])
   check(sha(local_log)==saved['log_sha256'] and log.startswith(local_log),'Original ready log prefix differs')
   ep=p.rec.json_lines(p.rec.owned_path(rec,record['raw_files']['epochs-after.jsonl']).read_bytes());di=p.rec.json_lines(p.rec.owned_path(rec,record['raw_files']['diagnostics-after.jsonl']).read_bytes())
   replayed,_=replay(local_log,inputs[:n],ep,di,eligible,local[-1]['timestamp']);compact=[{'event_id':x['event']['event_id'],'sequence':x.get('sequence'),'verified':x['verified'],'failures':x['failures']} for x in replayed]
   check(compact==saved['reloads'] and len(replayed)==n and all(x['verified'] for x in replayed),'Interim canonical replay differs')
   returned=next(x for x in ep if x['phase']=='return' and x['sequence']==n+2);stability=core.trailing_stability(local,n+2,returned['monotonic_nanos'],summary['policy']['interval']+summary['policy']['freshness_seconds'])
   check(stability==saved['stability'] and stability['consumer_seconds']>=60 and stability['native_seconds']>=60,'Measured stable spans differ')
   check(p.observer.instant(execution['completed_at'])<p.observer.instant(inputs[n]['input']['issued_at']),'Next input preceded readiness')
   histories.append(n)
  check(histories==list(range(1,20)),'Nineteen original interim checks required')
  post=HERE/'post20';ps=read(post/'summary.json');check(ps['status']=='settled' and ps['passed'] is True and ps['baseline_completed_epoch_sequence']==22,'Independent post20 check failed')
  check(p.observer.instant(ps['started'])>=p.observer.instant(summary['ended']),'Post20 observer overlaps main consumer')
  pr=ps['native_log_stream'];pl=p.logs.verify_capture(post/'native-log',post/'native-log'/pr['receipt']);check(pl.startswith(log) and sha(pl)==ps['log_sha256_at_completion'],'Post20 complete log differs')
  pdata=rows(post/'samples.jsonl');check(sha((post/'samples.jsonl').read_bytes())==ps['samples_sha256'],'Post20 samples differ')
  stable=core.trailing_stability(pdata,22,next(x for x in epochs if x['phase']=='return' and x['sequence']==22)['monotonic_nanos'],ps['policy']['interval']+ps['policy']['freshness_seconds'])
  check(stable['consumer_seconds']>=60 and stable['native_seconds']>=60,'Independent final stability is too short')
  check(not ps['native_diagnostics']['unreviewed_native'] and ps['native_diagnostics']['native_attribution']['passed'],'Post20 diagnostic review failed')
  check(not ps['source_changed_during_observation'] and not ps['neutral_sources_changed'] and not ps['native_log_sources_changed'],'Post20 source drift recorded')
  check(ps['auxiliary_shutdown']['worker_stopped'] and not ps['auxiliary_shutdown']['uncompleted_request_ids'],'Post20 auxiliary work did not close')
  jar=HERE/binding['candidate_reference'];check(sha(jar.read_bytes())==binding['candidate_sha256']==p.plan['artifact']['sha256'],'Tested artifact differs')
  installed=read(HERE/'installed-fingerprints.json')['files'];expected={'mods/'+x['filename']:x['sha256'] for x in p.plan['mods']};expected.update({'resourcepacks/'+x['filename']:x['sha256'] for x in p.plan['packs']})
  check(len(installed)==len(expected)==19 and {x['relative_path'] for x in installed}==set(expected),'Installed file scope differs')
  check(all(x['sha256']==x['expected_sha256']==expected[x['relative_path']] and x['before_mtime_ns']==x['after_mtime_ns'] and x['binary_copied'] is False for x in installed),'Installed file hashes differ')
  collector=read(HERE/'collector-final/execution.json');check(collector['status']=='exited' and collector['exit_code']==0 and collector['pid']==p.launch['pid'],'Owned JVM did not exit normally')
  owned=read(HERE/'collector-final/endurance-owned-exit.json');check(owned['exit_code']==0 and owned['pid']==p.launch['pid'],'Owned wait receipt differs')
  for name,expected in collector['files'].items():
   if name=='native-snapshots.jsonl':continue
   relative=PureWindowsPath(name);check(not relative.is_absolute() and '..' not in relative.parts,'Collector path escapes scope')
   check(sha((HERE/'collector-final'/Path(*relative.parts)).read_bytes())==expected,'Closed process payload differs: '+name)
  final_log=(HERE/'collector-final/logs/latest.log').read_bytes();final_snapshot=read(HERE/'collector-final/game-probe/native-observer.json')
  final_review=p.diagnostics.review_diagnostics(p.analysis.native_diagnostics(final_log.decode('utf-8')),final_log.decode('utf-8'),rows(HERE/'collector-final/game-probe/native-invalid-model.jsonl'),rows(HERE/'collector-final/game-probe/native-resource-epochs.jsonl'),p.context['process'],p.metadata,p.review,{'start':p.plan['timestamp'],'end':collector['ended']},final_snapshot)
  check(not final_review['unreviewed_native'] and final_review['native_attribution']['passed'],'Late process diagnostic failure')
  jfr=read(HERE/'jfr-readability/check.json');check(jfr['pid']==p.launch['pid'] and jfr['summary_exit']==0 and jfr['bytes']>0 and len(jfr['sha256'])==64 and jfr['before_mtime_ns']==jfr['after_mtime_ns'] and jfr['binary_copied'] is False,'Final JFR metadata differs')
  check(read(HERE/'jfr-readability/execution.json')['exit_code']==0 and b'Version:' in (HERE/'jfr-readability/summary.stdout.log').read_bytes(),'Final JFR summary failed')
 print(json.dumps({'passed':True,'reloads':20,'interim_stable_checks':histories,'post20_stability':stable,'payloads':len(index),'scope':'NF265 full16pack lifecycle and reload endurance only; no performance acceptance'}))
if __name__=='__main__':verify()
