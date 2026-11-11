from pathlib import Path
import base64,hashlib,json,subprocess
p=Path('/tmp/kdlock-kernel8-managed-killable-20261111-03');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'first-read-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'first-read-stdin.py'),'timeout_seconds':60},indent=2)+chr(10))
with (p/'first-read.stdout').open('xb') as out,(p/'first-read.stderr').open('xb') as err:r=subprocess.run(a,input=(p/'first-read-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=60)
(p/'first-read-return.json').write_text(json.dumps({'returncode':r.returncode})+chr(10));assert r.returncode==0
v=json.loads((p/'first-read.stdout').read_text());q=p/'first-read';q.mkdir()
for n,x in v['files'].items():
 if x.get('absent'):continue
 b=base64.b64decode(x.pop('data'));assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'];f=q/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
(p/'first-read-index.json').write_text(json.dumps(v,indent=2)+chr(10));print(json.dumps({k:v[k] for k in ('identity','modules')},indent=2));print((q/'managed-killable-driver-03/stderr').read_text())
f=q/'managed-killable-live-03/result.json'
if f.exists():print(json.dumps({k:v for k,v in json.loads(f.read_text()).items() if k in ('status','error','controller_pid','live_children')},indent=2))
