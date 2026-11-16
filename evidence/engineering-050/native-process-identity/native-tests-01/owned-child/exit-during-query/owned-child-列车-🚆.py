import json,os,sys
print(json.dumps({'pid':os.getpid(),'argv':sys.argv},ensure_ascii=False),flush=True)
sys.stdin.buffer.read(1)
