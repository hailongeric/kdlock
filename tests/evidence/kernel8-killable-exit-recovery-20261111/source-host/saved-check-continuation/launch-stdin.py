from pathlib import Path
import hashlib,json,os,subprocess,time
args=['/usr/bin/python3', '-B', '/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/host-source-correction-de76da8a-input-01/checks.py'];h=Path(args[2]);assert hashlib.sha256(h.read_bytes()).hexdigest()=='3c4b2889e613493f1efe4c5fd6d51d67236adb1277c0559bd500738394e5a424'
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/host-source-correction-de76da8a-driver-01');d.mkdir(mode=0o700)
def put(n,v):
 with (d/n).open('x') as f:json.dump(v,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
put('command.json',{'argv':args,'helper_sha256':'3c4b2889e613493f1efe4c5fd6d51d67236adb1277c0559bd500738394e5a424'});start=time.time()
with (d/'stdout').open('xb') as out,(d/'stderr').open('xb') as err:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);put('dispatch.json',{'pid':child.pid});print(json.dumps({'event':'DISPATCHED','pid':child.pid}),flush=True)
 try:code=child.wait(timeout=240)
 except subprocess.TimeoutExpired:put('return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid});raise
put('return.json',{'returncode':code,'elapsed_seconds':time.time()-start});print(json.dumps({'event':'RETURNED','returncode':code}),flush=True);raise SystemExit(code)
