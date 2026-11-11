
import os,json,subprocess,datetime
data={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hostname':open('/etc/hostname').read().strip(),'uid':os.getuid(),'uname':list(os.uname()),'boot':open('/proc/sys/kernel/random/boot_id').read().strip(),'taint':open('/proc/sys/kernel/tainted').read().strip()}
data['lsblk']=json.loads(subprocess.run(['lsblk','-b','-J','-o','NAME,KNAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,PKNAME,MODEL,SERIAL,HCTL,TRAN'],capture_output=True,text=True,check=True,timeout=10).stdout)
data['mounts']={}
for path in ['/','/boot/efi','/mnt/kdlock-builds','/mnt/kdlock-builds2']:
 p=subprocess.run(['findmnt','-J','-T',path,'-o','TARGET,SOURCE,FSTYPE,OPTIONS'],capture_output=True,text=True,check=True,timeout=5)
 st=os.statvfs(path);data['mounts'][path]={'findmnt':json.loads(p.stdout),'filesystem_bytes':st.f_blocks*st.f_frsize,'available_bytes':st.f_bavail*st.f_frsize}
data['sysfs']={n:os.path.realpath('/sys/block/'+n+'/device') for n in ['sda','sdb','sdc'] if os.path.exists('/sys/block/'+n)}
print(json.dumps(data,sort_keys=True))
