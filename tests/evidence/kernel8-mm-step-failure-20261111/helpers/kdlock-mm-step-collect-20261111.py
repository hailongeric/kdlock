"""Copy a bounded read-only snapshot of retained-run evidence."""
from pathlib import Path
import base64,hashlib,json,subprocess,time
OUT=Path('/tmp/kdlock-kernel8-mm-step-collection-20261111-01')
assert not OUT.exists();OUT.mkdir()
raw=br'''from pathlib import Path
import base64,hashlib,json,os,stat,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
kernel=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts')
roots={'runtime':base/'mm-mmap-step-live-0798c1ab-01','outer':base/'mm-mmap-step-receipts-0798c1ab-01','input':base/'mm-mmap-step-input-0798c1ab-01','diagnostic-partial':base/'mm-mmap-step-diagnostic-02','repeat':kernel/'repeat-kdrebuild8-mm-step-01','postboot':kernel/'postboot-kdrebuild8-mm-step-01'}
def identity(p):
 s=p.stat();return [s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
selected={}
for prefix,root in roots.items():
 assert root.resolve(strict=True)==root
 for p in sorted(root.rglob('*')):
  assert not p.is_symlink()
  if p.is_file():
   assert stat.S_ISREG(p.stat().st_mode)
   selected[prefix+'/'+str(p.relative_to(root))]=p
assert len(selected)<=2048 and sum(p.stat().st_size for p in selected.values())<=128*1024*1024
result={'stage':'READ_ONLY_SNAPSHOT_ACTORS_RETAINED_NO_DRAIN_CLAIM','captured_unix':time.time(),'files':[],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'taint':Path('/proc/sys/kernel/tainted').read_text().strip()}
assert result['boot_id']=='4a98638f-c01c-4fc9-8de8-69a74346aa0f'
for name,p in selected.items():
 before=identity(p);assert before[4]<=32*1024*1024
 data=p.read_bytes();after=identity(p);assert before==after and len(data)==before[4],str(p)
 result['files'].append({'path':name,'source':str(p),'identity_before':before,'identity_after':after,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'data':base64.b64encode(data).decode()})
result['finished_unix']=time.time()
print(json.dumps(result,sort_keys=True,separators=(',',':')))
'''
(OUT/'read.py').write_bytes(raw)
argv=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-']
(OUT/'command.json').write_text(json.dumps({'argv':argv,'stdin_sha256':hashlib.sha256(raw).hexdigest(),'timeout_seconds':120,'scope':'Bounded regular evidence files; no actor control or cleanup'},indent=2)+'\n')
started=time.time()
with (OUT/'transport.json').open('xb') as stdout,(OUT/'stderr').open('xb') as stderr:
 result=subprocess.run(argv,input=raw,stdout=stdout,stderr=stderr,timeout=120)
(OUT/'return.json').write_text(json.dumps({'returncode':result.returncode,'elapsed_seconds':time.time()-started},indent=2)+'\n')
assert result.returncode==0,result.returncode
transport=OUT/'transport.json';assert transport.stat().st_size<=180*1024*1024
data=json.loads(transport.read_text());payload=OUT/'payload';payload.mkdir()
index=[];total=0
for row in data['files']:
 name=Path(row['path']);assert not name.is_absolute() and '..' not in name.parts
 raw=base64.b64decode(row['data'],validate=True)
 assert (len(raw),hashlib.sha256(raw).hexdigest())==(row['bytes'],row['sha256']) and row['identity_before']==row['identity_after']
 path=payload/name;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as f:f.write(raw)
 assert path.read_bytes()==raw;total+=len(raw)
 index.append({k:v for k,v in row.items() if k!='data'})
(OUT/'copy-index.json').write_text(json.dumps({'stage':data['stage'],'boot_id':data['boot_id'],'taint':data['taint'],'files':index},indent=2,sort_keys=True)+'\n')
print(json.dumps({'stage':data['stage'],'files':len(index),'raw_bytes':total,'taint':data['taint'],'transport_bytes':transport.stat().st_size,'transport_sha256':hashlib.sha256(transport.read_bytes()).hexdigest()}))
