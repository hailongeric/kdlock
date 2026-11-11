from pathlib import Path
import json,subprocess
p=Path('/tmp/kdlock-kernel8-private-live-20261111-01');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'rwsem-stage-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'rwsem-stage-stdin.py'),'timeout_seconds':60},indent=2)+chr(10))
with (p/'rwsem-stage.stdout').open('xb') as out,(p/'rwsem-stage.stderr').open('xb') as err:r=subprocess.run(a,input=(p/'rwsem-stage-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=60)
(p/'rwsem-stage-return.json').write_text(json.dumps({'returncode':r.returncode})+chr(10));print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
