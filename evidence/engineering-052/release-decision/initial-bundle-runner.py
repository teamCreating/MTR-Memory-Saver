from pathlib import Path
import json,subprocess,datetime,os,shutil,hashlib,zipfile
r=Path.cwd();o=r/'.cache/acceptance/revised048-final-bundles';o.mkdir(exist_ok=False);env=os.environ.copy();env['JAVA_HOME']=r'C:\Users\ben_l\Saved Games\Yuuniverse 1.20.1 Shenyang\porting-output\work\tools\jdk21\jdk-21.0.11+10';env['PATH']=env['JAVA_HOME']+r'\bin;'+env['PATH']
def run(args,folder,label):
 v={'argv':args,'started':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 with (folder/(label+'.stdout.log')).open('xb') as out,(folder/(label+'.stderr.log')).open('xb') as err:
  p=subprocess.Popen(args,stdout=out,stderr=err,env=env);v['pid']=p.pid;v['exit_code']=p.wait()
 v['ended']=datetime.datetime.now(datetime.timezone.utc).isoformat();(folder/(label+'.execution.json')).write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8');assert v['exit_code']==0;print(label,v['exit_code'],flush=True)
assets=o/'assets';assets.mkdir();records=[]
for target,expected in [('official-nf248','943b3d455fa3ce9d3ede74bc1a2071ece7bf70b09d9b7f829027347b53a9b588'),('official-nf265','134770acd53ec81325993604e8441d213d9ea1be990adb3bc2877b0cb7cc17dd')]:
 d=o/target;d.mkdir();run([str(r/'gradlew.bat'),'-Ptarget='+target,'verifyRelease','releaseBundle'],d,'build')
 name=f'mtr-memory-saver-{target}-0.4.8.zip';shutil.copyfile(r/'build/releases'/name,assets/name)
 with zipfile.ZipFile(assets/name) as z:
  jar=f'mtr-memory-saver-{target}-0.4.8.jar';assert hashlib.sha256(z.read(jar)).hexdigest()==expected;assert json.loads(z.read('docs/VALIDATION.json'))['status']=='verified-packaged-scope';assert b'twenty consecutive full-pack' in z.read('README.md')
 records.append({'target':target,'bundle':name,'bundle_sha256':hashlib.sha256((assets/name).read_bytes()).hexdigest(),'jar_sha256':expected,'publication_status':'held_for_unverified_performance'})
for action in ['checksums','verify-assets']:run(['python','-X','utf8','tools/ci.py',action,str(assets)],o,action)
(o/'assessment.json').write_text(json.dumps({'bundles':records,'performance_accepted':False,'release_accepted':False},indent=2)+'\n',encoding='utf-8')
