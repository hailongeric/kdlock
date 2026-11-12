"""Copy completed kernel9 build evidence without loading or installing code."""
from pathlib import Path
import base64,hashlib,json,subprocess,time
OUT=Path('/tmp/kdlock-kernel9-build-collection-20261111-01')
assert not OUT.exists();OUT.mkdir()
raw=br'''from pathlib import Path
import base64,hashlib,json,os,stat,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel9-6e486ece-01');inp=Path('/mnt/kdlock-builds2/kdlock-main-kernel9-input-6e486ece-01')
result=json.loads((base/'receipts/build-01/result.json').read_text())
assert result['status']=='KERNEL9_BUILD_AND_LINKED_IDENTITY_COMPLETE'
assert json.loads((inp/'driver-return.json').read_text())['returncode']==0
assert os.uname().release=='7.0.0-38-kdlock1' and Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='f1442f01-e060-46fa-a480-da508d7ce8a9'
selected={}
for prefix,root in [('input',inp),('receipts',base/'receipts')]:
 assert root.resolve(strict=True)==root
 for p in sorted(root.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():selected[prefix+'/'+str(p.relative_to(root))]=p
for name in ['kernel/kdlock/kernel/mutex.o','kernel/kdlock/kernel/.mutex.o.cmd','.config','Module.symvers','System.map','arch/x86/boot/bzImage','certs/signing_key.x509','fs/nls/nls_iso8859-1.ko','include/config/auto.conf','include/config/kernel.release','include/generated/autoconf.h','include/generated/utsrelease.h','include/generated/utsversion.h','modules.builtin','modules.builtin.modinfo','modules.order','vmlinux.symvers']:
 selected['build/'+name]=base/'build'/name
selected['source/mutex.c']=base/'source/kernel/kdlock/kernel/mutex.c'
assert len(selected)<=256 and sum(p.stat().st_size for p in selected.values())<=192*1024*1024
def identity(p):
 s=p.stat();assert stat.S_ISREG(s.st_mode);return [s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
transport={'stage':'COMPLETED_BUILD_ONLY_NO_INSTALL_BOOT_OR_RUNTIME_TEST','files':[],'captured_unix':time.time(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'release':os.uname().release,'taint':Path('/proc/sys/kernel/tainted').read_text().strip()}
for name,p in selected.items():
 assert p.resolve(strict=True)==p and '.pem' not in p.name
 before=identity(p);assert before[4]<=96*1024*1024
 data=p.read_bytes();after=identity(p);assert before==after and len(data)==before[4]
 transport['files'].append({'path':name,'source':str(p),'identity_before':before,'identity_after':after,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'data':base64.b64encode(data).decode()})
transport['finished_unix']=time.time()
print(json.dumps(transport,sort_keys=True,separators=(',',':')))
'''
(OUT/'read.py').write_bytes(raw)
argv=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-']
(OUT/'command.json').write_text(json.dumps({'argv':argv,'stdin_sha256':hashlib.sha256(raw).hexdigest(),'observer_seconds':120},indent=2)+'\n')
started=time.time()
with (OUT/'transport.json').open('xb') as out,(OUT/'stderr').open('xb') as err:
 p=subprocess.run(argv,input=raw,stdout=out,stderr=err,timeout=120)
(OUT/'return.json').write_text(json.dumps({'returncode':p.returncode,'elapsed_seconds':time.time()-started},indent=2)+'\n')
assert p.returncode==0,p.returncode
d=json.loads((OUT/'transport.json').read_text());index=[]
for row in d['files']:
 rel=Path(row['path']);assert not rel.is_absolute() and '..' not in rel.parts
 data=base64.b64decode(row['data'],validate=True)
 assert (len(data),hashlib.sha256(data).hexdigest())==(row['bytes'],row['sha256'])
 path=OUT/'payload'/rel;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as f:f.write(data)
 assert path.read_bytes()==data
 index.append({k:v for k,v in row.items() if k!='data'})
metadata={k:v for k,v in d.items() if k!='files'};metadata.update(files=index,raw_bytes=sum(x['bytes'] for x in index),transport_sha256=hashlib.sha256((OUT/'transport.json').read_bytes()).hexdigest())
(OUT/'copy-index.json').write_text(json.dumps(metadata,indent=2,sort_keys=True)+'\n')
print(json.dumps({'stage':d['stage'],'files':len(index),'raw_bytes':metadata['raw_bytes'],'transport_sha256':metadata['transport_sha256']}))
