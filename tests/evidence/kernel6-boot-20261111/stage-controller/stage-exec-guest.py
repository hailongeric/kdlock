import sys,json,base64,hashlib,os,time,datetime
from pathlib import Path
v=json.loads(sys.stdin.buffer.readline(1048576));b=base64.b64decode(v['proof'],validate=True);assert hashlib.sha256(b).hexdigest()==v['sha'];p=Path(v['path']);assert p==Path('/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04/ops-kdrebuild6-api-01/recovery-stage-01.json') and not os.path.lexists(p);assert 0<=time.time()-datetime.datetime.fromisoformat(json.loads(b)['utc']).timestamp()<120
with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
print(json.dumps({'controller_pid':os.getpid(),'argv':v['argv']}),flush=True);os.execvp(v['argv'][0],v['argv'])
