#!/usr/bin/env python3
"""Audit and summarize this frozen 21-point microbenchmark round."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics

THREADS=[*range(1,9),*range(12,61,4)]
ARMS=('native','tclock','kdlock')
LABELS=dict(native='Linux Native',tclock='TCLock',kdlock='KDLock')

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def load(p):
    return json.loads(p.read_text())

def write(p,x):
    p.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')

def csv_write(p,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with p.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in row.items()})

def peak_check(row):
    m=row['measurement']
    start=max(w['active_started_ns'] for w in m['workers'])+m['peak_settle_ns']
    end=min(m['deadline_ns'],*(w['kernel_finished_ns'] for w in m['workers']))
    eligible=[s for s in m['samples'] if s['started_ns']>=start and s['finished_ns']<=end]
    best=None
    for index,first in enumerate(eligible):
        for last in eligible[index+1:]:
            elapsed=last['finished_ns']-first['started_ns']
            if elapsed<m['peak_window_ns']: continue
            deltas=[b-a for a,b in zip(first['completed'],last['completed'])]
            if min(deltas)>0 and (best is None or sum(deltas)*best[1]>best[0]*elapsed):
                best=(sum(deltas),elapsed)
            break
    assert best and math.isclose(best[0]*1e9/best[1],m['peak']['throughput_ops_s'],rel_tol=1e-12),row['name']

def aggregate(key,rows):
    group,percent,threads,arm=key
    good=[r for r in rows if r['accepted']]
    result=dict(group=group,write_percent=percent,threads=threads,arm=arm,
        planned=len(rows),accepted=len(good),complete=len(good)==3,
        jit_rounds=sum(r['jit_bodies']>0 for r in good),
        execution_types=sorted({r['execution_type'] for r in good}))
    for metric in ('peak','whole'):
        values=[r[metric+'_ops_s'] for r in good]
        for label,fn in [('min',min),('median',statistics.median),('max',max)]:
            result[f'{metric}_{label}_ops_s']=fn(values) if values else None
        result[metric+'_spread_pct']=100*(max(values)-min(values))/statistics.median(values) if values else None
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--raw',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--plots',action='store_true')
    args=p.parse_args(); root=args.raw.resolve(); out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    plan=load(root/'matrix-plan.json'); status=load(root/'matrix-status.json')
    assert status['threads']==THREADS and status['collector_cpu']==63
    assert status['worker_cpus']==list(range(60))
    assert len(plan)==11 and len({g['name'] for g in plan})==11
    assert sum(g['expected_sessions'] for g in plan)==status['expected_sessions']==2079
    approved=load(root/'control/source-sha256.json')
    for name,h in approved.items(): assert digest(root/'source'/name)==h,name
    samples=[]; workers=[]; nodes=[]; coverage=[]; counts=Counter()
    for group in plan:
        folder=root/group['name']
        if not (folder/'records.json').exists():
            coverage.append(dict(group=group['name'],planned=group['expected_sessions'],executed=0,accepted=0,status='NOT_RUN'))
            continue
        records=load(folder/'records.json'); specs=load(folder/'plan.json')
        assert len(records)==len(specs)==group['expected_sessions'],group['name']
        assert {r['name'] for r in records}=={r['name'] for r in specs}
        mixes=([1,20] if group['family']=='synthetic' and group['lock_kind']=='rwlock' else [None])
        expected={(p,t,a,n) for p in mixes for t in THREADS for a in group['backends'] for n in range(3)}
        actual={(r.get('write_percent'),r['threads'],r['arm'],r['repeat']) for r in records}
        assert len(records)==len(expected) and actual==expected,group['name']
        for name,h in load(folder/'source-sha256.json').items():
            assert digest(folder/'source'/name)==h,name
            if name in approved: assert approved[name]==h,name
            counts['source_hashes']+=1
        if group['family']=='api':
            binaries={str(folder/'build'/name):item['sha256'] for name,item in load(folder/'binaries.json').items()}
            for name,h in load(folder/'kernel-inputs-sha256.json').items():
                assert digest(folder/'kernel-inputs'/name)==h,name
                counts['kernel_input_hashes']+=1
        else:
            binaries={}
            for original,h in load(folder/'binary-sha256.json').items():
                _,marker,relative=original.partition('/'+group['name']+'/')
                dest=folder/relative if marker else folder/'binaries'/Path(original).name
                binaries[str(dest)]=h
        for name,h in binaries.items(): assert digest(Path(name))==h,name
        counts['binary_hashes']+=len(binaries)
        used=0
        for r in records:
            executed=r.get('execution_status')!='NOT_RUN'
            m=r.get('measurement',{})
            valid_measurement=(r.get('execution_status') in ('OK','NO_JIT') and r.get('drained') is True and
                (m.get('ok') is True if group['family']=='api' else m.get('data_ok') is True and m.get('complete') is True))
            accepted=valid_measurement and r.get('execution_status')=='OK'
            if executed: counts['executed']+=1
            if r.get('drained'): counts['drained']+=1
            assert r['threads'] in THREADS and r['cpus']==list(range(r['threads'])) and r['collector_cpu']==63
            assert r['arm'] in group['backends'] and r['repeat'] in range(3)
            assert r['lock_kind']==group['lock_kind'] and r['duration_ms']==2000
            if group['family']=='synthetic':
                assert r['workload']==group['workload'] and r['cachelines']==group['cachelines']
                assert r['post_work_rounds']==(4 if group['lock_kind']=='rwlock' else 64)
                assert r['warmup_iterations_per_worker']==48000
            else:
                assert r['kind']==group['workload'] and r['query']==group['query']
                assert r['entries']==group['entries'] and r['value_size']==64
                assert r['warmup']==48000 and r['warmup_ms']==1000
            if r['arm']=='kdlock':
                assert r['mutex_implementation']=='owned-v1'
                assert r['registry_lock_kind']==3 and r['entry_abi']==4 and r['caller_abi']=='c'
                assert r['mutex_wait_mode']=='blocking' and r['mutex_spin_limit']==4096
                assert r['owned_mutex_reuse_spins']==32
                assert r['owned_mutex_origin_spin'] is False and r['owned_mutex_numa'] is False
                params=r['parameters']
                assert params['owned_mutex_protocol']=='linux_local_first_v1'
                for name,value in {'owned_mutex_spin_limit':4096,'owned_mutex_reuse_spins':32,
                                   'owned_mutex_origin_spin':0,'owned_mutex_numa':0,
                                   'owned_mutex_self_route':0,'owned_mutex_native_after_control':0,
                                   'owned_mutex_refill':0,'owned_mutex_preflight_spins':0,
                                   'owned_mutex_preflight_queue':0}.items():
                    actual={'Y':1,'N':0}.get(params[name],params[name])
                    assert int(actual)==value,(r['name'],name,actual)
            if valid_measurement:
                assert m['completed']==sum(w['completed'] for w in m['workers'])
                assert len(m['workers'])==r['threads']
                assert all(w['cpu']==w['observed_cpu']==i and w['completed']>0 for i,w in enumerate(m['workers']))
                assert m['collector_observed_cpu']==63 and m['collector_error']==0
                assert m['peak_window_ns']==m['peak_settle_ns']==300000000
                peak_check(r); counts['recomputed_peaks']+=1; used+=int(accepted)
                peak_workers=m['peak']['worker_completed']
                assert len(peak_workers)==r['threads'] and min(peak_workers)>0
                assert sum(peak_workers)==m['peak']['completed']
                if r['arm']=='kdlock':
                    assert r['retired']==dict(state=2,modules=0,frames=0,writers=0)
                    publication=r.get('published_before',r.get('publication'))
                    if 'published_before' in r: assert publication==r['published_after']
                    if publication:
                        entry=publication['entry']
                        assert entry['entry_abi']==4 and entry['lock_kind']==3 and entry['status']==0
                        assert publication['source']==dict(state=0,modules=1,frames=0,writers=0)
                        if group['family']=='api': assert r['source_quiescent'] is True
                        images=folder/r['name']/'workspace/daemon'/hex(entry['entry'])/str(entry['tgid'])/'asm'
                        for name,h in publication['images'].items(): assert digest(images/name)==h,name
                        counts['jit_image_hashes']+=len(publication['images'])
                if group['family']=='api':
                    assert r['redirected_calls']==m['completed']
                    denominator=m['writes'] if r['kind']=='utsname' else m['completed']
                    assert 0<=r['jit_bodies']<=denominator
                node_totals=defaultdict(Counter)
                for w,peak_completed in zip(m['workers'],peak_workers):
                    node=0 if w['cpu']<32 else 1
                    workers.append(dict(group=group['name'],session=r['name'],arm=r['arm'],threads=r['threads'],repeat=r['repeat'],
                        write_percent=r.get('write_percent'),node=node,
                        peak_completed=peak_completed,peak_share=peak_completed/m['peak']['completed'],
                        share=w['completed']/m['completed'],**w))
                    node_totals[node].update(workers=1,whole_completed=w['completed'],peak_completed=peak_completed)
                for node,totals in node_totals.items():
                    nodes.append(dict(group=group['name'],session=r['name'],arm=r['arm'],threads=r['threads'],
                        repeat=r['repeat'],write_percent=r.get('write_percent'),node=node,**totals,
                        whole_share=totals['whole_completed']/m['completed'],
                        peak_share=totals['peak_completed']/m['peak']['completed']))
            jit=r.get('jit_bodies',0)
            execution=('ACTUAL_JIT' if jit else 'KD_SELF' if r.get('mutex_implementation')=='owned-v1' else 'NO_JIT') if r['arm']=='kdlock' else 'COMPILED_'+r['arm'].upper()
            samples.append(dict(group=group['name'],family=group['family'],lock_kind=group['lock_kind'],
                session=r['name'],threads=r['threads'],arm=r['arm'],repeat=r['repeat'],
                post_work_rounds=r.get('post_work_rounds'),
                mutex_implementation=r.get('mutex_implementation'),entry_abi=r.get('entry_abi'),
                owned_mutex_reuse_spins=r.get('owned_mutex_reuse_spins'),
                owned_mutex_origin_spin=r.get('owned_mutex_origin_spin'),owned_mutex_numa=r.get('owned_mutex_numa'),
                write_percent=r.get('write_percent'),accepted=accepted,valid_measurement=valid_measurement,
                execution_status=r.get('execution_status'),
                drained=r.get('drained'),execution_type=execution,jit_bodies=jit,
                jit_share=r.get('jit_share',r.get('jit_writer_share')),
                delegated_bodies=r.get('delegated_bodies',r.get('tclock_delegation')),
                peak_ops_s=m.get('peak',{}).get('throughput_ops_s'),
                whole_ops_s=m['completed']*1e9/m['wall_ns'] if m.get('wall_ns') else None,
                worker_cpu_ns_per_op=sum(w.get('cpu_ns',0) for w in m.get('workers',[]))/m['completed'] if m.get('completed') else None))
        coverage.append(dict(group=group['name'],planned=len(records),executed=sum(r.get('execution_status')!='NOT_RUN' for r in records),accepted=used,status='COMPLETE' if all(r.get('drained') for r in records) else 'INCOMPLETE'))
    grouped=defaultdict(list); separated=defaultdict(list)
    for r in samples:
        key=(r['group'],r['write_percent'],r['threads'],r['arm'])
        grouped[key].append(r); separated[key+(r['execution_type'],)].append(r)
    stats=[aggregate(k,rs) for k,rs in grouped.items()]
    by_execution=[dict(aggregate(k[:4],rs),execution_type=k[4]) for k,rs in separated.items()]
    controls=[dict(aggregate(k[:4],[dict(r,accepted=r['valid_measurement']) for r in rs]),
        execution_type=k[4],scope='NO_JIT control only; does not pass JIT acceptance')
        for k,rs in separated.items() if k[4]=='NO_JIT' and any(not r['accepted'] for r in rs)]
    points=defaultdict(dict)
    for r in stats: points[(r['group'],r['write_percent'],r['threads'])][r['arm']]=r
    comparisons=[]
    for (group,percent,threads),arms in points.items():
        row=dict(group=group,write_percent=percent,threads=threads,
                 kd_execution_types=arms.get('kdlock',{}).get('execution_types',[]),
                 comparison_scope='descriptive throughput; not a JIT/parity acceptance gate')
        for a in ('tclock','kdlock'):
            for b in ('native','tclock'):
                if a==b: continue
                for metric in ('whole_median_ops_s','peak_max_ops_s'):
                    row[f'{a}_over_{b}_{metric}']=(arms[a][metric]/arms[b][metric]
                        if a in arms and b in arms and arms[a]['complete'] and arms[b]['complete'] else None)
        comparisons.append(row)
    verification=dict(counts,planned=status['expected_sessions'],accepted=sum(s['accepted'] for s in samples),
        complete=status['state']=='COMPLETE',matrix_state=status['state'],source_files=len(approved),
        auditor_sha256=digest(Path(__file__)),
        execution_status_counts=dict(Counter(s['execution_status'] for s in samples)))
    if verification['complete']:
        assert len(samples)==counts['executed']==counts['drained']==status['expected_sessions']
        assert all(len(rows)==3 and {r['repeat'] for r in rows}=={0,1,2} for rows in grouped.values())
    for name,rows in [('samples',samples),('statistics',stats),('statistics-by-execution',by_execution),
                     ('no-jit-controls',controls),('comparisons',comparisons),('workers',workers),
                     ('node-progress',nodes),('coverage',coverage)]:
        csv_write(out/(name+'.csv'),rows)
        if name!='workers': write(out/(name+'.json'),rows)
    write(out/'verification.json',verification)
    retained=['matrix-plan.json','matrix-status.json','driver.py','run.sh',
              'control/source-state.json','control/source-sha256.json','control/workspace.patch',
              'control/host-before.json','control/guest-before.json',
              'control/host-after.json','control/guest-after.json',
              'control/validation.json','control/unit-results.json','control/pilot-status.json',
              'control/regression-status.json','control/full-driver-plan-check.json',
              'control/monitor-events.jsonl']
    for relative in retained:
        source=root/relative
        if source.exists(): shutil.copyfile(source,out/source.name)
    if Path(__file__).resolve()!=out/'analyze.py': shutil.copyfile(__file__,out/'analyze.py')
    readme(out,root,status,plan,verification,stats,comparisons)
    if args.plots:
        plot(out,plan,stats)
    print(json.dumps(verification))


def readme(out,root,status,plan,verification,stats,comparisons):
    source=load(root/'control/source-state.json')
    host=load(root/'control/host-before.json')
    governors=sorted({r.get('scaling_governor','unavailable') for r in host['frequency'].values()})
    kd=[r for r in load(out/'samples.json') if r['arm']=='kdlock']
    execution=Counter(r['execution_type'] for r in kd)
    lines=['# Expanded KD mutex workloads: 1 to 60 workers','',
        f"This fresh comparison contains {verification['executed']:,} executed, "
        f"{verification['drained']:,} drained and {verification['accepted']:,} accepted sessions "
        f"across all {len(plan)} mutex workload variants. Matrix state: **{status['state']}**.",'',
        'Every variant compares Linux Native, TCLock and KD at **1, 2, 3, 4, 5, 6, 7, 8, '
        '12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56 and 60 workers**, with three repetitions. '
        'The 693 KD sessions include the 630 previously omitted measurements and 63 fresh c01 controls. '
        'Native and TCLock also have 693 fresh sessions each. No earlier samples enter this report.','',
        '## What changed','',
        'The owned mutex workload now registers and dispatches c02/c04/c08/c16 in addition to c01, '
        'and the build and planner allow RCUHT. The syscall adapter now supplies an explicit private '
        'KD-owned object for pipebytes, pipecap and seek. All measured consumers of the bound object '
        'use the selected protocol; retained file/pipe references survive worker join, source retirement '
        'and hook removal. KD never shares that object with Linux mutex waiters. '
        'The lock/provider algorithm was not changed by this expansion.','',
        'Synthetic variants: c01/c02/c04/c08/c16 and RCUHT. API variants: pipebytes query at n16/n128, '
        'pipecap query at n16, and seek set/end at n16. '
        'The [earlier all-lock round](../workloads-20261015T180603Z/README.md) remains the separate '
        'spin/rwlock and other-API comparison. Its omissions are historical, not silently filled with new samples.','',
        '## Configuration and validation','',
        f"Source: `{source['git_head']}` plus the captured workspace patch and SHA256 manifest. "
        'All 35 preexisting kernel-module edits match the earlier round byte for byte. '
        'A private mount namespace binds the frozen source at the guest build path.','',
        'Physical host: `10.176.26.71`. Exactly 64 guest vCPUs; node 0 uses CPUs 0–31 and node 1 uses '
        '32–63, each pinned to the same-numbered physical host core. Workers use CPUs 0 through N−1; '
        'collector CPU 63 is separate. Cohorts of 36–60 workers cross NUMA nodes. Kernel '
        '`6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, '
        '`nokaslr nopvspin`, voluntary preemption, verified native qspinlocks. '
        f"Host governors: {', '.join(governors)}. Timed providers and workloads have UBSAN disabled.",'',
        'KD uses owned-v1, ordinary C ABI4, reuse allowance 32, result-poll budget 4096 and blocking waits; '
        'owned origin spin and NUMA selection remain off. Synthetic acceptance is adaptive-performance. '
        'The initial validation passed 93 basic/affected unit tests, 12 synthetic functional sessions '
        '(all six payloads with both ABI2 and ABI4), 15 API mutex sessions at 1/16/60 workers, and two '
        'API spin/rwlock regression sessions. All contended mutex pilots returned JIT bodies. '
        'The complete-matrix planner was also checked without executing its unsupported separate-collector '
        '64-worker placement. See the [validation receipt](validation.json).','',
        '## Measurement and interpretation','',
        'Each synthetic worker warms up for 48,000 operations. API workers warm up for at least '
        '48,000 operations and one second. Timing lasts two seconds. The best warmed peak is the '
        'highest observed valid 300 ms window after 300 ms settling, requiring every worker to progress. '
        'Whole-run throughput includes the entire measured phase and its tail. The main table uses '
        'the median of three whole-run rates; CSVs retain min/median/max, spread and the highest warmed peak. '
        'Backend order reverses on the second synthetic repetition and rotates for API repetitions. '
        'Synthetic mutex loops retain 64 arithmetic rounds after unlock. API rates include the syscall '
        'and result check. Rates are throughput, not lock acquisition latency.','',
        f"Of the {len(kd)} KD sessions, {execution['ACTUAL_JIT']} returned JIT bodies and "
        f"{execution['KD_SELF']} completed on the local KD path with zero returned JIT bodies. "
        'The raw API runner calls zero-body results NO_JIT; the audit labels owned-mutex local executions '
        'KD_SELF. Neither a local result nor image publication is JIT execution evidence. '
        'The report preserves statistics by execution type. Aggregate throughput compares the selected '
        'adaptive implementation, and does not establish JIT parity or change optimization acceptance.','',
        'The pipe/seek results use a controlled client and private objects for KD/TCLock. '
        'Native uses the original embedded kernel mutex around the matched compiled body, so lock placement differs. This validates these '
        'bounded benchmark APIs, not arbitrary replacement of Linux kernel-owned mutexes or concurrent '
        'unhooked pipe/file operations. The unmodified Stock arm is outside this three-backend comparison.','',
        '## Results at 60 workers','',
        'Rates are million operations per second. Ratios above one favor KD. All three repetitions '
        'must be accepted for a comparison ratio.','',
        '| Workload | Native median | TCLock median | KD median | KD / Native | KD / TCLock | KD JIT rounds |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for g in plan:
        arms={r['arm']:r for r in stats if r['group']==g['name'] and r['threads']==60}
        def value(arm):
            r=arms.get(arm);return r['whole_median_ops_s'] if r and r['complete'] else None
        def rate(arm):
            v=value(arm);return f'{v/1e6:.3f}' if v is not None else '—'
        def ratio(other):
            a,b=value('kdlock'),value(other);return f'{a/b:.2f}×' if a is not None and b else '—'
        k=arms.get('kdlock')
        evidence=f"{k['jit_rounds']}/3" if k and k['complete'] else '—'
        lines.append(f'| {g["name"]} | {rate("native")} | {rate("tclock")} | {rate("kdlock")} | '
                     f'{ratio("native")} | {ratio("tclock")} | {evidence} |')
    valid=[r for r in comparisons if r.get('kdlock_over_native_whole_median_ops_s') is not None]
    if valid:
        lower=[r for r in valid if r['kdlock_over_native_whole_median_ops_s']<1]
        lines+=['',f'Across the {len(valid)} workload/worker-count points, KD whole-run median throughput '
                f'is below Native at {len(lower)} points. This is a descriptive count, not an acceptance gate. '
                'The full curves retain those regressions. The five lowest KD/Native whole-run ratios are:','']
        for r in sorted(valid,key=lambda r:r['kdlock_over_native_whole_median_ops_s'])[:5]:
            lines.append(f"- {r['group']}, {r['threads']} workers: "
                         f"{r['kdlock_over_native_whole_median_ops_s']:.3f}× Native.")
    lines+=['','## Scaling curves','']
    for family in ('synthetic','api'):
        lines += [f'### {family.capitalize()} mutex','',
                  f'![Median whole-run throughput]({family}-mutex-whole.svg)','',
                  f'[Best warmed peak]({family}-mutex-peak.svg)','']
    lines+=['Bands show the three-repetition min–max range. Gray regions span both NUMA nodes. '
            'Hollow KD markers mean all repetitions returned zero JIT bodies; diamonds mark a mixture '
            'of local and JIT repetitions. A filled marker means every repetition returned at least '
            'one JIT body, not that every operation was delegated.','',
            '## Evidence','',
            '- [Every session](samples.csv)', '- [Three-round statistics](statistics.csv)',
            '- [Statistics by execution type](statistics-by-execution.csv)',
            '- [Comparison ratios](comparisons.csv)',
            '- [Per-worker progress and CPU time](workers.csv)', '- [NUMA-node progress](node-progress.csv)',
            '- [Workload coverage](coverage.csv)', '- [Independent audit](verification.json)',
            '- [Support validation](validation.json)', '- [Run commands](matrix-plan.json)',
            '- [Source identity](source-state.json)', '- [Source hashes](source-sha256.json)',
            '- [Captured workspace changes](workspace.patch)', '- [Offline auditor](analyze.py)','',
            f'Complete raw evidence is retained under `{root}` in the guest and the matching '
            'machine-specific archive on both source and benchmark hosts. It includes the pilot '
            'evidence. The audit verifies source, module and JIT image hashes, worker placement, '
            'owned ABI4 policy, immutable publication and complete retirement, and independently '
            'recomputes every accepted warmed peak from raw progress samples.','']
    for name,label in [('host-before','Host before measurement'),('guest-before','Guest before measurement'),
                       ('host-after','Host after measurement'),('guest-after','Guest after measurement')]:
        if (out/(name+'.json')).exists():lines.append(f'- [{label}]({name}.json)')
    (out/'README.md').write_text('\n'.join(lines)+'\n')

def plot(out,plan,stats):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none'})
    colors=dict(native='#626973',tclock='#0072B2',kdlock='#D55E00')
    for family in ('synthetic','api'):
        for kind in ('spin','mutex','rwlock'):
            groups=[g for g in plan if g['family']==family and g['lock_kind']==kind]
            if not groups: continue
            panels=[(g['name'],p) for g in groups for p in ([1,20] if family=='synthetic' and kind=='rwlock' else [None])]
            for metric,title in [('whole_median_ops_s','Median whole-run throughput'),('peak_max_ops_s','Best warmed peak')]:
                fig,axes=plt.subplots(math.ceil(len(panels)/2),2,figsize=(14,3.5*math.ceil(len(panels)/2)),squeeze=False)
                for ax,(group,percent) in zip(axes.flat,panels):
                    ax.axvspan(32.5,61,color='#eef1f5'); ax.axvline(32.5,color='#888',linestyle=':',linewidth=1)
                    ax.set_title(group+(f' / {percent}% writes' if percent is not None else ''),loc='left',fontsize=10)
                    for arm in ARMS:
                        rows=sorted((r for r in stats if r['group']==group and r['write_percent']==percent and r['arm']==arm),key=lambda r:r['threads'])
                        if not rows: continue
                        x=[r['threads'] for r in rows]; y=[r[metric]/1e6 if r['complete'] else math.nan for r in rows]
                        stem='whole' if metric.startswith('whole') else 'peak'
                        ax.plot(x,y,'o-',label=LABELS[arm],color=colors[arm],markersize=3,linewidth=1.4)
                        if arm=='kdlock':
                            for row,xx,yy in zip(rows,x,y):
                                if row['complete'] and any(t in ('NO_JIT','KD_SELF') for t in row['execution_types']):
                                    ax.plot(xx,yy,marker='D' if len(row['execution_types'])>1 else 'o',
                                            markerfacecolor='white',markeredgecolor=colors[arm],markersize=4.5)
                        ax.fill_between(x,[r[stem+'_min_ops_s']/1e6 if r['complete'] else math.nan for r in rows],
                            [r[stem+'_max_ops_s']/1e6 if r['complete'] else math.nan for r in rows],color=colors[arm],alpha=.12)
                    ax.set(xlim=(0,61),ylim=(0,None),xlabel='Workers',ylabel='Mops/s')
                    ax.set_xticks([1,8,16,24,32,40,48,60]); ax.grid(axis='y',alpha=.2); ax.legend(fontsize=8)
                for ax in list(axes.flat)[len(panels):]: ax.set_visible(False)
                fig.suptitle(f'{family.capitalize()} {kind}: {title}',fontsize=16)
                footer=('Three repetitions; bands show min–max. Gray region: workers span both NUMA nodes.\n'
                        'KD hollow circle: local execution in every repetition; diamond: mixed local/JIT repetitions.\n'
                        'Filled KD marker: at least one returned JIT body per repetition. Host 10.176.26.71; collector CPU 63.')
                fig.text(.06,.10/fig.get_figheight(),footer,fontsize=8,va='bottom')
                fig.tight_layout(rect=(0,.70/fig.get_figheight(),1,1-.40/fig.get_figheight()))
                stem=out/f'{family}-{kind}-{metric.split("_")[0]}'
                fig.savefig(str(stem)+'.png',dpi=150); fig.savefig(str(stem)+'.svg')
                svg=Path(str(stem)+'.svg'); svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
                plt.close(fig)

if __name__=='__main__': main()
