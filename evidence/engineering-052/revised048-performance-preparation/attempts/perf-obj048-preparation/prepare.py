from pathlib import Path
import json,sys,subprocess,datetime,hashlib
r=Path.cwd();root=Path(__file__).resolve().parent
for role in ['baseline','candidate']:
 for mode in ['plain','profile']:
  label=role+'-'+mode;out=root/label;out.mkdir(exist_ok=False)
  companion=(r/'.cache/acceptance/official-nf248-perf-049-baseline-plain/mods/mtr-memory-sharing-neoforge-v030-nf248.jar') if role=='baseline' else (r/'evidence/engineering-051/streamed-obj-input/runs/02-final-nf248/mtr-memory-saver-official-nf248-0.4.8.jar')
  args=[sys.executable,'-u','-X','utf8','tools/packaged_client.py','prepare','--source',str(r.parent/'.cache/game-test/nf248-official-3g'),'--instance',str(r/'.cache/acceptance'/('official-nf248-perf-obj048-'+label)),'--companion',str(companion),'--observer',str(r/'.cache/acceptance/official-nf248-obj048-full02/mods/mtr-native-observer-official-nf248-1.0.3.jar'),'--catalogue',str(r.parent/'[MTR4.1原生目录]产物/catalog.json'),'--world','Vehicle Acceptance 1_21_1','--username','VehicleTest','--heap-mib','3072','--initial-heap-mib','512','--performance','--controls',str(root/'context.json')]
  if role=='baseline':args+=['--legacy-baseline','official-030-nf248']
  if mode=='profile':args+=['--jfr']
  receipt={'argv':args,'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'companion_sha256':hashlib.sha256(companion.read_bytes()).hexdigest(),'scope':'Preparation only; no qualification, trials or observer-off calibration'}
  with (out/'stdout.log').open('xb') as o,(out/'stderr.log').open('xb') as e:
   p=subprocess.Popen(args,stdout=o,stderr=e);receipt['pid']=p.pid;receipt['exit_code']=p.wait()
  receipt['ended']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(label,receipt['exit_code'],flush=True)
  if receipt['exit_code']:raise SystemExit(receipt['exit_code'])
