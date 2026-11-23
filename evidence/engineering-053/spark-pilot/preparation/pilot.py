from pathlib import Path
from types import SimpleNamespace
import datetime,json,sys,time,zipfile
ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'tools'),str(ROOT)]
import packaged_client as client
from observe_packaged_client import WindowsProcess
from windows_snapshot_io import read_snapshot_bytes
out=Path(__file__).resolve().parent/'pilot01';out.mkdir(exist_ok=False)
instance=ROOT/'.cache/acceptance/official-nf248-spark048-pilot01'
plan=client.read(instance/'packaged-client-plan.json')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
save('intent.json',{'started':now(),'scope':'Spark compatibility and local-file CPU sampler pilot, not scheduled performance qualification','plan_sha256':client.digest(instance/'packaged-client-plan.json'),'source_sha256':client.digest(Path(__file__))})
process=client.launch(SimpleNamespace(instance=instance,wait_seconds=None));launch=client.read(instance/'packaged-client-launch.json');observer=WindowsProcess(plan,launch)
save('actual-process.json',{**observer.identity,'created':observer.created});save('launch.json',launch)
metadata=None
for mod in plan['mods']:
 if mod['role']=='observer':
  with zipfile.ZipFile(instance/'mods'/mod['filename']) as z:metadata=json.loads(z.read('mtr-native-observer-target.json'))
assert metadata is not None
print(json.dumps({'pid':process.pid,'created':observer.created}),flush=True)
try:
 with (out/'samples.jsonl').open('x',encoding='utf-8') as stream:
  while process.poll() is None:
   sample={'observed_at':now(),'os':observer.sample(),'native':None,'errors':[]}
   try:
    raw=read_snapshot_bytes(instance/metadata['snapshot_path']);sample['native']=json.loads(raw)
   except Exception as error:sample['errors'].append(repr(error))
   stream.write(json.dumps(sample,ensure_ascii=False)+'\n');stream.flush();time.sleep(2)
 save('execution.json',{'pid':process.pid,'exit_code':process.wait(),'ended':now(),'scope':'Actual owned JVM wait result'})
finally:observer.close()
