from pathlib import Path
import base64,hashlib,json,subprocess
p=Path('/tmp/kdlock-kernel8-killable-fixed-host-checks-20261111-02');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'read-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'read-stdin.py'),'timeout_seconds':60},indent=2)+chr(10))
with (p/'read.stdout').open('xb') as out,(p/'read.stderr').open('xb') as err:r=subprocess.run(a,input=(p/'read-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=60)
(p/'read-return.json').write_text(json.dumps({'returncode':r.returncode})+chr(10))
if r.returncode:raise SystemExit(r.returncode)
rows=json.loads((p/'read.stdout').read_text());q=p/'completed';q.mkdir()
for n,x in rows.items():
 b=base64.b64decode(x.pop('data'));assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'];(q/Path(n).name).write_bytes(b)
(p/'read-index.json').write_text(json.dumps(rows,indent=2)+chr(10));v=json.loads((q/'result.json').read_text());print(json.dumps({'status':v['status'],'sha256':rows['result.json']['sha256'],'checks':v.get('checks'),'identity_after':v.get('identity_after')}))
