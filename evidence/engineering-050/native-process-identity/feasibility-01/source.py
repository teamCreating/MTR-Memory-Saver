"""Owned-child Win10 class-60 feasibility; no game or existing process is queried."""
import ctypes as c
from ctypes import wintypes as w
import datetime as dt, hashlib, json, os, pathlib, queue, subprocess, sys, threading
root=pathlib.Path.cwd();out=root/'evidence/engineering-050/native-process-identity/feasibility-01';out.mkdir(exist_ok=False)
sys.path.insert(0,str(root/'tools'));import observe_packaged_client as observer
kernel=c.WinDLL('kernel32',use_last_error=True);ntdll=c.WinDLL('ntdll')
for name,args,result in [('OpenProcess',[w.DWORD,w.BOOL,w.DWORD],w.HANDLE),('GetProcessId',[w.HANDLE],w.DWORD),('GetExitCodeProcess',[w.HANDLE,c.POINTER(w.DWORD)],w.BOOL),('GetProcessTimes',[w.HANDLE]+[c.POINTER(w.FILETIME)]*4,w.BOOL),('CloseHandle',[w.HANDLE],w.BOOL),('QueryFullProcessImageNameW',[w.HANDLE,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD)],w.BOOL),('IsWow64Process2',[w.HANDLE,c.POINTER(w.USHORT),c.POINTER(w.USHORT)],w.BOOL)]:
 f=getattr(kernel,name);f.argtypes=args;f.restype=result
query=ntdll.NtQueryInformationProcess;query.argtypes=[w.HANDLE,w.ULONG,c.c_void_p,w.ULONG,c.POINTER(w.ULONG)];query.restype=c.c_long
class UnicodeString(c.Structure):_fields_=[('Length',w.USHORT),('MaximumLength',w.USHORT),('Buffer',c.c_void_p)]
class NativeFailure(Exception):pass

def live(handle):
 code=w.DWORD()
 if not kernel.GetExitCodeProcess(handle,c.byref(code)):raise c.WinError(c.get_last_error())
 if code.value!=259:raise NativeFailure('Process exited with '+str(code.value))
def inspect(handle,after_size=None):
 live(handle);pid=kernel.GetProcessId(handle)
 times=[w.FILETIME() for _ in range(4)]
 if not kernel.GetProcessTimes(handle,*[c.byref(t) for t in times]):raise c.WinError(c.get_last_error())
 filetime=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
 created=(dt.datetime(1601,1,1,tzinfo=dt.timezone.utc)+dt.timedelta(microseconds=filetime//10)).isoformat()
 count=w.DWORD(32768);name=c.create_unicode_buffer(count.value)
 if not kernel.QueryFullProcessImageNameW(handle,0,name,c.byref(count)):raise c.WinError(c.get_last_error())
 pm,nm=w.USHORT(),w.USHORT()
 if not kernel.IsWow64Process2(handle,c.byref(pm),c.byref(nm)):raise c.WinError(c.get_last_error())
 needed=w.ULONG();status=query(handle,60,None,0,c.byref(needed))&0xffffffff
 if status!=0xc0000004 or not 16<=needed.value<=1048576:raise NativeFailure(f'Size query {status:08x}, {needed.value}')
 if after_size:after_size()
 memory=c.create_string_buffer(needed.value);returned=w.ULONG()
 status=query(handle,60,memory,len(memory),c.byref(returned))&0xffffffff
 if status:raise NativeFailure(f'Data query {status:08x}')
 value=UnicodeString.from_buffer(memory);base=c.addressof(memory)
 if value.Length%2 or value.Length>value.MaximumLength or not base+c.sizeof(UnicodeString)<=value.Buffer<=base+len(memory) or value.Buffer+value.Length>base+len(memory):raise NativeFailure('Invalid inline UnicodeString')
 command=c.string_at(value.Buffer,value.Length).decode('utf-16-le')
 live(handle)
 return {'pid':pid,'created':created,'executable':name.value,'command':command,'architecture':{'process_machine':pm.value,'native_machine':nm.value},'command_buffer_bytes':len(memory),'command_returned_bytes':returned.value}

child=out/'owned-child-列车-🚆.py';child.write_text("import json,os,sys\nprint(json.dumps({'pid':os.getpid(),'argv':sys.argv},ensure_ascii=False),flush=True)\nsys.stdin.buffer.read(1)\n",encoding='utf-8')
arguments=['','space value','列车🚆','quote"value','ends-in-slash\\','space then slash\\','backslashes\\\\"quote','x'*20000]
command=[sys.executable,'-X','utf8','-u',str(child),*arguments]
started=dt.datetime.now(dt.timezone.utc).isoformat();p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
lines=queue.Queue()
threading.Thread(target=lambda:lines.put(p.stdout.readline()),daemon=True).start()
handle=None;report={'started_at':started,'pid':p.pid,'argv':command,'python_bits':c.sizeof(c.c_void_p)*8,'windows':list(sys.getwindowsversion()),'query_class':60}
try:
 raw=lines.get(timeout=30);(out/'child-ready.json').write_bytes(raw);actual_child=json.loads(raw)
 assert actual_child['pid']==p.pid and actual_child['argv']==[str(child),*arguments]
 handle=kernel.OpenProcess(0x0410,False,p.pid)
 if not handle:raise c.WinError(c.get_last_error())
 actual=inspect(handle)
 assert actual['architecture']=={'process_machine':0,'native_machine':0x8664}
 expected={'pid':p.pid,'timestamp':started,'command':command};plan={'java':sys.executable}
 parsed=observer.windows_arguments(actual['command']);observer.verify_process_identity(plan,expected,actual,parsed)
 assert parsed==command
 report['actual']=actual;report['parsed_argv']=parsed;report['exact_argv_passed']=True
 controls=[]
 for field,replacement in [('pid',p.pid+1),('created','2000-01-01T00:00:00Z'),('executable',str(out/'wrong.exe'))]:
  wrong=dict(actual);wrong[field]=replacement
  try:observer.verify_process_identity(plan,expected,wrong,parsed)
  except ValueError as error:controls.append({'name':'wrong_'+field,'rejected':True,'error':str(error)})
  else:raise AssertionError('Accepted '+field)
 try:observer.verify_process_identity(plan,expected,actual,parsed[:-1])
 except ValueError as error:controls.append({'name':'wrong_argv','rejected':True,'error':str(error)})
 else:raise AssertionError('Accepted wrong argv')
 def exit_between_queries():p.stdin.write(b'x');p.stdin.flush();p.wait(timeout=20)
 try:inspect(handle,exit_between_queries)
 except (OSError,NativeFailure) as error:controls.append({'name':'exit_during_query','rejected':True,'error':str(error)})
 else:raise AssertionError('Accepted exited child')
 report['controls']=controls;report['passed']=True
finally:
 if handle:
  if not kernel.CloseHandle(handle):raise c.WinError(c.get_last_error())
 if p.poll() is None:p.stdin.write(b'x');p.stdin.flush();p.wait(timeout=20)
 stdout,stderr=p.communicate(timeout=20);(out/'child-remaining.stdout.log').write_bytes(stdout);(out/'child.stderr.log').write_bytes(stderr)
 report.update({'child_exit_code':p.returncode,'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'scope':'Owned Python child only; no game, WMI, PowerShell or existing process query.'})
 (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
 print(json.dumps({k:report.get(k) for k in ('pid','passed','child_exit_code','python_bits','windows','controls')},ensure_ascii=False))
