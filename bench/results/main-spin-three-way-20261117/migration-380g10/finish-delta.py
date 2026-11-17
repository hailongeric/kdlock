from pathlib import Path
import sys,json,base64,hashlib,time
from rpc import rpc
R=Path('/tmp/kdlock-380g10-migration-20261117');blob=(R/'delta.json.gz').read_bytes();names=[]
for i,start in enumerate(range(0,len(blob),131072)):
 name=f'main-spin-migration-delta-{i:03d}';data=blob[start:start+131072]
 v=rpc({'id':name,'action':'put','name':name,'data':base64.b64encode(data).decode(),'sha256':hashlib.sha256(data).hexdigest()},timeout=60)
 assert v.get('written')==len(data),v;names.append(name);print('Delta chunk verified',i+1,flush=True)
meta=json.loads((R/'package.json').read_text())
code='''import pathlib,hashlib,json,gzip,zlib,base64,os,termios,subprocess
P=pathlib.Path
meta=META
names=NAMES
root=P('/var/lib/kdlock-run');blob=b''.join((root/n).read_bytes() for n in names)
assert hashlib.sha256(blob).hexdigest()=='DELTAHASH'
delta=json.loads(gzip.decompress(blob))
parts=[root/('main-spin-migration-20261117-part-%04d'%i) for i in range(delta['prefix_parts'])]
prefix=b''.join(p.read_bytes() for p in parts)
assert hashlib.sha256(prefix).hexdigest()==delta['prefix_sha256']
base=zlib.decompressobj(31).decompress(prefix)
assert hashlib.sha256(base).hexdigest()==delta['base_sha256']
assert os.uname().release=='7.0.0-38-kdrebuild16'
assert P('/proc/sys/kernel/random/boot_id').read_text().strip()=='84a3b76f-af03-4db6-86b4-7d81e2472f50'
assert not P('/sys/module/kd_bench').exists()
fd=os.open('/dev/ttyS0',os.O_RDWR|os.O_NOCTTY);speed=termios.tcgetattr(fd)[4:6];os.close(fd);assert speed==[9600,9600],speed
dest=P(meta['destination']);dest.mkdir(exist_ok=False)
def target(name):
 p=P(name);assert not p.is_absolute() and '..' not in p.parts
 return dest/p
for name,mode in delta['dirs']:target(name).mkdir(parents=True,exist_ok=True)
literals=[base64.b64decode(b) for b in delta['literals']]
for item in delta['files']:
 p=target(item['name']);p.parent.mkdir(parents=True,exist_ok=True)
 if 'link' in item:
  assert (p.parent/item['link']).resolve().is_relative_to(dest.resolve())
  p.symlink_to(item['link']);continue
 remain=item['bytes'];digest=hashlib.sha256()
 with p.open('xb') as out:
  for op in item['ops']:
   block=base[op-1:op+511] if op>0 else literals[-op-1]
   assert len(block)==512
   block=block[:min(remain,512)];out.write(block);digest.update(block);remain-=len(block)
 assert remain==0 and digest.hexdigest()==item['sha256'],item['name']
 os.chmod(p,item['mode'])
# Independently reread every reconstructed file before reporting success.
for item in delta['files']:
 p=target(item['name'])
 if 'link' in item:assert os.readlink(p)==item['link'];continue
 assert p.stat().st_size==item['bytes']
 assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256'],item['name']
receipt={'destination':str(dest),'source_package':meta,'method':'verified block reconstruction from transferred prefix and delta','verified_entries':len(delta['files']),'kernel':os.uname().release,'boot':P('/proc/sys/kernel/random/boot_id').read_text().strip(),'modules':P('/proc/modules').read_text(),'loaded_modules':False,'built':False,'serial_speed':speed,'warnings':[s for s in subprocess.check_output(['dmesg'],text=True).splitlines() if 'soft lockup' in s or 'BUG:' in s]}
(dest/'migration-receipt.json').write_text(json.dumps(receipt,indent=2))
for p in parts+[root/n for n in names]:p.unlink()
os.sync();print(json.dumps(receipt))
'''.replace('META',repr(meta)).replace('NAMES',repr(names)).replace('DELTAHASH',hashlib.sha256(blob).hexdigest())
q={'id':'main-spin-migration-delta-finish-20261117','action':'start','argv':['python3','-B','-c',code]};v=rpc(q,timeout=60);assert v.get('started'),v
for _ in range(120):
 v=rpc({'id':q['id']+'-poll','action':'poll','job':q['id']},timeout=30)
 if v.get('returncode') is not None:break
 time.sleep(1)
(R/'migration-result.json').write_text(json.dumps(v,indent=2));print(json.dumps(v),flush=True);assert v.get('returncode')==0
