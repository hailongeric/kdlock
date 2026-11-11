from pathlib import Path
import base64,hashlib,json,subprocess,time
p=Path('/tmp/kdlock-kernel8-install-run-20261111-01');raw=(p/'recovery.json').read_bytes();stage=json.loads((p/'actual-stage-argv.json').read_text());check=json.loads((p/'check-argv.json').read_text())
script="""from pathlib import Path
import base64,hashlib,json,os,subprocess,time
raw=base64.b64decode(DATA);stage=STAGE;check=CHECK
q=Path(stage[stage.index('--recovery-receipt')+1]);assert q.parent.resolve(strict=True)==q.parent and not os.path.lexists(q);assert hashlib.sha256(raw).hexdigest()==stage[stage.index('--recovery-receipt-sha256')+1]
for n,h in {'kdlock-kdrebuild8-install.py':'409f640efa69425ee8b8849c4f1897b9df83e4c1a7eccbea2b596ab7bb99a99b','kdlock-kdrebuild8-checks.py':'1726d01a4794f82ca8cb1a92218a70dd59272fa2e5e8bdd27a266bd31d92a472','kdlock-kdrebuild8-postboot.py':'269102a5f82f87f2e86ce0437bdd2766aac99248937907f60fa33ed964e675bb'}.items():assert hashlib.sha256((q.parent/n).read_bytes()).hexdigest()==h
with q.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
d=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/install-stage-check-driver-01');d.mkdir(mode=0o700)
def put(n,v):
 with (d/n).open('x') as f:json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
for phase,args,seconds in [('stage',stage,1200),('check',check,600)]:
 put(phase+'-command.json',{'argv':args,'recovery_sha256':hashlib.sha256(raw).hexdigest(),'started_unix':time.time()})
 start=time.time()
 with (d/(phase+'.stdout')).open('xb') as out,(d/(phase+'.stderr')).open('xb') as err:
  child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);put(phase+'-dispatch.json',{'pid':child.pid,'unix':time.time()});print(json.dumps({'phase':phase,'event':'DISPATCHED','pid':child.pid,'driver':str(d)}),flush=True)
  try:code=child.wait(timeout=seconds)
  except subprocess.TimeoutExpired:put(phase+'-return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid,'elapsed_seconds':time.time()-start});raise
 put(phase+'-return.json',{'returncode':code,'pid':child.pid,'elapsed_seconds':time.time()-start});print(json.dumps({'phase':phase,'event':'RETURNED','returncode':code,'driver':str(d)}),flush=True)
 if code:raise SystemExit(code)
""".replace('DATA',repr(base64.b64encode(raw).decode())).replace('STAGE',repr(stage)).replace('CHECK',repr(check))
(p/'stage-check-stdin.py').write_text(script)
a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'stage-check-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'stage-check-stdin.py'),'timeout_seconds':1840},indent=2)+'\n');start=time.time()
with (p/'stage-check.stdout').open('xb') as out,(p/'stage-check.stderr').open('xb') as err:
 child=subprocess.Popen(a,stdin=subprocess.PIPE,stdout=out,stderr=err);child.stdin.write(script.encode());child.stdin.close()
 try:code=child.wait(timeout=1840)
 except subprocess.TimeoutExpired:(p/'stage-check-return.json').write_text(json.dumps({'status':'SSH_CHILD_RETAINED_UNCERTAIN','pid':child.pid})+'\n');raise
(p/'stage-check-return.json').write_text(json.dumps({'returncode':code,'elapsed_seconds':time.time()-start},indent=2)+'\n');print((p/'stage-check.stdout').read_text());print((p/'stage-check.stderr').read_text())
