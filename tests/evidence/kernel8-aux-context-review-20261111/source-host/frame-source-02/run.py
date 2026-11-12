from pathlib import Path
import json,hashlib,subprocess,time,sys
p=Path('/tmp/kdlock-kernel8-aux-context-controls-20261111-02');phase=sys.argv[1];assert phase in ('before','collection','after');start=time.time()
if phase=='collection':
 a=json.loads((p/'collection-command.json').read_text())['argv'];assert hashlib.sha256(Path('/tmp/kdlock-rw-collect5.py').read_bytes()).hexdigest()=='3cd38218bee1a01d9747deee866eba8122144ec6571634f86872ba3cc1f9890d';data=None;seconds=180
else:
 a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];data=(p/'pins-stdin.py').read_bytes();seconds=60
 with (p/(phase+'-command.json')).open('x') as f:json.dump({'argv':a,'stdin':str(p/'pins-stdin.py'),'stdin_sha256':hashlib.sha256(data).hexdigest(),'timeout_seconds':seconds},f,indent=2);f.write(chr(10))
with (p/(phase+'.stdout')).open('xb') as out,(p/(phase+'.stderr')).open('xb') as err:r=subprocess.run(a,input=data,stdout=out,stderr=err,timeout=seconds)
with (p/(phase+'-return.json')).open('x') as f:json.dump({'returncode':r.returncode,'elapsed_seconds':time.time()-start},f);f.write(chr(10))
print(json.dumps({'phase':phase,'returncode':r.returncode}));raise SystemExit(r.returncode)
