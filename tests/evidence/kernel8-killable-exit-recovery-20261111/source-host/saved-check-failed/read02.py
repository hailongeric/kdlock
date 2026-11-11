from pathlib import Path
import base64,hashlib,json,subprocess
p=Path('/tmp/kdlock-kernel8-killable-fixed-host-checks-20261111-01');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'read02-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'read02-stdin.py'),'timeout_seconds':60},indent=2)+chr(10))
with (p/'read02.stdout').open('xb') as out,(p/'read02.stderr').open('xb') as err:r=subprocess.run(a,input=(p/'read02-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=60)
(p/'read02-return.json').write_text(json.dumps({'returncode':r.returncode})+chr(10))
if r.returncode:raise SystemExit(r.returncode)
rows=json.loads((p/'read02.stdout').read_text());q=p/'completed02';q.mkdir()
for n,x in rows.items():
 if x.get('absent'):continue
 b=base64.b64decode(x.pop('data'));assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'];(q/Path(n).name).write_bytes(b)
(p/'read-index.json').write_text(json.dumps(rows,indent=2)+chr(10));v=json.loads((q/'result.json').read_text());print(json.dumps({'status':v['status'],'sha256':rows['result.json']['sha256'],'checks':v.get('checks'),'identity_after':v.get('identity_after')}))
