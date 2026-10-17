#!/usr/bin/env python3
"""Replay the paired legacy compatibility experiment; never access live modules."""
import argparse,csv,gzip,hashlib,importlib.util,json,math,statistics,sys
from collections import Counter,defaultdict
from pathlib import Path

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
HERE=Path(__file__).resolve().parent
base=module('legacy_audit',HERE/'legacy-audit.py');api=module('api_audit',HERE/'api-audit.py')
load,save,check,sha=base.read,base.save,base.check,base.sha
THREADS=[*range(1,9),*range(12,61,4)]
GROUPS=('c01-post64','api-pipebytes-query-n16')
ARMS=('native','tclock','legacy','compat')
LABELS=dict(native='Linux Native',tclock='TCLock',legacy='KD legacy',compat='KD legacy + compatibility')

def table(path,rows):base.table(path,rows)

def plot(stats,out):
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 colors=dict(native='#777777',tclock='#0072B2',legacy='#D55E00',compat='#009E73')
 plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':'legacy-mutex-compat'})
 for metric,title in [('whole','Median whole-run throughput'),('peak','Best warmed peak across three repetitions')]:
  fig,axs=plt.subplots(1,2,figsize=(12,4.8),sharex=True)
  handles=[]
  for ax,group in zip(axs,GROUPS):
   ax.axvspan(32.5,61,color='#eeeeee',zorder=0)
   for arm in ARMS:
    rows=sorted((r for r in stats if r['workload']==group and r['arm']==arm),key=lambda r:r['threads'])
    y=[r['whole_median_ops_s']/1e6 if metric=='whole' else r['best_peak_ops_s']/1e6 for r in rows]
    line,=ax.plot(THREADS,y,color=colors[arm],label=LABELS[arm],marker='o',markersize=3,linewidth=1.5)
    ax.fill_between(THREADS,[r[metric+'_min_ops_s']/1e6 for r in rows],[r[metric+'_max_ops_s']/1e6 for r in rows],color=colors[arm],alpha=.10)
    if ax is axs[0]:handles.append(line)
   ax.set_title(group);ax.set_xlabel('Workers');ax.set_ylabel('Mops/s');ax.set_xlim(0,61);ax.set_xticks([1,4,8,16,24,32,40,48,56,60]);ax.grid(axis='y',alpha=.2)
  fig.suptitle(title,x=.07,ha='left',fontsize=14)
  fig.legend(handles=handles,loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,.045))
  fig.text(.07,.015,'Fresh adjacent KD pairs; 3 repetitions; bands: min–max. Gray: two NUMA nodes. Host governor: ondemand.',fontsize=9)
  fig.tight_layout(rect=(0,.15,1,.93))
  for ext in ('png','svg'):
   path=out/f'{metric}-throughput.{ext}';fig.savefig(path,dpi=170)
   if ext=='svg':path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')
  plt.close(fig)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--plots',action='store_true');args=p.parse_args()
 root,out=args.root.resolve(),args.output.resolve();out.mkdir(parents=True,exist_ok=True)
 state=load(root/'status.json');check(state['state']=='COMPLETE' and state['completed']==504,'unfinished final matrix')
 source=load(root/'control/source-sha256.json')
 for n,h in source.items():check(sha(root/'frozen-source'/n)==h,'source identity: '+n)
 for n,h in load(root/'control/prepared-inputs-sha256.json').items():check(sha(root/n)==h,'frozen input: '+n)
 check(all(r['exit_code']==0 for r in load(root/'validation/checks.json')),'unpassed required checks')
 samples=[];workers=[];checks={};records_by_key={}
 identity=load(root/'control/kernel-identity.json')
 for version in ('baseline','compat'):
  for group in GROUPS:
   folder=root/version/group
   if group.startswith('c01'):audit,records=base.audit_c01(folder)
   else:
    audit=api.audit(folder);records=load(folder/'records.json')
    prepared=root/'control'/('api-prepared-provider' if version=='compat' else 'baseline-api-prepared-provider')
    audit['prepared_provider']=base.prepared_provider(prepared,folder/'source')
   checks[version+'/'+group]=audit
   check(load(folder/('baseline.json' if group.startswith('c01') else 'kernel-identity.json'))==identity,'kernel identity differs')
   expected={(n,r,a) for n in THREADS for r in range(3) for a in (('kdlock',) if version=='baseline' else ('native','tclock','kdlock'))}
   check(len(records)==len(expected) and {(r['threads'],r['repeat'],r['arm']) for r in records}==expected,'missing/duplicate configurations')
   for row in records:
    check(row['mutex_version']==version and row['lock_kind']=='mutex' and row['duration_ms']==2000 and row['drained'],'version/timing/drain')
    check(row['peak_window_ms']==row['peak_settle_ms']==300 and row['sample_ms']==10,'peak intervals')
    if group.startswith('api'):
     check(row['kind']=='pipebytes' and row['query']=='query' and row['entries']==16 and row['warmup']==48000 and row['warmup_ms']==1000,'API configuration')
    if version=='compat' and row['arm']=='kdlock':
     im=row['image_generation_before'];check(im==row['image_generation_after'],'image changed during timing')
     check(im['capabilities']==[4,11,256,8192] and im['abi']==2 and im['generation']==1 and im['requirements']==0,'live immutable image contract')
    result=base.sample(group,row)
    result.update(arm=('legacy' if version=='baseline' else 'compat') if row['arm']=='kdlock' else row['arm'],mutex_version=version,sequence=row['sequence'])
    samples.append(result);records_by_key[(group,row['threads'],row['repeat'],result['arm'])]=row
    for worker in row['measurement']['workers']:workers.append(dict(workload=group,arm=result['arm'],repeat=row['repeat'],threads=row['threads'],sequence=row['sequence'],**worker))
 check(len({s['sequence'] for s in samples})==504,'sequence duplicated')
 ordered=sorted(samples,key=lambda s:s['sequence'])
 for record,scheduled in zip(ordered,load(root/'control/execution-order.json')):
  group,n,rep,v,arm=scheduled
  check((record['workload'],record['threads'],record['repeat'],record['mutex_version'])==(group,n,rep,v),'schedule mismatch')
  check(record['arm']==(('legacy' if v=='baseline' else 'compat') if arm=='kdlock' else arm),'scheduled arm mismatch')
 buckets=defaultdict(list)
 for s in samples:buckets[(s['workload'],s['threads'],s['arm'])].append(s)
 stats=[]
 for key,rows in sorted(buckets.items()):
  result=base.aggregate(key,rows)
  if key[2] in ('legacy','compat'):result['no_jit_rounds']=sum(r['accepted'] and not r['jit_bodies'] for r in rows)
  stats.append(result)
 pairs=[]
 bysample={(s['workload'],s['threads'],s['repeat'],s['arm']):s for s in samples}
 for group in GROUPS:
  for n in THREADS:
   for rep in range(3):
    old=bysample[group,n,rep,'legacy'];new=bysample[group,n,rep,'compat']
    check(abs(old['sequence']-new['sequence'])==1,'KD pair not adjacent')
    pairs.append(dict(workload=group,threads=n,repeat=rep,accepted=old['accepted'] and new['accepted'],legacy_first=old['sequence']<new['sequence'],whole_ratio=new['whole_ops_s']/old['whole_ops_s'],peak_ratio=new['peak_ops_s']/old['peak_ops_s'],legacy_whole_ops_s=old['whole_ops_s'],compat_whole_ops_s=new['whole_ops_s']))
 index={(r['workload'],r['threads'],r['arm']):r for r in stats};comparison=[]
 for group in GROUPS:
  for n in THREADS:
   old,new=index[group,n,'legacy'],index[group,n,'compat'];ps=[x for x in pairs if x['workload']==group and x['threads']==n and x['accepted']]
   r=dict(workload=group,threads=n,complete=old['complete'] and new['complete'],legacy_whole_mops=old['whole_median_ops_s']/1e6,compat_whole_mops=new['whole_median_ops_s']/1e6,legacy_peak_mops=old['best_peak_ops_s']/1e6,compat_peak_mops=new['best_peak_ops_s']/1e6)
   r.update(whole_change_pct=100*(r['compat_whole_mops']/r['legacy_whole_mops']-1),peak_change_pct=100*(r['compat_peak_mops']/r['legacy_peak_mops']-1),paired_whole_ratio_median=statistics.median(x['whole_ratio'] for x in ps),paired_whole_ratio_min=min(x['whole_ratio'] for x in ps),paired_whole_ratio_max=max(x['whole_ratio'] for x in ps))
   for arm in ('native','tclock'):r['compat_over_'+arm]=new['whole_median_ops_s']/index[group,n,arm]['whole_median_ops_s']
   comparison.append(r)
 for name,rows in [('samples',samples),('statistics',stats),('paired-samples',pairs),('comparison',comparison)]:save(out/(name+'.json'),rows);table(out/(name+'.csv'),rows)
 fields=list(dict.fromkeys(k for r in workers for k in r))
 with gzip.open(out/'workers.csv.gz','wt',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(workers)
 lines=['# Full paired scaling results','','Whole: median of three runs. Peak: highest valid warmed 300 ms window. Rates in Mops/s.','']
 for group in GROUPS:
  lines += ['## '+group,'','| Workers | Native whole | TCLock whole | Legacy whole | Backport whole | Change | Legacy peak | Backport peak |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
  for n in THREADS:
   c=next(r for r in comparison if r['workload']==group and r['threads']==n)
   lines.append(f"| {n} | {index[group,n,'native']['whole_median_ops_s']/1e6:.3f} | {index[group,n,'tclock']['whole_median_ops_s']/1e6:.3f} | {c['legacy_whole_mops']:.3f} | {c['compat_whole_mops']:.3f} | {c['whole_change_pct']:+.2f}% | {c['legacy_peak_mops']:.3f} | {c['compat_peak_mops']:.3f} |")
  lines.append('')
 (out/'SCALING.md').write_text('\n'.join(lines))
 verification=dict(status='PASS',sessions=len(samples),accepted=sum(s['accepted'] for s in samples),drained=sum(s['drained'] for s in samples),actual_jit=sum(s['jit_bodies']>0 for s in samples),kd_no_jit=sum(s['arm'] in ('legacy','compat') and not s['jit_bodies'] for s in samples),timed_operations=sum(s['completed'] for s in samples),independent_peaks=len(samples),frozen_source_files=len(source),checks=checks)
 save(out/'verification.json',verification)
 if args.plots:plot(stats,out)
 print(json.dumps({k:v for k,v in verification.items() if k!='checks'},indent=2))
 print(json.dumps([r for r in comparison if r['threads']==60],indent=2))
if __name__=='__main__':main()
