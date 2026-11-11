from pathlib import Path
import base64,datetime,hashlib,json,subprocess,sys,time
p=Path('/tmp/kdlock-kernel8-install-run-20261111-01');phase=sys.argv[1];assert phase in ('install','arm')
raw=Path('/tmp/kdlock-kernel6-preflight-20261111-01/host-read.py').read_bytes();assert hashlib.sha256(raw).hexdigest()=='05936f37e7ba3ae185b04c14ccfc87d3de74b429626329842ac1d10c585949b2'
host=['ssh','-T','-p','22','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71','sudo','-n','python3','-B','-'];(p/(phase+'-proof-command.json')).write_text(json.dumps({'argv':host,'stdin':'/tmp/kdlock-kernel6-preflight-20261111-01/host-read.py','timeout_seconds':60},indent=2)+chr(10))
with (p/(phase+'-proof.json')).open('xb') as out,(p/(phase+'-proof.stderr')).open('xb') as err:r=subprocess.run(host,input=raw,stdout=out,stderr=err,timeout=60)
if r.returncode:raise SystemExit(r.returncode)
raw=(p/(phase+'-proof.json')).read_bytes();proof=json.loads(raw);policy=json.loads(Path('/tmp/kdlock-kernel8-affected-20261111-01/config.json').read_text())['recovery_policy'];assert all(proof[k]==policy[k] for k in ('hostname','pid','exe'));assert len(proof['images'])==3 and {x['path'] for x in proof['images']}==set(policy['image_paths']) and all(x['path']==x['realpath'] and x['open_fds'] and x['host_available']>=policy['host_floor_bytes'] for x in proof['images']);texts={x['command']:x['output'] for x in proof['hmp']};assert 'VM status: running' in texts['info status'];assert any(policy['tag'] in x.split() for x in texts['info snapshots'].split('List of snapshots present on all disks:',1)[1].split('List of partial',1)[0].splitlines());assert 0<=time.time()-datetime.datetime.fromisoformat(proof['utc']).timestamp()<120
args=json.loads((p/(phase+'-argv.json')).read_text())
script=r'''from pathlib import Path
import base64,hashlib,json,os,runpy,subprocess,time
phase=PHASE;args=ARGS;raw=base64.b64decode(PROOF);digest=PROOFSHA
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01');inp=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01/install-helpers-01');assert hashlib.sha256(raw).hexdigest()==digest
for n,h in {'kdlock-kdrebuild8-install.py':'409f640efa69425ee8b8849c4f1897b9df83e4c1a7eccbea2b596ab7bb99a99b','kdlock-kdrebuild8-checks.py':'1726d01a4794f82ca8cb1a92218a70dd59272fa2e5e8bdd27a266bd31d92a472','kdlock-kdrebuild8-postboot.py':'269102a5f82f87f2e86ce0437bdd2766aac99248937907f60fa33ed964e675bb'}.items():assert hashlib.sha256((inp/n).read_bytes()).hexdigest()==h
for n,h in {'stage':'fedb5a315041a7503167df8d83f0c70960625a5922b14f25fa2847cb871a918c','check':'9bd3fcd4671643ab461846684d1093e4c8754ec35d0ad3b49e2a617b9a90fa9b'}.items():
 b=(base/'receipts/install-kdrebuild8-api-01'/(n+'-complete.json')).read_bytes();assert hashlib.sha256(b).hexdigest()==h and json.loads(b)['status']=='COMPLETE'
if phase=='arm':assert json.loads((base/'receipts/install-kdrebuild8-api-01/install-complete.json').read_text())['status']=='COMPLETE'
h=inp.parent/'full-build.py';assert hashlib.sha256(h.read_bytes()).hexdigest()=='cf062063edb80334b09734db4461d4c4fcd66c486909c04a3ddac3afa115990e';ns=runpy.run_path(str(h));f=json.loads((base/'receipts/focused-01/result.json').read_text());idle=ns['idle'](f['identity_after'])
env=subprocess.run(['grub-editenv','list'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10);assert env.returncode==0 and all(not x.startswith('next_entry=') or x=='next_entry=' for x in env.stdout.decode().splitlines())
q=inp/('recovery-'+phase+'.json')
with q.open('xb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
d=base/'receipts'/('install-driver-'+phase+'-01');d.mkdir(mode=0o700)
def put(n,v):
 with (d/n).open('x') as o:json.dump(v,o,indent=2);o.write(chr(10));o.flush();os.fsync(o.fileno())
 fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
put('command.json',{'argv':args,'proof_sha256':digest,'idle':idle,'grub_environment':env.stdout.decode(),'unix':time.time()});start=time.time()
with (d/'stdout').open('xb') as out,(d/'stderr').open('xb') as err:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);put('dispatch.json',{'pid':child.pid,'unix':time.time()});print(json.dumps({'phase':phase,'event':'DISPATCHED','pid':child.pid,'driver':str(d),'proof_sha256':digest}),flush=True)
 try:code=child.wait(timeout=1200)
 except subprocess.TimeoutExpired:put('return.json',{'status':'INCOMPLETE_CHILD_RETAINED','pid':child.pid});raise
put('return.json',{'returncode':code,'pid':child.pid,'elapsed_seconds':time.time()-start});print(json.dumps({'phase':phase,'event':'RETURNED','returncode':code,'driver':str(d)}),flush=True)
raise SystemExit(code)
'''.replace('PHASE',repr(phase)).replace('ARGS',repr(args)).replace('PROOFSHA',repr(hashlib.sha256(raw).hexdigest())).replace('PROOF',repr(base64.b64encode(raw).decode()))
(p/(phase+'-stdin.py')).write_text(script);a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/(phase+'-command.json')).write_text(json.dumps({'argv':a,'stdin':str(p/(phase+'-stdin.py')),'timeout_seconds':1240},indent=2)+chr(10));start=time.time()
with (p/(phase+'.stdout')).open('xb') as out,(p/(phase+'.stderr')).open('xb') as err:
 child=subprocess.Popen(a,stdin=subprocess.PIPE,stdout=out,stderr=err);child.stdin.write(script.encode());child.stdin.close()
 try:code=child.wait(timeout=1240)
 except subprocess.TimeoutExpired:(p/(phase+'-return.json')).write_text(json.dumps({'status':'SSH_CHILD_RETAINED_UNCERTAIN','pid':child.pid})+chr(10));raise
(p/(phase+'-return.json')).write_text(json.dumps({'returncode':code,'elapsed_seconds':time.time()-start},indent=2)+chr(10));print((p/(phase+'.stdout')).read_text());print((p/(phase+'.stderr')).read_text());raise SystemExit(code)
