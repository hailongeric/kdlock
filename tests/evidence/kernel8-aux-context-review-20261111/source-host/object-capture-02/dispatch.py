from pathlib import Path
import base64,hashlib,json,os,subprocess,time
p=Path('/tmp/kdlock-kernel8-aux-object-capture-controls-20261111-02');plan=Path('/tmp/kdlock-kernel8-aux-object-capture-plan-20261111-02.json');data=(p/'capture.py').read_bytes();raw=plan.read_bytes()
assert hashlib.sha256(data).hexdigest()=='b34d306a14ebdb6c493f857dce86b6589141874486ebda17e883f5d876e2bf6c' and hashlib.sha256(raw).hexdigest()=='af42fd1972f7809deec96ecb763b8fd898fb72e55f5023d4650996d1ece3e505'
a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-',base64.b64encode(raw).decode()]
def put(n,value):
 with (p/n).open('x') as f:json.dump(value,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
 fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
put('dispatch-command.json',{'argv':a,'stdin':str(p/'capture.py'),'stdin_sha256':hashlib.sha256(data).hexdigest(),'plan_sha256':hashlib.sha256(raw).hexdigest(),'outer_observer_seconds':240});start=time.time()
with (p/'dispatch.stdout').open('xb') as out,(p/'dispatch.stderr').open('xb') as err:
 child=subprocess.Popen(a,stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True);put('dispatch-pid.json',{'pid':child.pid});child.stdin.write(data);child.stdin.close()
 try:code=child.wait(timeout=240)
 except subprocess.TimeoutExpired:put('dispatch-return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid,'elapsed_seconds':time.time()-start});raise
put('dispatch-return.json',{'returncode':code,'elapsed_seconds':time.time()-start});print(json.dumps({'returncode':code}));raise SystemExit(code)
