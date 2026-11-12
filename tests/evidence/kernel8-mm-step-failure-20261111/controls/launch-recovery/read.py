
import datetime,json,os,socket
pid=257489;prefix='/proc/'+str(pid)
data={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hostname':open('/etc/hostname').read().strip(),'uname':list(os.uname()),'pid':pid,'exe':os.readlink(prefix+'/exe'),'stat':open(prefix+'/stat').read(),'argv':[x.decode() for x in open(prefix+'/cmdline','rb').read().split(b'\0') if x]}
assert data['hostname']=='Super-Server' and data['exe']=='/usr/bin/qemu-system-x86_64'
data['images']=[]
for path in ['/home/eric/vm/qemu-disks/ubuntu22.04.img','/home/eric/vm/qemu-disks/sda.qcow2','/home/eric/vm/qemu-disks/kdlock-builds2-20261031/builds.qcow2']:
 st=os.stat(path);v=os.statvfs(path)
 data['images'].append({'path':path,'realpath':os.path.realpath(path),'device':st.st_dev,'inode':st.st_ino,'apparent_bytes':st.st_size,'allocated_bytes':st.st_blocks*512,'mtime_ns':st.st_mtime_ns,'host_available':v.f_bavail*v.f_frsize,'open_fds':[]})
for fd in os.listdir(prefix+'/fd'):
 try:p=os.readlink(prefix+'/fd/'+fd)
 except FileNotFoundError:continue
 for row in data['images']:
  if p==row['path']:row['open_fds'].append(fd)
assert all(r['open_fds'] and r['path']==r['realpath'] for r in data['images'])
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(5);s.connect('/tmp/qemu-monitor.sock')
def prompt():
 b=b''
 while b'(qemu) ' not in b:
  c=s.recv(16384)
  if not c:raise RuntimeError('monitor closed')
  b+=c
  if len(b)>1024*1024:raise RuntimeError('monitor output bound')
 return b.decode(errors='replace')
data['greeting']=prompt();data['hmp']=[]
for cmd in ['info version','info status','info block','info block -v drive_system','info block -v drive_data1','info block -v drive_kdlock_builds2','info snapshots','info block-jobs']:
 s.sendall((cmd+'\n').encode());reply=prompt();data['hmp'].append({'command':cmd,'output':reply})
s.close();print(json.dumps(data,sort_keys=True))
