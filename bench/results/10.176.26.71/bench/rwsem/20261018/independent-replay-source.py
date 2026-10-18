"""Independent offline arithmetic replay; does not import repository programs."""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import math
import re
import statistics
import tarfile

archive_path = Path('bench/results/10.176.26.71/raw/bench/rwsem-delegation-20261018/guest-evidence.tar.gz')
root = 'rwsem-delegation-grid-20261018/'
targets = {root + n for n in ('plan.json', 'records.json', 'summary.json', 'parity.json')}
objects, logs = {}, {}
with tarfile.open(archive_path, 'r|gz') as archive:
    for member in archive:
        if not member.isfile():
            continue
        if member.name in targets:
            objects[member.name[len(root):]] = json.load(archive.extractfile(member))
        elif member.name.startswith(root) and member.name.endswith('/kernel.log'):
            logs[member.name[len(root):].split('/')[0]] = archive.extractfile(member).read().decode()
plan, records, summary, parity = (objects[n] for n in ('plan.json', 'records.json', 'summary.json', 'parity.json'))
checks = Counter()
failures = []
def check(ok, label):
    checks[label] += 1
    if not ok:
        failures.append(label)
def equal(actual, expected, label):
    check(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9) if isinstance(expected, float)
          else actual == expected, label)
def median(values):
    ordered = sorted(values)
    n = len(ordered)
    return ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2

grids = [*range(1, 9), *range(12, 61, 4)]
check(len(plan) == len(records) == 756, '756 planned and present')
check({r['threads'] for r in records} == set(grids), 'standard worker grid')
check(len({r['name'] for r in records}) == len(records), 'unique session names')
check([r['name'] for r in records] == [r['name'] for r in plan], 'planned order and identities')
groups = defaultdict(list)
totals = Counter()
for row in records:
    name, m = row['name'], row['measurement']
    check(row['execution_status'] == 'OK' and row['drained'] and m['data_ok'] and m['complete'], 'successful correct drained session')
    check(m['wall_ns'] == m['finished_ns'] - m['started_ns'] > 0, 'whole interval')
    check(len(m['workers']) == row['threads'], 'worker count')
    for i, worker in enumerate(m['workers']):
        check(worker['reads'] + worker['writes'] == worker['completed'], 'worker total')
        check(worker['writes'] == (worker['completed'] * row['write_percent'] + (17 * i) % 100) // 100, 'exact deterministic write mix')
        check(worker['completed'] > 0 and worker['completed'] % 256 == 0 and not worker['error'] and worker['read_errors'] == 0, 'worker progress and errors')
        check(worker['cpu'] == worker['observed_cpu'] == row['cpus'][i], 'worker affinity')
    for key in ('completed', 'reads', 'writes'):
        equal(m[key], sum(w[key] for w in m['workers']), 'aggregate ' + key)
        totals[key] += m[key]
    delta = [a-b for a,b in zip(m['after']['values'], m['before']['values'])]
    if row['workload'] == 'cacheline':
        check(delta == [m['writes']] * row['cachelines'] + [0] * (16-row['cachelines']), 'cacheline protected effects')
    else:
        check(delta[0] == m['writes'] == sum(delta[1:4]) and all(x >= 0 for x in delta[:4]) and delta[4:] == [0]*12, 'hash protected effects')
    for state in (m['before'], m['after']):
        check(all(state[k] == 0 for k in ('active','cnts','gate')), 'payload quiescence')
    check(row['jit_bodies'] == row['jit_after'] - row['jit_before'], 'entry counter delta')
    check(row['jit_completions'] == row['jit_complete_after'] - row['jit_complete_before'], 'completion counter delta')
    check(0 <= row['jit_completions'] <= row['jit_bodies'] <= m['writes'], 'JIT body bounds')
    totals['jit_entries'] += row['jit_bodies']; totals['jit_completions'] += row['jit_completions']
    # Independent peak reconstruction using conservative timestamp brackets and
    # binary search for the earliest eligible endpoint, not repository helpers.
    eligible = [(i,s) for i,s in enumerate(m['samples'])
                if s['started_ns'] >= max(w['active_started_ns'] for w in m['workers']) + m['peak_settle_ns']
                and s['finished_ns'] <= min(m['deadline_ns'], *(w['kernel_finished_ns'] for w in m['workers']))]
    best = None
    windows = 0
    for pos,(i,first) in enumerate(eligible):
        lo,hi = pos+1,len(eligible)
        while lo < hi:
            mid = (lo+hi)//2
            if eligible[mid][1]['finished_ns'] - first['started_ns'] < m['peak_window_ns']:
                lo = mid+1
            else:
                hi = mid
        if lo == len(eligible):
            continue
        j,last = eligible[lo]
        elapsed = last['finished_ns'] - first['started_ns']
        changes = [b-a for a,b in zip(first['completed'],last['completed'])]
        windows += 1
        if min(changes) <= 0:
            continue
        operations = sum(changes)
        if best is None or operations * best['elapsed'] > best['operations'] * elapsed:
            best = {'i':i,'j':j,'elapsed':elapsed,'operations':operations,'changes':changes,
                    'writes':sum(((17*k)%100 + b*row['write_percent'])//100 - ((17*k)%100 + a*row['write_percent'])//100
                                 for k,(a,b) in enumerate(zip(first['completed'],last['completed'])))}
    check(best is not None, 'full-cohort peak exists')
    p = m['peak']
    for key,value in {'start_sample_index':best['i'],'end_sample_index':best['j'],
                      'elapsed_ns':best['elapsed'],'completed':best['operations'],
                      'worker_completed':best['changes'],'writes':best['writes'],
                      'reads':best['operations']-best['writes'],'candidate_windows':windows,
                      'eligible_samples':len(eligible)}.items():
        equal(p[key], value, 'peak ' + key)
    whole, peak = m['completed'] * 1e9 / m['wall_ns'], best['operations'] * 1e9 / best['elapsed']
    equal(row['whole_ops_s'], whole, 'whole throughput')
    equal(row['peak_ops_s'], peak, 'peak throughput')
    equal(p['throughput_ops_s'], peak, 'peak nested throughput')
    for kind in ('reads','writes'):
        equal(row['read_ops_s' if kind=='reads' else 'write_ops_s'], m[kind] * 1e9 / m['wall_ns'], 'whole ' + kind + ' rate')
    groups[(row['variant'],row['write_percent'],row['threads'],row['jit_status'])].append((row,whole,peak))
check(len(groups) == len(summary), 'summary group count')
for saved in summary:
    key = tuple(saved[k] for k in ('variant','write_percent','threads','jit_status'))
    rows = groups[key]; whole=[r[1] for r in rows]; peaks=[r[2] for r in rows]
    expected = {'valid_rounds':len(rows),'expected_rounds':3,'complete':len(rows)==3,
                'best_peak_ops_s':max(peaks),'peak_min_ops_s':min(peaks),'peak_median_ops_s':median(peaks),
                'peak_max_ops_s':max(peaks),'peak_spread_pct':(max(peaks)-min(peaks))*100/min(peaks),
                'whole_min_ops_s':min(whole),'whole_median_ops_s':median(whole),'whole_max_ops_s':max(whole),
                'whole_spread_pct':(max(whole)-min(whole))*100/min(whole),'samples':[r[0]['name'] for r in rows]}
    for key,value in expected.items():equal(saved[key],value,'summary '+key)
points = defaultdict(lambda:defaultdict(list))
for saved in summary:
    example = groups[tuple(saved[k] for k in ('variant','write_percent','threads','jit_status'))][0][0]
    points[(example['workload'],example['cachelines'],example['write_percent'],example['threads'])][example['arm']].append(saved)
parity_statuses=Counter(); selected=[]; split=[]
for saved in parity['points']:
    key=tuple(saved[k] for k in ('workload','cachelines','write_percent','threads'))
    arms=points[key]
    comparable=set(arms)=={'native','kdlock'} and all(len(v)==1 and v[0]['complete'] and v[0]['valid_rounds']==3 for v in arms.values())
    if comparable:
        native,kd=arms['native'][0],arms['kdlock'][0]
        ratios={'best_peak':kd['best_peak_ops_s']/native['best_peak_ops_s'],
                'median_whole':kd['whole_median_ops_s']/native['whole_median_ops_s']}
        status='PASS' if min(ratios.values())>=1 else 'FAIL'
        for label,ratio in ratios.items():equal(saved['ratios']['native'][label],ratio,'parity '+label)
        item=dict(workload=key[0],cachelines=key[1],write_percent=key[2],threads=key[3],
                  kd_jit_status=kd['jit_status'],native_median_Mops=native['whole_median_ops_s']/1e6,
                  kd_median_Mops=kd['whole_median_ops_s']/1e6,ratios=ratios,status=status)
        if key[3]==60:selected.append(item)
    else:
        status='INCOMPLETE'
        split.append(dict(workload=key[0],cachelines=key[1],write_percent=key[2],threads=key[3],
                          valid_sessions=sum(g['valid_rounds'] for v in arms.values() for g in v),
                          groups={arm:[{'jit_status':g['jit_status'],'rounds':g['valid_rounds'],'samples':g['samples'],
                                       'whole_median_Mops':g['whole_median_ops_s']/1e6} for g in gs] for arm,gs in arms.items()}))
    equal(saved['status'],status,'parity point status');parity_statuses[status]+=1
check(len(points)==len(parity['points'])==126,'parity point count')
equal(parity['status'],'FAIL' if parity_statuses['FAIL'] else 'PASS' if not parity_statuses['INCOMPLETE'] else 'INCOMPLETE','overall parity')

def heat(name):
    text=logs.get(name,''); cpus=[];locks=[]
    for line in text.splitlines():
        if 'kd_hotlock mutex ratio:' in line:
            cpus.append({k:int(v) for k,v in re.findall(r'(cpu|entries|contentions|last_entries|checks|cpu_hot)=(\d+)',line)})
        if 'kd_hotlock final:' in line and 'type=mutex' in line:
            locks.append({k:int(v) for k,v in re.findall(r'(cpu|count|cpu_hot|lock_hot)=(\d+)',line)})
    stats=[line.split('kd_mutex stats:',1)[1].strip() for line in text.splitlines() if 'kd_mutex stats:' in line]
    def span(rows,key):return [min(r[key] for r in rows),max(r[key] for r in rows)] if rows else None
    return {'reported_cpus':len(cpus),'cpu_hot_count':sum(r['cpu_hot'] for r in cpus),
            'cpu_checks_range':span(cpus,'checks'),'residual_contentions_range':span(cpus,'contentions'),
            'last_entries_range':span(cpus,'last_entries'),'reported_locks':len(locks),
            'lock_hot_count':sum(r['lock_hot'] for r in locks),'lock_sample_count_range':span(locks,'count'),
            'mutex_stats':stats[-1] if stats else None}
positive=[];at60=[]
for r in records:
    if r['arm']!='kdlock':continue
    if r['jit_completions'] or r['threads']==60:
        item={k:r[k] for k in ('name','workload','cachelines','write_percent','threads','repeat','jit_status','jit_bodies','jit_completions')}
        item['writes']=r['measurement']['writes'];item['heat']=heat(r['name'])
        if r['jit_completions']:positive.append(item)
        if r['threads']==60:at60.append(item)
report={'schema':1,'static_offline_only':True,'repository_programs_imported_or_executed':False,
        'archive':str(archive_path),'archive_sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        'source':'Frozen archive records, samples, summary, parity, plan and kernel logs; no guest access.',
        'passed':not failures,'checks':dict(checks),'failure_count':len(failures),'failures':failures[:20],
        'sessions':len(records),'per_arm':dict(Counter(r['arm'] for r in records)),
        'execution_statuses':dict(Counter(r['execution_status'] for r in records)),
        'jit_groups':dict(Counter(r['arm']+':'+r['jit_status'] for r in records)),
        'totals':dict(totals),'replayed_summary_groups':len(summary),'replayed_points':len(points),
        'parity_statuses':dict(parity_statuses),'split_points':split,'sixty_worker_results':selected,
        'timed_jit_positive_sessions':positive,'sixty_worker_heat_snapshots':at60,
        'scope_limits':['Runtime correctness flags and recorded payload effects were checked; this is not a new execution.',
                        'Post-work checksum and complete hash-table structure are not independently re-executed.',
                        'Heat logs are final cumulative/unfinished-window diagnostics and do not time-localize admission within measurement.',
                        'Mixed JIT statuses are never pooled into three-repetition point medians.']}
out=Path('/tmp/kd-rwsem-delegation-20261018');(out/'independent-replay.json').write_text(json.dumps(report,indent=2)+'\n')
lines=['# Independent offline replay','',f"Replayed all {len(records)} sessions, {len(summary)} execution-status summary groups and {len(points)} comparison points from the saved archive. All arithmetic and identity checks passed: {not failures}. No repository runner or test program was executed.",'',
       f"Parity counts: {dict(parity_statuses)}. The incomplete point has six valid sessions; it is split by KD JIT status, not skipped.",'',
       '## Timed returned-JIT sessions','', '| Case | Completed / writes | Final CPU-hot / reported | Final lock-hot / reported | CPU checks | Lock residual samples |', '| --- | ---: | ---: | ---: | --- | --- |']
for r in positive:
 h=r['heat'];lines.append(f"| {r['name']} | {r['jit_completions']} / {r['writes']} | {h['cpu_hot_count']} / {h['reported_cpus']} | {h['lock_hot_count']} / {h['reported_locks']} | {h['cpu_checks_range']} | {h['lock_sample_count_range']} |")
lines += ['', 'These are measured entry/completion deltas, not warmup totals. Final heat records support the presence of admitted hot locks but do not identify when each CPU became hot or bound how much delegation occurred in a selected peak window.', '', '## Sixty-worker outcomes', '', '| Case | Native median Mops/s | KD median Mops/s | KD/Native whole | KD/Native best peak | Status |', '| --- | ---: | ---: | ---: | ---: | --- |']
for r in selected:
 label=f"{r['workload']}-c{r['cachelines']:02d}, writes {r['write_percent']}%"
 lines.append(f"| {label} | {r['native_median_Mops']:.6f} | {r['kd_median_Mops']:.6f} | {r['ratios']['median_whole']:.6f} | {r['ratios']['best_peak']:.6f} | {r['kd_jit_status']}; {r['status']} |")
lines += ['', '| KD 60-worker session | CPU-hot / reported | CPU checks | Lock-hot / reported | Lock residual samples |', '| --- | ---: | --- | ---: | --- |']
for r in at60:
 h=r['heat'];lines.append(f"| {r['name']} | {h['cpu_hot_count']} / {h['reported_cpus']} | {h['cpu_checks_range']} | {h['lock_hot_count']} / {h['reported_locks']} | {h['lock_sample_count_range']} |")
lines += ['', 'The unchanged mutex policy first evaluates CPU heat after 1,024 contention samples and uses `(entries >> 10) < 256` plus its existing CPU time bound. Once a CPU is hot, a lock needs 1,025 records within its existing lock time bound. Promotion/reset can restart per-lock samples. Final `contentions` and lock `count` fields are residual sampling windows, not lifetime contention totals. Low end-of-run residuals alone cannot prove that a lock was never hot; interpret them together with check counts, hot flags and actual measured JIT completions.', '', 'The rwsem admission layer can block writers before the mutex acquisition; those waits do not themselves count as mutex contention samples. This is a source-level explanation of why overall rwsem contention need not imply mutex heat, not a measured attribution of every slow operation.', '', 'No policy change or performance claim is inferred from the diagnostics. The acceptance runs at 80%/100% writes remain separate from this 1%/20% timed matrix.']
(out/'diagnostics.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'passed':not failures,'failures':failures[:10],'sessions':len(records),'groups':len(summary),'points':len(points),'parity':dict(parity_statuses),'totals':dict(totals),'split':split,'at60':selected,'positive':[(r['name'],r['jit_completions']) for r in positive]},indent=2))
