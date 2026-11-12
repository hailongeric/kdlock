from pathlib import Path
import json,subprocess
p=Path('/tmp/kdlock-kernel8-repeatboot-run-20261111-01');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-']
with (p/'lib-root-check-command.json').open('x') as f:json.dump({'argv':a,'stdin':str(p/'lib-root-check-stdin.py'),'timeout_seconds':30},f,indent=2);f.write(chr(10))
with (p/'lib-root-check.json').open('xb') as out,(p/'lib-root-check.stderr').open('xb') as err:r=subprocess.run(a,input=(p/'lib-root-check-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=30)
with (p/'lib-root-check-return.json').open('x') as f:json.dump({'returncode':r.returncode},f);f.write(chr(10))
print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
