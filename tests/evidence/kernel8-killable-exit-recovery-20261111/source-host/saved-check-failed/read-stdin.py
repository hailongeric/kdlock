from pathlib import Path
import hashlib,json,base64
root=Path('/mnt/kdlock-builds2/kdlock-main-kernel8-fixtures-140aecc4-01/host-checks-de76da8a-01/receipts')
rows={}
for name in ('result.json','fixed-killable-runner-ast.log','saved-source-named-spans.log','../saved-source/named-source-proof.json'):
 p=root/name;a=p.stat();assert a.st_size<=16777216;b=p.read_bytes();c=p.stat();assert (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns)==(c.st_dev,c.st_ino,c.st_size,c.st_mtime_ns)
 rows[name]={'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'data':base64.b64encode(b).decode()}
print(json.dumps(rows))
