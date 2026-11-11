
import os,json,subprocess,datetime,socket,re,stat
data={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hostname':open('/etc/hostname').read().strip(),'uid':os.getuid(),'uname':list(os.uname())}
pid=257489
args=open('/proc/'+str(pid)+'/cmdline','rb').read().split(b'\0')
args=[a.decode() for a in args if a]
data['qemu']={'pid':pid,'exe':os.readlink('/proc/'+str(pid)+'/exe'),'argv':args}
paths=['/home/eric/vm/qemu-disks/ubuntu22.04.img','/home/eric/vm/qemu-disks/sda.qcow2','/home/eric/vm/qemu-disks/kdlock-builds2-20261031/builds.qcow2']
data['images']=[]
for path in paths:
 st=os.stat(path);v=os.statvfs(path)
 data['images'].append({'path':path,'realpath':os.path.realpath(path),'device':st.st_dev,'inode':st.st_ino,'mode':st.st_mode,'apparent_bytes':st.st_size,'allocated_bytes':st.st_blocks*512,'mtime_ns':st.st_mtime_ns,'host_fs_available':v.f_bavail*v.f_frsize,'open_fds':[]})
for fd in os.listdir('/proc/'+str(pid)+'/fd'):
 try:p=os.readlink('/proc/'+str(pid)+'/fd/'+fd)
 except FileNotFoundError:continue
 for row in data['images']:
  if p==row['path']:row['open_fds'].append(int(fd))
sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.settimeout(3);sock.connect('/tmp/qemu-monitor.sock')
def prompt():
 b=b''
 while b'(qemu) ' not in b:
  part=sock.recv(4096)
  if not part:raise RuntimeError('monitor closed')
  b+=part
  if len(b)>262144:raise RuntimeError('monitor response bound exceeded')
 return b.decode(errors='replace')
data['hmp_greeting']=prompt();data['hmp']=[]
for command in ['info status','info block','info snapshots']:
 sock.sendall((command+'\n').encode());data['hmp'].append({'command':command,'output':prompt()})
sock.close()
print(json.dumps({'phase':'metadata','data':data},sort_keys=True),flush=True)
# This is a normal read-only qemu-img open. No -U/--force-share or lock bypass.
p=subprocess.run(['qemu-img','info','--output=json','--backing-chain',paths[0]],capture_output=True,text=True,timeout=15)
print(json.dumps({'phase':'qemu_img_info','argv':['qemu-img','info','--output=json','--backing-chain',paths[0]],'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr},sort_keys=True),flush=True)
raise SystemExit(p.returncode)
