import sys,json,base64,hashlib,os,tarfile,io
from pathlib import Path,PurePosixPath
v=json.loads(sys.stdin.buffer.readline(1048576));p=Path(v['root']);assert p==Path('/mnt/kdlock-builds/kdlock-main-work/kernel6-private-fixtures-80c272e5-01') and p.parent.resolve(strict=True)==p.parent and not os.path.lexists(p);assets={}
for n,r in v['assets'].items():
 assert n in ('manifest.json','source-state.json','kernel-package.json','kernel-pins.json','gs-config.json','private-fixture.py');b=base64.b64decode(r['base64'],validate=True);assert hashlib.sha256(b).hexdigest()==r['sha256'];assets[n]=b
assert len(assets)==6;archive=sys.stdin.buffer.read(1269761);assert len(archive)==1269760 and hashlib.sha256(archive).hexdigest()=='24c2a256397df1481443a0cb6a0e89df9c7799da602188ce494769c89f7d1342';manifest=json.loads(assets['manifest.json']);assert len(manifest)==117;parents={str(x) for n in manifest for x in PurePosixPath(n).parents if str(x)!='.'};payload={};seen=set()
with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as stream:
 for m in stream:
  n=m.name.rstrip('/');q=PurePosixPath(n);assert n==str(q) and not q.is_absolute() and '..' not in q.parts and n not in seen;seen.add(n)
  if m.isdir():assert n in parents;continue
  assert m.isfile() and n in manifest and m.size==manifest[n]['bytes']
  with stream.extractfile(m) as f:b=f.read(m.size+1)
  assert len(b)==m.size and hashlib.sha256(b).hexdigest()==manifest[n]['sha256'];payload[n]=b
assert set(payload)==set(manifest);p.mkdir(mode=0o700)
for n,b in dict(assets,**{'source.tar':archive}).items():
 with (p/n).open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
(p/'input').mkdir(mode=0o700)
for n,b in payload.items():
 fpath=p/'input'/n;fpath.parent.mkdir(parents=True,exist_ok=True)
 with fpath.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
assert all(hashlib.sha256((p/'input'/n).read_bytes()).hexdigest()==r['sha256'] for n,r in manifest.items());print(json.dumps({'status':'EXACT_PRIVATE117_STAGED','files':len(payload),'root':str(p)}))
