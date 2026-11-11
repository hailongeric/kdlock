from pathlib import Path
import base64,hashlib,json,subprocess
p=Path('/tmp/kdlock-kernel8-private-live-20261111-01');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'rwsem-read-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'rwsem-read-stdin.py'),'timeout_seconds':60},indent=2)+chr(10))
with (p/'rwsem-read.stdout').open('xb') as out,(p/'rwsem-read.stderr').open('xb') as err:r=subprocess.run(a,input=(p/'rwsem-read-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=60)
(p/'rwsem-read-return.json').write_text(json.dumps({'returncode':r.returncode})+chr(10))
if r.returncode:raise SystemExit(r.returncode)
rows=json.loads((p/'rwsem-read.stdout').read_text());q=p/'rwsem-completed';q.mkdir()
for n,x in rows.items():
 b=base64.b64decode(x.pop('data'));assert len(b)==x['bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'];f=q/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
(p/'rwsem-read-index.json').write_text(json.dumps(rows,indent=2)+chr(10));v=json.loads((q/'private-rwsem-receipts-01/result.json').read_text());print(json.dumps({'status':v['status'],'sha256':rows['private-rwsem-receipts-01/result.json']['sha256'],'inner_sha256':rows['private-rwsem-query-01/result.json']['sha256'],'identity_after':v['identity_after']}))
