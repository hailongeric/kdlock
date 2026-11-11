import sys,json,base64,hashlib,os,subprocess
from pathlib import Path
v=json.loads(sys.stdin.buffer.readline(1048576));p=Path(v['argv'][2]);assert p==Path('/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04/finalize-focus.py') and p.parent.resolve(strict=True)==p.parent and not os.path.lexists(p);b=base64.b64decode(v['base64'],validate=True);assert hashlib.sha256(b).hexdigest()==v['sha256']
with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
child=subprocess.Popen(v['argv']);print(json.dumps(dict(helper_pid=child.pid,helper_sha256=v['sha256'])),flush=True)
try:rc=child.wait(timeout=90)
except subprocess.TimeoutExpired:print(json.dumps(dict(status='TIMEOUT_CHILD_RETAINED',pid=child.pid)),flush=True);raise
r=p.parent/'receipts/focused-finalization-01/result.json'
if r.exists():print(json.dumps(dict(receipt=str(r),receipt_sha256=hashlib.sha256(r.read_bytes()).hexdigest(),result=json.loads(r.read_text()))),flush=True)
raise SystemExit(rc)
