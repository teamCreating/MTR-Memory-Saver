from pathlib import Path
import json,subprocess,datetime,os,time,ctypes,sys,hashlib
r=Path.cwd();out=r/'.cache/acceptance/gl-positive-053b';instance=r/'.cache/acceptance/official-nf248-obj048-full04';plan=json.loads((instance/'packaged-client-plan.json').read_bytes());java=Path(plan['java']);native=instance/'versions/neoforge-21.1.248/natives';cp=os.pathsep.join(str(instance/'libraries/org/lwjgl'/a/'3.3.3'/(a+'-3.3.3.jar')) for a in ['lwjgl','lwjgl-glfw','lwjgl-opengl'])
compile_args=[str(java.with_name('javac.exe')),'-cp',cp,'-d',str(out),str(out/'FramePositiveControl.java')]
with (out/'compile.stdout.log').open('xb') as o,(out/'compile.stderr.log').open('xb') as e:
 c=subprocess.Popen(compile_args,stdout=o,stderr=e);code=c.wait()
(out/'compile.execution.json').write_text(json.dumps({'argv':compile_args,'pid':c.pid,'exit_code':code},indent=2)+'\n',encoding='utf-8');assert code==0
args=[str(java),'-Djava.library.path='+str(native),'-cp',str(out)+os.pathsep+cp,'FramePositiveControl',str(out),'180'];receipt={'argv':args,'started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Known WGL rendering positive; swap-call markers are not ETW presentation measurements'}
with (out/'stdout.log').open('xb') as o,(out/'stderr.log').open('xb') as e:
 p=subprocess.Popen(args,stdout=o,stderr=e);receipt['pid']=p.pid;(out/'launch.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
 sys.path.insert(0,str(r));from tools.windows_process_identity import NativeApi,query_identity
 api=NativeApi();api.kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32];api.kernel.OpenProcess.restype=ctypes.c_void_p;api.kernel.CloseHandle.argtypes=[ctypes.c_void_p];handle=api.kernel.OpenProcess(0x1000,False,p.pid)
 try:identity=query_identity(handle,api)
 finally:api.kernel.CloseHandle(handle)
 (out/'target.json').write_text(json.dumps(identity,indent=2)+'\n',encoding='utf-8');print(json.dumps({'pid':p.pid,'created':identity['created']}),flush=True)
 receipt['exit_code']=p.wait();receipt['ended']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(json.dumps({'exit_code':receipt['exit_code']}))
