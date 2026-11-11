from pathlib import Path
import base64,hashlib,json,subprocess,time
p=Path('/tmp/kdlock-kernel8-install-run-20261111-01');names={n:Path('/tmp')/n for n in ('kdlock-kdrebuild8-install.py','kdlock-kdrebuild8-checks.py','kdlock-kdrebuild8-postboot.py')};rows={}
for name,path in names.items():
 raw=path.read_bytes();rows[name]={'sha256':hashlib.sha256(raw).hexdigest(),'base64':base64.b64encode(raw).decode()}
assert rows['kdlock-kdrebuild8-install.py']['sha256']=='409f640efa69425ee8b8849c4f1897b9df83e4c1a7eccbea2b596ab7bb99a99b'
assert rows['kdlock-kdrebuild8-checks.py']['sha256']=='1726d01a4794f82ca8cb1a92218a70dd59272fa2e5e8bdd27a266bd31d92a472'
assert rows['kdlock-kdrebuild8-postboot.py']['sha256']=='269102a5f82f87f2e86ce0437bdd2766aac99248937907f60fa33ed964e675bb'
script='''import ast,base64,hashlib,json,os,runpy,time
from pathlib import Path
rows=ROWS
h=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01/full-build.py');assert hashlib.sha256(h.read_bytes()).hexdigest()=='cf062063edb80334b09734db4461d4c4fcd66c486909c04a3ddac3afa115990e';ns=runpy.run_path(str(h));f=json.loads(Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/focused-01/result.json').read_text());idle=ns['idle'](f['identity_after'])
root=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01');assert root.resolve(strict=True)==root
for row in rows.values():assert hashlib.sha256(base64.b64decode(row['base64'])).hexdigest()==row['sha256']
out=root/'install-helpers-01';assert not os.path.lexists(out);out.mkdir(mode=0o700)
for name,row in rows.items():
 p=out/name;raw=base64.b64decode(row['base64'])
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
for n in rows:ast.parse((out/n).read_bytes(),filename=str(out/n))
print(json.dumps({'phase':'FROZEN_INPUT_STAGED','root':str(root),'files':{n:r['sha256'] for n,r in rows.items()},'vm_ast':'PASS','identity':idle,'unix':time.time()}))
'''.replace('ROWS',repr(rows))
(p/'stage-stdin.py').write_text(script)
a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'stage-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'stage-stdin.py'),'timeout_seconds':45},indent=2)+'\n');start=time.time()
with (p/'stage.stdout').open('xb') as out,(p/'stage.stderr').open('xb') as err:r=subprocess.run(a,input=script.encode(),stdout=out,stderr=err,timeout=45)
(p/'stage-result.json').write_text(json.dumps({'returncode':r.returncode,'elapsed_seconds':time.time()-start},indent=2)+'\n');print(json.dumps({'returncode':r.returncode,'stdout':str(p/'stage.stdout'),'stderr':str(p/'stage.stderr')}))
