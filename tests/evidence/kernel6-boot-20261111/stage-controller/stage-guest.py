import sys,json,os,base64,hashlib
from pathlib import Path
v=json.loads(sys.stdin.buffer.readline(1048576));p=Path(v['root']);assert p==Path('/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04/ops-kdrebuild6-api-01') and p.parent.resolve(strict=True)==p.parent and not os.path.lexists(p);assert not os.path.lexists(p.parent/'install-stage-kdrebuild6-api-01') and not os.path.lexists(p.parent/'receipts/install-kdrebuild6-api-01');payload={}
for n,r in v['assets'].items():
 assert n in ('kdlock-kdrebuild6-install.py','kdlock-kdrebuild6-checks.py','kdlock-kdrebuild6-postboot.py');b=base64.b64decode(r['base64'],validate=True);assert hashlib.sha256(b).hexdigest()==r['sha256'];payload[n]=b
assert len(payload)==3;p.mkdir(mode=0o700)
for n,b in payload.items():
 with (p/n).open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
print(json.dumps({'status':'EXACT_HELPERS_STAGED','files':list(payload)}))
