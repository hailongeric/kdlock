from pathlib import Path
import json,subprocess,time
p=Path('/tmp/kdlock-kernel8-frontier-claim-ast-20261111-01');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];start=time.time()
with (p/('launch'+'-command.json')).open('x') as f:json.dump({'argv':a,'stdin':str(p/('launch'+'-stdin.py')),'timeout_seconds':240},f,indent=2);f.write(chr(10))
with (p/('launch'+'.stdout')).open('xb') as out,(p/('launch'+'.stderr')).open('xb') as err:r=subprocess.run(a,input=(p/('launch'+'-stdin.py')).read_bytes(),stdout=out,stderr=err,timeout=240)
with (p/('launch'+'-return.json')).open('x') as f:json.dump({'returncode':r.returncode,'elapsed_seconds':time.time()-start},f);f.write(chr(10))
print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
