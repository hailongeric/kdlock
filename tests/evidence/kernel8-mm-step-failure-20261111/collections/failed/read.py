from pathlib import Path
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
