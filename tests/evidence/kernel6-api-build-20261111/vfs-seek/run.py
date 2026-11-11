from pathlib import Path
import subprocess,json,hashlib,base64,os,time
p=Path('/tmp/kdlock-kernel6-llseek-audit-20261111-01')
a=json.loads((p/"command.json").read_text())["argv"]
s=time.time()
with (p/"guest-read.py").open("rb") as i,(p/"stdout").open("xb") as o,(p/"stderr").open("xb") as e:
 c=subprocess.Popen(a,stdin=i,stdout=o,stderr=e);r=c.wait(timeout=55)
assert r==0,(r,(p/"stderr").read_text())
v=json.loads((p/"stdout").read_text());q=p/"payload";q.mkdir()
for n,row in v["files"].items():
 b=base64.b64decode(row.pop("base64"),validate=True);assert hashlib.sha256(b).hexdigest()==row["copied_sha256"] and len(b)==row["payload_bytes"];f=q/n.lstrip("/");f.parent.mkdir(parents=True,exist_ok=True)
 with f.open("xb") as o:o.write(b);o.flush();os.fsync(o.fileno())
with (p/"verified.json").open("x") as f:json.dump(v,f,indent=2,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
print(json.dumps(dict(status="COMPLETE",files=len(v["files"]),output=str(p),hashes={n:row["copied_sha256"] for n,row in v["files"].items()}),indent=2))
