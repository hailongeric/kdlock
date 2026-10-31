#!/usr/bin/env python3
"""Write one data-only nano spec for the existing transport; execute nothing."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path('/tmp/kdlock-writer-queue-nano-20261031.py')
SCRIPT='1857baca9f699907c9eb418e8cb347d601095be95d688e1b9d604aa3fc8a2731'
COHORT=Path('/tmp/kdlock-writer-queue-nano-20261031.cohort.json')
COHORT_SHA='58c4050871f2d483a01ae1c423326c45ad2d03704a9c0b8a9ce4ba4b58751a0a'
ROOT=Path('/tmp/kdlock-writer-queue-controls-20261031')
EVIDENCE=Path('/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests')
BOOT='fa97b9f8-fefc-49b9-abc1-636861e64fc0'
SNAPSHOT='kdlock-builddisk-clean-20261031'
POOL='6f1f718b6ba72b9b4899b3437e6211d8dd891f4041acd7aca36906c12953b8b4'
REFERENCE='249ac70a92705afbd138e46e272010427ef98cff3c7906d724650423db020198'
POLICY='41272e05fbec14df9aad450a3980718a48ce33ec5d8c4a1e870266c01f032f7b'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_bytes())
def need(x,t):
 if not x:raise ValueError(t)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('phase',choices=('run','endpoint','archive'));p.add_argument('--arm',choices=('baseline','candidate'),required=True)
p.add_argument('--output',type=Path,required=True)
for n in ('sync','sync-guest','host-before','host-before-guest','run-log','output-prefix','host-output','run-owner','endpoint-prefix','endpoint-guest-prefix'):
 p.add_argument('--'+n,type=Path)
a=p.parse_args();need(not a.output.exists(),'preserve existing spec')
need(sha(HERE)==SCRIPT and sha(COHORT)==COHORT_SHA,'reviewed executable/cohort changed')
cfg=load(COHORT);arm=next(x for x in cfg['arms'] if x['label']==a.arm)
args=[a.phase,'--commit',arm['commit'],'--cohort-file',str(COHORT),'--cohort-sha256',COHORT_SHA]
def add(k,v):args.extend(['--'+k,str(v)])
def bound(name,local,guest):
 need(local is not None and guest is not None and local.is_absolute() and guest.is_absolute(),'actual local/guest '+name+' required')
 add(name,guest);add(name+'-sha256',sha(local))
if a.phase=='endpoint':
 for n in ('run_log','output_prefix','host_output'):
  value=getattr(a,n);need(value is not None and value.is_absolute(),'explicit endpoint '+n+' required');add(n.replace('_','-'),value)
 policy=load(ROOT/'baseline-bindings/policy.json');need(sha(ROOT/'baseline-bindings/policy.json')==POLICY,'pool changed')
 add('policy',Path('/tmp/kdlock-writer-queue-pool-activate-20261031/result.json'));add('policy-sha256',POLICY)
 add('snapshot-tag',SNAPSHOT);add('cohort',policy['cohort'])
 spec={'execution_host':'380G10','argv':['python3',str(HERE),*args],'script_sha256':SCRIPT,'cohort_sha256':COHORT_SHA,'executes_nothing':True}
else:
 for k,v in [('output',arm['output']),('boot-id',BOOT),('snapshot-tag',SNAPSHOT),('host-mode','strict'),('policy-controller-sha256',POOL)]:add(k,v)
 if a.phase=='run':
  sync=load(a.sync);need(sync['git_head']==arm['commit'] and sync['git_status']=='' and sync['synchronization_completed'],'fresh exact sync required')
  digest=hashlib.sha256(json.dumps(sync['tracked_sha256'],sort_keys=True,separators=(',',':')).encode()).hexdigest();need(digest==arm['source_map_sha256'],'sync source map differs')
  bound('sync',a.sync,a.sync_guest);bound('host-before',a.host_before,a.host_before_guest)
  need(sha(ROOT/'baseline-bindings/reference.json')==REFERENCE and sha(ROOT/'baseline-bindings/policy.json')==POLICY,'original cohort inputs changed')
  add('host-reference','/tmp/kdlock-writer-queue-reference-20261031.json');add('host-reference-sha256',REFERENCE)
  add('policy-receipt','/tmp/kdlock-writer-queue-policy-20261031.json');add('policy-receipt-sha256',POLICY)
  stem='f7' if a.arm=='baseline' else '1b6f256b';checks=EVIDENCE/('writer-queue-'+stem+'-20261031')
  for key,leaf in [('prior-unit','result.json'),('prior-live','rwsem/result.json'),('prior-live-source','rwsem/source-sha256.json')]:add(key,checks/leaf);add(key+'-sha256',arm[key.replace('-','_')+'_sha256'])
  basic=ROOT/(a.arm+'-basic')/'result.json';r=load(basic);need(r['passed'] and r['final_idle'] and r['boot_id']==BOOT,'actual same-boot basic required')
  add('basic-result',EVIDENCE/('writer-queue-'+stem+'-basic-20261031')/'result.json');add('basic-result-sha256',sha(basic))
 else:
  need(a.run_owner is not None,'actual run owner required');r=load(a.run_owner)
  need(r['completed'] and r['idle'] and r['validated_points']==210 and r['source_commit']==arm['commit'] and r['boot_id']==BOOT,'completed current arm required')
  add('run-owner-sha256',sha(a.run_owner));add('endpoint-controller-sha256',SCRIPT)
  need(a.endpoint_prefix is not None and a.endpoint_guest_prefix is not None,'actual endpoint prefixes required')
  for key,suffix in [('host-after','.json'),('endpoint-receipt','-receipt.json'),('endpoint-policy','-policy.json')]:bound(key,Path(str(a.endpoint_prefix)+suffix),Path(str(a.endpoint_guest_prefix)+suffix))
 result=arm['output']+'-control/'+('owner.json' if a.phase=='run' else 'archive-owner.json')
 spec={'script':str(HERE),'script_sha256':SCRIPT,'argv':args,'result':result,'timeout':15000 if a.phase=='run' else 3900,'affinity':'0-63','success_key':'completed'}
with a.output.open('x') as f:json.dump(spec,f,indent=2);f.write('\n')
print(json.dumps({'output':str(a.output),'sha256':sha(a.output),'phase':a.phase,'arm':a.arm}))
