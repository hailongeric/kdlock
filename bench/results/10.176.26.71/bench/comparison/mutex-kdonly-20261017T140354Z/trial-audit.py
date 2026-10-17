#!/usr/bin/env python3
"""Offline audit for a six-repetition paired physical-core trial."""
import argparse,importlib.util,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
native_imports=module('native_imports',HERE/'imports-audit.py')
base=module('trial_base',HERE/'legacy-audit.py');api=module('trial_api',HERE/'api-audit.py');read,save,check=base.read,base.save,base.check
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root,out=a.root.resolve(),a.output.resolve();out.mkdir(parents=True,exist_ok=True)
if root.name=='trial-owner-layout':threads,repeats=(4,),9
elif root.name in ('trial-probe32','trial-combiner-guard'):threads,repeats=(2,4,7,8,60),9
elif root.name in ('trial-queue-guard','trial-gate-guard'):threads,repeats=(2,7,8,60),6
else:threads,repeats=(2,60),6
state=read(root/'status.json');expected_sessions=len(threads)*repeats*4
check(state['state']=='COMPLETE' and state['completed']==expected_sessions,'unfinished trial')
for n,h in read(root/'control/source-sha256.json').items():check(base.sha(root/'frozen-source'/n)==h,'trial source changed')
for n,h in read(root/'control/prepared-inputs-sha256.json').items():check(base.sha(root/n)==h,'trial input changed')
check(all(r['exit_code']==0 for r in read(root/'validation/checks.json')),'unpassed trial check')
samples=[];audits={};stats=[]
for group in ('c01-post64','api-pipebytes-query-n16'):
 for v in ('baseline','compat'):
  folder=root/v/group
  if group.startswith('c01'):audit,rows=base.audit_c01(folder)
  else:
   audit=api.audit(folder);rows=read(folder/'records.json')
   audit['prepared_provider']=base.prepared_provider(root/'control'/('baseline-api-prepared-provider' if v=='baseline' else 'api-prepared-provider'),folder/'source')
  check(len(rows)==len(threads)*repeats and {(r['threads'],r['repeat'],r['arm']) for r in rows}=={(n,rep,'kdlock') for n in threads for rep in range(repeats)},'trial coverage differs')
  for r in rows:
   check(r['drained'] and r['duration_ms']==2000 and r['mutex_version']==v,'trial timing/drain')
   if v=='compat':
    im=r['image_generation_before'];check(im==r['image_generation_after'] and im['capabilities']==[5,27,256,8192] and im['generation']==1,'trial immutable image changed')
   s=base.sample(group,r);s.update(version=v,sequence=r['sequence']);samples.append(s)
  if v=='compat':audit['no_native_mutex_imports']=native_imports.audit(folder,group)
  audits[v+'/'+group]=audit
  for n in threads:
   rs=[s for s in samples if s['workload']==group and s['version']==v and s['threads']==n]
   st=base.aggregate((group,n,v),rs);st['complete']=st['valid_rounds']==repeats;stats.append(st)
index={(s['workload'],s['threads'],s['repeat'],s['version']):s for s in samples};comparison=[]
for g in ('c01-post64','api-pipebytes-query-n16'):
 for n in threads:
  before=[index[g,n,r,'baseline'] for r in range(repeats)];after=[index[g,n,r,'compat'] for r in range(repeats)]
  for a,b in zip(before,after):check(abs(a['sequence']-b['sequence'])==1,'trial KD pair not adjacent')
  x=statistics.median(s['whole_ops_s'] for s in before)/1e6;y=statistics.median(s['whole_ops_s'] for s in after)/1e6
  ratios=[b['whole_ops_s']/a['whole_ops_s'] for a,b in zip(before,after)]
  comparison.append(dict(workload=g,threads=n,repeats=repeats,baseline_whole_mops=x,kdonly_whole_mops=y,whole_change_pct=100*(y/x-1),paired_ratio_min=min(ratios),paired_ratio_median=statistics.median(ratios),paired_ratio_max=max(ratios),slower_pairs=sum(r<1 for r in ratios)))
for name,rows in [('trial-samples',samples),('trial-statistics',stats),('trial-comparison',comparison)]:save(out/(name+'.json'),rows);base.table(out/(name+'.csv'),rows)
v=dict(status='PASS',sessions=expected_sessions,accepted=sum(s['accepted'] for s in samples),drained=sum(s['drained'] for s in samples),actual_jit=sum(s['jit_bodies']>0 for s in samples),checks=audits)
save(out/'trial-verification.json',v)
import json
print(json.dumps({'status':'PASS','accepted':v['accepted'],'comparison':comparison},indent=2))
