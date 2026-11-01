from pathlib import Path
import json,shlex,subprocess
out=Path('/tmp/kdlock-master-nano-summary-20261101.json');assert not out.exists()
code='''from pathlib import Path
import hashlib,json
base=Path('/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/bench/master-native-20261101/nano');owner=json.loads((base/'owner.json').read_text());assert len(owner['blocks'])==10 and all(b['returncode']==0 and not b['completion_unconfirmed'] for b in owner['blocks'])
rows=[];files={}
for block in owner['blocks']:
 p=base/block['profile']/'records.json';raw=p.read_bytes();records=json.loads(raw);files[str(p)]=hashlib.sha256(raw).hexdigest();assert len(records)==42
 plan=json.loads((p.parent/'plan.json').read_text());assert [r['name'] for r in records]==[r['name'] for r in plan]
 for r in records:
  assert r['execution_status']=='OK' and r['drained'] and r['measurement']['data_ok'] and r['measurement']['complete'] and r['repeat']==0
  rows.append({k:r.get(k) for k in ['name','arm','threads','lock_kind','cachelines','write_percent','whole_ops_s','peak_ops_s','jit_bodies','jit_completions','execution_class','functional','post_work_rounds','provider_mutex_policy']})
assert len(rows)==420
print(json.dumps({'rows':rows,'files':files,'points':len(rows),'rounds_per_point':1}))
'''
r=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','eric@10.176.26.71',shlex.join(['/home/eric/vm/qemu-scripts/vm_ssh.sh','taskset -c 63 python3 -'])],input=code.encode(),capture_output=True,timeout=120)
assert r.returncode==0,r.stderr.decode();d=json.loads(r.stdout);out.write_bytes(r.stdout);print(json.dumps({'output':str(out),'points':d['points']}))
