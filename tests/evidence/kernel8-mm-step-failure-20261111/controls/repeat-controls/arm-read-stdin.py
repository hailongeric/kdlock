from pathlib import Path
import hashlib,json,os,stat,base64
paths=['/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/repeat-kdrebuild8-mm-step-01/arm/result.json', '/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/repeat-kdrebuild8-mm-step-arm-driver-01/return.json', '/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts/repeat-kdrebuild8-mm-step-arm-driver-01/stderr']
rows=[]
for name in paths:
 p=Path(name);before=p.stat();assert p.resolve(strict=True)==p and stat.S_ISREG(before.st_mode) and before.st_size<=4*1024**2
 b=p.read_bytes();after=p.stat();assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) and len(b)==before.st_size
 rows.append({'path':name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'data':base64.b64encode(b).decode()})
print(json.dumps({'files':rows},sort_keys=True))
