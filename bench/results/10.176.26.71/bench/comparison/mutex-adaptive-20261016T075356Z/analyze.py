#!/usr/bin/env python3
"""Export source-separated mutex samples and recomputable statistics."""
import argparse,csv,hashlib,json,re,statistics,math,gzip
from collections import Counter
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path);p.add_argument('--phase',default='full-v8');p.add_argument('--plots',action='store_true');a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=True)
flat=[]
audit=Counter()
workers=[]
nodes=[]
final_runtime=json.loads((a.root/'control/final-runtime-sha256.json').read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path): return json.loads(path.read_text())
def mapped(path):
 marker='/mutex-adaptive-20261016T075356Z/'
 assert marker in str(path),path
 return a.root/str(path).split(marker,1)[1]
def peak_check(r):
 m=r['measurement'];start=max(w['active_started_ns'] for w in m['workers'])+m['peak_settle_ns']
 end=min(m['deadline_ns'],*(w['kernel_finished_ns'] for w in m['workers']))
 samples=[s for s in m['samples'] if s['started_ns']>=start and s['finished_ns']<=end]
 best=None
 for i,first in enumerate(samples):
  for last in samples[i+1:]:
   elapsed=last['finished_ns']-first['started_ns']
   if elapsed<m['peak_window_ns']:continue
   values=[b-a for a,b in zip(first['completed'],last['completed'])]
   if min(values)>0 and (best is None or sum(values)*best[1]>best[0]*elapsed):best=(sum(values),elapsed)
   break
 assert best and math.isclose(best[0]*1e9/best[1],m['peak']['throughput_ops_s'],rel_tol=1e-12),r['name']
 audit['recomputed_peaks']+=1
if (a.root/(a.phase+'-status.json')).exists():
 state=load(a.root/(a.phase+'-status.json'));assert state['state']=='COMPLETE',state
 manifest=load(a.root/'control/baseline-source-sha256.json')
 for n,h in manifest.items():assert sha(a.root/'baseline-source'/n)==h,n
 audit['baseline_source_files']=len(manifest)

for d in sorted(a.root.iterdir()):
 if not d.is_dir() or not (d.name.endswith('-mutex-c01') or d.name.endswith('-api-pipebytes-query-n16')):continue
 workload='c01-post64' if d.name.endswith('-mutex-c01') else 'api-pipebytes-query-n16'
 phase=d.name.removesuffix('-mutex-c01').removesuffix('-api-pipebytes-query-n16')
 if phase==a.phase:
  expected={(t,arm,r) for t in [*range(1,9),*range(12,61,4)] for arm in ('native','tclock','before','adaptive') for r in range(3)}
  records=load(d/'records.json');specs=load(d/'plan.json')
  assert len(records)==len(specs)==252
  assert {(r['threads'],r['comparison_arm'],r['repeat']) for r in records}==expected
  assert {r['name'] for r in records}=={r['name'] for r in specs}
  record_index={r['name']:r for r in records}
  assert {p.parent.name for p in d.glob('*/session.json')}==set(record_index)
  for n,h in load(d/'source-sha256.json').items():
   assert sha(d/'source'/n)==h,n
   if n in final_runtime:assert final_runtime[n]==h,n
   audit['source_hashes']+=1
  if workload=='api-pipebytes-query-n16':
   binaries={d/'build'/n:r['sha256'] for n,r in load(d/'binaries.json').items()}
   for n,h in load(d/'kernel-inputs-sha256.json').items():
    assert sha(d/'kernel-inputs'/n)==h,n
    audit['kernel_input_hashes']+=1
  else:
   binaries={mapped(n) if '/mutex-adaptive-20261016T075356Z/' in n else d/'binaries'/Path(n).name:h for n,h in load(d/'binary-sha256.json').items()}
  for n,h in binaries.items():assert sha(n)==h,n
  audit['binary_hashes']+=len(binaries)
 for path in sorted(d.glob('*/session.json')):
  r=json.loads(path.read_text());m=r.get('measurement',{});ws=m.get('workers',[])
  good=r.get('execution_status')=='OK' and r.get('drained') is True
  if good:
   assert len(ws)==r['threads'] and all(w['completed']>0 and w['cpu_ns']>0 for w in ws),path
   assert m['completed']==sum(w['completed'] for w in ws),path
   assert (m.get('data_ok') and m.get('complete')) if workload=='c01-post64' else m.get('ok'),path
  if phase==a.phase:
   assert good,path
   expected_record=dict(r)
   if workload=='c01-post64':
    expected_record.update(whole_throughput_ops_s=m['completed']*1e9/m['wall_ns'],whole_amortized_ns_op=m['wall_ns']/m['completed'],throughput_ops_s=m['peak']['throughput_ops_s'],amortized_ns_op=m['peak']['amortized_ns_op'],score_eligible=not(r.get('diagnostic',False) or r.get('pmu',False)))
   assert expected_record==record_index[r['name']],path
   assert r['cpus']==list(range(r['threads'])) and r['collector_cpu']==63 and r['duration_ms']==2000
   assert m['collector_observed_cpu']==63 and m['collector_error']==0
   assert all(w['cpu']==w['observed_cpu']==i for i,w in enumerate(ws))
   assert m['peak_settle_ns']==m['peak_window_ns']==300000000
   assert len(m['peak']['worker_completed'])==r['threads'] and min(m['peak']['worker_completed'])>0
   assert sum(m['peak']['worker_completed'])==m['peak']['completed']
   peak_check(r)
   if workload=='c01-post64':
    assert r['post_work_rounds']==64 and r['warmup_iterations_per_worker']==48000 and r['cachelines']==1
   else:
    assert r['kind']=='pipebytes' and r['query']=='query' and r['entries']==16 and r['value_size']==64
    assert r['warmup']==48000 and r['warmup_ms']==1000 and r['redirected_calls']==m['completed']
   if r['arm']=='kdlock':
    adaptive=r['comparison_arm']=='adaptive'
    assert r['entry_abi']==4 and r['registry_lock_kind']==3 and r['mutex_implementation']=='owned-v1'
    assert r['owned_mutex_object_bytes']==(128 if adaptive else 32)
    assert r['owned_mutex_numa'] is adaptive and not r['owned_mutex_origin_spin']
    assert bool(r.get('owned_mutex_adaptive',False)) is adaptive
    assert r['owned_mutex_reuse_spins']==32 and r['mutex_spin_limit']==4096 and r['mutex_wait_mode']=='blocking'
    params=r['parameters'];assert params['owned_mutex_protocol']==('contention_adaptive_v8' if adaptive else 'linux_local_first_v1')
    assert params['owned_mutex_numa']==('Y' if adaptive else 'N') and params['owned_mutex_origin_spin']=='N'
    for field,value in {'owned_mutex_spin_limit':4096,'owned_mutex_reuse_spins':32,'owned_mutex_self_route':0,'owned_mutex_native_after_control':0,'owned_mutex_refill':0,'owned_mutex_preflight_spins':0,'owned_mutex_preflight_queue':0}.items():
     actual={'Y':1,'N':0}.get(params[field],params[field]);assert int(actual)==value,(path,field,actual)
    if workload=='api-pipebytes-query-n16':assert r['source_quiescent'] is True
    else:assert r['kd_provider_ubsan']=='off' and not r['diagnostic']
    if adaptive:assert params['owned_mutex_adaptive']=='Y'
    else:
     for n,h in r['baseline_binary_sha256'].items():assert sha(mapped(n))==h,n
     audit['baseline_binary_checks']+=len(r['baseline_binary_sha256'])
    if workload=='c01-post64':assert r['owned_queue_policy']==('bounded_numa_cohort_refill' if adaptive else 'finite_fifo')
    assert r['retired']==dict(state=2,modules=0,frames=0,writers=0)
    pub=r.get('published_before',r.get('publication'))
    if 'published_before' in r:assert pub==r['published_after']
    if pub:
     e=pub['entry'];assert e['entry_abi']==4 and e['lock_kind']==3 and e['status']==0
     assert pub['source']==dict(state=0,modules=1,frames=0,writers=0)
     images=path.parent/'workspace/daemon'/hex(e['entry'])/str(e['tgid'])/'asm'
     for n,h in pub['images'].items():assert sha(images/n)==h,n
     audit['jit_image_hashes']+=len(pub['images'])
    assert 0<=r['jit_bodies']<=m['completed']
   node_rows={}
   for w,peak_count in zip(ws,m['peak']['worker_completed']):
    node=0 if w['cpu']<32 else 1
    totals=node_rows.setdefault(node,Counter());totals.update(workers=1,whole_completed=w['completed'],peak_completed=peak_count,cpu_ns=w['cpu_ns'])
    workers.append(dict(workload=workload,session=r['name'],arm=r['comparison_arm'],threads=r['threads'],repeat=r['repeat'],node=0 if w['cpu']<32 else 1,peak_completed=peak_count,whole_share=w['completed']/m['completed'],**w))
   for node,totals in node_rows.items():
    nodes.append(dict(workload=workload,session=r['name'],arm=r['comparison_arm'],threads=r['threads'],repeat=r['repeat'],node=node,**totals,whole_share=totals['whole_completed']/m['completed'],peak_share=totals['peak_completed']/m['peak']['completed']))
  whole=(r.get('whole_throughput_ops_s') or m['completed']*1e9/m['wall_ns']) if good else None
  peak=(r.get('peak_throughput_ops_s') or m['peak']['throughput_ops_s']) if good else None
  if good:assert math.isclose(whole,m['completed']*1e9/m['wall_ns'],rel_tol=1e-12),path
  row=dict(phase=phase,workload=workload,threads=r['threads'],arm=r.get('comparison_arm',r['arm']),repeat=r['repeat'],
    session=str(path.relative_to(a.root)),execution_status=r.get('execution_status'),drained=r.get('drained'),accepted=good,
    whole_ops_s=whole,peak_ops_s=peak,completed=m.get('completed'),jit_bodies=r.get('jit_bodies',0),
    cpu_ns_per_op=sum(w['cpu_ns'] for w in ws)/m['completed'] if good else None,
    min_worker_share=min(w['completed'] for w in ws)/m['completed'] if good else None,
    max_worker_share=max(w['completed'] for w in ws)/m['completed'] if good else None,
    parks=r.get('mutex_wait_delta',{}).get('result_schedule_calls'),wakes=r.get('mutex_wait_delta',{}).get('result_wakes'),
    object_bytes=r.get('owned_mutex_object_bytes',32) if r['arm']=='kdlock' else None,
    protocol=r.get('parameters',{}).get('owned_mutex_protocol'),
    source_manifest=str((d/'source-sha256.json').relative_to(a.root)),
    baseline_binary_sha256=r.get('baseline_binary_sha256'))
  row['jit_share']=row['jit_bodies']/m['completed'] if good else None
  flat.append(row)
groups={}
for r in flat:groups.setdefault(tuple(r[k] for k in ('phase','workload','threads','arm')),[]).append(r)
summary=[]
for key,rows in sorted(groups.items()):
 good=[r for r in rows if r['accepted']]
 row=dict(zip(('phase','workload','threads','arm'),key));row.update(samples=len(rows),accepted=len(good),rounds=sorted(r['repeat'] for r in good))
 for metric in ('whole_ops_s','peak_ops_s','cpu_ns_per_op','jit_share'):
  values=[r[metric] for r in good]
  for stat,fn in [('min',min),('median',statistics.median),('max',max)]:row[metric+'_'+stat]=fn(values) if values else None
  row[metric+'_spread_pct']=100*(max(values)-min(values))/statistics.median(values) if values and statistics.median(values)>0 else None
 row['parks_total']=sum(r['parks'] or 0 for r in good)
 row['jit_bodies_total']=sum(r['jit_bodies'] for r in good)
 row['min_worker_share']=min((r['min_worker_share'] for r in good),default=None)
 row['max_worker_share']=max((r['max_worker_share'] for r in good),default=None)
 if good:
  best=max(good,key=lambda r:r['peak_ops_s']);row['best_peak_session']=best['session'];row['best_peak_paired_whole_ops_s']=best['whole_ops_s']
 summary.append(row)
for name,rows in [('samples',flat),('summary',summary)]:
 (a.output/(name+'.json')).write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
 with (a.output/(name+'.csv')).open('w',newline='') as f:
  fields=list(dict.fromkeys(k for r in rows for k in r));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
comparisons=[]
index={(r['phase'],r['workload'],r['threads'],r['arm']):r for r in summary}
for (phase,workload,t,arm),r in index.items():
 if arm!='adaptive':continue
 b=index.get((phase,workload,t,'before'))
 if not b or r['accepted']!=3 or b['accepted']!=3:continue
 ratios={metric:r[metric]/b[metric] for metric in ('whole_ops_s_median','peak_ops_s_max','best_peak_paired_whole_ops_s')}
 comparisons.append(dict(phase=phase,workload=workload,threads=t,**ratios))
(a.output/'comparisons.json').write_text(json.dumps(comparisons,indent=2)+'\n')
selected=[r for r in flat if r['phase']==a.phase]
verification=dict(phase=a.phase,samples=len(selected),accepted=sum(r['accepted'] for r in selected),auditor_sha256=sha(Path(__file__)),**audit)
if selected:assert len(selected)==verification['accepted']==verification['recomputed_peaks']==504
(a.output/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
if workers:
 with gzip.open(a.output/'workers.csv.gz','wt',newline='') as f:
  fields=list(dict.fromkeys(k for r in workers for k in r));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(workers)
if nodes:
 with (a.output/'nodes.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(nodes[0]));w.writeheader();w.writerows(nodes)
print(json.dumps(verification))


if a.plots:
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 colors={'native':'#2563a6','tclock':'#8a4baf','before':'#62727b','adaptive':'#d35a16'}
 labels={'native':'Linux Native','tclock':'TCLock','before':'KD before (32 B)','adaptive':'KD adaptive (128 B)'}
 for metric,name,title in [('whole_ops_s','whole','Median whole-run throughput'),('peak_ops_s','peak','Highest valid warmed peak')]:
  fig,axes=plt.subplots(1,2,figsize=(12,4.4),sharex=True)
  for ax,workload in zip(axes,('c01-post64','api-pipebytes-query-n16')):
   ax.axvspan(32.5,60,color='#e9edf0',zorder=0)
   for arm in ('native','tclock','before','adaptive'):
    rows=sorted((r for r in summary if r['phase']==a.phase and r['workload']==workload and r['arm']==arm),key=lambda r:r['threads'])
    assert len(rows)==21 and all(r['accepted']==3 for r in rows)
    x=[r['threads'] for r in rows];key=metric+('_median' if name=='whole' else '_max')
    ax.plot(x,[r[key]/1e6 for r in rows],color=colors[arm],label=labels[arm],marker='o',markersize=3,linewidth=1.6)
    ax.fill_between(x,[r[metric+'_min']/1e6 for r in rows],[r[metric+'_max']/1e6 for r in rows],color=colors[arm],alpha=.12)
   ax.set_title(workload);ax.set_xlabel('Worker threads');ax.set_ylabel('Million operations / second')
   ax.set_xlim(1,60);ax.set_ylim(bottom=0);ax.set_xticks([1,4,8,16,24,32,40,48,60]);ax.grid(alpha=.2)
  axes[0].legend(fontsize=9);fig.suptitle(title)
  fig.text(.5,.01,'Three repetitions per point; bands show min–max. Gray region uses both NUMA nodes.',ha='center',fontsize=9)
  fig.tight_layout(rect=(0,.03,1,.95))
  fig.savefig(a.output/(name+'.svg'));fig.savefig(a.output/(name+'.png'),dpi=160);plt.close(fig)
 fig,axes=plt.subplots(1,2,figsize=(12,3.8),sharey=True)
 for ax,workload in zip(axes,('c01-post64','api-pipebytes-query-n16')):
  ax.axvspan(32.5,60,color='#e9edf0',zorder=0)
  for arm in ('before','adaptive'):
   rows=sorted((r for r in summary if r['phase']==a.phase and r['workload']==workload and r['arm']==arm),key=lambda r:r['threads'])
   ax.plot([r['threads'] for r in rows],[100*r['jit_share_median'] for r in rows],marker='o',markersize=3,color=colors[arm],label=labels[arm])
  ax.set_title(workload);ax.set_xlabel('Worker threads');ax.set_ylim(0,100);ax.set_ylabel('Median returned JIT body share (%)');ax.grid(alpha=.2)
 axes[0].legend(fontsize=9);fig.tight_layout();fig.savefig(a.output/'jit-share.svg');plt.close(fig)
