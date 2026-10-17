#!/usr/bin/env python3
"""Independently replay the selected low-throughput follow-up; no live accesses."""
import argparse,importlib.util,json,statistics
from pathlib import Path

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
HERE=Path(__file__).resolve().parent
native_imports=module('recheck_imports',HERE/'imports-audit.py')
base=module('recheck_base',HERE/'legacy-audit.py');api=module('recheck_api',HERE/'api-audit.py')
read,save,check=base.read,base.save,base.check
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--main',default='matrix3');args=p.parse_args()
root,out=args.root.resolve(),args.output.resolve();out.mkdir(parents=True,exist_ok=True)
main=root.parent/args.main;selection=read(root/'selection.json');status=read(root/'status.json')
check(status['state']=='COMPLETE','unfinished recheck')
check(selection['extra_pairs_per_point']==9,'wrong follow-up repeat count')
expected={(r['workload'],r['threads']) for r in read(main/'analysis/comparison.json') if r['whole_change_pct'] < -5}
check(expected=={(r['workload'],r['threads']) for r in selection['points']},'selection differs from prespecified loss threshold')
samples=[];audits={}
for group in sorted({g for g,n in expected}):
 for version in ('baseline','compat'):
  folder=root/version/group
  if group.startswith('c01'):audit,rows=base.audit_c01(folder)
  else:
   audit=api.audit(folder);rows=read(folder/'records.json')
   prep=main/'control'/('baseline-api-prepared-provider' if version=='baseline' else 'api-prepared-provider')
   audit['prepared_provider']=base.prepared_provider(prep,folder/'source')
  if args.main=='matrix7':
   original=main/version/group
   check(read(folder/'source-sha256.json')==read(original/'source-sha256.json'),'follow-up source differs from final matrix')
   if group.startswith('c01'):
    check(read(folder/'binary-sha256.json')==read(original/'binary-sha256.json'),'follow-up binary identities differ')
   else:
    identities=lambda d:{k:v['sha256'] for k,v in d.items()}
    check(identities(read(folder/'binaries.json'))==identities(read(original/'binaries.json')),'follow-up API binary identities differ')
   audit['identical_to_final_matrix']=True
   if version=='compat':audit['no_native_mutex_imports']=native_imports.audit(folder,group)
  audits[version+'/'+group]=audit
  for row in rows:
   check((group,row['threads']) in expected and row['repeat'] in range(9) and row['arm']=='kdlock','unexpected follow-up sample')
   check(row['drained'] and row['duration_ms']==2000 and row['mutex_version']==version,'follow-up contract')
   if version=='compat':
    if args.main=='matrix7' and group.startswith('c01'):
     address=row['layout']['lock_addr'];address=int(address,0) if isinstance(address,str) else address
     check(address%128==0,'follow-up KD object alignment')
    im=row['image_generation_before'];check(im==row['image_generation_after'] and im['capabilities']==[5,27,256,8192] and im['generation']==1,'immutable image changed')
   r=base.sample(group,row);r.update(version=version,sequence=row['sequence']);samples.append(r)
check(len(samples)==18*len(expected)==status['completed'],'missing follow-up sessions')
idx={(r['workload'],r['threads'],r['repeat'],r['version']):r for r in samples};check(len(idx)==len(samples),'duplicate sample')
pairs=[];comparisons=[]
for g,n in sorted(expected):
 for rep in range(9):
  a,b=idx[g,n,rep,'baseline'],idx[g,n,rep,'compat'];check(abs(a['sequence']-b['sequence'])==1,'not adjacent')
  pairs.append(dict(workload=g,threads=n,repeat=rep,whole_ratio=b['whole_ops_s']/a['whole_ops_s'],peak_ratio=b['peak_ops_s']/a['peak_ops_s']))
 a=[idx[g,n,r,'baseline']['whole_ops_s']/1e6 for r in range(9)];b=[idx[g,n,r,'compat']['whole_ops_s']/1e6 for r in range(9)]
 ps=[r['whole_ratio'] for r in pairs if r['workload']==g and r['threads']==n]
 record=dict(workload=g,threads=n,repeats=9,accepted_whole_mops=statistics.median(a),kdonly_whole_mops=statistics.median(b),whole_change_pct=100*(statistics.median(b)/statistics.median(a)-1),paired_ratio_min=min(ps),paired_ratio_median=statistics.median(ps),paired_ratio_max=max(ps),slower_pairs=sum(x<1 for x in ps),accepted_range_mops=[min(a),max(a)],kdonly_range_mops=[min(b),max(b)])
 comparisons.append(record)
for name,rows in [('recheck-samples',samples),('recheck-pairs',pairs),('recheck-comparison',comparisons)]:
 save(out/(name+'.json'),rows)
 if rows:base.table(out/(name+'.csv'),rows)
verification=dict(status='PASS',sessions=len(samples),accepted=sum(r['accepted'] for r in samples),drained=sum(r['drained'] for r in samples),actual_jit=sum(r['jit_bodies']>0 for r in samples),checks=audits)
save(out/'recheck-verification.json',verification)
print(json.dumps({'sessions':len(samples),'status':'PASS','comparison':comparisons},indent=2))
