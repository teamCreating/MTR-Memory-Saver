from pathlib import Path
import os,sys,subprocess,json,datetime,hashlib
r=Path.cwd();root=r/'.cache/acceptance/revised048-delivery-build';root.mkdir(exist_ok=False)
env=os.environ.copy();env['JAVA_HOME']=r'C:\Users\ben_l\Saved Games\Yuuniverse 1.20.1 Shenyang\porting-output\work\tools\jdk21\jdk-21.0.11+10';env['PATH']=env['JAVA_HOME']+r'\bin;'+env['PATH']
for target in ['official-nf248','official-nf265']:
 out=root/target;out.mkdir();args=[str(r/'gradlew.bat'),'-Ptarget='+target,'verifyRelease','releaseBundle'];receipt={'argv':args,'started':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 with (out/'stdout.log').open('xb') as o,(out/'stderr.log').open('xb') as e:
  p=subprocess.Popen(args,stdout=o,stderr=e,env=env);receipt['pid']=p.pid;receipt['exit_code']=p.wait()
 receipt['ended']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(target,receipt['exit_code'],flush=True)
 if receipt['exit_code']:raise SystemExit(receipt['exit_code'])
