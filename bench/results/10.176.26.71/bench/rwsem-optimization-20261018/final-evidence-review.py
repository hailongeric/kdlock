#!/usr/bin/env python3
"""Targeted offline review; no repository imports, tracing or benchmark execution."""
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics as stats

ROOT = Path('/home/eric/vm/vm-shared/kdlock')
WORK = Path('/tmp/kd-rwsem-opt-20261018')
ANALYSIS = WORK / 'final-analysis'
RAW = ROOT / 'bench/results/10.176.26.71/raw/bench/rwsem-optimization-20261018/receipts'
OLD = ROOT / 'bench/results/10.176.26.71/raw/bench/rwsem-delegation-20261018/evidence'
inputs = {}
checks = 0

def read(path):
    data = path.read_bytes()
    inputs[str(path)] = hashlib.sha256(data).hexdigest()
    return json.loads(data)

def check(ok, label):
    global checks
    checks += 1
    if not ok:
        raise ValueError(label)

def near(x, y):
    return math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-9)

def key(r):
    return (r['workload'], int(r['write_percent']), int(r['threads']))

def rawkey(r):
    return ('RCUHT' if r['workload'] == 'rcuht' else 'c%02d' % r['cachelines'], r['write_percent'], r['threads'])

a = read(ANALYSIS / 'analysis.json')
records = {
    'before': read(OLD / 'records.json'),
    'after': read(RAW / 'main/final-grid/records.json'),
    'reference': read(RAW / 'reference/final-reference/records.json'),
}
for label, name, base in [('before', 'baseline-grid', OLD), ('after', 'final-grid', RAW/'main/final-grid'), ('reference', 'final-reference', RAW/'reference/final-reference')]:
    run = a['runs'][name]
    for f, expected in run['input_sha256'].items():
        read(base / f)
        check(inputs[str(base/f)] == expected, f'{name} {f} raw hash')
    source = read(base/'source-sha256.json')
    canonical = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    check(canonical == run['source_id'], f'{name} canonical source identity')
    check(len(records[label]) == run['valid_sessions'], f'{name} coverage')
    check(all(r['drained'] and r['execution_status'] == 'OK' and r['measurement']['complete'] and r['measurement']['data_ok'] for r in records[label]), f'{name} drain/data completion')

for filename, expected in [('points.csv', a['points']), ('sixty-workers.csv', [r for r in a['points'] if r['threads']==60]), ('rwlock-reference.csv', a['references'])]:
    path = ANALYSIS/filename
    data = path.read_bytes()
    inputs[str(path)] = hashlib.sha256(data).hexdigest()
    check(b'\r' not in data, filename+' LF')
    rows = list(csv.DictReader(data.decode().splitlines()))
    check(len(rows) == len(expected), filename+' coverage')
    expected = {key(r): r for r in expected}
    for row in rows:
        origin = expected[key(row)]
        for k, v in row.items():
            val = origin[k]
            check((v == '' if val is None else near(float(v), val) if isinstance(val, (int, float)) else v == val), filename+' '+str(key(row))+' '+k)

def series(label, point, arm):
    return sorted((r for r in records[label] if rawkey(r)==key(point) and r['arm']==arm), key=lambda r:r['repeat'])

def verify_group(label, point, arm, prefix):
    ss = series(label, point, arm)
    check(len(ss)==3, 'three repetitions')
    if len({r['jit_status'] for r in ss}) != 1:
        check(point.get(prefix+'_whole_median_ops_s') is None, 'split group suppressed')
        return
    whole = [r['measurement']['completed']*1e9/r['measurement']['wall_ns'] for r in ss]
    peak = [r['measurement']['peak']['completed']*1e9/r['measurement']['peak']['elapsed_ns'] for r in ss]
    for field, value in [('whole_min_ops_s', min(whole)), ('whole_median_ops_s', stats.median(whole)), ('whole_max_ops_s', max(whole)), ('best_peak_ops_s', max(peak))]:
        check(near(point[prefix+'_'+field], value), f'{label} {key(point)} {arm} {field}')

target_points = [r for r in a['points'] if r['threads']==60 or r['kd_after_before_status']=='FAIL' or r['after_kd_native_status']=='FAIL']
for point in target_points:
    for label in ['before', 'after']:
        for arm in ['kdlock', 'native']:
            verify_group(label, point, arm, label+'_'+arm)
for point in a['references']:
    for arm in ['kdlock', 'tclock', 'native']:
        verify_group('reference', point, arm, arm)

before = a['runs']['baseline-grid']
after = a['runs']['final-grid']
check({k:v for k,v in before['environment'].items() if k!='argv'} == {k:v for k,v in after['environment'].items() if k!='argv'}, 'kernel boot topology runtime equality')
changed = [p for p in before['source_sha256'] if before['source_sha256'][p] != after['source_sha256'].get(p)]
check(changed == ['include/kd_rwsem.h', 'kernel_module/kd_rwsem.c'], 'only two rwsem source changes')

regressions = []
for comparison in ['kd_after_before', 'after_kd_native']:
    for r in a['points']:
        if r[comparison+'_status'] != 'FAIL':
            continue
        regressions.append({k:r[k] for k in ['workload','write_percent','threads','before_kdlock_groups','after_kdlock_groups']} | {'comparison': comparison, 'whole_ratio': r[comparison+'_whole_ratio'], 'peak_ratio': r[comparison+'_peak_ratio'], 'whole_loss_percent': (1-r[comparison+'_whole_ratio'])*100, 'peak_loss_percent': (1-r[comparison+'_peak_ratio'])*100})

low = []
for r in a['points']:
    if r['workload'] not in ['c01','c08'] or r['write_percent']!=20 or r['threads'] not in [2,3,4]:
        continue
    point = {k:r[k] for k in ['workload','write_percent','threads','kd_after_before_whole_ratio','kd_after_before_peak_ratio','native_after_before_whole_ratio','native_after_before_peak_ratio']}
    for label in ['before','after']:
        for arm in ['kdlock','native']:
            ss = series(label,r,arm)
            values=[]
            for s in ss:
                m=s['measurement']; workers=m['workers']; pk=m['peak']; counts=[w['completed'] for w in workers]
                fairness=[]; zero=0
                for l,h in zip(m['samples'],m['samples'][1:]):
                    if l['started_ns']<pk['eligible_started_ns'] or h['finished_ns']>pk['active_finished_ns']:
                        continue
                    d=[y-x for x,y in zip(l['completed'],h['completed'])]
                    if sum(d):
                        fairness.append(sum(d)**2/(len(d)*sum(x*x for x in d)))
                        zero += any(x==0 for x in d)
                values.append({'repeat':s['repeat'],'jit_status':s['jit_status'],'whole_ops_s':s['whole_ops_s'],'peak_ops_s':s['peak_ops_s'],'worker_completed':counts,'worker_cpu_seconds':[w['cpu_ns']/1e9 for w in workers],'worker_cpu_ns_per_op':sum(w['cpu_ns'] for w in workers)/m['completed'],'peak_worker_share':[x/sum(pk['worker_completed']) for x in pk['worker_completed']],'eligible_10ms_intervals':len(fairness),'intervals_with_any_worker_zero':zero,'interval_jain_fairness_median':stats.median(fairness)})
            point[label+'_'+arm]={'sessions':values,'whole_median_ops_s':stats.median(s['whole_ops_s'] for s in ss),'whole_min_ops_s':min(s['whole_ops_s'] for s in ss),'whole_max_ops_s':max(s['whole_ops_s'] for s in ss),'best_peak_ops_s':max(s['peak_ops_s'] for s in ss),'worker_cpu_ns_per_op_median':stats.median(s['worker_cpu_ns_per_op'] for s in values)}
    low.append(point)

references=[]
for r in a['references']:
    row=dict(r)
    row['kd_tclock_whole_ratio']=r['kdlock_whole_median_ops_s']/r['tclock_whole_median_ops_s']
    row['kd_tclock_peak_ratio']=r['kdlock_best_peak_ops_s']/r['tclock_best_peak_ops_s']
    row['kd_tclock_status']='PASS' if row['kd_tclock_whole_ratio']>=1 and row['kd_tclock_peak_ratio']>=1 else 'FAIL'
    references.append(row)

profiles={}
for name, source_hash in [('baseline-profile',before['input_sha256']['source-sha256.json']),('final-profile',after['input_sha256']['source-sha256.json'])]:
    root=RAW/'profiles'/name
    meta=read(root/'diagnostic.json'); result=read(root/'result.json'); controls=read(root/'controls-final.json'); summary=read(root/'function-count-summary.json'); observations=read(root/'function-observations.json'); sessions=read(root/'rwsem/records.json'); read(root/'rwsem/source-sha256.json')
    check(inputs[str(root/'rwsem/source-sha256.json')]==source_hash, name+' source')
    check(result['completed'] and result['tracing_restored'] and result['guest_idle'] and not result['score_eligible'], name+' restored non-scoring')
    for s in summary:
        vals=[o['hits']/o['completed'] for o in observations if o['backend']==s['backend'] and o['function']==s['function'] and o['jit_status']==s['jit_status']]
        check(len(vals)==s['repetitions'] and near(stats.median(vals),s['median_hits_per_completed_op']), name+' '+s['function']+' count aggregation')
    profiles[name]={'metadata':meta,'result':result,'controls_final':controls,'source_manifest_sha256':source_hash,'jit_status_counts':dict(collections.Counter(s['jit_status'] for s in sessions)),'jit_completions':sum(s['jit_completions'] for s in sessions),'function_counts':summary}

review={'schema':1,'status':'PASS','checks':checks,'scope':'Targeted raw recomputation of 60-worker rows, every regression, and every reference point; CSV/JSON consistency; source identities; low-count worker progress/CPU observations; profile aggregation. No runtime work or full-analysis rerun.','inputs_sha256':inputs,'counts':{n:{'sessions':r['valid_sessions'],'expected':r['expected_sessions'],'jit_status_counts':r['kd_jit_status_counts'],'jit_completions':sum(s['jit_completions'] for s in r['sessions'])} for n,r in a['runs'].items()},'source_identity':{'before':before['source_id'],'after':after['source_id'],'before_raw_manifest_sha256':before['input_sha256']['source-sha256.json'],'after_raw_manifest_sha256':after['input_sha256']['source-sha256.json'],'changed_paths':changed,'environment_equal_except_argv':True},'comparison_counts':{c:dict(collections.Counter(r[c+'_status'] for r in a['points'])) for c in ['kd_after_before','after_kd_native','native_after_before']},'sixty_workers':[r for r in a['points'] if r['threads']==60],'regressions':regressions,'low_count_detail':low,'reference_counts':{c:dict(collections.Counter(r[c+'_status'] for r in references)) for c in ['kd_tclock','kd_native','tclock_native']},'references':references,'profiles':profiles}
(WORK/'final-evidence-review.json').write_text(json.dumps(review,indent=2,sort_keys=True)+'\n')

lines=['# Targeted final evidence review','',f'PASS: {checks} offline checks. Final rwsem: 756/756 valid sessions, 126 points; reference: 270/270, 30 points. Raw rates, the CSVs and analysis JSON agree for all 60-worker cases, all regression cases and all spinning-rwlock references. All measured sessions drained and passed data checks. No benchmark was rerun.','', 'Baseline/final environments match except command-line ordering/output. The 233-entry source manifests differ only in `include/kd_rwsem.h` and `kernel_module/kd_rwsem.c`; the KD mutex and runner hashes match. Final KD rwsem has 155 PASS and 223 NO_JIT sessions, with 7,275,620 completed JIT bodies. Mixed final statuses at c01 write20 workers 5/6/7 and old c08 write20 workers16 are excluded from the affected homogeneous comparisons.','', '## Sixty-worker sleeping rwsem','', 'Mops/s; whole is the three-run median, peak is the maximum observed warmed window.','', '| Case | Writes | Before KD whole / peak | Final KD whole / peak | Final Native whole / peak | KD before ratio whole / peak | KD Native ratio whole / peak |','| --- | --- | --- | --- | --- | --- | --- |']
for r in review['sixty_workers']:
    def rates(p):return f"{r[p+'_whole_median_ops_s']/1e6:.6f} / {r[p+'_best_peak_ops_s']/1e6:.6f}"
    lines.append(f"| {r['workload']} | {r['write_percent']}% | {rates('before_kdlock')} | {rates('after_kdlock')} | {rates('after_native')} | {r['kd_after_before_whole_ratio']:.4f} / {r['kd_after_before_peak_ratio']:.4f} | {r['after_kd_native_whole_ratio']:.4f} / {r['after_kd_native_peak_ratio']:.4f} |")
lines += ['', '## Low-count regression detail','', 'All 12 before/after comparison failures occur at 1–5 workers. Ten are at least 5% worse on one metric; the single-worker c01 differences are −1.79% whole/−0.10% peak (1% writes) and +0.13% whole/−0.03% peak (20% writes). The worst case is c08, 20% writes, two workers: −72.45% whole and −72.96% peak. These are descriptive differences, not significance tests.','', '| Case | Workers | Before KD whole [min,max] | Final KD whole [min,max] | CPU ns/op before → final | Native whole before → final |','| --- | --- | --- | --- | --- | --- |']
for r in low:
    b=r['before_kdlock'];f=r['after_kdlock'];bn=r['before_native'];fn=r['after_native']
    def spread(v):return f"{v['whole_median_ops_s']/1e6:.3f} [{v['whole_min_ops_s']/1e6:.3f},{v['whole_max_ops_s']/1e6:.3f}]"
    lines.append(f"| {r['workload']} w20 | {r['threads']} | {spread(b)} | {spread(f)} | {b['worker_cpu_ns_per_op_median']:.1f} → {f['worker_cpu_ns_per_op_median']:.1f} | {bn['whole_median_ops_s']/1e6:.3f} → {fn['whole_median_ops_s']/1e6:.3f} |")
lines += ['', 'At two/three workers, every KD repetition is NO_JIT before and after. All new warmed peaks are below all old warmed peaks. Old workers consume roughly 1.2–1.5 CPU-seconds each per two-second session; final workers consume nearly 2.0 each. The old samples are somewhat less balanced, but every worker progresses in every eligible 10ms interval. Median per-interval Jain fairness is 0.958–0.999 before and 0.998–1.000 after. A stalled worker does not explain the old score at that resolution.','', 'The source change replaces immediate wait-event fallback with up to 16,384 predicate probes before sleeping, alongside split queues and cacheline separation. The timing/CPU evidence is consistent with more simultaneous busy contention at low counts. Baseline blocking may reduce simultaneous contention and permit inexpensive bursts, but no low-count scheduler trace was captured: sleeping versus other scheduling effects and sub-10ms burst patterns cannot be isolated. The 60-worker function profiles cannot establish a low-count cause.','', 'The six final/Native comparison failures are c01 w20 t1/t36, c08 w1 t2, c08 w20 t1/t36, and RCUHT w20 t1. Exact ratios and both metrics are retained in JSON.','', '## Separate spinning-rwlock reference','', 'KD/TCLock wins both metrics at 28/30 points; exceptions: c08 w20 t1 (0.99147 whole, 0.99181 peak) and RCUHT w1 t60 (0.95930 whole, 0.95804 peak). KD/Native wins both at 29/30, with c08 w20 t1 at 0.95317 whole/0.93843 peak. TCLock/Native wins both at 15/30. All reference groups have three homogeneous repetitions. TCLock delegation remains UNMEASURED; its NATIVE JIT label is not proof of local execution. These are rwlock references, not rwsem parity.','', '| Case | Writes | Native whole / peak | TCLock whole / peak | KD whole / peak | KD/TCLock whole / peak | KD/Native whole / peak |','| --- | --- | --- | --- | --- | --- | --- |']
for r in references:
    if r['threads']!=60:continue
    def rates(p):return f"{r[p+'_whole_median_ops_s']/1e6:.6f} / {r[p+'_best_peak_ops_s']/1e6:.6f}"
    lines.append(f"| {r['workload']} | {r['write_percent']}% | {rates('native')} | {rates('tclock')} | {rates('kdlock')} | {r['kd_tclock_whole_ratio']:.4f} / {r['kd_tclock_peak_ratio']:.4f} | {r['kd_native_whole_ratio']:.4f} / {r['kd_native_peak_ratio']:.4f} |")
lines += ['', '## Diagnostic scope and counts','', 'Each profile runs c01/write20/60 workers, Native and KD, three repetitions, with the same profiler-script SHA256 and kernel config. Source manifest hashes match the before/final performance sources respectively. Tracing restoration and guest idle are recorded. Baseline KD profiles are NO_JIT3; final KD profiles are PASS3, so this compares changed source plus observed execution behavior, not an isolated queue-only effect. Instrumentation covers all CPUs/tasks during measure, including client startup and publication/counter reads, while excluding preparation/warmup/cleanup. It includes background work and changes execution cost; rates and inclusive nested function times are not scored.','', '| Function | KD calls/op before → final | Native calls/op before → final |','| --- | --- | --- |']
for function in ['schedule','try_to_wake_up','_raw_spin_lock_irqsave','native_queued_spin_lock_slowpath','prepare_to_wait_event','autoremove_wake_function','kd_up_read']:
    vals={}
    for n,p in profiles.items():
        for row in p['function_counts']:
            if row['function']==function:vals[(n,row['backend'])]=row['median_hits_per_completed_op']
    def fmt(arm):
        v=[vals.get((n,arm)) for n in ['baseline-profile','final-profile']]
        return '—' if None in v else f'{v[0]:.6f} → {v[1]:.6f}'
    lines.append(f'| {function} | {fmt("kdlock")} | {fmt("native")} |')
lines += ['', 'KD `kd_up_read` rises from 0.804 to 2.227 calls/op despite ~0.8 reads/op. The function is also called to roll back a raced reader admission; these counts must not be interpreted as completed read unlocks alone. The reduction in waitqueue/scheduler calls supports avoiding frequent sleeps at high contention, without establishing exclusive CPU costs or ownership.','', 'Full exact worker counts, CPU times, status groups, reference ratios, source IDs, profile counts and input hashes are in `final-evidence-review.json`.']
(WORK/'final-evidence-review.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'status':'PASS','checks':checks,'json':str(WORK/'final-evidence-review.json'),'markdown':str(WORK/'final-evidence-review.md')}))
