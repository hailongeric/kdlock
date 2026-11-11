from pathlib import Path
import hashlib,json,os,subprocess,time
args=['/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3', '-B', '/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/killable-final-recovery-input-01/recover.py']
h=Path(args[2]);assert hashlib.sha256(h.read_bytes()).hexdigest()=='00dbff6fd3dfe6606332cefe295560b3bd14a09fedb8736d1276c9d8115a3ceb'
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/killable-final-recovery-driver-01');d.mkdir(mode=0o700)
def put(n,v):
 with (d/n).open('x') as f:json.dump(v,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
 fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
put('command.json',{'argv':args,'helper_sha256':'00dbff6fd3dfe6606332cefe295560b3bd14a09fedb8736d1276c9d8115a3ceb'});start=time.time()
with (d/'stdout').open('xb') as out,(d/'stderr').open('xb') as err:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);put('dispatch.json',{'pid':child.pid});print(json.dumps({'event':'DISPATCHED','pid':child.pid}),flush=True);deadline=time.monotonic()+180
 while child.poll() is None:
  result=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/recovery-killable-final-01/result.json');failed=False
  if result.exists():
   try:failed=json.loads(result.read_text()).get('status')=='FAILED_RETAINED'
   except json.JSONDecodeError:pass
  if failed or time.monotonic()>=deadline:
   put('return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid,'observed_failure':failed});print(json.dumps({'event':'CHILD_RETAINED','pid':child.pid}),flush=True);raise SystemExit(124)
  time.sleep(0.25)
 code=child.returncode
put('return.json',{'returncode':code,'elapsed_seconds':time.time()-start});print(json.dumps({'event':'RETURNED','returncode':code}),flush=True);raise SystemExit(code)
