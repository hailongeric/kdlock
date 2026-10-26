import hashlib,json,sys
from pathlib import Path
r=json.load(sys.stdin)
for name,row in r.items():
 p=Path(name);data=row['text'].encode();assert hashlib.sha256(data).hexdigest()==row['sha256'] and not p.exists()
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(data)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
print(json.dumps({name:row['sha256'] for name,row in r.items()}),flush=True)
