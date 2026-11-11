from pathlib import Path
import json,subprocess
p=Path('/tmp/kdlock-kernel8-managed-killable-20261111-02');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'stage-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'stage-stdin.py'),'timeout_seconds':60},indent=2)+chr(10))
with (p/'stage.stdout').open('xb') as out,(p/'stage.stderr').open('xb') as err:r=subprocess.run(a,input=(p/'stage-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=60)
(p/'stage-return.json').write_text(json.dumps({'returncode':r.returncode})+chr(10));print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
