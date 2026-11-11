from pathlib import Path
import json,subprocess
p=Path('/tmp/kdlock-kernel8-managed-killable-20261111-01');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'status-read-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'status-read-stdin.py'),'timeout_seconds':60},indent=2)+chr(10))
with (p/'status-read.json').open('xb') as out,(p/'status-read.stderr').open('xb') as err:r=subprocess.run(a,input=(p/'status-read-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=60)
(p/'status-read-return.json').write_text(json.dumps({'returncode':r.returncode})+chr(10));print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
