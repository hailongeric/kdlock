from pathlib import Path
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
