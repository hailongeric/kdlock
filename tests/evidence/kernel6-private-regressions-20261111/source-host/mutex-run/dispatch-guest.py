import sys,json,base64,hashlib,os,time,datetime
from pathlib import Path
v=json.loads(sys.stdin.buffer.readline(1048576));p=Path('/mnt/kdlock-builds/kdlock-main-work/kernel6-private-fixtures-80c272e5-01/recovery-mutex-01.json');b=base64.b64decode(v['proof'],validate=True);assert not os.path.lexists(p) and hashlib.sha256(b).hexdigest()==v['sha'] and 0<=time.time()-datetime.datetime.fromisoformat(json.loads(b)['utc']).timestamp()<120
with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
print(json.dumps({'controller_pid':os.getpid(),'recovery_sha256':v['sha'],'argv':v['argv']}),flush=True);os.execvp(v['argv'][0],v['argv'])
