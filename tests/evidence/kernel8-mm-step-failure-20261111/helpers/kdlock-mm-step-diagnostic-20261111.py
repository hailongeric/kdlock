"""Capture retained-run observations without changing its actors or state."""
from pathlib import Path
import hashlib,json,subprocess,time
BASE=Path('/tmp/kdlock-kernel8-mm-step-20261111-01')
OUT=BASE/'diagnostic-step-01'
assert not OUT.exists();OUT.mkdir()
raw=b'''from pathlib import Path
import hashlib,json,os,subprocess,time
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
out=base/'mm-mmap-step-diagnostic-01'
assert not out.exists();out.mkdir(mode=0o700)
record={'started_unix':time.time(),'mutations_to_test':False,'signals_or_cleanup':False,'files':{},'tasks':{}}
def capture(name,data):
 p=out/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 record['files'][name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def identity():
 return {'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'release':os.uname().release,'taint':Path('/proc/sys/kernel/tainted').read_text().strip(),'modules':Path('/proc/modules').read_text()}
record['identity_before']=identity()
assert record['identity_before']['boot_id']=='4a98638f-c01c-4fc9-8de8-69a74346aa0f'
for name,argv in [('kernel-log.txt',['/usr/bin/dmesg','--raw']),('task-list.txt',['/usr/bin/ps','-eLo','pid,tid,psr,stat,wchan:32,comm'])]:
 r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
 capture(name,r.stdout);capture(name+'.stderr',r.stderr);record[name+'_returncode']=r.returncode
for pid in [2902,2908]:
 parent=Path('/proc')/str(pid)
 if not parent.exists():record['tasks'][str(pid)]={'absent':True};continue
 tids=sorted(p for p in (parent/'task').iterdir() if p.name.isdigit())
 assert len(tids)<=128
 for thread in tids:
  row={}
  for leaf in ['comm','stat','status','stack','wchan','syscall','children']:
   try:
    data=(thread/leaf).read_bytes();assert len(data)<=65536;capture('tasks/'+thread.name+'/'+leaf,data);row[leaf]='captured'
   except (OSError,AssertionError) as e:row[leaf]=repr(e)
  record['tasks'][thread.name]=row
device=Path('/dev/kd_mmap_api_events')
if device.exists():
 with device.open('rb',buffering=0) as f:
  parts=[];total=0
  while True:
   part=f.read(min(65536,10485801-total))
   if not part:break
   parts.append(part);total+=len(part);assert total<=10485800
  data=b''.join(parts)
 capture('events-current.bin',data)
else:record['events_device_absent']=True
record['identity_after']=identity();record['elapsed_seconds']=time.time()-record['started_unix']
capture('capture-summary.json',(json.dumps(record,indent=2,sort_keys=True)+'\n').encode())
print(json.dumps({'status':'RETAINED_RUN_READ_ONLY_DIAGNOSTICS_CAPTURED','path':str(out),'files':record['files'],'identity_after':record['identity_after'],'tasks':record['tasks']},sort_keys=True))
'''
(OUT/'read.py').write_bytes(raw)
argv=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-']
(OUT/'command.json').write_text(json.dumps({'argv':argv,'stdin_sha256':hashlib.sha256(raw).hexdigest(),'timeout_seconds':45,'scope':'Read existing task stacks/log and one immutable-prefix event snapshot; no test control or cleanup'},indent=2)+'\n')
started=time.time()
with (OUT/'result.json').open('xb') as stdout,(OUT/'stderr').open('xb') as stderr:
 r=subprocess.run(argv,input=raw,stdout=stdout,stderr=stderr,timeout=45)
(OUT/'return.json').write_text(json.dumps({'returncode':r.returncode,'elapsed_seconds':time.time()-started},indent=2)+'\n')
assert r.returncode==0,r.returncode
value=json.loads((OUT/'result.json').read_text())
print(json.dumps({'status':value['status'],'path':value['path'],'files':len(value['files']),'identity_after':value['identity_after']}))
