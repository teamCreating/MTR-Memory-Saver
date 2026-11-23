"""Read and hash this closed owned runtime; never send game input."""
from pathlib import Path
import datetime as dt, hashlib, json, shutil, subprocess

root=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def fingerprint(p):
 a=p.stat()
 with p.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
 b=p.stat()
 assert (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)
 return {'bytes':b.st_size,'sha256':digest,'before_mtime_ns':a.st_mtime_ns,'after_mtime_ns':b.st_mtime_ns}

def main():
 client=root/'endurance';owned=read(root/'endurance-owned-exit.json');plan=read(client/'packaged-client-plan.json')
 assert owned['exit_code']==0 and owned['exited'] is True
 assert read(root/'consumer03/summary.json')['passed'] is True
 assert read(root/'post20/summary.json')['passed'] is True
 assert read(root/'recorder03/session-end.json')['status']=='stopped'
 files=[]
 for directory,entries in [('mods',plan['mods']),('resourcepacks',plan['packs'])]:
  for entry in entries:
   path=client/directory/entry['filename'];assert path.resolve().is_relative_to(client.resolve())
   record=fingerprint(path);assert record['sha256']==entry['sha256']
   files.append({'relative_path':path.relative_to(client).as_posix(),'expected_sha256':entry['sha256'],'binary_copied':False,**record})
 assert len(files)==19
 write(root/'installed-fingerprints.json',{'files':files,'checked_at':now()})
 candidate=client/'mods'/plan['artifact']['artifact'];assert not (root/'candidate.jar').exists()
 shutil.copyfile(candidate,root/'candidate.jar')
 assert fingerprint(root/'candidate.jar')['sha256']==plan['artifact']['sha256']
 out=root/'jfr-readability';out.mkdir(exist_ok=False)
 recording=client/'acceptance.jfr';before=fingerprint(recording)
 command=[str(Path(plan['java']).with_name('jfr.exe')),'summary',str(recording)]
 result={'argv':command,'started':now(),'target_pid':owned['pid']}
 with (out/'summary.stdout.log').open('xb') as stdout,(out/'summary.stderr.log').open('xb') as stderr:
  helper=subprocess.Popen(command,stdout=stdout,stderr=stderr);result['helper_pid']=helper.pid;result['exit_code']=helper.wait()
 result['ended']=now();write(out/'execution.json',result)
 assert result['exit_code']==0 and b'Version:' in (out/'summary.stdout.log').read_bytes()
 after=fingerprint(recording);assert before==after and after['bytes']>0
 check={'pid':owned['pid'],'summary_exit':result['exit_code'],'source':str(recording),'binary_copied':False,**after}
 write(out/'check.json',check)
 print(json.dumps({'installed_files':len(files),'owned':owned,'jfr':check}))
if __name__=='__main__':main()
