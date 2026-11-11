import hashlib,json,subprocess,time
from pathlib import Path
p=Path('/tmp/kdlock-rwlock-native-recovery-e5b7.py');raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()=='cc250d7147073f61eff01695d52328d29239d2aac2f242eb0034831c7f4232ec'
out=Path('/tmp/kdlock-rwlock-native-recovery-controller-01');out.mkdir(exist_ok=False)
a=['ssh','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=8','root@10.176.26.71','timeout 90 python3 -']
code=b'import ast\nast.parse('+repr(raw).encode()+b')\n'+raw
start=time.time();x=subprocess.run(a,input=code,capture_output=True,timeout=105)
(out/'stdout.log').write_bytes(x.stdout);(out/'stderr.log').write_bytes(x.stderr);(out/'command.json').write_text(json.dumps({'argv':a,'sha256':hashlib.sha256(code).hexdigest(),'helper_sha256':hashlib.sha256(raw).hexdigest(),'started_unix':start,'finished_unix':time.time(),'returncode':x.returncode},indent=2)+'\n')
print('returncode',x.returncode,x.stdout.decode()[-3000:],x.stderr.decode()[-3000:]);raise SystemExit(x.returncode)
