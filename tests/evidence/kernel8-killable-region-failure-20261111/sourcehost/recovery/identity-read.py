from pathlib import Path
import json,subprocess
p=Path('/tmp/kdlock-kernel8-killable-region-recovery-20261111-01');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'identity-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'identity-stdin.py'),'timeout_seconds':30},indent=2)+chr(10))
with (p/'identity.json').open('xb') as out,(p/'identity.stderr').open('xb') as err:r=subprocess.run(a,input=(p/'identity-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=30)
(p/'identity-return.json').write_text(json.dumps({'returncode':r.returncode})+chr(10));assert r.returncode==0;v=json.loads((p/'identity.json').read_text());print(json.dumps({'pid':v['pid'],'startticks':v['startticks'],'wchan':v['wchan']}))
