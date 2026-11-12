"""Preserve existing serial bytes before recovery; no VM state change."""
from pathlib import Path
import gzip,hashlib,json,subprocess,time
BASE=Path('/tmp/kdlock-kernel8-mm-step-20261111-01');OUT=BASE/'serial-full-01'
assert not OUT.exists();OUT.mkdir()
raw=br'''import gzip,hashlib,json,os,sys,time
assert os.readlink('/proc/257489/exe')=='/usr/bin/qemu-system-x86_64'
assert open('/etc/hostname').read().strip()=='Super-Server'
path='/tmp/qemu-serial.log';h=hashlib.sha256();count=0
with open(path,'rb') as f:
 before=os.fstat(f.fileno());assert before.st_size<=256*1024*1024
 with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',mtime=0) as out:
  remaining=before.st_size
  while remaining:
   b=f.read(min(1048576,remaining));assert b
   h.update(b);out.write(b);count+=len(b);remaining-=len(b)
 after=os.fstat(f.fileno());assert (before.st_dev,before.st_ino)==(after.st_dev,after.st_ino)
print(json.dumps({'path':path,'bytes':count,'sha256':h.hexdigest(),'device':before.st_dev,'inode':before.st_ino,'size_before':before.st_size,'size_after':after.st_size,'mtime_before_ns':before.st_mtime_ns,'mtime_after_ns':after.st_mtime_ns,'captured_unix':time.time()}),file=sys.stderr)
'''
(OUT/'read.py').write_bytes(raw)
argv=['ssh','-T','-p','22','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71','sudo','-n','python3','-B','-']
(OUT/'command.json').write_text(json.dumps({'argv':argv,'stdin_sha256':hashlib.sha256(raw).hexdigest(),'timeout_seconds':90,'scope':'Read existing serial bytes only; no guest or monitor mutation'},indent=2)+'\n')
started=time.time()
with (OUT/'serial.log.gz').open('xb') as stdout,(OUT/'stderr').open('xb') as stderr:
 r=subprocess.run(argv,input=raw,stdout=stdout,stderr=stderr,timeout=90)
(OUT/'return.json').write_text(json.dumps({'returncode':r.returncode,'elapsed_seconds':time.time()-started},indent=2)+'\n')
assert r.returncode==0,r.returncode
metadata=json.loads((OUT/'stderr').read_text().splitlines()[-1]);data=gzip.decompress((OUT/'serial.log.gz').read_bytes())
assert len(data)==metadata['bytes'] and hashlib.sha256(data).hexdigest()==metadata['sha256']
marker=b'Linux version 7.0.0-38-kdrebuild8';start=data.rfind(marker);assert start>=0
current=data[start:];(OUT/'current-boot-serial.bin.gz').write_bytes(gzip.compress(current,mtime=0))
offsets=[current.find(pattern) for pattern in [b'kernel BUG',b'Oops:',b'general protection fault',b'BUG: kernel']]
first=min(i for i in offsets if i>=0)
summary={'full_serial':metadata,'current_boot_offset':start,'current_boot_bytes':len(current),'current_boot_sha256':hashlib.sha256(current).hexdigest(),'first_diagnostic_offset':first}
(OUT/'index.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
(OUT/'first-diagnostic.txt').write_bytes(current[max(0,first-4096):first+24000])
print(json.dumps(summary));print((OUT/'first-diagnostic.txt').read_text(errors='replace')[:18000])
