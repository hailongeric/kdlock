"""Read preserved one-round records on the source host; never run workloads."""
import argparse,csv,json,math
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
def load(path,prefix):
 raw=json.loads(path.read_text());rows={}
 for name,records in raw.items():
  if not name.startswith(prefix+'-'):continue
  family,placement=name[len(prefix)+1:].split('-',1)
  for r in records:
   assert r['execution_status']=='OK' and r['drained'] and not r.get('cleanup_error'),r['name']
   assert r['repeat']==0 and not r.get('functional') and not r.get('diagnostic'),r['name']
   assert r['measurement']['complete'] and r['measurement']['data_ok'],r['name']
   assert r['score_eligible'],r['name']
   key=(family,r['cachelines'],r.get('write_percent',100),placement,r['threads'],r['arm'])
   assert key not in rows,key
   rows[key]=r
 return rows
b=load(a.before,'before');c=load(a.after,'after');assert len(b)==288 and len(c)==96,(len(b),len(c))
def rate(r):return r.get('whole_ops_s',r.get('whole_throughput_ops_s'))
def pct(new,old):return 100*(new/old-1)
def wr(r):return r.get('jit_completions',r.get('jit_bodies'))
def csvwrite(name,rows):
 with (a.output/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
points=[]
for key,after in sorted(c.items()):
 family,cl,w,placement,n,arm=key;assert arm=='kdlock'
 before=b[key];native=b[(*key[:-1],'native')];tc=b[(*key[:-1],'tclock')]
 for ref in (before,native,tc):assert ref['cpus']==after['cpus'],key
 for name in ('duration_ms','cachelines','threads','warmup_iterations_per_worker','post_work_rounds','caller_abi','call_shell','caller_shell','numa_policy','provider_mutex_policy','delegation_batch_limit','spin_entry_ratio_limit','spin_prefetch','mix_policy','provider_ubsan','kd_provider_ubsan','mutex_api','rwsem_writer_shell','entry_abi','delegate','collector_cpu','peak_settle_ms','peak_window_ms','sample_ms'):
  assert before.get(name)==after.get(name),(key,name,before.get(name),after.get(name))
 for parameter in ('spin_delegate','spin_entry_ratio_limit','spin_prefetch','bench_complete_probe','bench_quiet','hotlock_stats','jit_timing','target_process'):
  assert before.get('parameters',{}).get(parameter)==after.get('parameters',{}).get(parameter),(key,parameter)
 row=dict(family=family,cachelines=cl,write_percent=w,placement=placement,workers=n,cpus=','.join(map(str,after['cpus'])),
  native_before_ops_s=rate(native),tclock_before_ops_s=rate(tc),kd_before_ops_s=rate(before),kd_after_ops_s=rate(after),
  before_vs_tclock_pct=pct(rate(before),rate(tc)),after_vs_tclock_pct=pct(rate(after),rate(tc)),after_vs_before_pct=pct(rate(after),rate(before)),
  after_is_lower=rate(after)<rate(before),before_jit_completions=wr(before),after_jit_completions=wr(after),
  before_execution=before.get('execution_class',before.get('jit_status')),after_execution=after.get('execution_class',after.get('jit_status')),
  before_session=before['name'],after_session=after['name'])
 points.append(row)
csvwrite('points.csv',points)
numa=[]
for family,cl,w in sorted({k[:3] for k in c}):
 for n in (20,32):
  same=next(r for r in points if (r['family'],r['cachelines'],r['write_percent'],r['placement'],r['workers'])==(family,cl,w,'contiguous',n))
  split=next(r for r in points if (r['family'],r['cachelines'],r['write_percent'],r['placement'],r['workers'])==(family,cl,w,'split'+str(n),n))
  row=dict(family=family,cachelines=cl,write_percent=w,workers=n)
  for arm in ('native_before','tclock_before','kd_before','kd_after'):
   row[arm+'_same_ops_s']=same[arm+'_ops_s'];row[arm+'_split_ops_s']=split[arm+'_ops_s'];row[arm+'_split_vs_same_pct']=pct(split[arm+'_ops_s'],same[arm+'_ops_s'])
  numa.append(row)
csvwrite('numa.csv',numa)
summary=[]
for family,cl,w in sorted({k[:3] for k in c}):
 selected=[r for r in points if (r['family'],r['cachelines'],r['write_percent'])==(family,cl,w)]
 delta=[r['kd_after_ops_s']/r['kd_before_ops_s'] for r in selected]
 worst=min(selected,key=lambda r:r['after_vs_before_pct']);best=max(selected,key=lambda r:r['after_vs_before_pct'])
 summary.append(dict(family=family,cachelines=cl,write_percent=w,points=len(selected),
  geometric_mean_pct=100*(math.exp(sum(map(math.log,delta))/len(delta))-1),negative_points=sum(x<1 for x in delta),
  worst_pct=worst['after_vs_before_pct'],worst_point=f"{worst['placement']}/{worst['workers']}",best_pct=best['after_vs_before_pct'],best_point=f"{best['placement']}/{best['workers']}"))
csvwrite('summary.csv',summary)
lines=['# Every scored Nano point','',
 'One round per point. Rates are whole-run million operations/second. Native and TCLock are the retained baseline arms; before/after KD are separate source versions. Every negative delta is retained. The spin shell uses post64; the other families use post256. Do not compare absolute throughput across these shells.','']
for family,cl,w in sorted({k[:3] for k in c}):
 lines += [f'## {family} c{cl:02d} w{w:03d}','', '| Placement | Workers | Native | TCLock | KD before | KD after | After / before | After / TCLock | Returned bodies before / after |','|---|---:|---:|---:|---:|---:|---:|---:|---|']
 for r in points:
  if (r['family'],r['cachelines'],r['write_percent'])!=(family,cl,w):continue
  lines.append('| '+ ' | '.join([r['placement'],str(r['workers']),*[f"{r[k]/1e6:.4f}" for k in ('native_before_ops_s','tclock_before_ops_s','kd_before_ops_s','kd_after_ops_s')],f"{r['after_vs_before_pct']:+.2f}%",f"{r['after_vs_tclock_pct']:+.2f}%",f"{r['before_jit_completions']} / {r['after_jit_completions']}" + (" (NO_JIT)" if r['before_jit_completions']==0 or r['after_jit_completions']==0 else "")])+ ' |')
 lines.append('')
(a.output/'ALL_POINTS.md').write_text('\n'.join(lines)+'\n')
(a.output/'summary.json').write_text(json.dumps(dict(before_points=len(b),after_points=len(c),families=summary,negative_points=[r for r in points if r['after_is_lower']]),indent=2)+'\n')
print(json.dumps(summary,indent=2))
