import gzip,hashlib,json,os,sys,time
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
