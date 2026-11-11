from pathlib import Path
import base64,hashlib,json,subprocess,time
p=Path('/tmp/kdlock-kernel8-offroot-20261111-01');raw=(p/'full-recovery.json').read_bytes();args=json.loads((p/'actual-argv.json').read_text())
script='''import base64,hashlib,json,os,subprocess,time
from pathlib import Path
raw=base64.b64decode(PAYLOAD);args=ARGV;expected=DIGEST
p=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01/recovery-nls-stage.json')
assert not os.path.lexists(p) and p.parent.resolve(strict=True)==p.parent
assert hashlib.sha256(raw).hexdigest()==expected
helper=Path(args[1]);assert hashlib.sha256(helper.read_bytes()).hexdigest()=='cf062063edb80334b09734db4461d4c4fcd66c486909c04a3ddac3afa115990e'
with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/nls-stage-driver-01');d.mkdir(mode=0o700)
def put(name,v):
 with (d/name).open('x') as f:json.dump(v,f,indent=2);f.write('\\n');f.flush();os.fsync(f.fileno())
put('command.json',{'argv':args,'helper_sha256':hashlib.sha256(helper.read_bytes()).hexdigest(),'recovery_sha256':expected,'started_unix':time.time()})
start=time.time()
with (d/'stdout').open('xb') as out,(d/'stderr').open('xb') as err:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
 put('dispatch.json',{'pid':child.pid,'started_unix':time.time()})
 print(json.dumps({'phase':'DISPATCHED','pid':child.pid,'driver':str(d),'recovery_sha256':expected}),flush=True)
 try:r=child.wait(timeout=420)
 except subprocess.TimeoutExpired:
  put('result.json',{'status':'OBSERVER_TIMEOUT_CHILD_RETAINED','pid':child.pid,'elapsed_seconds':time.time()-start});raise
put('result.json',{'returncode':r,'pid':child.pid,'elapsed_seconds':time.time()-start})
print(json.dumps({'phase':'RETURNED','returncode':r,'driver':str(d)}),flush=True)
'''.replace('PAYLOAD',repr(base64.b64encode(raw).decode())).replace('ARGV',repr(args)).replace('DIGEST',repr(hashlib.sha256(raw).hexdigest()))
(p/'launch-stdin.py').write_text(script)
argv=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'launch-command.json').write_text(json.dumps({'argv':argv,'stdin':str(p/'launch-stdin.py'),'timeout_seconds':430},indent=2)+'\n')
start=time.time()
with (p/'launch.stdout').open('xb') as out,(p/'launch.stderr').open('xb') as err:
 child=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=out,stderr=err)
 child.stdin.write(script.encode());child.stdin.close()
 (p/'launch-dispatch.json').write_text(json.dumps({'pid':child.pid,'started_unix':start},indent=2)+'\n')
 try:r=child.wait(timeout=430)
 except subprocess.TimeoutExpired:
  (p/'launch-result.json').write_text(json.dumps({'status':'SSH_CHILD_RETAINED_UNCERTAIN','pid':child.pid,'elapsed_seconds':time.time()-start},indent=2)+'\n');raise
(p/'launch-result.json').write_text(json.dumps({'returncode':r,'elapsed_seconds':time.time()-start},indent=2)+'\n');print(json.dumps({'returncode':r,'stdout':str(p/'launch.stdout')}))
