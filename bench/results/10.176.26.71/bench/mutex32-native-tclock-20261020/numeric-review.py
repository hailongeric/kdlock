"""Independent arithmetic review of compact JSON only; does not read raw archives."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

BASE=Path('/home/eric/vm/vm-shared/kdlock/bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020')
FILES=('comparison.json','validation.json','health.json','host-before.json','host-after.json','current/matrix.json')
INPUT={name:json.loads((BASE/name).read_text()) for name in FILES}
c=INPUT['comparison.json']; sessions=c['sessions']; groups=c['groups']; issues=[]; checks=Counter()

def check(kind, value, detail=None):
    checks[kind]+=1
    if not value:issues.append({'check':kind,'detail':detail})

def eq(a,b):
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(eq(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)) and isinstance(b,(list,tuple)):return len(a)==len(b) and all(eq(x,y) for x,y in zip(a,b))
    if type(a) in (int,float) and type(b) in (int,float):return math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-15)
    return type(a)==type(b) and a==b

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def stats(values):return dict(n=len(values),min=min(values) if values else None,max=max(values) if values else None,median=statistics.median(values) if values else None)
def key(r):return r['workload'],r['backend'],r['threads'],r['jit_class']
expected={(w,b,n,r) for w in ('c01','c08','rcuht','seek-set','seek-end','pipebytes','pipecap') for b in ('native','tclock','kdlock') for n in (1,2,4,8,16,32,36,48,60) for r in range(3)}
check('inventory',len(sessions)==567 and {(r['workload'],r['backend'],r['threads'],r['repeat']) for r in sessions}==expected)
check('summary_complete',c['complete'] and not c['issues'])
check('source_identity',len({r['source_commit'] for r in sessions})==1 and all(r['source_commit']==c['source_commit'] for r in sessions))
rows=defaultdict(list)
for r in sessions:
    name=r['session_path']; rows[key(r)].append(r); n=r['completed']; wall=r['wall_ns']; ident=r['identity']
    check('session_valid_drained',r['valid'] is True and r['drained'] is True and r['execution_status']=='OK' and not r['issues'],name)
    check('whole_rate',eq(r['observed_whole_mops'],n*1000/wall),name)
    check('worker_collector',ident['cpus']==list(range(r['threads'])) and ident['collector_cpu']==63,name)
    check('timing_settings',[ident[k] for k in ('duration_ms','peak_window_ms','peak_settle_ms','sample_ms')]==[2000,300,300,10],name)
    check('count_bounds',0<=r['jit_bodies']<=n and (r['jit_completions'] is None or 0<=r['jit_completions']<=r['jit_bodies']),name)
    kd=r['backend']=='kdlock';tc=r['backend']=='tclock'
    check('entry_share',eq(r['measured_body_entry_share'],r['jit_bodies']/n if kd else None),name)
    check('returned_share',eq(r['measured_returned_jit_share'],r['jit_completions']/n if kd and r['jit_completions'] is not None else None),name)
    check('tclock_share',eq(r['measured_tclock_delegation_share'],r['tclock_delegated']/n if tc else None),name)
    check('kernel_faults',r['whole_session_diagnostics']['fault_count']==0 and not r['whole_session_diagnostics']['issues'],name)
    if kd:
        p=r['whole_session_diagnostics']['mutex_stats'];t=r['whole_session_diagnostics']['mutex_tasks']
        check('physical_drain',p['active_waiters']==p['reserved_nodes']==p['frame_failure']==t['active_tasks']==0 and p['origin_acquires']==p['origin_releases'],name)
        check('batch_ratio',eq(r['whole_session_diagnostics']['bodies_per_combiner'],p['jit_success']/p['combiner'] if p['combiner'] else None),name)
check('group_inventory',len(groups)==len(rows) and {key(g) for g in groups}==rows.keys())
for g in groups:
    selected=[r for r in rows[key(g)] if r['score_eligible']]
    check('whole_group_statistics',eq(g['whole_mops'],stats([r['observed_whole_mops'] for r in selected])),key(g))
    check('peak_group_statistics',eq(g['peak_mops'],stats([r['measured_peak_mops'] for r in selected])),key(g))
    check('group_repeats',g['valid']==len(selected) and g['repeats']==[r['repeat'] for r in selected] and g['planned']==3,key(g))
    total=sum(r['completed'] for r in selected)
    for field,source,backend in [('measured_body_entry_share','jit_bodies','kdlock'),('measured_returned_jit_share','jit_completions','kdlock'),('measured_tclock_delegation_share','tclock_delegated','tclock')]:
        val=sum(r[source] for r in selected)/total if total and g['backend']==backend and all(r[source] is not None for r in selected) else None
        check('weighted_group_share',eq(g[field],val),(key(g),field))
    check('batch_group_statistics',eq(g['whole_session_bodies_per_combiner'],stats([r['whole_session_diagnostics']['bodies_per_combiner'] for r in selected if r['whole_session_diagnostics']['bodies_per_combiner'] is not None])),key(g))

# Comparable three-repeat medians only. Observed ranges are not confidence intervals.
comparisons=[]; incomplete=[]
for g in groups:
    if g['backend']!='kdlock':continue
    if g['status']!='COMPLETE':
        incomplete.append(dict(workload=g['workload'],threads=g['threads'],jit_class=g['jit_class'],repeats=g['repeats'],whole_mops=g['whole_mops'],peak_mops=g['peak_mops']))
        continue
    for backend in ('native','tclock'):
        controls=[x for x in groups if x['workload']==g['workload'] and x['threads']==g['threads'] and x['backend']==backend]
        check('complete_control',len(controls)==1 and controls[0]['status']=='COMPLETE',(g['workload'],g['threads'],backend))
        ctl=controls[0]
        d=dict(workload=g['workload'],threads=g['threads'],jit_class=g['jit_class'],comparator=backend)
        for metric in ('whole_mops','peak_mops'):
            k,other=g[metric],ctl[metric]
            overlap=max(k['min'],other['min'])<=min(k['max'],other['max'])
            d[metric]=dict(kd=k,control=other,median_difference_pct=100*(k['median']/other['median']-1),
                observed_ranges_overlap=overlap,range_separation='overlap' if overlap else 'KD_above' if k['min']>other['max'] else 'KD_below')
        comparisons.append(d)

# Host metadata establishes policies and snapshots, not constant instantaneous frequency or perfect residency.
before,after=INPUT['host-before.json'],INPUT['host-after.json'];q0,q1=before['qemu'][0],after['qemu'][0]
check('host_cpufreq_unchanged',before['cpufreq']==after['cpufreq'])
check('host_numa_policy_unchanged',before['numa']==after['numa']=={'node0':'0-31','node1':'32-63'})
check('same_qemu',q0['pid']==q1['pid'] and q0['args']==q1['args'])
check('recovery_snapshot',before['snapshot_listed'] and after['snapshot_listed'] and before['recovery_snapshot']==after['recovery_snapshot'])
t0={t['tid']:t for t in q0['tasks']};t1={t['tid']:t for t in q1['tasks']}
check('vcpu_pins_unchanged',{k:v for k,v in t0.items() if v['comm'].startswith('CPU ')}=={k:v for k,v in t1.items() if v['comm'].startswith('CPU ')})
check('service_pins',all(t['affinity']==[63] for t in list(t0.values())+list(t1.values()) if not t['comm'].startswith('CPU ')))
residency=[]
for label,q in [('before',q0),('after',q1)]:
    found=[]
    for line in q['numa_maps'].splitlines():
        match=re.search(r'\bbind:(\d+)\b',line)
        if not match:continue
        target=int(match.group(1)); counts={int(k):int(v) for k,v in re.findall(r'\bN(\d+)=(\d+)\b',line)}
        fields={k:int(v) for k,v in re.findall(r'\b(anon|dirty|swapcache|kernelpagesize_kB)=(\d+)\b',line)}
        resident=sum(counts.values());remote=resident-counts.get(target,0)
        found.append(dict(address=line.split()[0],target_node=target,resident_pages_by_node=counts,resident_pages=resident,
            remote_resident_pages=remote,remote_resident_pct=100*remote/resident,**fields))
    check('two_bound_ram_mappings',len(found)==2 and {r['target_node'] for r in found}=={0,1},label)
    residency.append(dict(snapshot=label,mappings=found))
policy_configs={tuple(sorted({k:v for k,v in cfg.items() if k!='affected_cpus'}.items())) for cfg in before['cpufreq'].values()}
host=dict(frequency_policy_count=len(before['cpufreq']),frequency_policy_configurations=[dict(v) for v in sorted(policy_configs)],
    frequency_policy_unchanged=True,instantaneous_frequency_measured=False,vcpu_pins_unchanged=True,
    configured_nodes=before['numa'],qemu_pid=q0['pid'],recovery_snapshot=before['recovery_snapshot'],
    service_threads_before=len(t0)-64,service_threads_after=len(t1)-64,ram_residency=residency,
    limitation='Configured bind policies are stable, but both RAM mappings have nonlocal resident pages and nonzero swapcache. Snapshots do not measure active paging or per-session memory placement.')

classes={w:dict(Counter(r['jit_class'] for r in sessions if r['backend']=='kdlock' and r['workload']==w)) for w in ('c01','c08','rcuht','seek-set','seek-end','pipebytes','pipecap')}
jit_rows=[]
for g in groups:
    if g['backend'] not in ('kdlock','tclock'):continue
    selected=rows[key(g)]
    jit_rows.append(dict(workload=g['workload'],backend=g['backend'],threads=g['threads'],jit_class=g['jit_class'],repeats=g['repeats'],
        entries=[r['jit_bodies'] for r in selected],completions=[r['jit_completions'] for r in selected],
        delegated=[r['tclock_delegated'] for r in selected],entry_share=g['measured_body_entry_share'],returned_share=g['measured_returned_jit_share'],
        tclock_delegation_share=g['measured_tclock_delegation_share'],whole_session_bodies_per_combiner=g['whole_session_bodies_per_combiner']))
spread=[]
for g in groups:
    if g['status']=='COMPLETE':
        v=g['whole_mops'];spread.append(dict(workload=g['workload'],backend=g['backend'],threads=g['threads'],jit_class=g['jit_class'],
            whole_mops=v,spread_pct=100*(v['max']-v['min'])/v['median']))
spread.sort(key=lambda x:x['spread_pct'],reverse=True)
sixty=[]
for w in ('c01','c08','rcuht','seek-set','seek-end','pipebytes','pipecap'):
    r={g['backend']:g for g in groups if g['workload']==w and g['threads']==60}
    sixty.append(dict(workload=w,rates_mops={b:r[b]['whole_mops'] for b in ('native','tclock','kdlock')},jit_class=r['kdlock']['jit_class'],
        kd_entry_share=r['kdlock']['measured_body_entry_share'],kd_returned_share=r['kdlock']['measured_returned_jit_share'],
        tclock_delegation_share=r['tclock']['measured_tclock_delegation_share']))
validation=INPUT['validation.json'];health=INPUT['health.json'];matrix=INPUT['current/matrix.json']
check('comparison_validation_binding',validation['comparison_sha256']==digest(BASE/'comparison.json'))
check('health_validation_binding',health['validation_sha256']==digest(BASE/'validation.json'))
check('final_health',health['idle'] is True and not health['per_session_kernel_faults'] and len(health['kernel_logs'])==567)
check('measured_scope',matrix['plain_sessions']==567 and matrix['profile_sessions']==0 and matrix['passed'] and matrix['final_idle'])
check('elapsed_bound',matrix['elapsed_seconds']<matrix['total_timeout_seconds'])
output=dict(schema=1,passed=not issues,created_utc=datetime.now(timezone.utc).isoformat(),
    scope='Independent compact-JSON arithmetic and interpretation review on source host. No raw archives, retained helper code, binaries, tests, modules or VM commands were read/executed.',
    comparison_sha256=digest(BASE/'comparison.json'),input_sha256={name:digest(BASE/name) for name in FILES},
    review_script_sha256=digest(Path(__file__)),source_commit=c['source_commit'],total_checks=sum(checks.values()),checks=dict(checks),issues=issues,
    session_count=len(sessions),group_count=len(groups),complete_group_count=sum(g['status']=='COMPLETE' for g in groups),
    execution_status_counts=c['execution_status_counts'],kd_execution_classes_by_workload=classes,retained_no_jit_rejections=c['retained_no_jit_rejections'],
    incomplete_class_groups=incomplete,comparisons=comparisons,sixty_worker_summary=sixty,jit_and_tclock_evidence=jit_rows,
    largest_whole_run_spreads=spread[:20],host=host,measurement=matrix['measurement'],elapsed_collection_seconds=matrix['elapsed_seconds'],
    limits=['Only same-workload, same-worker complete class triplets are compared; c08/t2 is split and receives no pooled median comparison.',
        'Observed range overlap is descriptive; three repetitions do not establish confidence intervals or statistical significance.',
        'Whole-run shares do not describe the selected peak windows; synthetic entry witnesses do not prove returned bodies.',
        'The raw archive/source/peak audit is separate and was not run for this receipt.',
        'Stable ondemand policy is not fixed clock speed; RAM bind configuration is not proof of wholly local residency.',
        'The seven workload blocks were sequential and include local-execution classes; no global workload-average speedup is claimed.'])
p=BASE/'numeric-review.json'
if p.exists():raise RuntimeError('preserve earlier receipt before another review')
p.write_text(json.dumps(output,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(json.dumps(dict(passed=output['passed'],checks=output['total_checks'],issues=len(issues),comparisons=len(comparisons),receipt=str(p))))
for row in sixty:
    rates=row['rates_mops']; print(row['workload'],'60 Native/TC/KD',*[round(rates[b]['median'],6) for b in ('native','tclock','kdlock')],
        'KD shares',row['kd_entry_share'],row['kd_returned_share'],'TC',row['tclock_delegation_share'])
for backend in ('native','tclock'):
    slower=[d for d in comparisons if d['comparator']==backend and d['whole_mops']['median_difference_pct']<0]
    print('SLOWER_THAN',backend,[(d['workload'],d['threads'],round(d['whole_mops']['median_difference_pct'],2),d['whole_mops']['range_separation']) for d in slower])
print('LARGEST_SPREADS',[(r['workload'],r['backend'],r['threads'],round(r['spread_pct'],2)) for r in spread[:10]])
