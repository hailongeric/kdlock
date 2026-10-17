#!/usr/bin/env python3
"""Audit the deliberately stopped unguarded-probe matrix; never complete its grid."""
import argparse,importlib.util,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent

def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
native_imports=module('native_imports',HERE/'imports-audit.py')
base=module('partial_base',HERE/'legacy-audit.py');api=module('partial_api',HERE/'api-audit.py');read,save,check=base.read,base.save,base.check
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root,out=a.root.resolve(),a.output.resolve();out.mkdir(parents=True,exist_ok=True)
state=read(root/'status.json');check(state['state']=='STOPPED' and state['boundary']=='drained','not a drained stop');check(state['completed']==len(state['sessions'])==206,'partial coverage differs')
check(read(root/'control/guest-after.json')['idle'],'missing idle receipt')
for n,h in read(root/'control/source-sha256.json').items():check(base.sha(root/'frozen-source'/n)==h,'partial source changed')
for n,h in read(root/'control/prepared-inputs-sha256.json').items():check(base.sha(root/n)==h,'partial prepared input changed')
check(all(r['exit_code']==0 for r in read(root/'validation/checks.json')),'unpassed check')
rows=[];audits={}
for version in ('baseline','compat'):
 for group in ('c01-post64','api-pipebytes-query-n16'):
  src=root/version/group;selected={r['name'] for r in state['sessions'] if r['version']==version and r['workload']==group}
  plan=[r for r in read(src/'plan.json') if r['name'] in selected];check(len(plan)==len(selected),'partial plan mismatch')
  records=[read(src/r['name']/'session.json') for r in plan]
  # Present only completed records to the existing per-session auditor. Original
  # plans, source snapshots and prepared-input hashes remain untouched above.
  with tempfile.TemporaryDirectory(prefix='kd-partial-replay-') as temp:
   folder=Path(temp)/group;folder.mkdir()
   for child in src.iterdir():
    if child.name not in ('plan.json','records.json'):(folder/child.name).symlink_to(child,target_is_directory=child.is_dir())
   save(folder/'plan.json',plan);save(folder/'records.json',records)
   if group.startswith('c01'):audit,verified=base.audit_c01(folder);check(verified==records,'partial records changed')
   else:
    audit=api.audit(folder)
    audit['prepared_provider']=base.prepared_provider(root/'control'/('baseline-api-prepared-provider' if version=='baseline' else 'api-prepared-provider'),src/'source')
  if version=='compat':audit['no_native_mutex_imports']=native_imports.audit(src,group)
  audits[version+'/'+group]=audit
  for r in records:
   check(r['drained'] and r['mutex_version']==version and r['duration_ms']==2000,'partial contract')
   if version=='compat' and r['arm']=='kdlock':
    im=r['image_generation_before'];check(im==r['image_generation_after'] and im['capabilities']==[5,27,256,8192] and im['generation']==1,'partial image changed')
   s=base.sample(group,r);s.update(arm=('legacy' if version=='baseline' else 'compat') if r['arm']=='kdlock' else r['arm'],version=version,sequence=r['sequence']);rows.append(s)
check(len(rows)==206 and {r['sequence'] for r in rows}==set(range(206)),'partial sequences differ')
rows.sort(key=lambda r:r['sequence']);save(out/'partial-samples.json',rows);base.table(out/'partial-samples.csv',rows)
stats=[]
for key in sorted({(r['workload'],r['threads'],r['arm']) for r in rows}):stats.append(base.aggregate(key,[r for r in rows if (r['workload'],r['threads'],r['arm'])==key]))
save(out/'partial-statistics.json',stats);base.table(out/'partial-statistics.csv',stats)
v=dict(status='PASS',experiment_state='STOPPED',sessions=206,accepted=sum(r['accepted'] for r in rows),drained=sum(r['drained'] for r in rows),excluded_from_final_scores=True,planned=504,checks=audits)
save(out/'partial-verification.json',v);print({k:v for k,v in v.items() if k!='checks'})
