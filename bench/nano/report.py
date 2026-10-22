#!/usr/bin/env python3
"""Render one frozen nano collection, including missing and unsupported points.

Run analysis/plotting in the VM. Does not load modules or change collection inputs.
"""
import argparse
import csv
import itertools
import json
from pathlib import Path
import statistics

THREADS=[1,2,3,4,5,6,7,8,12,16,20,24,28,32,36,40,44,48,52,56,60]
VARIANTS=[('cacheline',1),('cacheline',8),('rcuht',0),('list',16),('list',128),('list-prefetch',16),('list-prefetch',128)]
KEY=['lock','workload','size','write_percent','workers','implementation']

def dump(path,rows,fields=None):
    fields=fields or list(rows[0])
    with path.open('w') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def identity(r):
    lock=r['lock_kind']; workload=r.get('workload','cacheline')
    size=r.get('list_nodes',0) if workload.startswith('list') else r.get('cachelines',0)
    return (lock,workload,size,r.get('write_percent',100),r['threads'],r['arm'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--no-plots',action='store_true');a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=True)
    found={};held={}
    held_names={r['name']:r['reason']
        for receipt in a.input.glob('continuation*/prefix-finished.json')
        for r in json.loads(receipt.read_text()).get('skipped',[])}
    for plan in a.input.glob('*/plan.json'):
        for spec in json.loads(plan.read_text()):
            if spec['name'] in held_names:
                held[identity(spec)+(spec['repeat'],)]=held_names[spec['name']]
    for path in sorted(a.input.glob('*/*/session.json')):
        r=json.loads(path.read_text());key=identity(r)+(r['repeat'],)
        if 'measurement' not in r and path.with_name('measure.json').is_file():
            # Retain failed clients' exact totals without granting a score.
            r['measurement']=json.loads(path.with_name('measure.json').read_text())
        if key in found: raise ValueError('duplicate measurement '+str(key))
        found[key]=(r,str(path.relative_to(a.input)))
    rows=[]
    for lock,(workload,size),workers,arm,rep in itertools.product(('spin','mutex','rwlock','rwsem'),VARIANTS,THREADS,('native','tclock','kdlock'),range(3)):
        for mix in ([1,20] if lock in ('rwlock','rwsem') else [100]):
            key=(lock,workload,size,mix,workers,arm);r,path=found.get(key+(rep,),({},''));m=r.get('measurement',{})
            unsupported=lock=='rwsem' and arm=='tclock'
            valid=(r.get('execution_status')=='OK' and r.get('drained') is True and m.get('complete') is True and m.get('data_ok') is True)
            # A strict delegation refusal can still be a correct local baseline.
            local=(r.get('execution_status')=='NO_JIT' and r.get('jit_bodies')==0 and r.get('drained') is True and not r.get('cleanup_error') and m.get('complete') is True and m.get('data_ok') is True)
            terminal=r and r.get('execution_status') not in ('PREPARING','MEASURING')
            status='unsupported' if unsupported else 'completed' if valid or local else 'failed' if terminal else 'missing'
            entries=r.get('jit_bodies') if arm=='kdlock' else None
            returns=r.get('jit_completions') if arm=='kdlock' else None
            eligible=m.get('writes') if lock in ('rwlock','rwsem') else m.get('completed')
            execution=('local-zero-delegation' if entries==0 else 'returned-delegation' if returns and returns>0 else 'entry-only' if entries else 'unmeasured') if arm=='kdlock' else 'control'
            row=dict(zip(KEY,key));row.update(repetition=rep,status=status,reason='TCLock has no sleeping rwsem port' if unsupported else r.get('error') or held.get(key+(rep,),'not collected' if status=='missing' else ''),
                runner_status=r.get('execution_status',''),execution=execution,completed_operations=m.get('completed'),reads=m.get('reads'),writes=m.get('writes'),
                wall_ns=m.get('wall_ns'),throughput_ops_s=m['completed']*1e9/m['wall_ns'] if status=='completed' else None,
                peak_ops_s=(m.get('peak') or {}).get('throughput_ops_s'),kd_entries=entries,kd_completions=returns,
                kd_eligible_operations=eligible if arm=='kdlock' else None,
                kd_entry_share=entries/eligible if entries is not None and eligible else None,
                kd_completion_share=returns/eligible if returns is not None and eligible else None,
                kd_entries_without_matching_completion=entries-returns if entries is not None and returns is not None else None,
                kd_no_generated_entry_operations=m['completed']-entries if entries is not None and 'completed' in m else None,
                drained=r.get('drained'),data_ok=m.get('data_ok'),complete=m.get('complete'),oversubscribed=False,session=path)
            rows.append(row)
    dump(out/'runs.csv',rows);(out/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
    groups={}
    for r in rows:
        if r['status']=='completed': groups.setdefault(tuple(r[k] for k in KEY),[]).append(r)
    aggregate=[]
    for key,items in groups.items():
        rates=[r['throughput_ops_s'] for r in items];med=statistics.median(rates)
        modes=sorted({r['execution'] for r in items})
        row=dict(zip(KEY,key));row.update(execution=modes[0] if len(modes)==1 else 'mixed-delegation',
            local_repetitions=sum(r['execution']=='local-zero-delegation' for r in items),
            returned_delegation_repetitions=sum(r['execution']=='returned-delegation' for r in items),
            entry_only_repetitions=sum(r['execution']=='entry-only' for r in items),
            repetitions=len(items),median_ops_s=med,min_ops_s=min(rates),max_ops_s=max(rates),
            spread_percent=(max(rates)-min(rates))/med*100,cv_percent=statistics.stdev(rates)/statistics.mean(rates)*100 if len(rates)>1 else None,
            kd_speedup_native=None,kd_speedup_tclock=None)
        aggregate.append(row)
    lookup={tuple(r[k] for k in KEY):r for r in aggregate if r['repetitions']==3}
    for r in aggregate:
        if r['implementation']!='kdlock' or r['repetitions']!=3:continue
        for arm in ('native','tclock'):
            other=lookup.get(tuple(r[k] for k in KEY[:-1])+(arm,))
            if other:r['kd_speedup_'+arm]=r['median_ops_s']/other['median_ops_s']
    fields=KEY+['execution','local_repetitions','returned_delegation_repetitions','entry_only_repetitions','repetitions','median_ops_s','min_ops_s','max_ops_s','spread_percent','cv_percent','kd_speedup_native','kd_speedup_tclock']
    dump(out/'aggregate.csv',aggregate,fields)
    coverage=[]
    for lock,(workload,size),arm in itertools.product(('spin','mutex','rwlock','rwsem'),VARIANTS,('native','tclock','kdlock')):
        subset=[r for r in rows if (r['lock'],r['workload'],r['size'],r['implementation'])==(lock,workload,size,arm)]
        coverage.append(dict(lock=lock,workload=workload,size=size,implementation=arm,**{s:sum(r['status']==s for r in subset) for s in ('completed','failed','unsupported','missing')}))
    dump(out/'coverage.csv',coverage)
    configurations={}
    for r in rows:
        configurations.setdefault(tuple(r[k] for k in KEY),[]).append(r)
    config_coverage=[]
    for key,items in configurations.items():
        counts={s:sum(r['status']==s for r in items) for s in ('completed','failed','unsupported','missing')}
        status=('unsupported' if counts['unsupported']==3 else 'completed' if counts['completed']==3
            else 'failed' if counts['failed'] else 'missing')
        config_coverage.append(dict(zip(KEY,key),status=status,**counts,
            reasons='; '.join(sorted({r['reason'] for r in items if r['reason']}))))
    dump(out/'coverage-configurations.csv',config_coverage)
    config_totals={s:sum(r['status']==s for r in config_coverage) for s in ('completed','failed','unsupported','missing')}
    (out/'coverage-configurations.json').write_text(json.dumps(config_totals,indent=2)+'\n')
    totals={s:sum(r['status']==s for r in rows) for s in ('completed','failed','unsupported','missing')}
    (out/'coverage.json').write_text(json.dumps(totals,indent=2)+'\n')
    figures=[]
    if not a.no_plots and aggregate:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        for lock,(workload,size) in itertools.product(('spin','mutex','rwlock','rwsem'),VARIANTS):
            for mix in ([1,20] if lock in ('rwlock','rwsem') else [100]):
                selected=[r for r in aggregate if (r['lock'],r['workload'],r['size'],r['write_percent'])==(lock,workload,size,mix)]
                if not selected:continue
                fig,ax=plt.subplots(figsize=(8,4.5))
                for arm,label,color in [('native','Linux Native','#555555'),('tclock','TCLock','#d97706'),('kdlock','kdlock','#2563eb')]:
                    rr=sorted([r for r in selected if r['implementation']==arm and r['repetitions']==3],key=lambda r:r['workers'])
                    if rr:
                        x=[r['workers'] for r in rr];y=[r['median_ops_s']/1e6 for r in rr]
                        # NaNs prevent a line from bridging missing worker points.
                        values={r['workers']:r['median_ops_s']/1e6 for r in rr}
                        ax.plot(THREADS,[values.get(n,float('nan')) for n in THREADS],color=color,label=label,marker='o',markersize=3)
                        ax.vlines(x,[r['min_ops_s']/1e6 for r in rr],[r['max_ops_s']/1e6 for r in rr],color=color,alpha=.5)
                    partial=[r for r in selected if r['implementation']==arm and r['repetitions']<3]
                    if partial: ax.scatter([r['workers'] for r in partial],[r['median_ops_s']/1e6 for r in partial],facecolors='none',edgecolors=color,label=label+' incomplete')
                ax.set(xlabel='Workers',ylabel='Million operations/second',title=f'{lock}: {workload} {size or ""}, {mix}% writes')
                ax.grid(alpha=.2);ax.legend(fontsize=8);fig.tight_layout()
                name=f'{lock}-{workload}-{size}-w{mix}.png';fig.savefig(out/name,dpi=150);plt.close(fig);figures.append(name)
    wins=[];losses=[]
    for r in aggregate:
        for arm,label in (('native','Linux Native'),('tclock','TCLock')):
            ratio=r.get('kd_speedup_'+arm)
            if ratio is None:continue
            item=(ratio,f"{r['lock']} {r['workload']} size {r['size']}, {r['write_percent']}% writes, {r['workers']} workers: {ratio:.2f}× {label}")
            (wins if ratio>=1 else losses).append(item)
    text=['# Nano benchmark: first results', '',f"Measured runs: {totals['completed']} completed, {totals['failed']} failed, {totals['missing']} missing; {totals['unsupported']} unsupported repetition slots.",'',
          f"Configurations: {config_totals['completed']} have all three valid repetitions, {config_totals['failed']} contain a failure, {config_totals['missing']} are otherwise incomplete, and {config_totals['unsupported']} are unsupported. See coverage-configurations.csv for every worker count and write mix.", '',
          'This report contains only this collection. Missing points are not passes. The earlier 40-vCPU campaign is a separate historical dataset. No performance acceptance is claimed outside completed configurations.', '',
          'Throughput is completed operations divided by measured wall time. Plots show the median of three repetitions with minimum–maximum whiskers. Open points have fewer than three valid repetitions. Coefficient of variation (CV) is sample standard deviation divided by the mean. Speedup is kdlock median divided by the matching control median; values below one are regressions. Ratios require three valid repetitions for both implementations.', '',
          'Delegation means another lock holder executes the caller’s critical section. Just-in-time (JIT) entry counts and matching completed bodies are recorded separately. Zero-entry runs remain local baselines. A published NORMAL image is not proof of execution. Counts exclude warmup and cover the full measured interval, not the selected peak window. The no-generated-entry count includes local rwlock/rwsem readers; it is not an exact count of admission failures. Medians combine repetitions of the same frozen configuration even when observed delegation varies. The mixed-delegation label and per-mode repetition counts expose that variation; per-run counts remain available. Source versions, workload settings and topologies are never pooled.', '',
          '## Observed comparisons', '']
    text += ['- '+s for _,s in sorted(wins,reverse=True)[:5]] or ['No complete matched wins available yet.']
    text += ['']+(['- '+s for _,s in sorted(losses)[:5]] or ['No complete matched regressions available yet.'])
    text += ['', 'These are the largest observed ratios among complete matched groups, not statistical significance claims. All valid repetitions remain in the data files.']
    failed=[r for r in rows if r['status']=='failed']
    withheld=[r for r in rows if r['status']=='missing' and r['reason']!='not collected']
    if withheld:
        text += ['', '## Withheld repetitions', '']
        text += [f"- {r['lock']} {r['workload']} size {r['size']}, {r['workers']} workers, {r['implementation']}, repetition {r['repetition']+1}: {r['reason']}. Counted as missing, not as a pass." for r in withheld]
    if failed:
        text += ['', '## Failed cases retained', '']
        text += [f"- {r['lock']} {r['workload']} size {r['size']}, {r['workers']} workers, {r['implementation']}, repetition {r['repetition']+1}: {r['reason']}. Drained: {r['drained']}. No throughput score." for r in failed]
        audit_path=a.input/'first-audit.json'
        if audit_path.is_file():
            for f in json.loads(audit_path.read_text()).get('failed_sessions',[]):
                for mismatch in f.get('post_finish_sample_mismatches',[]):
                    text += ['', f"Saved audit: {f['session']}, sample {mismatch['sample']}, worker {mismatch['worker']}: progress lagged by {mismatch['gap']} operations, {mismatch['sample_begin']-mismatch['kernel_finished']} ns after the worker’s recorded finish time. Client data check: {f.get('client_data_ok')}; client completed: {f.get('client_complete')}."]
        text += ['', 'For a post-finish progress mismatch, publication/timestamp ordering is a possible explanation, not an established cause. The check remains enabled; failed evidence is not converted into a passing sample. Raw client results and the audit retain the exact discrepancy.']
    text += ['', '## Environment and method','',
       'The existing VM at 10.176.26.71:2222 runs 6.1.159-kdclobber2 with nokaslr, nopvspin and voluntary preemption. It has 64 vCPUs and 24 GiB RAM: CPUs 0–31 on NUMA node 0, 32–63 on node 1. NUMA means memory access cost depends on the CPU and memory node. Workers use CPUs 0 through N−1; collector CPU 63 is separate. No requested point oversubscribes the guest. Host vCPUs are pinned one-to-one; the observed host governor is ondemand, so clock frequency is not fixed.', '',
       'The 1–32-worker points stay on node 0; the 36–60-worker points span both nodes. At 60 workers the split is 32 on node 0 and 28 on node 1. QEMU service threads share host CPU 63 with the collector. This placement is part of the result identity, not a claim that every possible placement has the same scaling.', '',
       'All arms use 48,000 warmup operations per worker and a 2,000 ms measured interval. A separate secondary peak uses the highest valid 300 ms window after 300 ms settling, sampled every 10 ms. Conclusions and ratios use whole-run medians. Spin/mutex have 64 dependent arithmetic rounds after unlock; rwlock/rwsem have four. Do not compare rates across these different lock-family workloads as though they were equivalent.', '',
       'Cacheline c01/c08 update one/eight padded 64-byte counters. Lists visit 16/128 resident nodes in a fixed permutation; prefetch/no-prefetch are separate variants. RCUHT names the hash-table workload: it has 1,024 buckets, 4,096 preallocated nodes and 8,192 possible keys. Its exclusive operations attempt moves, including misses and conflicts; this nano workload performs no per-operation allocation or read-copy-update (RCU) memory reclamation.', '',
       'Each fresh workload module starts cacheline/list values at zero. A list node occupies 64 bytes, so the selected list footprints are 1 KiB and 8 KiB. List links advance five array slots. Hash nodes begin with keys 0–4,095, inserted into bucket key modulo 1,024; bucket and node strides are 64 bytes. Hash random streams use the same CPU-derived seed in every arm. All workers complete warmup before the measured snapshot; timed hash interleavings can produce different valid table states. The captured owner uses ordinary time-sharing scheduling with nice value 5, inherited by its clients.', '',
       'Spinlocks wait by spinning; mutexes can sleep. Reader/writer spinlocks (rwlocks) allow concurrent readers or an exclusive writer. Reader/writer semaphores (rwsems) offer those ownership modes with sleeping waits. Spin/mutex operations here are exclusive writes. For rwlock/rwsem every worker mixes local shared readers and exclusive writers at 1% or 20% writes; there are no dedicated writer threads. Readers compare cacheline/list values or search a hash bucket. KD writers may delegate. TCLock has no sleeping rwsem implementation.', '',
       'Public mutex macros use the current unified binary calling interface, ABI2. The existing private KD observation provider has UndefinedBehaviorSanitizer (UBSAN) instrumentation disabled; actual compiler commands and source/binary hashes are retained per block. Completion probes are enabled for every KD payload. No lock or workload tuning occurred.', '',
       'Each three-backend block rotates order across the three repetitions. With two backends, three repetitions necessarily leave one order occurring twice. Each session validates data, every worker’s completed work, source/frame retirement and module cleanup. Failures stop the affected collection and remain in raw evidence. Zero-delegation strict-JIT refusals are explicitly retained as local throughput only when data, completed work and cleanup all pass.', '',
       '## Artifacts and reproduction','',
       'See `runs.csv`/`runs.json`, `aggregate.csv`, `coverage.csv` and `coverage.json`. Exact source revision, artifact locations, commands, recovery snapshot, validation logs and hashes belong in `reproducibility.json`. Raw session paths in runs.csv are relative to the collection root. Retained build logs contain exact compiler settings. No p95 latency or MM performance is measured.', '',
       'Run the frozen `bench/nano/run.py --output NEW_EXTERNAL_DIRECTORY` in the verified idle recovery VM with the recorded translation environment and confirmed recovery variables. The exact expanded commands are retained in commands.json. Generate this report using the plotting environment: `python3 bench/nano/report.py COLLECTION OUTPUT`. Never reuse an existing output directory for a fresh collection.', '', '## Throughput plots','']
    text += [f'![{n}]({n})' for n in figures]
    (out/'README.md').write_text('\n'.join(text)+'\n')
    print(json.dumps(totals))

if __name__=='__main__':main()
