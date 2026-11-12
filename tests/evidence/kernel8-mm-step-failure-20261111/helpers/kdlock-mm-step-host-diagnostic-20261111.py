"""Read the existing VM console and QEMU diagnostic state only."""
from pathlib import Path
import base64,hashlib,json,subprocess,time
BASE=Path('/tmp/kdlock-kernel8-mm-step-20261111-01')
OUT=BASE/'host-diagnostic-01';assert not OUT.exists();OUT.mkdir()
raw=br'''import base64,datetime,json,os,socket
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
'''
(OUT/'read.py').write_bytes(raw)
argv=['ssh','-T','-p','22','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71','sudo','-n','python3','-B','-']
(OUT/'command.json').write_text(json.dumps({'argv':argv,'stdin_sha256':hashlib.sha256(raw).hexdigest(),'timeout_seconds':60,'scope':'Read existing serial bytes and info-only QEMU status/register/snapshot commands'},indent=2)+'\n')
started=time.time()
with (OUT/'result.json').open('xb') as stdout,(OUT/'stderr').open('xb') as stderr:
 result=subprocess.run(argv,input=raw,stdout=stdout,stderr=stderr,timeout=60)
(OUT/'return.json').write_text(json.dumps({'returncode':result.returncode,'elapsed_seconds':time.time()-started},indent=2)+'\n')
assert result.returncode==0,result.returncode
record=json.loads((OUT/'result.json').read_text());serial=base64.b64decode(record['serial']['data'],validate=True)
(OUT/'serial-tail.bin').write_bytes(serial)
for i,row in enumerate(record['hmp']): (OUT/f'info-{i:02d}.txt').write_text(row['output'])
print(json.dumps({'returncode':result.returncode,'utc':record['utc'],'serial_bytes':len(serial),'serial_sha256':hashlib.sha256(serial).hexdigest(),'info_commands':[r['command'] for r in record['hmp']]}))
print(serial.decode(errors='replace')[-18000:])
