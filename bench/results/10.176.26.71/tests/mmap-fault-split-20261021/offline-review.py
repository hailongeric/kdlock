#!/usr/bin/env python3
"""Inert archive, Git, callback, latency and variance review on the source host."""
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import tarfile
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mmap-fault-split-20261021/archives'
HELPER=ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest()=='05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
spec=importlib.util.spec_from_file_location('inert_archive_helper',HELPER)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
a=m.Audit(SimpleNamespace(repo=ROOT,raw=RAW,report=HERE));a.windows=[]
groups,links=a.load_archives();sources,binaries=a.manifests()


def data(name):
    if name in a.contents:return a.contents[name]
    with tarfile.open(RAW/a.members[name]['archive']) as archive:
        return archive.extractfile(a.prefix+name).read()


def stat(values):
    return dict(n=len(values),minimum=min(values),maximum=max(values),median=statistics.median(values),
        cv_pct=100*statistics.pstdev(values)/statistics.mean(values),
        spread_pct=100*(max(values)-min(values))/statistics.median(values))


# Every copied source file must match both the frozen manifest and its Git tree.
for name,version in [('live-1','9291000'),('live-2','9291000'),('timing-prepare-1','8e87640'),('timing-prepare-2','77cadf5')]:
    manifest=a.jread(name+'/committed-source.json');revision=a.revision(version)
    a.check(manifest['commit']==revision,'source_commit',name)
    for path,digest in manifest['files'].items():
        member=name+'/source/'+path
        if member in a.files:
            a.check(a.files[member]==digest==m.sha(a.git_bytes(revision,path)),'frozen_git_source',member)
    result=a.jread(name+'/result.json')
    if name=='timing-prepare-1':
        a.check(result['state']=='FAILED' and not result['passed'] and not result['sessions'],'failed_attempt_retained')
        a.check("No rule to make target '../../daemon/daemon.c'" in data(name+'/basic.log').decode(),'missing_dependency_not_pass')
    else:
        a.check(result['passed'] and result['drained'] and result['final_idle'] and result['accepted'] is False,'successful_scope_drain',name)
    a.check(result['kernel_identity']['running_build_id']=='5ca28058e156f34a2c7fe91e8e0fbf92f4e51960','same_kernel',name)

# Reconstruct observation overlay with the existing independent in-memory patcher.
original='live-1/source/'
changed=a.reconstruct(original,data(original+'bench/spin_cacheline/provider/observation.patch'))
for path,digest in a.jread('live-1/prepared-source-sha256.json').items():
    content=(data(original+'bench/spin_cacheline/provider/'+Path(path).name) if path in
             ('include/kd_bench.h','kernel_module/kd_bench.c') else changed[path] if path in changed else data(original+path))
    a.check(m.sha(content)==digest,'observed_provider_reconstructed',path)

inputs=a.jread('timing-prepare-2/inputs.json')
a.check(inputs==a.jread('timing-run-1/inputs.json'),'same_prepared_timing_inputs')
for path,digest in inputs['files'].items():
    if path.startswith(a.guest_base):
        member=path[len(a.guest_base):]
        a.check(a.files.get(member)==digest,'retained_input_hash',member)
    elif path.startswith('/root/host_fs/kdlock/'):
        source=path[len('/root/host_fs/kdlock/'):]
        a.check(m.sha(a.git_bytes(a.revision('77cadf5'),source))==digest,'current_source_binding',source)
    else:a.check(False,'input_outside_retained_roots',path)
a.check(a.members['timing-prepare-2/timed-client']['magic']=='7f454c46','timed_client_elf')

# Fixed-work split checks retain the absence of faults in the mmap task.
split=[]
for name,count in [('live-1',12),('live-2',6)]:
    r=a.jread(name+'/result.json');a.check(len(r['split_cases'])==count,'split_case_count',name)
    for c in r['split_cases']:
        n,it=c['workers'],c['iterations'];last=c['completion']
        a.check(c['passed'] and not c['delegated_reader'] and last['joined']==n and
            last['completed']==n*it and all(w['completed']==it and not w['errors'] for w in last['workers']),
            'split_exact_workers',(name,c['mode'],c['backend']))
        a.check(c['before']['faults']==c['before']['reads']==c['before']['writes']==0,'setup_untouched',c['mode'])
        if c['after'] is not None:
            s=c['after'];faults=0 if c['mode']=='mmap' else it*(n-(c['mode']=='concurrent'))
            writes=it if c['mode']=='concurrent' else 0
            a.check(s['faults']==s['reads']==s['read_ends']==faults and
                    s['epoch']==s['writes']==s['write_ends']==writes and
                    s['vmas']==s['context_errors']==s['data_errors']==0,'split_callback_mode',c['mode'])
        else:a.check(c['mode']=='lifetime' and c['health'].endswith('release_errors=0'),'VMA_only_release')
        split.append(dict(run=name,backend=c['backend'],mode=c['mode'],workers=n,completed=n*it))

per_repeat=[];latency_total=0;operation_total=0
for collection,expected in [('timing-prepare-2',8),('timing-run-1',48)]:
    r=a.jread(collection+'/result.json');plan=a.jread(collection+'/plan.json')
    a.check(r['passed'] and r['drained'] and r['final_idle'] and len(r['sessions'])==len(plan)==expected,'timed_session_count',collection)
    for row,spec in zip(r['sessions'],plan):
        name=collection+'/'+row['name'];receipt=a.jread(name+'/result.json')
        a.check(all(row[k]==spec[k] for k in spec) and all(row[k]==v for k,v in receipt.items()),'session_plan_receipt',name)
        lines=[json.loads(line) for line in data(name+'/client.jsonl').splitlines()]
        ready,raw=lines;n=row['threads'];summary=row['measurement']
        a.check(row['passed'] and row['drained'] and row['health']=='files=0 destroyed=1 release_errors=0','timed_exact_drain',name)
        if row['arm']=='tclock':a.check(row['tclock_quiescent'] and row['retired'] is None,'tclock_scope',name)
        else:a.check(row['retired']==dict(state=2,modules=0,writers=0,frames=0) and row['jit_observation']['registry_empty'],'kd_exact_retirement',name)
        a.check(not summary['delegated'] and row['accepted'] is False and len(set(ready['pids']))==n,'local_reader_scope',name)
        values=[]
        for i,w in enumerate(raw['workers']):
            first=(-i)%64;count=max(0,1+(w['completed']-1-first)//64) if row['observation']=='sampled' else 0
            a.check(w['pid']==ready['pids'][i] and w['cpu']==w['observed_cpu']==i and not w['error'],'timed_worker_identity',name)
            a.check(len(w['latency_ns'])==count and count<=65536 and all(v>0 for v in w['latency_ns']),'exact_latency_sampling',name)
            values.extend(w['latency_ns'])
        values.sort();p95=values[math.ceil(.95*len(values))-1] if values else None
        a.check(len(values)==summary['latency_samples'] and p95==summary['completed_operation_p95_ns'],'independent_p95',name)
        after=raw['after'];callbacks=0 if row['workload']=='mmap' else raw['completed']
        a.check(after['faults']==after['reads']==after['read_ends']==callbacks and after['writes']==after['write_ends']==0,'timed_reader_only_callbacks',name)
        reconstructed=dict(raw,peak=summary['peak'])
        a.peak(dict(row,measurement=reconstructed,execution_status='OK',whole_throughput_ops_s=summary['whole_ops_s']),name)
        if collection=='timing-run-1':
            operation_total+=raw['completed'];latency_total+=len(values)
            per_repeat.append(dict(name=row['name'],workload=row['workload'],threads=n,arm=row['arm'],repeat=row['repeat'],observation=row['observation'],
                whole_ops_s=summary['whole_ops_s'],peak_ops_s=summary['peak']['throughput_ops_s'],p95_ns=p95,samples=len(values),completed=raw['completed']))

summary=a.jread('timing-run-1/summary.json')
for g in summary['groups']:
    rows=[r for r in per_repeat if all(r[k]==g[k] for k in ('workload','threads','arm','observation'))]
    a.check(len(rows)==3 and {r['repeat'] for r in rows}=={0,1,2},'three_distinct_repetitions',g)
    a.equal('whole_variance',g['whole_ops_s'],stat([r['whole_ops_s'] for r in rows]),g)
    a.equal('peak_variance',g['peak_ops_s'],stat([r['peak_ops_s'] for r in rows]),g)
    if g['observation']=='sampled':a.equal('p95_variance',g['completed_operation_p95_ns'],stat([r['p95_ns'] for r in rows]),g)
for pair in summary['observation_pairs']:
    rows={r['observation']:r for r in per_repeat if all(r[k]==pair[k] for k in ('workload','threads','arm','repeat'))}
    a.equal('observation_pair',pair['sampled_plain_whole_ratio'],rows['sampled']['whole_ops_s']/rows['plain']['whole_ops_s'],pair)
    a.equal('observation_peak_pair',pair['sampled_plain_peak_ratio'],rows['sampled']['peak_ops_s']/rows['plain']['peak_ops_s'],pair)

health=a.jread('final-health.json')
a.check(health['idle'] and not health['per_session_kernel_faults'] and health['script_sha256']==a.files['capture-health.py'],'final_health')
endpoint=a.jread('control/kd-mf-time-host-immediate-after.json');before=a.jread('timing-run-1/host-before.json')
tasks=lambda x:sorted(x['qemu'][0]['tasks'],key=lambda t:t['tid'])
exact=tasks(endpoint)==tasks(before)
a.check(len(tasks(before))==67 and len(tasks(endpoint))==health['strict_host_endpoint']['threads'] and
        exact==health['strict_host_endpoint']['exact_original_threads'],'strict_endpoint_receipt')
acceptance=[dict(check='strict_original_host_endpoint',passed=exact,original_threads=67,endpoint_threads=len(tasks(endpoint))),
            dict(check='seven_mutex_causes_resolved',passed=False)]
with (HERE/'per-repeat.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=list(per_repeat[0]),lineterminator='\n');writer.writeheader();writer.writerows(per_repeat)
report=dict(evidence_consistent=not a.issues,issues=a.issues,checks=sum(a.counts.values()),check_counts=dict(a.counts),
    archives=groups,members=len(a.members),files=len(a.files),symlinks=len(links),split_cases=len(split),
    timed_validation_sessions=8,timed_sessions=48,operations=operation_total,latency_samples=latency_total,
    strict_acceptance_checks=acceptance,accepted=False,archive_manifest_sha256=m.hashfile(RAW/'archives.json'),
    script_sha256=m.hashfile(Path(__file__)),helper_sha256=m.hashfile(HELPER))
(HERE/'offline-review.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:report[k] for k in ('evidence_consistent','issues','checks','operations','latency_samples','strict_acceptance_checks')}))
raise SystemExit(bool(a.issues))
