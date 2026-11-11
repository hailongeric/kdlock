from pathlib import Path
import json,subprocess,time
p=Path('/tmp/kdlock-kernel8-private-live-20261111-01');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'rwsem-launch-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'rwsem-launch-stdin.py'),'timeout_seconds':780},indent=2)+chr(10));start=time.time()
with (p/'rwsem-launch.stdout').open('xb') as out,(p/'rwsem-launch.stderr').open('xb') as err:
 r=subprocess.run(a,input=(p/'rwsem-launch-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=780)
(p/'rwsem-launch-result.json').write_text(json.dumps({'returncode':r.returncode,'elapsed_seconds':time.time()-start})+chr(10));print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
