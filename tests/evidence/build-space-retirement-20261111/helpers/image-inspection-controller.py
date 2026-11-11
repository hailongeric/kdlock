#!/usr/bin/env python3
"""Capture only read-only guest block and host live-image metadata."""
import datetime, hashlib, json, os, subprocess
from pathlib import Path

OUT=Path('/tmp/kdlock-host-image-size-20261111-01')
OUT.mkdir(mode=0o700)
GUEST=r'''
import os,json,subprocess,datetime
data={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hostname':open('/etc/hostname').read().strip(),'uid':os.getuid(),'uname':list(os.uname()),'boot':open('/proc/sys/kernel/random/boot_id').read().strip(),'taint':open('/proc/sys/kernel/tainted').read().strip()}
data['lsblk']=json.loads(subprocess.run(['lsblk','-b','-J','-o','NAME,KNAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,PKNAME,MODEL,SERIAL,HCTL,TRAN'],capture_output=True,text=True,check=True,timeout=10).stdout)
data['mounts']={}
for path in ['/','/boot/efi','/mnt/kdlock-builds','/mnt/kdlock-builds2']:
 p=subprocess.run(['findmnt','-J','-T',path,'-o','TARGET,SOURCE,FSTYPE,OPTIONS'],capture_output=True,text=True,check=True,timeout=5)
 st=os.statvfs(path);data['mounts'][path]={'findmnt':json.loads(p.stdout),'filesystem_bytes':st.f_blocks*st.f_frsize,'available_bytes':st.f_bavail*st.f_frsize}
data['sysfs']={n:os.path.realpath('/sys/block/'+n+'/device') for n in ['sda','sdb','sdc'] if os.path.exists('/sys/block/'+n)}
print(json.dumps(data,sort_keys=True))
'''
HOST=r'''
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
'''

for label,port,user,remote,payload in [
 ('guest',2222,'root','timeout 25s python3 -',GUEST),
 ('host',22,'eric','sudo -n timeout 25s python3 -',HOST)]:
 argv=['ssh','-p',str(port),'-o','BatchMode=yes','-o','ConnectTimeout=10',user+'@10.176.26.71',remote]
 (OUT/(label+'-script.py')).write_text(payload)
 result=subprocess.run(argv,input=payload.encode(),capture_output=True,timeout=35)
 (OUT/(label+'-stdout.jsonl')).write_bytes(result.stdout)
 (OUT/(label+'-stderr.log')).write_bytes(result.stderr)
 receipt={'label':label,'argv':argv,'returncode':result.returncode,'script_sha256':hashlib.sha256(payload.encode()).hexdigest(),'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(result.stderr).hexdigest(),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 (OUT/(label+'-receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n')
 print(json.dumps(receipt),flush=True)
 if result.returncode:
  print(json.dumps({'status':'STOPPED','no_retry_or_alternate_access':True,'receipt_root':str(OUT)}),flush=True)
  raise SystemExit(result.returncode)
print(json.dumps({'status':'COMPLETE','receipt_root':str(OUT)}),flush=True)
