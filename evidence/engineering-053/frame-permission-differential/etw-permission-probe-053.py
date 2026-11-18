"""Bounded per-provider ETW permission probe, only unique owned sessions."""
import argparse,ctypes,datetime,hashlib,json,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.frame_diagnostics.etw_diagnostic import WindowsBackend,load_profile,run_command,write_new
p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'.cache') and not out.exists();out.mkdir(parents=True)
backend=WindowsBackend();profile=load_profile();rows=[]
write_new(out/'context.json',{'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elevated':bool(ctypes.windll.shell32.IsUserAnAdmin()),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Per-provider permission only; not a frame measurement; no permission changes'})
for provider in profile['providers']:
 folder=out/provider['name'];folder.mkdir();name='mtr-frame-diagnostic-'+str(uuid.uuid4());before=backend.query(name);write_new(folder/'before.json',before);assert before['status']==4201
 token=None;errors=[];receipt=None
 try:
  args=[str(backend.system32/'logman.exe'),'create','trace',name,'-ets','-p','{'+provider['guid']+'}',provider['keywords'],str(provider['level']),'-o',str(folder/'raw.etl'),'-f','bin','-ct','perf','-max','4']
  receipt=run_command(args,folder,'enable',timeout_seconds=15)
  token=backend.query(name);write_new(folder/'created.json',token)
  if receipt['exit_code']==0:time.sleep(.2)
 except BaseException as e:errors.append(repr(e))
 finally:
  if token is None:token=backend.query(name);write_new(folder/'recovery.json',token)
  if token['status']==0:write_new(folder/'stop.json',backend.stop_owned(token))
  after=backend.query(name);write_new(folder/'after.json',after);assert after['status']==4201,'Owned session did not close'
 row={'provider':provider['name'],'enable_exit':receipt['exit_code'] if receipt else None,'cleanup_absent':after['status']==4201,'errors':errors};rows.append(row);print(json.dumps(row),flush=True)
write_new(out/'assessment.json',{'providers':rows,'all_enabled':all(x['enable_exit']==0 and not x['errors'] for x in rows),'all_owned_sessions_closed':all(x['cleanup_absent'] for x in rows)})
