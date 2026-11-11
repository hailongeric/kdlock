from pathlib import Path
import json,subprocess,time
p=Path('/tmp/kdlock-kernel8-killable-exit-ack-20261111-01');a=['ssh','-T','-p','2222','-o','BatchMode=yes','-o','ConnectTimeout=10','root@10.176.26.71','python3','-B','-'];(p/'launch-command.json').write_text(json.dumps({'argv':a,'stdin':str(p/'launch-stdin.py'),'timeout_seconds':120},indent=2)+chr(10));start=time.time()
with (p/'launch.stdout').open('xb') as out,(p/'launch.stderr').open('xb') as err:
 r=subprocess.run(a,input=(p/'launch-stdin.py').read_bytes(),stdout=out,stderr=err,timeout=120)
(p/'launch-result.json').write_text(json.dumps({'returncode':r.returncode,'elapsed_seconds':time.time()-start})+chr(10));print(json.dumps({'returncode':r.returncode}));raise SystemExit(r.returncode)
