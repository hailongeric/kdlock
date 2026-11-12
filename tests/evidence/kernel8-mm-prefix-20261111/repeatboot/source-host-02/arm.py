from pathlib import Path
import json,subprocess,time
p=Path('/tmp/kdlock-kernel8-repeatboot-run-20261111-02');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];start=time.time()
with (p/('arm'+'-command.json')).open('x') as f:json.dump({'argv':a,'stdin':str(p/('arm'+'-stdin.py')),'timeout_seconds':360},f,indent=2);f.write(chr(10))
with (p/('arm'+'.stdout')).open('xb') as out,(p/('arm'+'.stderr')).open('xb') as err:r=subprocess.run(a,input=(p/('arm'+'-stdin.py')).read_bytes(),stdout=out,stderr=err,timeout=360)
with (p/('arm'+'-return.json')).open('x') as f:json.dump({'returncode':r.returncode,'elapsed_seconds':time.time()-start},f);f.write(chr(10))
print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
