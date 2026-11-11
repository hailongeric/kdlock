import subprocess,json,time,os
from pathlib import Path
p=Path('/tmp/kdlock-kernel6-finalization-run-20261111-01')
a=json.loads((p/"command.json").read_text())["argv"]
start=time.time()
with (p/"input.json").open("rb") as i,(p/"stdout").open("xb") as o,(p/"stderr").open("xb") as e:
 c=subprocess.Popen(a,stdin=i,stdout=o,stderr=e);r=c.wait(timeout=110)
with (p/"result.json").open("x") as f:json.dump(dict(returncode=r,elapsed_seconds=time.time()-start),f);f.flush();os.fsync(f.fileno())
print((p/"stdout").read_text());print((p/"stderr").read_text());raise SystemExit(r)
