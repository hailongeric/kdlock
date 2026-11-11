from pathlib import Path
import base64,hashlib,json,os
base=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01');rows={}
for rel in ('managed-killable-driver-02/stderr','managed-killable-driver-02/stdout','managed-killable-receipts-02/result.json','managed-killable-receipts-02/managed-killable.log','managed-killable-live-02/result.json'):
 p=base/rel
 if not p.exists():rows[rel]={'absent':True};continue
 a=p.stat();assert a.st_size<=16777216;b=p.read_bytes();c=p.stat();assert (a.st_ino,a.st_size,a.st_mtime_ns)==(c.st_ino,c.st_size,c.st_mtime_ns)
 rows[rel]={'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'data':base64.b64encode(b).decode()}
print(json.dumps({'files':rows,'identity':{'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'release':os.uname().release,'taint':Path('/proc/sys/kernel/tainted').read_text().strip()},'modules':Path('/proc/modules').read_text()}))
