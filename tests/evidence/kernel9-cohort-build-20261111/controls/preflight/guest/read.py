from pathlib import Path
import hashlib,json,os,subprocess,time
def sha(p):return hashlib.file_digest(open(p,'rb'),'sha256').hexdigest()
def command(argv,timeout=30):
 p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 return {'argv':argv,'returncode':p.returncode,'stdout':p.stdout.decode(errors='replace'),'stderr':p.stderr.decode(errors='replace')}
tools={}
for name in ['python3','cp','make','gcc','ld','as','readelf','objdump','modinfo']:
 import shutil
 path=Path(shutil.which(name));real=path.resolve(strict=True)
 tools[name]={'path':str(path),'realpath':str(real),'sha256':sha(real)}
root=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01')
disks={}
for p in ['/','/mnt/kdlock-builds2']:
 v=os.statvfs(p);disks[p]={'free_bytes':v.f_bavail*v.f_frsize,'block_bytes':v.f_frsize}
result={'captured_unix':time.time(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'release':os.uname().release,'taint':Path('/proc/sys/kernel/tainted').read_text().strip(),'modules':Path('/proc/modules').read_text(),'tools':tools,'disks':disks,'seed_allocated':command(['du','-s','-B1',str(root/'source'),str(root/'build')]),'grub_env':command(['grub-editenv','/boot/grub/grubenv','list'])}
assert result['boot_id']=='f1442f01-e060-46fa-a480-da508d7ce8a9' and result['release']=='7.0.0-38-kdlock1' and result['taint']=='0'
print(json.dumps(result,sort_keys=True))
