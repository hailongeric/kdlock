"""Stage one frozen kernel9 recipe, then observe its single bounded build."""
from pathlib import Path
import base64,hashlib,json,subprocess,time
SRC=Path('/tmp/kdlock-kernel9-cohort-build-20261111')
OUT=Path('/tmp/kdlock-kernel9-build-controls-20261111/stage-launch-01')
assert not OUT.exists();OUT.mkdir()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha((SRC/'build.py').read_bytes())=='0535aa78d56e019b11de988e217416110176645fb9f25fce4dca9427881e0d57'
assert sha((SRC/'plan.json').read_bytes())=='0df23f4f69069b9b8dfcff3c58b69df9b4b6904f7e2abff3073ee9dd71215408'
plan=json.loads((SRC/'plan.json').read_text())
files={}
for name in ['build.py','plan.json','package.tar','package.json','export-receipt.json']+list(plan['provenance_files']):
 data=(SRC/name).read_bytes();files[name]={'bytes':len(data),'sha256':sha(data),'data':base64.b64encode(data).decode()}
recovery=Path('/tmp/kdlock-kernel9-build-controls-20261111/preflight/host/result.json').read_bytes()
assert sha(recovery)=='961b759f10bc891113e4c63199bde612c150791348b5584268881e39d5aa53f9'
files['recovery.json']={'bytes':len(recovery),'sha256':sha(recovery),'data':base64.b64encode(recovery).decode()}
blob=base64.b64encode(json.dumps({'input':plan['input'],'target':plan['target'],'files':files},sort_keys=True).encode()).decode()
raw=("import base64,json\npayload=json.loads(base64.b64decode('"+blob+"'))\n").encode()+br'''from pathlib import Path
import hashlib,os,subprocess,time
assert os.geteuid()==0 and os.uname().release=='7.0.0-38-kdlock1'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='f1442f01-e060-46fa-a480-da508d7ce8a9'
assert Path('/proc/sys/kernel/tainted').read_text().strip()=='0'
root=Path(payload['input']);assert not root.exists() and root.parent.resolve(strict=True)==root.parent
assert not Path(payload['target']).exists()
root.mkdir(mode=0o700)
for name,row in payload['files'].items():
 rel=Path(name);assert not rel.is_absolute() and '..' not in rel.parts
 data=base64.b64decode(row['data'],validate=True)
 assert (len(data),hashlib.sha256(data).hexdigest())==(row['bytes'],row['sha256'])
 target=root/rel;target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 assert hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256']
pins={n:{k:v for k,v in row.items() if k!='data'} for n,row in payload['files'].items()}
(root/'stage-receipt.json').write_text(json.dumps({'status':'EXACT_INPUTS_STAGED','files':pins,'boot_id':'f1442f01-e060-46fa-a480-da508d7ce8a9','unix':time.time()},indent=2)+'\n')
argv=['/usr/bin/python3','-B',str(root/'build.py'),'--plan-json',str(root/'plan.json'),'--plan-sha256',pins['plan.json']['sha256'],'--recovery-json',str(root/'recovery.json'),'--recovery-sha256',pins['recovery.json']['sha256']]
started=time.time()
with (root/'driver.stdout').open('xb') as stdout,(root/'driver.stderr').open('xb') as stderr:
 child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True)
 (root/'dispatch.json').write_text(json.dumps({'argv':argv,'pid':child.pid,'unix':started,'observer_seconds':1900},indent=2)+'\n')
 try:code=child.wait(timeout=1900)
 except subprocess.TimeoutExpired:code=None
result={'returncode':code,'elapsed_seconds':time.time()-started,'signals_sent':False,'source_commit':'6e486ecec398111fb5d5e30ffc76495f32f557b7','target':payload['target']}
(root/'driver-return.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
if code != 0:raise SystemExit(1)
'''
(OUT/'stage-and-build.py').write_bytes(raw)
(OUT/'input-index.json').write_text(json.dumps({n:{k:v for k,v in row.items() if k!='data'} for n,row in files.items()},indent=2,sort_keys=True)+'\n')
argv=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-']
(OUT/'command.json').write_text(json.dumps({'argv':argv,'stdin_sha256':sha(raw),'observer_seconds':1950,'scope':'One fresh source/O build, mutex object, bzImage, single NLS; no install/boot/test'},indent=2)+'\n')
started=time.time()
with (OUT/'result.json').open('xb') as out,(OUT/'stderr').open('xb') as err:
 child=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True)
 (OUT/'dispatch.json').write_text(json.dumps({'pid':child.pid,'started_unix':started},indent=2)+'\n')
 child.stdin.write(raw);child.stdin.close()
 try:code=child.wait(timeout=1950)
 except subprocess.TimeoutExpired:code=None
(OUT/'return.json').write_text(json.dumps({'returncode':code,'elapsed_seconds':time.time()-started,'signals_sent':False},indent=2)+'\n')
assert code==0,code
print((OUT/'result.json').read_text())
