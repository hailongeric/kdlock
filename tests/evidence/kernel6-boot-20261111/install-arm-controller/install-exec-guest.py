import sys,json,base64,hashlib,os,time,datetime
from pathlib import Path
v=json.loads(sys.stdin.buffer.readline(1048576));root=Path('/mnt/kdlock-builds2/kdlock-main-kernel6-532b68a6-rwsem-04/ops-kdrebuild6-api-01');pins={'kdlock-kdrebuild6-install.py':'ba6f3ee167a8b55807804597b5ea416aedaf33ddd990879bbd70da1736908018','kdlock-kdrebuild6-checks.py':'a94a086efb7fccc443c11b25629888c148af88297c59f0a6d66c21bd862121ce','kdlock-kdrebuild6-postboot.py':'c234e11984c57e1ecc792b89ba110c35c4da6b639fa2f99aeaafedf61e1d02cb'}
for n,h in pins.items():assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h
p=root/('recovery-'+v['phase']+'-01.json');assert v['phase'] in ('install','arm') and not os.path.lexists(p);b=base64.b64decode(v['proof'],validate=True);assert hashlib.sha256(b).hexdigest()==v['sha'] and 0<=time.time()-datetime.datetime.fromisoformat(json.loads(b)['utc']).timestamp()<120
with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
print(json.dumps({'controller_pid':os.getpid(),'phase':v['phase'],'recovery_sha256':v['sha'],'argv':v['argv']}),flush=True);os.execvp(v['argv'][0],v['argv'])
