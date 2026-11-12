from pathlib import Path
import hashlib,json,os,subprocess,time
p=Path('/tmp/kdlock-kernel8-runtime-metadata-20261111-01');data=(p/'read.py').read_bytes();assert hashlib.sha256(data).hexdigest()=='cd24f4dc09ee6c55f02cdda506870c5ed860d4f6c0231659b0d46295f4213ccc'
a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];start=time.time()
with (p/'command.json').open('x') as f:json.dump({'argv':a,'stdin':str(p/'read.py'),'stdin_sha256':'cd24f4dc09ee6c55f02cdda506870c5ed860d4f6c0231659b0d46295f4213ccc','timeout_seconds':90},f,indent=2);f.write(chr(10))
with (p/'stdout.json').open('xb') as out,(p/'stderr').open('xb') as err:r=subprocess.run(a,input=data,stdout=out,stderr=err,timeout=90)
with (p/'return.json').open('x') as f:json.dump({'returncode':r.returncode,'elapsed_seconds':time.time()-start},f);f.write(chr(10));f.flush();os.fsync(f.fileno())
print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
