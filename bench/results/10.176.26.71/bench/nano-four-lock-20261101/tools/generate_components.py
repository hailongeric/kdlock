"""Offline component comparison; no extra scored baseline round."""
from pathlib import Path
import csv,json,math,statistics
root=Path('/tmp/kdlock-nano-four-lock-results-20261102/bench/results/10.176.26.71/bench/nano-four-lock-20261101')
data=json.load(open('/tmp/kdlock-four-lock-components-final-20261102.json'))
base=json.load(open('/tmp/kdlock-four-lock-before-final-20261101.json'))
both=list(csv.DictReader((root/'reader-entry/points.csv').open()))
versions={'rwsem-reader-only':'252825407cd40d91a32010e82c8c111a768e7fcf','osq-poll-only':'4df80e5a14d0368b07c5c0a63b49f0b79b80ca4f'}
rows=[];profiles={};checks={}
for arm,ds in data.items():
 checks[arm]={p:v for p,v in ds.items() if p in ('unit-control/owner.json','basic/result.json','mutex-local/result.json','rwsem/result.json','final-health.json')}
 assert checks[arm]['unit-control/owner.json']['source_commit']==versions[arm]
 for p in ('unit-control/owner.json','basic/result.json','mutex-local/result.json','rwsem/result.json'):assert checks[arm][p]['passed'],(arm,p)
 for path,rs in ds.items():
  if path.endswith('perf-worker-summary.json'):
   profiles[arm+'/'+path]=rs;continue
  if not path.startswith('after-rwsem-') or not path.endswith('records.json'):continue
  placement=path.split('/')[0].removeprefix('after-rwsem-')
  for r in rs:
   assert r['arm']=='kdlock' and r['repeat']==0 and r['drained'] and r['execution_status']=='OK' and r['score_eligible']
   assert r['measurement']['data_ok'] and r['measurement']['complete'] and not r.get('cleanup_error')
   matches=[b for b in base['before-rwsem-'+placement] if b['arm']=='kdlock' and (b['cachelines'],b['write_percent'],b['threads'])==(r['cachelines'],r['write_percent'],r['threads'])];assert len(matches)==1;b=matches[0]
   for key in ('cpus','cachelines','write_percent','threads','post_work_rounds','duration_ms','caller_abi','call_shell','delegate','entry_abi','rwsem_writer_shell','mix_policy','provider_mutex_policy','provider_ubsan','warmup_iterations_per_worker','collector_cpu','spin_entry_ratio_limit','spin_prefetch','numa_policy'):
    assert b.get(key)==r.get(key),(arm,key,b.get(key),r.get(key))
   c=next(x for x in both if (x['family'],int(x['cachelines']),int(x['write_percent']),int(x['workers']),x['placement'])==('rwsem',r['cachelines'],r['write_percent'],r['threads'],placement))
   ws=r['measurement']['workers'];cpu=sum(x['cpu_ns'] for x in ws);wall=sum(x['kernel_finished_ns']-x['active_started_ns'] for x in ws);counts=[x['completed'] for x in ws]
   rows.append(dict(component=arm,source_commit=versions[arm],cachelines=r['cachelines'],write_percent=r['write_percent'],workers=r['threads'],placement=placement,
    baseline_ops_s=b['whole_ops_s'],both_components_ops_s=float(c['kd_after_ops_s']),component_ops_s=r['whole_ops_s'],component_vs_baseline_pct=100*(r['whole_ops_s']/b['whole_ops_s']-1),
    baseline_returned_jit=b['jit_completions'],component_returned_jit=r['jit_completions'],worker_cpu_seconds=cpu/1e9,worker_utilization_pct=100*cpu/wall,worker_completion_cv_pct=100*statistics.pstdev(counts)/statistics.mean(counts),session=r['name']))
assert len(rows)==6
rows.sort(key=lambda r:(r['cachelines'],r['write_percent'],r['workers'],r['component']))
with (root/'components.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
(root/'correctness/components.json').write_text(json.dumps(checks,indent=2)+'\n')
p=json.loads((root/'profiles.json').read_text());p.update(profiles);(root/'profiles.json').write_text(json.dumps(p,indent=2)+'\n')
(root/'component-profiles.json').write_text(json.dumps(profiles,indent=2)+'\n')
lines=['# Three-point component comparisons','',
 'These are separate source versions, each with one round per selected point. The retained baseline is `87a3a41f1ba3746b7716e611541068bd3ab6e975`; it was not rerun to replace a score. The combined candidate is `1ba4cc6e59f5451eaecafcf1c3a36861d026e5d9`.','',
 '- Reader-entry only: `252825407cd40d91a32010e82c8c111a768e7fcf`; exact baseline OSQ restored.','- OSQ64 only: `4df80e5a14d0368b07c5c0a63b49f0b79b80ca4f`; exact baseline rwsem entry/release restored.','',
 'Both passed the five affected unit groups, basic returned-JIT mutex/rwsem checks and live local mutex/rwsem API checks before profiling and timing. All six scored sessions returned correct data and drained. This narrow comparison cannot establish a full-grid regression pass.','',
 '| Workload/placement/workers | Component | Baseline Mops/s | Both Mops/s | Component Mops/s | Component/baseline | Returned JIT |','|---|---|---:|---:|---:|---:|---:|']
for r in rows:
 lines.append(f"| c{r['cachelines']:02d} w{r['write_percent']:03d} {r['placement']}/{r['workers']} | {r['component']} | {r['baseline_ops_s']/1e6:.4f} | {r['both_components_ops_s']/1e6:.4f} | {r['component_ops_s']/1e6:.4f} | {r['component_vs_baseline_pct']:+.2f}% | {r['component_returned_jit']} |")
lines+=['','## Eight-worker unscored cycle profiles','','Flat sampled worker-cycle shares; these percentages are neither score ratios nor inclusive elapsed times. No baseline c01/w1 eight-worker cycle profile was captured, so per-instruction cost changes cannot be assigned from this table alone.','','| Version | Read entry | Read release | OSQ lock | Outlined read slowpath | Common rb_run |','|---|---:|---:|---:|---:|---:|']
ref=json.load(open('/tmp/kdlock-four-lock-reader-entry-profiles-20261101.json'))['after-record8']
ref=next(v for k,v in ref.items() if 'rwsem-c01-w001/' in k)
for name,p in [('both',ref),*[(arm,next(v for k,v in profiles.items() if k.startswith(arm+'/'))) for arm in versions]]:
 shares={x['symbol']:100*x['worker_period_share'] for x in p['hot_paths']}
 lines.append('| '+name+' | '+' | '.join(f'{shares.get(k,0):.2f}%' for k in ('kd_down_read','kd_up_read','kd_mutex_osq_lock','kd_down_read_slowpath','rb_run'))+' |')
lines+=['','[Exact scores and worker CPU-time data](components.csv), [profile summaries](component-profiles.json), [correctness receipts](correctness/components.json). Each observed negative remains in the table; no value is substituted into a full-grid candidate result.']
(root/'COMPONENTS.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(rows,indent=2))
