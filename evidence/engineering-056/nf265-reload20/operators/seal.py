"""Select a literal closed twenty-reload proof; never controls or queries a process."""
from pathlib import Path, PureWindowsPath
import argparse, datetime, hashlib, json, shutil

parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
repo=Path.cwd().resolve();cache=repo/'.cache/acceptance'
run=cache/'release048-nf265';rec=run/'recorder03';obs=run/'consumer03';settled=run/'post20';collector=run/'endurance'
def read(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def lines(p):return [json.loads(x) for x in p.read_bytes().splitlines() if x]
summary=read(obs/'summary.json');end=read(rec/'session-end.json');post=read(settled/'summary.json');execution=read(run/'closed-execution.json')
assert summary['status']=='reloads_verified' and summary['passed'] is True and summary['verified_reload_count']==summary['longest_verified_reload_run']==20
assert end['status']=='stopped' and end['process_handle_closed'] is True
assert post['status']=='settled' and post['passed'] is True and post['baseline_completed_epoch_sequence']==22
assert execution['status']=='exited' and execution['exit_code']==0
out=args.output.resolve();assert out.is_relative_to(repo/'evidence') and not out.exists();out.mkdir(parents=True)
receipts=[]
def copy(source,relative):
 source=source.resolve(strict=True);dest=out/relative;assert source.is_relative_to(repo) and source.suffix.lower()!='.jfr';assert dest.resolve().is_relative_to(out)
 a=source.stat();raw=source.read_bytes();b=source.stat();assert (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns),str(source)
 if dest.exists():assert dest.read_bytes()==raw;return
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
 receipts.append({'source':str(source),'destination':dest.relative_to(out).as_posix(),'bytes':len(raw),'sha256':sha(raw),'before_mtime_ns':a.st_mtime_ns,'after_mtime_ns':b.st_mtime_ns})
def tree(source,relative):
 for p in source.rglob('*'):
  if p.is_file() and '__pycache__' not in p.parts:copy(p,relative/p.relative_to(source))
def flat(source,relative,exclude=()):
 for p in source.iterdir():
  if p.is_file() and p.name not in exclude:copy(p,relative/p.name)
def log_closure(source,relative,reference):
 flat(source,relative)
 p=(source/reference['receipt']).resolve();assert p.is_relative_to(source.resolve())
 copy(p,relative/reference['receipt']);data=read(p)
 assert sha(p.read_bytes())==reference['receipt_sha256']
 for segment in data['segments']:copy(source/segment['blob'],relative/segment['blob'])
flat(rec,Path('recorder'));tree(rec/'sources',Path('recorder/sources'));tree(rec/'input-attempts',Path('recorder/input-attempts'))
flat(obs,Path('observer'));log_closure(obs/'native-log',Path('observer/native-log'),summary['native_log_stream'])
flat(settled,Path('post20'));log_closure(settled/'native-log',Path('post20/native-log'),post['native_log_stream'])
inputs=lines(rec/'inputs.jsonl');assert len(inputs)==20 and all(e['record_status']=='selected' and e['input']['succeeded'] is True for e in inputs)
retained={int(e['event_id'].rsplit(':',1)[1]) for e in inputs};histories=[]
for number in range(1,20):
 source=run/f'ready-{number+2:03d}';v=read(source/'result.json');assert v['status']=='ready' and v['verified_reload_count']==v['longest_verified_reload_run']==number
 assert read(source/'execution.json')['returned_exit_code']==0
 tree(source,Path('waiters')/f'{number:03d}');record=int(v['capture_record_id'].rsplit(':',1)[1]);retained.add(record);histories.append({'number':number,'record_number':record})
journal=lines(rec/'journal.jsonl');last=next(row['event'] for row in reversed(journal) if row['event']['kind'] in ['published','ineligible','capture_failed']);assert last['kind']=='published';retained.add(int(last['record_id'].rsplit(':',1)[1]))
for number in sorted(retained):
 source=rec/'records'/f'{number:08d}';target=Path('recorder/records')/source.name;flat(source,target)
 for row in lines(source/'raw-evidence.jsonl'):copy(rec/row['path'],Path('recorder')/row['path'])
 record=read(source/'before.json');log_closure(rec/'native-log',Path('recorder/native-log'),record['native_log_stream'])

for number in range(3,23):copy(run/f'input-{number:03d}.json',Path('ui')/f'reload-{number-2:03d}.json')

for name in ['packaged-client-plan.json','packaged-client-launch.json']:copy(collector/name,Path('collector-final')/name)
copy(run/'closed-execution.json',Path('collector-final/execution.json'))
copy(run/'endurance-owned-exit.json',Path('collector-final/endurance-owned-exit.json'))
for directory in ['game-probe','logs']:
 if (collector/directory).is_dir():tree(collector/directory,Path('collector-final')/directory)
tree(run/'jfr-readability',Path('jfr-readability'))
copy(run/'installed-fingerprints.json',Path('installed-fingerprints.json'))
copy(run/'candidate.jar',Path('candidate.jar'))
old=repo/'evidence/engineering-051/streamed051a-reload-oom/capture-01'
tree(old/'proof-root',Path('proof-root'));copy(old/'operators/wait_reload_ready.py',Path('operators/wait_reload_ready.py'));copy(Path(__file__),Path('operators/seal.py'))
(out/'closure-bindings.json').write_text(json.dumps({'retained_record_numbers':sorted(retained),'histories':histories,'final_record_number':int(last['record_id'].rsplit(':',1)[1]),'candidate_reference':'candidate.jar','candidate_sha256':'920c1f833b6f173c7443ff5956493b779acfeceb293fa640817a459985db3f5b','copied_at':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)+'\n',encoding='utf-8')
(out/'read-receipts.json').write_text(json.dumps({'reads':receipts},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'copied_files':len(receipts),'retained_records':len(retained),'scope':'Unindexed draft closure; independent verification still required'}))
