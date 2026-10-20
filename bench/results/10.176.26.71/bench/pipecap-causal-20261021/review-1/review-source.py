#!/usr/bin/env python3
"""Independently review pipecap archives and diagnostic arithmetic on 380G10."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
import re
import socket
from statistics import median, mean, stdev
import sys
import tarfile
from types import SimpleNamespace

HELPER='bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
HELPER_SHA='05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
ORIGINAL_SHA='7b7dad099d06b2c8964d9e1831b9e02e7f0bba0e209420982a5904972330c3c4'
MODES=('plain','counts','profile','timing')
RESIDUAL={'kd_hotlock_mutex_entries','kd_hotlock_mutex_contentions','kd_hotlock_mutex_last_entries'}


def save(path,data):
    with path.open('x') as f:json.dump(data,f,indent=2,sort_keys=True);f.write('\n')


def stats(v):
    return dict(n=len(v),minimum=min(v),median=median(v),maximum=max(v),
                spread_pct=100*(max(v)-min(v))/median(v),cv_pct=100*stdev(v)/mean(v) if len(v)>1 else None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[5]
    assert socket.gethostname()=='380G10' and not args.output.exists()
    args.output.mkdir()
    sys.dont_write_bytecode=True
    helper_path=repo/HELPER
    assert hashlib.sha256(helper_path.read_bytes()).hexdigest()==HELPER_SHA
    spec=importlib.util.spec_from_file_location('pipecap_inert_helper',helper_path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    original_raw=args.raw.parent/'mutex-public-20261020-r2'
    assert helper.hashfile(original_raw/'archives.json')==ORIGINAL_SHA
    original_manifest=json.loads((original_raw/'archives.json').read_text())
    original_inventory=json.loads((original_raw/'input-inventory.json').read_text())
    assert helper.hashfile(original_raw/'input-inventory.json')==original_manifest['input_inventory_sha256']
    class JointAudit(helper.Audit):
        def retained_target(self, target):
            # Only the current archive and the pinned original archive may
            # satisfy a link. Resolve path components in memory, including
            # workspace -> replay view -> original bundle chains.
            roots = {self.guest_base.rstrip('/'): self.inventory,
                     original_manifest['guest_base']: original_inventory}
            seen = set()
            for _ in range(32):
                target = posixpath.normpath(target)
                if target in seen:
                    return False
                seen.add(target)
                root = next((r for r in roots if target == r or target.startswith(r+'/')), None)
                if root is None:
                    return False
                relative = target[len(root):].lstrip('/')
                if not relative:
                    return True
                if not helper.safe_relative(relative):
                    return False
                parts = relative.split('/')
                inventory = roots[root]
                for length in range(1, len(parts)+1):
                    name = '/'.join(parts[:length])
                    item = inventory.get(name)
                    if item is None:
                        return False
                    if item.get('link') is not None:
                        link = item['link']
                        target = (link if link.startswith('/') else
                                  posixpath.join(root, posixpath.dirname(name), link))
                        if length < len(parts):
                            target = posixpath.join(target, *parts[length:])
                        break
                else:
                    return relative in inventory
            return False

        def check(self, value, label, detail=None):
            if label == 'symlink_target_retained':
                value = self.retained_target(detail['target'])
            return super().check(value, label, detail)

    audit=JointAudit(SimpleNamespace(repo=repo,raw=args.raw,report=args.output))
    groups,links=audit.load_archives();audit.windows=[]
    # Bind retained original input manifests and selected records to the previously
    # reviewed original archive; never import or execute a frozen program.
    original={}
    for g in original_manifest['groups']:
        audit.equal('original_archive_hash',helper.hashfile(original_raw/g['file']),g['sha256'],g['file'])
        if g['group'] not in ('metadata','matrix'):continue
        with tarfile.open(original_raw/g['file']) as t:
            for name in ('frozen-inputs.json','harness-inputs.json','matrix/records.json','matrix/host-state.json'):
                try:original[name]=json.load(t.extractfile(original_manifest['archive_prefix']+'/'+name))
                except KeyError:pass
    baseline={r['name']:r for r in original['matrix/records.json']}
    health=audit.jread('final-health.json')
    audit.expect('final_idle',health['idle'] and not health['per_session_kernel_faults'])
    frozen={p:h for b in original['frozen-inputs.json'].values() for p,h in b['files'].items()}
    audit.equal('health_original_files',health['verified_original_files'],frozen)
    expected_host=original['matrix/host-state.json']
    host_results={}
    for run in ('run-1','run-2'):
        before=audit.jread(run+'/matrix/host-state.json')
        after=audit.jread('host-evidence/host-after-'+run[-1]+'.json')
        outcome={}
        for label,h in (('before',before),('after',after)):
            for k in ('cpufreq','numa','recovery_snapshot'):
                audit.equal('host_settings',h[k],expected_host[k],[run,label,k])
            for k in ('pid','args'):
                audit.equal('qemu_identity',h['qemu'][0][k],expected_host['qemu'][0][k],[run,label,k])
            expected=sorted(expected_host['qemu'][0]['tasks'],key=lambda t:t['tid'])
            actual=sorted(h['qemu'][0]['tasks'],key=lambda t:t['tid'])
            outcome[label]=dict(captured_utc=h['captured_utc'],threads=len(actual),exact_match=actual==expected,
                                pins_verified=h['pins_verified'],snapshot_listed=h['snapshot_listed'])
            audit.expect('host_receipt_valid',h['pins_verified'] and h['snapshot_listed'],[run,label])
            if label=='before':audit.expect('strict_preflight',actual==expected,run)
        host_results[run]=outcome
    checks=[]
    for name,count in (('checks-1',26),('checks-2',27),('checks-3',28)):
        result=audit.jread(name+'/result.json'); manifest=audit.jread(name+'/committed-source.json')
        audit.expect('basic_affected_success',result['passed'] and result['final_idle'] and result['source_unchanged'],name)
        audit.equal('check_revision',manifest['commit'],result['source_revision'],name)
        for p,h in manifest['files'].items():
            audit.equal('check_source_git',helper.sha(audit.git_bytes(manifest['commit'],p)),h,[name,p])
            audit.equal('check_frozen_source',audit.files.get(name+'/source/'+p),h,[name,p])
        audit.equal('basic_count',re.findall(r'Unit tests: (\d+) passed, (\d+) failed',audit.contents[name+'/unit.log'].decode()),[('2','0')],name)
        counts=[int(re.search(r'Ran (\d+) tests',audit.contents[name+'/'+Path(p).stem+'.log'].decode())[1]) for p in result['runner_tests']]
        audit.equal('affected_counts',sum(counts),count,name)
        checks.append(dict(name=name,revision=result['source_revision'],basic=2,affected=sum(counts)))
    bindings=('comparison_workload','threads','repeat','comparison_arm','arm','source_identity',
        'caller_shell','cookie_storage','cpus','cpu_nodes','collector_cpu','collector_shared',
        'duration_ms','peak_window_ms','peak_settle_ms','sample_ms','warmup','warmup_ms','entries',
        'value_size','file_descriptions','syscalls_per_op','numa_policy','spin_entry_ratio_limit',
        'delegation_batch_limit','kd_provider_ubsan')
    summaries=[]; failures=[]; retirements=[]; counter_sessions=0
    for run in ('run-1','run-2'):
        result=audit.jread(run+'/result.json')
        records=audit.jread(run+'/matrix/records.json');plan=audit.jread(run+'/matrix/plan.json')
        audit.equal('plan_length',[len(records),len(plan)],[48,48],run)
        audit.equal('diagnostic_acceptance',result['accepted'],False,run)
        for tool,h in audit.jread(run+'/tool-sha256.json').items():
            audit.equal('tool_copy',audit.files[run+'/tools/'+tool],h,[run,tool])
            audit.equal('tool_commit',h,helper.sha(audit.git_bytes(result['source_commit'],'bench/mutex_api_compare/'+tool)),[run,tool])
        for r,p in zip(records,plan):
            tag=r['name'];folder=str(Path(r['evidence_path']).relative_to(audit.guest_base.rstrip('/')))
            audit.equal('plan_fields',{k:r.get(k) for k in p},p,[run,tag])
            if r['execution_status']=='NOT_RUN':continue
            audit.equal('session_record',r,audit.jread(folder+'/session.json'),[run,tag])
            audit.expect('drained',r['drained'] and not r.get('cleanup_error'),[run,tag])
            audit.expect('kernel_clean',not helper.FAULT.search(audit.contents[folder+'/kernel.log'].decode()),[run,tag])
            if r['arm']=='kdlock':
                audit.equal('exact_retirement',r['retired'],dict(state=2,modules=0,frames=0,writers=0),[run,tag])
                retirements.append(dict(run=run,name=tag,retired=r['retired']))
            if r['execution_status'] not in ('OK','NO_JIT'):
                failures.append(dict(run=run,name=tag,status=r['execution_status']));continue
            original_name=tag.removesuffix('-'+r['causal_mode'])
            old=baseline[original_name]
            audit.equal('original_settings',{k:r.get(k) for k in bindings},{k:old.get(k) for k in bindings},[run,tag])
            audit.expect('diagnostic_only',r['diagnostic'] and not r['score_eligible'],[run,tag])
            m=r['measurement'];audit.expect('business_result',m['ok'],[run,tag])
            audit.equal('exact_redirected_work',r['redirected_calls'],m['completed'],[run,tag])
            audit.peak(r,folder)
            audit.expect('entry_completion_bounds',0<=r['jit_completions']<=r['jit_bodies']<=m['completed'],[run,tag])
            row=dict(run=run,name=tag,arm=r['comparison_arm'],repeat=r['repeat'],mode=r['causal_mode'],
                completed=m['completed'],whole_ops_s=m['completed']*1e9/m['wall_ns'],
                peak_ops_s=m['peak']['throughput_ops_s'],jit_bodies=r['jit_bodies'],jit_completions=r['jit_completions'],
                returned_fraction=r['jit_completions']/m['completed'],
                execution_class=('RETURNED_JIT' if r['jit_completions'] else 'NO_JIT') if r['arm']=='kdlock' else 'CONTROL',
                route=None,timings=None,observation_ns=None)
            if r['arm']=='kdlock':
                audit.equal('immutable_image',r['published_before'],r['published_after'],[run,tag])
            if r['route_snapshot']:
                counter_sessions+=1
                ss=audit.jread(folder+'/route-snapshots.json');b,a=ss['before'],ss['after'];delta=ss['delta']
                audit.equal('counter_delta_receipt',r['route_delta'],delta,[run,tag])
                for x in (b,a):
                    audit.equal('counter_cpu_domain',[v['cpu'] for v in x['cpus']],list(range(64)),[run,tag])
                    audit.equal('counter_cpu_sum',x['totals'],{k:sum(v['values'][k] for v in x['cpus']) for k in x['totals']},[run,tag])
                    audit.expect('quiescent_reservations',all(v['values']['kd_mutex_active_waiters']==v['values']['kd_mutex_reserved_nodes']==0 for v in x['cpus']),[run,tag])
                    audit.equal('timing_policy',x['timing_enabled'],r['inclusive_jit_timing'],[run,tag])
                d={k:a['totals'][k]-v for k,v in b['totals'].items() if k not in RESIDUAL}
                n={k:a['native'][k]-v for k,v in b['native'].items()}
                timing={phase:{field:a['timings'][phase][field]-v[field] for field in ('samples','ns')} for phase,v in b['timings'].items()}
                audit.equal('counter_delta_arithmetic',delta['counters'],d,[run,tag])
                audit.equal('native_delta_arithmetic',delta['native'],n,[run,tag])
                audit.equal('timing_delta_arithmetic',delta['timings'],timing,[run,tag])
                audit.expect('nonnegative_deltas',all(v>=0 for v in [*d.values(),*n.values(),*(v for t in timing.values() for v in t.values())]),[run,tag])
                audit.expect('capture_outside_measurement',b['finished_ns']<=m['started_ns'] and a['started_ns']>=m['finished_ns'],[run,tag])
                audit.equal('public_counter_witness',[d['kd_bench_bodies'],d['kd_bench_completions']],[r['jit_bodies'],r['jit_completions']],[run,tag])
                audit.expect('timing_valid',all(v['invalid']==0 for x in (a,b) for v in x['timings'].values()),[run,tag])
                row.update(route=dict(counters=d,native=n),timings={p:dict(**v,mean_ns=v['ns']/v['samples'] if v['samples'] else None) for p,v in timing.items()},
                           observation_ns=dict(before=b['finished_ns']-b['started_ns'],after=a['finished_ns']-a['started_ns']))
            summaries.append(row)
    valid=[r for r in summaries if r['run']=='run-2']
    audit.equal('corrected_completed',len(valid),48)
    audit.equal('failed_attempt',failures,[dict(run='run-1',name='pipecap-t05-r0-baseline-kd-counts',status='PREPARATION_FAILED')])
    grouped=[];comparisons=[];overhead=[]
    for mode in MODES:
        for arm in ('native','tclock','baseline-kd','public-kd'):
            rows=[r for r in valid if (r['mode'],r['arm'])==(mode,arm)]
            audit.equal('three_fixed_repeats',sorted(r['repeat'] for r in rows),[0,1,2],[mode,arm])
            grouped.append(dict(mode=mode,arm=arm,classes=dict(Counter(r['execution_class'] for r in rows)),
                whole=stats([r['whole_ops_s'] for r in rows]),peak=stats([r['peak_ops_s'] for r in rows]),returned_fraction=stats([r['returned_fraction'] for r in rows]) if all(r['returned_fraction'] for r in rows) else [r['returned_fraction'] for r in rows]))
        outer=[r for r in valid if r['mode']==mode and r['arm']=='baseline-kd']
        direct=[r for r in valid if r['mode']==mode and r['arm']=='public-kd']
        matched=all(a['execution_class']==b['execution_class'] for a,b in zip(outer,direct)) and len({r['execution_class'] for r in outer+direct})==1
        comparisons.append(dict(mode=mode,classes_match=matched,
            outer_classes=[r['execution_class'] for r in outer],direct_classes=[r['execution_class'] for r in direct],
            descriptive_whole_ratio=median(r['whole_ops_s'] for r in direct)/median(r['whole_ops_s'] for r in outer),
            accepted=False,paired_whole_ratios=[b['whole_ops_s']/a['whole_ops_s'] for a,b in zip(outer,direct)]))
    for arm in ('native','tclock','baseline-kd','public-kd'):
        for mode in MODES[1:]:
            rows=[]
            for repeat in range(3):
                plain=next(r for r in valid if (r['arm'],r['mode'],r['repeat'])==(arm,'plain',repeat))
                observed=next(r for r in valid if (r['arm'],r['mode'],r['repeat'])==(arm,mode,repeat))
                rows.append(dict(repeat=repeat,throughput_ratio=observed['whole_ops_s']/plain['whole_ops_s'],
                    plain_class=plain['execution_class'],observed_class=observed['execution_class'],
                    plain_returned_fraction=plain['returned_fraction'],observed_returned_fraction=observed['returned_fraction']))
            overhead.append(dict(arm=arm,mode=mode,paired=rows,ratio=stats([r['throughput_ratio'] for r in rows]),
                                 limits='Observer association includes time drift and class changes; not a subtractable instrumentation cost.'))
    for name,data in (('sessions.json',summaries),('groups.json',grouped),('comparisons.json',comparisons),('observer-effects.json',overhead)):
        save(args.output/name,data)
    with (args.output/'per-repeat.csv').open('x',newline='') as f:
        keys=('run','name','arm','repeat','mode','execution_class','completed','whole_ops_s','peak_ops_s','jit_completions','returned_fraction')
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in summaries)
    answer=dict(consistent=not audit.issues,issues=audit.issues,checks=sum(audit.counts.values()),check_counts=dict(audit.counts),
        archives=groups,symlinks=len(links),members=len(audit.members),files=len(audit.files),functional_checks=checks,
        completed_sessions=len(summaries),corrected_sessions=len(valid),counter_sessions=counter_sessions,
        retired=len(retirements),retirements=retirements,failures=failures,host_checks=host_results,
        source_sha256=helper.hashfile(Path(__file__)),archives_sha256=helper.hashfile(args.raw/'archives.json'),
        original_archives_sha256=ORIGINAL_SHA,accepted=False,
        limits='Class changes and failed endpoint checks remain unresolved. Counters are observations, not ownership authority. Inclusive timings overlap and change contention. No causal fix or performance acceptance is established.')
    save(args.output/'review.json',answer)
    print(json.dumps({k:answer[k] for k in ('consistent','checks','completed_sessions','corrected_sessions','counter_sessions','retired','host_checks','accepted')}))
    print('issues',Counter(i['check'] for i in audit.issues))
    return int(not answer['consistent'])


if __name__=='__main__':raise SystemExit(main())
