from pathlib import Path
import base64,hashlib,json,os,stat
root=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-0d42063e-01/receipts');rows={}
for name,limit in [('repeat-kdrebuild8-mm-frontier-01/preflight/result.json',4*1024**2),('repeat-kdrebuild8-mm-preflight-driver-01/stderr',65536),('repeat-kdrebuild8-mm-preflight-driver-01/stdout',65536),('repeat-kdrebuild8-mm-preflight-driver-01/return.json',65536)]:
 path=root/name
 if not os.path.lexists(path):rows[name]={'exists':False};continue
 before=path.lstat();assert path.resolve(strict=True)==path and stat.S_ISREG(before.st_mode) and before.st_size<=limit;data=path.read_bytes();after=path.lstat();assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns);rows[name]={'exists':True,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'data':base64.b64encode(data).decode()}
print(json.dumps(rows,sort_keys=True))
