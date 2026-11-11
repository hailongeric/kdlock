from pathlib import Path
import os,json,hashlib,struct
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01')
def blob(path,limit):
 p=Path(path)
 if not p.exists():return {'exists':False}
 with p.open('rb') as f:b=f.read(limit+1)
 if len(b)>limit:raise RuntimeError('bounded read exceeded: '+str(p))
 return {'exists':True,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'data':b}
def receipt(path):
 x=blob(path,2*1024**2)
 if not x['exists']:return x
 value=json.loads(x.pop('data'));out={k:value.get(k) for k in ('status','identity_before','identity_after','original_failure_preserved','archive','restored_producer','actions')}
 out['wire']=[{k:row.get(k) for k in ('operation','sequence','status','reply_bytes')} for row in value.get('wire',[])]
 return {**x,'summary':out}
notes=Path('/sys/kernel/notes').read_bytes();buildids=[];off=0
while off+12<=len(notes):
 namesz,descsz,kind=struct.unpack_from('<III',notes,off);off+=12
 if off+((namesz+3)&~3)+((descsz+3)&~3)>len(notes):raise RuntimeError('kernel notes bounds')
 name=notes[off:off+namesz];off+=(namesz+3)&~3;desc=notes[off:off+descsz];off+=(descsz+3)&~3
 if kind==3 and name.rstrip(b'\0')==b'GNU':buildids.append(desc.hex())
actors=[];blocked=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit() or int(p.name)==os.getpid():continue
 try:
  raw=(p/'stat').read_text();tail=raw[raw.rfind(')')+2:].split();comm=(p/'comm').read_text().strip();argv=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
  row={'pid':int(p.name),'comm':comm,'state':tail[0],'startticks':int(tail[19]),'argv':argv,'wchan':(p/'wchan').read_text().strip()}
  tokens=('tests/kernel/','killable-','mm-provider-context','kdlock-kernel8','collect.py','collection-helper.py')
  if any(t in argv for t in tokens) or comm in ('make','cc1','gcc','gcc-15','ld','as','insmod','rmmod','modprobe','mmap-userspace') or int(p.name) in (12651,13652):actors.append(row)
  if tail[0]=='D':blocked.append(row)
 except (FileNotFoundError,ProcessLookupError):continue
state={'identity':{'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'release':os.uname().release,'taint':int(Path('/proc/sys/kernel/tainted').read_text())},'running_build_ids':buildids,'kernel_notes_sha256':hashlib.sha256(notes).hexdigest(),'modules':Path('/proc/modules').read_text(),'devices':[p.name for p in Path('/dev').iterdir() if 'fixture' in p.name or p.name.startswith(('kd_rwsem','kd_mmap'))],'actors':actors,'blocked':blocked,'disks':{}}
for p in ('/',str(base)):
 s=os.statvfs(p);state['disks'][p]={'available':s.f_bavail*s.f_frsize,'device':os.stat(p).st_dev}
state['k03_cleanup']=receipt(base/'recovery-killable-final-01/result.json')
for label,path in [('original_runner',base/'managed-killable-live-03/result.json'),('original_outer',base/'managed-killable-receipts-03/result.json')]:
 x=blob(path,2*1024**2)
 if x['exists']:
  value=json.loads(x.pop('data'));x['status']=value.get('status');x['error']=value.get('error');x['case_names']=[r['name'] for r in value.get('cases',[])]
 state[label]=x
for label,path in [('provider_input',base/'mm-provider-context-input-de76da8a-01'),('provider_output',base/'mm-provider-context-build-de76da8a-01')]:
 state[label]={'path':str(path),'exists':path.exists(),'top_entries':sorted(p.name for p in path.iterdir())[:128] if path.exists() else []}
state['provider_build']=receipt(base/'mm-provider-context-build-de76da8a-01/receipts/result.json')
print(json.dumps(state,sort_keys=True))
