from pathlib import Path
import hashlib,json,os,subprocess,time
p=Path('/tmp/kdlock-kernel8-aux-object-discovery-20261111-02');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];start=time.time()
with (p/'command.json').open('x') as f:json.dump({'argv':a,'stdin':str(p/'discovery-stdin.py'),'stdin_sha256':hashlib.sha256((p/'discovery-stdin.py').read_bytes()).hexdigest(),'timeout_seconds':90},f,indent=2);f.write(chr(10))
with (p/'stdout.json').open('xb') as out,(p/'stderr').open('xb') as err:r=subprocess.run(a,input=(p/'discovery-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=90)
with (p/'return.json').open('x') as f:json.dump({'returncode':r.returncode,'elapsed_seconds':time.time()-start},f);f.write(chr(10));f.flush();os.fsync(f.fileno())
print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
