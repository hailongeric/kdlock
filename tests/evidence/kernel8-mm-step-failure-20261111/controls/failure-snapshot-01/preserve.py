import datetime,json,os,re,socket,time
name='kd-mm-step-failed-20261111-01';pid=257489
assert os.readlink('/proc/'+str(pid)+'/exe')=='/usr/bin/qemu-system-x86_64'
assert open('/etc/hostname').read().strip()=='Super-Server'
paths=['/home/eric/vm/qemu-disks/ubuntu22.04.img','/home/eric/vm/qemu-disks/sda.qcow2','/home/eric/vm/qemu-disks/kdlock-builds2-20261031/builds.qcow2']
def disks():
 rows=[]
 for p in paths:
  st=os.stat(p);v=os.statvfs(p);free=v.f_bavail*v.f_frsize
  assert os.path.realpath(p)==p and free>=80*1024**3
  rows.append({'path':p,'device':st.st_dev,'inode':st.st_ino,'bytes':st.st_size,'allocated_bytes':st.st_blocks*512,'free':free})
 return rows
result={'snapshot_name':name,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pid':pid,'disks_before':disks(),'commands':[],'drain_claim':False,'reset_performed':False}
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(180);s.connect('/tmp/qemu-monitor.sock')
def prompt():
 b=b''
 while b'(qemu) ' not in b:
  c=s.recv(65536)
  if not c:raise RuntimeError('monitor closed')
  b+=c
  if len(b)>8*1024*1024:raise RuntimeError('monitor output bound')
 return b.decode(errors='replace')
def command(text):
 s.sendall((text+'\n').encode());reply=prompt();result['commands'].append({'command':text,'output':reply});return reply
result['greeting']=prompt();before=command('info snapshots');assert name not in before
jobs=command('info block-jobs');assert 'No active jobs' in jobs or 'No active block jobs' in jobs
command('info status')
saved=command('savevm '+name)
after=command('info snapshots');assert name in after
for drive in ['drive_system','drive_data1','drive_kdlock_builds2']:
 reply=command('info block -v '+drive);assert name in reply
result['status']='FAILED_VM_SNAPSHOT_PRESERVED_ON_ALL_THREE_DISKS';result['disks_after']=disks();result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();command('info status');s.close()
print(json.dumps(result,sort_keys=True))
