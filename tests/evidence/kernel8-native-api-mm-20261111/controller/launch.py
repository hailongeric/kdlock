from pathlib import Path
import base64,hashlib,json,subprocess,time
p=Path('/tmp/kdlock-kernel8-native-api-20261111-01');rows={}
for name in ('config.json','recovery.json'):
 raw=(p/name).read_bytes();rows[name]={'sha256':hashlib.sha256(raw).hexdigest(),'base64':base64.b64encode(raw).decode()}
args=json.loads((p/'actual-argv.json').read_text())
s='''import base64,hashlib,json,os,subprocess,time
from pathlib import Path
rows=ROWS;args=ARGV;root=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01');out=root/'native-api-input-01'
assert out.resolve(strict=True)==out and hashlib.sha256((out/'controller.py').read_bytes()).hexdigest()=='2c2082e0bf7c807819ec7e28f744c34aaa94f38aa07faf5be1a197b1baced074'
for name,row in rows.items():
 p=out/name;assert not os.path.lexists(p);raw=base64.b64decode(row['base64']);assert hashlib.sha256(raw).hexdigest()==row['sha256']
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
d=root/'native-api-driver-01';d.mkdir(mode=0o700)
def put(name,v):
 with (d/name).open('x') as f:json.dump(v,f,indent=2);f.write('\\n');f.flush();os.fsync(f.fileno())
put('command.json',{'argv':args,'config_sha256':rows['config.json']['sha256'],'recovery_sha256':rows['recovery.json']['sha256']});start=time.time()
with (d/'stdout').open('xb') as out,(d/'stderr').open('xb') as err:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);put('dispatch.json',{'pid':child.pid,'unix':time.time()});print(json.dumps({'phase':'DISPATCHED','pid':child.pid,'driver':str(d)}),flush=True)
 try:r=child.wait(timeout=420)
 except subprocess.TimeoutExpired:put('result.json',{'status':'CHILD_RETAINED','pid':child.pid,'elapsed_seconds':time.time()-start});raise
put('result.json',{'returncode':r,'elapsed_seconds':time.time()-start});print(json.dumps({'phase':'RETURNED','returncode':r,'driver':str(d)}),flush=True)
'''.replace('ROWS',repr(rows)).replace('ARGV',repr(args))
(p/'launch-stdin.py').write_text(s)
a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'launch-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'launch-stdin.py'),'timeout_seconds':450},indent=2)+'\n');start=time.time()
with (p/'launch.stdout').open('xb') as out,(p/'launch.stderr').open('xb') as err:
 child=subprocess.Popen(a,stdin=subprocess.PIPE,stdout=out,stderr=err);child.stdin.write(s.encode());child.stdin.close()
 try:r=child.wait(timeout=450)
 except subprocess.TimeoutExpired:(p/'launch-result.json').write_text(json.dumps({'status':'SSH_CHILD_RETAINED_UNCERTAIN','pid':child.pid})+'\n');raise
(p/'launch-result.json').write_text(json.dumps({'returncode':r,'elapsed_seconds':time.time()-start},indent=2)+'\n');print((p/'launch.stdout').read_text());print((p/'launch.stderr').read_text())
