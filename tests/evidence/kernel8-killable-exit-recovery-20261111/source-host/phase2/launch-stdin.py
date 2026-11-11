from pathlib import Path
import hashlib,json,os,subprocess,time
args=['/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3', '-B', '/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/killable-cycle-recovery-input-01/phase2.py']
h=Path(args[2]);assert hashlib.sha256(h.read_bytes()).hexdigest()=='d464f26e78576e7faee73b8615268c0d3bf2d78d7a68b303851dad8214b2736e'
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/killable-cycle-recovery-driver-01');d.mkdir(mode=0o700)
def put(n,v):
 with (d/n).open('x') as f:json.dump(v,f,indent=2);f.write(chr(10));f.flush();os.fsync(f.fileno())
 fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
put('command.json',{'argv':args,'helper_sha256':'d464f26e78576e7faee73b8615268c0d3bf2d78d7a68b303851dad8214b2736e'});start=time.time()
with (d/'stdout').open('xb') as out,(d/'stderr').open('xb') as err:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);put('dispatch.json',{'pid':child.pid});print(json.dumps({'event':'DISPATCHED','pid':child.pid}),flush=True);deadline=time.monotonic()+180
 while child.poll() is None:
  result=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/recovery-killable-cycle-01/result.json');failed=False
  if result.exists():
   try:failed=json.loads(result.read_text()).get('status')=='FAILED_RETAINED'
   except json.JSONDecodeError:pass
  if failed or time.monotonic()>=deadline:
   put('return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid,'observed_failure':failed});print(json.dumps({'event':'CHILD_RETAINED','pid':child.pid}),flush=True);raise SystemExit(124)
  time.sleep(0.25)
 code=child.returncode
put('return.json',{'returncode':code,'elapsed_seconds':time.time()-start});print(json.dumps({'event':'RETURNED','returncode':code}),flush=True);raise SystemExit(code)
