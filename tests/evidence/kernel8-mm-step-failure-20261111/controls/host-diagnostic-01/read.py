import base64,datetime,json,os,socket
pid=257489;prefix='/proc/'+str(pid)
exe=os.readlink(prefix+'/exe');assert exe=='/usr/bin/qemu-system-x86_64'
assert open('/etc/hostname').read().strip()=='Super-Server'
argv=[v.decode() for v in open(prefix+'/cmdline','rb').read().split(b'\0') if v]
assert '/home/eric/vm/qemu-disks/ubuntu22.04.img' in ' '.join(argv)
data={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pid':pid,'exe':exe,'stat':open(prefix+'/stat').read(),'argv':argv,'hmp':[]}
p='/tmp/qemu-serial.log'
with open(p,'rb') as f:
 s=os.fstat(f.fileno());start=max(0,s.st_size-1048576);f.seek(start);raw=f.read(s.st_size-start);after=os.fstat(f.fileno())
 assert (s.st_dev,s.st_ino)==(after.st_dev,after.st_ino) and len(raw)==s.st_size-start
 data['serial']={'path':p,'start':start,'end':s.st_size,'size_after':after.st_size,'data':base64.b64encode(raw).decode()}
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(5);s.connect('/tmp/qemu-monitor.sock')
def prompt():
 b=b''
 while b'(qemu) ' not in b:
  c=s.recv(65536)
  if not c:raise RuntimeError('monitor closed')
  b+=c
  if len(b)>4194304:raise RuntimeError('diagnostic output bound')
 return b.decode(errors='replace')
data['greeting']=prompt()
for command in ['info status','info cpus','info registers -a','info block-jobs','info snapshots']:
 s.sendall((command+'\n').encode());data['hmp'].append({'command':command,'output':prompt()})
s.close();print(json.dumps(data,sort_keys=True))
