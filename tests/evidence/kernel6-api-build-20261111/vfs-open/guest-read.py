import os,json,hashlib,base64,time,stat
from pathlib import Path
names=['/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04/source/fs/open.c']
def read(name):
 fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  a=os.fstat(fd);assert stat.S_ISREG(a.st_mode);b=b''
  while True:
   c=os.read(fd,min(65536,1048577-len(b)))
   if not c:break
   b+=c;assert len(b)<=1048576
  z=os.fstat(fd);meta=lambda s:dict(device=s.st_dev,inode=s.st_ino,mode=s.st_mode,uid=s.st_uid,gid=s.st_gid,size=s.st_size,nlink=s.st_nlink,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns);assert meta(a)==meta(z);assert meta(z)==meta(os.lstat(name));return meta(a),b
 finally:os.close(fd)
v={'utc':time.time(),'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'release':os.uname().release,'taint':Path('/proc/sys/kernel/tainted').read_text().strip(),'files':{}}
assert (v['boot'],v['release'],v['taint'])==('51b49fa4-4d99-457e-a73e-632b690eb95e','7.0.0-38-kdlock1','0')
for name in names:
 before,a=read(name);copied,b=read(name);after,c=read(name);h=lambda x:hashlib.sha256(x).hexdigest();assert before==copied==after and h(a)==h(b)==h(c);v['files'][name]=dict(before=before,copied=copied,after=after,before_sha256=h(a),copied_sha256=h(b),after_sha256=h(c),payload_bytes=len(b),base64=base64.b64encode(b).decode())
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==v['boot'];print(json.dumps(v,sort_keys=True))
