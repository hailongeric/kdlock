#!/usr/bin/env python3
"""Read frozen local-first studies; never execute archived source or workloads."""
import argparse
import csv
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(ROOT/'bench/tclock_compare'))
import mutex_local_study as local
import mutex_study as study
from bench_runtime import require, digest
from session import (check_owned_caller_policy, check_kd_parameters,
                     check_jit_evidence, tc_quiescent, parse_owned_local_first_profile)
from summarize import valid


def write_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--scores', nargs='+', required=True, help='LABEL=relative-directory')
    p.add_argument('--profiles', nargs='*', default=[])
    p.add_argument('--controls', nargs='*', default=[], help='separate Native/TCLock groups')
    p.add_argument('--pmu', nargs='*', default=[], help='unscored PMU groups')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    h = local.generic_helpers()
    score_groups = h.declared(a.raw.resolve(), a.scores)
    profiles = h.declared(a.raw.resolve(), a.profiles)
    controls = h.declared(a.raw.resolve(), a.controls)
    pmu = h.declared(a.raw.resolve(), a.pmu)
    a.out.mkdir(parents=True, exist_ok=True)
    comparisons, samples, workers, receipts, diagnostic = [], [], [], {}, []
    seen = set()
    for label, folder in score_groups.items():
        rows = study.load_run(folder)
        study.require_fresh(rows, seen)
        receipts[label] = h.frozen(folder)
        receipts[label]['samples'] = len(rows)
        for t in sorted({r['threads'] for r in rows}):
            require(t in local.PRIMARY, 'outside current 1–8 scope')
            pair = {arm: study.metrics([r for r in rows if r['arm']==arm and r['threads']==t])
                    for arm in ('native','kdlock')}
            c = dict(group=label, threads=t)
            for arm, m in pair.items():
                for key in ('median_whole','best_peak','whole_spread_pct','peak_spread_pct','worker_share_min','worker_share_max'):
                    c[arm+'_'+key] = m[key]
            c.update(whole_ratio=pair['kdlock']['median_whole']/pair['native']['median_whole'],
                     peak_ratio=pair['kdlock']['best_peak']/pair['native']['best_peak'])
            c['passes_both'] = c['whole_ratio'] >= .97 and c['peak_ratio'] >= .97
            comparisons.append(c)
        for r in rows:
            m=r['measurement']
            s=dict(group=label, name=r['name'], arm=r['arm'], threads=r['threads'], repeat=r['repeat'],
                   whole=m['completed']*1e9/m['wall_ns'], peak=m['peak']['throughput_ops_s'],
                   cpu_ns_per_op=m['worker_cpu_ns']/m['completed'], cpu_equivalents=m['worker_cpu_ns']/m['wall_ns'],
                   jit_bodies=r['jit_bodies'], execution_class=r['execution_class'])
            samples.append(s)
            workers.extend(dict(group=label, name=r['name'], arm=r['arm'], threads=r['threads'],repeat=r['repeat'],
                                worker=i, completed=w['completed'], share=w['completed']/m['completed'])
                           for i,w in enumerate(m['workers']))
    for label, folder in profiles.items():
        h.environment(folder)
        receipts[label] = h.frozen(folder)
        plan = h.read(folder/'plan.json')
        rows = h.read(folder/'records.json')
        require(len(plan)==len(rows), 'incomplete profile block')
        byname={r['name']:r for r in rows}
        for spec in plan:
            path=folder/spec['name'];r=h.read(path/'session.json')
            require(all(r.get(k)==v for k,v in spec.items()) and all(byname[r['name']].get(k)==v for k,v in r.items()),
                    'profile records or policy differ')
            require(r['diagnostic'] and r['profile_lock'] and byname[r['name']]['score_eligible'] is False and valid(r),
                    'profile is not a valid unscored session')
            require(r['measurement']['peak']==h.validate_measurement(h.read(path/'measure.json'),r,r['iterations']),
                    'profile raw peak differs')
            log=(path/'kernel.log').read_text()
            require(not h.FAULT.search(log), 'kernel fault in profile')
            item=dict(group=label,name=r['name'],arm=r['arm'],threads=r['threads'],repeat=r['repeat'],
                      kernel_log_sha256=digest(path/'kernel.log'),jit_bodies=r['jit_bodies'],profile=r['lock_profile'])
            if r['arm']=='kdlock':
                check_owned_caller_policy(r)
                check_kd_parameters(r['parameters'],r,r['layout']['lock_addr'])
                counters=parse_owned_local_first_profile(log,r)
                require(counters==r['owned_local_first_profile'], 'local profile receipt differs')
                prof=r['lock_profile']
                require(prof['native_calls']==prof['owned']['linux_target_unlocks']==prof['missed']==prof['owned']['missed']==0,
                        'owned target used Linux API or missed probes')
                item['local_first']=counters
            diagnostic.append(item)
        receipts[label]['samples']=len(rows)
    context_counts = {}
    # Reuse archive traversal/export, but select current protocol validators.
    # The historical helper's default imports intentionally describe its old
    # frozen bounded-native-first study and must not validate this candidate.
    h.study = SimpleNamespace(**vars(study), policy_config=study.run)
    h.check_jit_evidence = check_jit_evidence
    h.check_kd_parameters = check_kd_parameters
    h.tc_quiescent = tc_quiescent
    h.POLICY = ('mutex_wait_counter_scope', 'mutex_spin_limit', 'numa_policy',
                'delegation_batch_limit', 'kd_provider_ubsan', *study.run.MUTEX_POLICY_FIELDS)
    for kind, groups in (('control', controls), ('pmu', pmu)):
        tables = {name: [] for name in ('statistics', 'samples', 'workers', 'batches',
                  'pmu', 'flat-profiles', 'lock-profiles', 'batch-histograms')}
        for label, folder in groups.items():
            # These paths have no old bounded-native-first profile. The shared
            # raw/backend checks use the maintained study/session validators.
            rows, receipt = h.audit_group(label, folder, kind == 'pmu')
            require(all(r['threads'] in local.PRIMARY for r in rows), 'context outside 1–8')
            if kind == 'control':
                require({r['arm'] for r in rows} == {'native', 'tclock'}, 'control backend differs')
            else:
                require(all(r['pmu'] and not r.get('profile_lock') for r in rows), 'PMU identity differs')
            h.summarize(label, rows, tables)
            receipts[kind + ':' + label] = receipt
        for name, rows in tables.items():
            if rows:
                write_csv(a.out/(kind + '-' + name + '.csv'), rows)
        context_counts[kind] = len(tables['samples'])
    write_csv(a.out/'comparisons.csv',comparisons)
    write_csv(a.out/'samples.csv',samples)
    write_csv(a.out/'workers.csv',workers)
    (a.out/'diagnostics.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
    (a.out/'coverage.json').write_text(json.dumps(dict(command=sys.argv,script_sha256=digest(Path(__file__)),
        receipts=receipts,scored_samples=len(samples),diagnostic_samples=len(diagnostic),
        separate_context_samples=context_counts,
        limitation='Partial screening groups may reject a candidate; only mutex_local_study.py can accept full confirmations.'),indent=2)+'\n')
    print(json.dumps(dict(scored_samples=len(samples),diagnostic_samples=len(diagnostic))))

if __name__=='__main__':
    main()
