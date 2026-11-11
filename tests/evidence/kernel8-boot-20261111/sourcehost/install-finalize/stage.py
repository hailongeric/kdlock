from pathlib import Path
import base64,hashlib,json,subprocess,time
p=Path('/tmp/kdlock-kernel8-install-finalize-20261111-01');names={'finalize-arm.py':p/'finalize-arm.py','checks-menu.py':Path('/tmp/kdlock-kdrebuild8-checks-menu.py'),'postboot.py':Path('/tmp/kdlock-kdrebuild8-postboot-finalized.py'),'origin-pins.json':p/'origin-pins.json'};rows={}
for name,path in names.items():
 raw=path.read_bytes();rows[name]={'sha256':hashlib.sha256(raw).hexdigest(),'base64':base64.b64encode(raw).decode()}
assert {n:x['sha256'] for n,x in rows.items()}=={'finalize-arm.py':'02de841b268a66d5321dc6d0be3bd907b17ac1349e1d52463e47ba6c363926f7','checks-menu.py':'2610bc0c19dafc9ccf87b56dd85802ac4f22d0dce2ac1b9ae6d0dd4c3cb8ecab','postboot.py':'7ba6bd53f6d281715f21dfdb11280cde751fc3bb6a471f5f33f40274c32146a7','origin-pins.json':'8550478a37e6dcb4bea6ee99a2d6082b8fd9b5b7dbc225f679d4f51a439bdbb3'}
script='''import ast,base64,hashlib,json,os,runpy,time
from pathlib import Path
rows=ROWS
h=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01/full-build.py');assert hashlib.sha256(h.read_bytes()).hexdigest()=='cf062063edb80334b09734db4461d4c4fcd66c486909c04a3ddac3afa115990e';ns=runpy.run_path(str(h));f=json.loads(Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/focused-01/result.json').read_text());idle=ns['idle'](f['identity_after'])
root=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-input-0d42063e-01');assert root.resolve(strict=True)==root
for row in rows.values():assert hashlib.sha256(base64.b64decode(row['base64'])).hexdigest()==row['sha256']
out=root/'install-finalize-helpers-01';assert not os.path.lexists(out);out.mkdir(mode=0o700)
for name,row in rows.items():
 p=out/name;raw=base64.b64decode(row['base64'])
 with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
for n in rows:
 if n.endswith('.py'):ast.parse((out/n).read_bytes(),filename=str(out/n))
print(json.dumps({'phase':'FROZEN_INPUT_STAGED','root':str(root),'files':{n:r['sha256'] for n,r in rows.items()},'vm_ast':'PASS','identity':idle,'unix':time.time()}))
'''.replace('ROWS',repr(rows))
(p/'stage-stdin.py').write_text(script)
a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'stage-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'stage-stdin.py'),'timeout_seconds':45},indent=2)+'\n');start=time.time()
with (p/'stage.stdout').open('xb') as out,(p/'stage.stderr').open('xb') as err:r=subprocess.run(a,input=script.encode(),stdout=out,stderr=err,timeout=45)
(p/'stage-result.json').write_text(json.dumps({'returncode':r.returncode,'elapsed_seconds':time.time()-start},indent=2)+'\n');print(json.dumps({'returncode':r.returncode,'stdout':str(p/'stage.stdout'),'stderr':str(p/'stage.stderr')}))
