#!/usr/bin/env python3
"""Audit the deliberately stopped unguarded-probe matrix; never complete its grid."""
import argparse,importlib.util,tempfile,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent

def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
native_imports=module('native_imports',HERE/'imports-audit.py')
base=module('partial_base',HERE/'legacy-audit.py');api=module('partial_api',HERE/'api-audit.py');read,save,check=base.read,base.save,base.check
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root,out=a.root.resolve(),a.output.resolve();out.mkdir(parents=True,exist_ok=True)
state=read(root/'status.json');check(state['state']=='STOPPED' and state['boundary']=='drained','not a drained stop');count={'matrix4':206,'matrix6':133,'trial-short-queue':48,'trial-short-queue8':85}.get(root.name);check(count is not None and state['completed']==len(state['sessions'])==count,'partial coverage differs')
check(read(root/'control/guest-after.json')['idle'],'missing idle receipt')
for n,h in read(root/'control/source-sha256.json').items():check(base.sha(root/'frozen-source'/n)==h,'partial source changed')
for n,h in read(root/'control/prepared-inputs-sha256.json').items():check(base.sha(root/n)==h,'partial prepared input changed')
check(all(r['exit_code']==0 for r in read(root/'validation/checks.json')),'unpassed check')
rows=[];audits={}
for version in ('baseline','compat'):
 for group in ('c01-post64','api-pipebytes-query-n16'):
  src=root/version/group;selected={r['name'] for r in state['sessions'] if r['version']==version and r['workload']==group}
  if not selected:continue
  plan=[r for r in read(src/'plan.json') if r['name'] in selected];check(len(plan)==len(selected),'partial plan mismatch')
  records=[read(src/r['name']/'session.json') for r in plan]
  if group.startswith('c01'):
   # Stopping before report() leaves derived CSV fields absent. Reconstruct
   # only these summaries in memory; the auditor still checks original raw
   # measurements and independently recomputes their peak windows.
   for row in records:
    m=row['measurement'];ok=row['execution_status']=='OK'
    row.update(whole_throughput_ops_s=m['completed']*1e9/m['wall_ns'] if ok else None,whole_amortized_ns_op=m['wall_ns']/m['completed'] if ok else None,throughput_ops_s=m['peak']['throughput_ops_s'] if ok else None,amortized_ns_op=1e9/m['peak']['throughput_ops_s'] if ok else None)
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
check(len(rows)==count and {r['sequence'] for r in rows}==set(range(count)),'partial sequences differ')
rows.sort(key=lambda r:r['sequence']);save(out/'partial-samples.json',rows);base.table(out/'partial-samples.csv',rows)
stats=[]
for key in sorted({(r['workload'],r['threads'],r['arm']) for r in rows}):stats.append(base.aggregate(key,[r for r in rows if (r['workload'],r['threads'],r['arm'])==key]))
save(out/'partial-statistics.json',stats);base.table(out/'partial-statistics.csv',stats)
v=dict(status='PASS',experiment_state='STOPPED',sessions=count,accepted=sum(r['accepted'] for r in rows),drained=sum(r['drained'] for r in rows),excluded_from_final_scores=True,planned=state['planned'],checks=audits)
save(out/'partial-verification.json',v);print({k:v for k,v in v.items() if k!='checks'})

if root.name in ('trial-short-queue','trial-short-queue8'):
 index={(s['workload'],s['threads'],s['repeat'],s['version']):s for s in rows};comparison=[]
 for g,n in sorted({(s['workload'],s['threads']) for s in rows}):
  available=[rep for rep in range(9) if (g,n,rep,'baseline') in index and (g,n,rep,'compat') in index]
  before=[index[g,n,rep,'baseline'] for rep in available];after=[index[g,n,rep,'compat'] for rep in available]
  for a,b in zip(before,after):check(abs(a['sequence']-b['sequence'])==1,'partial trial pair not adjacent')
  x=statistics.median(s['whole_ops_s'] for s in before)/1e6;y=statistics.median(s['whole_ops_s'] for s in after)/1e6
  ratios=[b['whole_ops_s']/a['whole_ops_s'] for a,b in zip(before,after)]
  comparison.append(dict(workload=g,threads=n,repeats=len(available),complete_nine_pairs=len(available)==9,baseline_whole_mops=x,kdonly_whole_mops=y,whole_change_pct=100*(y/x-1),paired_ratio_median=statistics.median(ratios),slower_pairs=sum(r<1 for r in ratios)))
 save(out/'partial-comparison.json',comparison);base.table(out/'partial-comparison.csv',comparison)
