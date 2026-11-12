from pathlib import Path
import datetime,hashlib,json,os,struct,subprocess
def read(p):return Path(p).read_text().strip()
def command(argv):
 r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 return {'argv':argv,'returncode':r.returncode,'stdout':r.stdout.decode(errors='replace'),'stderr':r.stderr.decode(errors='replace')}
assert os.geteuid()==0
notes=Path('/sys/kernel/notes').read_bytes();pos=0;ids=[]
while pos+12<=len(notes):
 namesz,descsz,typ=struct.unpack_from('<III',notes,pos);pos+=12
 name=notes[pos:pos+namesz];pos+=(namesz+3)&~3
 desc=notes[pos:pos+descsz];pos+=(descsz+3)&~3
 if name.rstrip(b'\0')==b'GNU' and typ==3:ids.append(desc.hex())
processes=[];blocked=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit() or int(p.name) in [os.getpid(),os.getppid()]:continue
 try:
  cmd=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace');status=(p/'status').read_text();state=next(x for x in status.splitlines() if x.startswith('State:'))
 except (FileNotFoundError,ProcessLookupError,PermissionError):continue
 row={'pid':int(p.name),'cmdline':cmd,'state':state}
 if any(x in cmd for x in ['mmap-userspace','run_runtime_fixture','run_rwsem_runtime_fixture','mmap_api/runner.py','kdlock-translation','cc1','make -']):processes.append(row)
 if state.split()[1]=='D':blocked.append(row)
disks=[]
for p in ['/','/mnt/kdlock-builds','/mnt/kdlock-builds2']:
 v=os.statvfs(p);disks.append({'path':p,'free':v.f_bavail*v.f_frsize,'total':v.f_blocks*v.f_frsize})
result={'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hostname':read('/etc/hostname'),'release':os.uname().release,'boot_id':read('/proc/sys/kernel/random/boot_id'),'build_ids':ids,'taint':read('/proc/sys/kernel/tainted'),'modules':read('/proc/modules'),'cmdline':read('/proc/cmdline'),'cpu_online':read('/sys/devices/system/cpu/online'),'meminfo':read('/proc/meminfo'),'preemption':read('/sys/kernel/debug/sched/preempt'),'grub_env':command(['grub-editenv','/boot/grub/grubenv','list']),'dmesg':command(['dmesg','--color=never']),'processes':processes,'blocked_processes':blocked,'disks':disks,'prior_run_drain':False,'recovery_method':'QEMU reset after preserved failed-state snapshot'}
print(json.dumps(result,sort_keys=True))
