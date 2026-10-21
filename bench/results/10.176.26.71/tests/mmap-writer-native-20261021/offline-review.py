#!/usr/bin/env python3
"""Read inert archives/Git and independently recompute shared-mm evidence."""
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
import tarfile
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
RAW=ROOT/'bench/results/10.176.26.71/raw/tests/mmap-writer-native-20261021/archives'
HELPER=ROOT/'bench/results/10.176.26.71/bench/mutex32-native-tclock-20261020/offline-review.py'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest()=='05b87daa59dd00c658b042f8e6bf30ee60d5c811956a5a132053d9708ae4ebf6'
spec=importlib.util.spec_from_file_location('inert_audit',HELPER);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
a=m.Audit(SimpleNamespace(repo=ROOT,raw=RAW,report=HERE));a.windows=[];groups,links=a.load_archives()
# Cache JSON-lines as data, never import or execute retained runtime code.
for group in groups:
    with tarfile.open(RAW/group['file']) as t:
        for member in t:
            if member.isfile() and member.name.endswith(('.jsonl','.asm')):
                a.contents[member.name[len(a.prefix):]]=t.extractfile(member).read()

def data(name):return a.contents[name]
def rows(name):return [json.loads(line) for line in data(name).splitlines()]
def stat(v):
    return dict(n=len(v),minimum=min(v),maximum=max(v),median=statistics.median(v),
                cv_pct=100*statistics.pstdev(v)/statistics.mean(v),spread_pct=100*(max(v)-min(v))/statistics.median(v))

attempts=[]
for name,version in [('live-1','4a960ab'),('live-2','3e19abb'),('live-3','b9fe567'),('timing-prepare-1','b043da5')]:
    revision=a.revision(version);manifest=a.jread(name+'/committed-source.json');r=a.jread(name+'/result.json')
    a.check(manifest['commit']==revision==r['source_commit'],'source_commit',name)
    for path,digest in a.jread(name+'/source-sha256.json').items():
        a.check(a.files[name+'/source/'+path]==digest==manifest['files'][path]==m.sha(a.git_bytes(revision,path)),
                'frozen_git_source',(name,path))
    if name+'/binary-sha256.json' in a.files:
        for path,digest in a.jread(name+'/binary-sha256.json').items():
            member=name+'/'+path
            a.check(a.files[member]==digest and a.members[member]['magic']=='7f454c46','binary_identity',member)
    a.check(b'Unit tests: 2 passed, 0 failed' in data(name+'/basic.log'),'basic_two_passed',name)
    a.check(r['kernel_identity']['running_build_id']=='5ca28058e156f34a2c7fe91e8e0fbf92f4e51960','same_kernel',name)
    if name in ('live-1','live-2'):
        c=a.jread(name+'/cleanup.json')
        a.check(r['state']=='FAILED' and not r['passed'] and len(r['cases'])==2,'failed_probe_retained',name)
        a.check(c['normal_unload'] and not c['workers'] and c['health_before']=='files=0 mm_refs=0 destroyed=3 release_errors=0','failed_probe_drained',name)
        a.check(b'FAIL line ' in data(name+'/02-cycle-16.jsonl'),'raw_probe_failure',name)
    else:a.check(r['passed'] and r['drained'] and r['final_idle'] and not r['accepted'],'successful_scope_drain',name)
    attempts.append(dict(name=name,source_commit=revision,state=r['state'],passed=r['passed']))

live=a.jread('live-3/result.json');a.check(len(live['cases'])==6,'six_focused_cases')
for index,c in enumerate(live['cases']):
    a.check(c['passed'] and c['health']==f'files=0 mm_refs=0 destroyed={index+1} release_errors=0','case_lifetime_drain',c['name'])
    for s in c['observations']:
        a.check(s['faults']==s['context_errors']==0 and s['maps']+s['clones']==s['closes']+s['vmas'],'VMA_conservation',c['name'])
    if c['mode'] in ('cycle','lifetime'):
        ws=c['completion']['workers'];id=c['identity'];n=c['threads'];it=c['iterations']
        a.check(len(ws)==c['completion']['joined']==n and c['completion']['completed']==n*it and len({w['tid'] for w in ws})==n,'correctness_exact_joins',c['name'])
        for i,w in enumerate(ws):
            a.check(w['cpu']==i and w['tid']!=id['tid'] and w['completed']==it and not w['errors'] and
                    all(w[k]==id[k] for k in ('mm','mmap_lock','tgid','object')),'shared_mm_identity',c['name'])
    if c['mode']=='cycle':
        s=c['observations'][-1];a.check(s['maps']==s['closes']==c['threads']*c['iterations'] and s['vmas']==s['clones']==0,'cycle_no_faults_or_clones')
    elif c['mode']=='scope':
        s=c['observations'][0];a.check(s['maps']==s['clones']==1 and s['closes']==s['foreign_rejects']==2 and s['vmas']==0,'scope_split_and_rejection')
    elif c['mode']=='exit':
        s=c['observations'][0];a.check(s['maps']==s['vmas']==1 and s['closes']==0,'exit_VMA_only_setup')
stack=next(r for r in rows('live-3/02-cycle-16.jsonl') if r['event']=='writer_stack')
proof=a.jread('kernel-elf-1/writer-elf-capture.json');site=proof['sites'][stack['caller']]
a.check(a.files['kernel-elf-1/vmlinux']==proof['vmlinux_sha256']==live['writer_sites']['vmlinux_sha256'],'exact_kernel_elf')
for name,digest in proof['outputs'].items():a.check(a.files['kernel-elf-1/writer-elf/'+name]==digest,'disassembly_hash',name)
assembly=data('kernel-elf-1/writer-elf/'+stack['caller']+'.asm').decode()
a.check(site['call_line'] in assembly and site['next_line'] in assembly and '<down_write_killable>' in site['call_line'],'decoded_writer_call')
frames=re.findall(r'\] (\w+)\+0x([0-9a-f]+)/',stack['raw_stack'])
a.check(stack['proof']=='FILTERED_SCHED_RETURN_SITE' and frames[0][0]==stack['caller'] and
        int(frames[0][1],16)==stack['return_offset']==site['return_offset'] and
        stack['state_before']==stack['state_after']=='D' and stack['wchan_before']==stack['wchan_after']==stack['caller'] and
        stack['schedstat_before']==stack['schedstat_after'],'blocked_writer_proof')
case=live['cases'][2]
a.check(stack['tid'] in {w['tid'] for w in case['completion']['workers']} and
        all(stack[k]==case['identity'][k] for k in ('mm','mmap_lock')) and case['observations'][-1]['contended_mmaps']>0,'writer_binding')
capture=a.jread('kernel-capture-1/capture.json');audit=json.loads((HERE/'kernel-audit.json').read_text())
a.check(a.files['kernel-capture-1/kernel-inputs.tar.gz']==capture['archive_sha256']==audit['archive_sha256'] and
        a.files['kernel-capture-1/source-sha256.json']==capture['manifest_sha256']==audit['manifest_sha256'] and
        capture['files']==audit['verified_files']==61567,'full_source_capture_binding')

inputs=a.jread('timing-prepare-1/inputs.json');a.check(inputs==a.jread('timing-run-1/inputs.json'),'fixed_timing_inputs')
for path,digest in inputs['files'].items():
    if path.startswith(a.guest_base):a.check(a.files[path[len(a.guest_base):]]==digest,'retained_timing_input',path)
    elif path.startswith('/root/host_fs/kdlock/'):
        a.check(m.sha(a.git_bytes(a.revision('b043da5'),path[len('/root/host_fs/kdlock/'):]))==digest,'timing_source_binding',path)
    else:a.check(False,'unknown_timing_input',path)
per_repeat=[];operations=latency_total=0
for collection,expected in [('timing-prepare-1',4),('timing-run-1',12)]:
    r=a.jread(collection+'/result.json');plan=a.jread(collection+'/plan.json')
    a.check(r['passed'] and r['drained'] and r['final_idle'] and len(r['sessions'])==len(plan)==expected,'timed_count_drain',collection)
    for row,planned in zip(r['sessions'],plan):
        name=collection+'/'+row['name'];receipt=a.jread(name+'/result.json');ready,raw=rows(name+'/client.jsonl');summary=row['measurement'];id=ready['identity'];ws=raw['workers']
        a.check(all(row[k]==v for k,v in receipt.items()) and all(row[k]==v for k,v in planned.items()),'plan_receipt',name)
        a.check(row['passed'] and row['drained'] and not row['accepted'] and row['health']=='files=0 mm_refs=0 destroyed=1 release_errors=0','timed_exact_drain',name)
        a.check(len(ws)==raw['joined']==row['threads'] and len({w['identity']['tid'] for w in ws})==len(ws),'timed_exact_joins',name)
        values=[]
        for i,w in enumerate(ws):
            who=w['identity'];a.check(who['tid']!=id['tid'] and all(who[k]==id[k] for k in ('object','mm','mmap_lock','tgid')),'timed_shared_mm',name)
            first=(-i)%64;count=max(0,1+(w['completed']-1-first)//64) if row['observation']=='sampled' else 0
            a.check(len(w['latency_ns'])==count<=65536 and all(type(v) is int and v>0 for v in w['latency_ns']),'sample_coverage',name);values+=w['latency_ns']
        values.sort();p95=values[math.ceil(.95*len(values))-1] if values else None
        a.check(len(values)==summary['latency_samples'] and p95==summary['completed_operation_p95_ns'],'independent_p95',name)
        b,s=raw['before'],raw['after'];quiet=('clones','vmas','faults','context_errors','foreign_rejects','observe','contended_mmaps')
        a.check(b['object']==s['object']==id['object'] and b['maps']==b['closes']==0 and
                s['maps']==s['closes']==raw['completed'] and all(b[k]==s[k]==0 for k in quiet),'exact_mmap_callbacks',name)
        a.check(raw['worker_cpu_ns']==sum(w['cpu_ns'] for w in ws) and raw['finished_ns']==max(w['finished_ns'] for w in ws),'thread_cpu_and_completion',name)
        a.peak(dict(row,measurement=dict(raw,peak=summary['peak']),execution_status='OK',whole_throughput_ops_s=summary['whole_ops_s']),name)
        if collection=='timing-run-1':
            operations+=raw['completed'];latency_total+=len(values)
            per_repeat.append(dict(name=row['name'],threads=row['threads'],repeat=row['repeat'],observation=row['observation'],
                whole_ops_s=summary['whole_ops_s'],peak_ops_s=summary['peak']['throughput_ops_s'],p95_ns=p95,samples=len(values),completed=raw['completed']))
summary=a.jread('timing-run-1/summary.json')
for g in summary['groups']:
    rs=[r for r in per_repeat if r['threads']==g['threads'] and r['observation']==g['observation']]
    a.check(len(rs)==3 and {r['repeat'] for r in rs}=={0,1,2},'three_repetitions')
    a.equal('whole_variance',g['whole_ops_s'],stat([r['whole_ops_s'] for r in rs]));a.equal('peak_variance',g['peak_ops_s'],stat([r['peak_ops_s'] for r in rs]))
    if g['observation']=='sampled':a.equal('p95_variance',g['completed_operation_p95_ns'],stat([r['p95_ns'] for r in rs]))
for pair in summary['observation_pairs']:
    rs={r['observation']:r for r in per_repeat if r['threads']==pair['threads'] and r['repeat']==pair['repeat']}
    a.equal('paired_whole',pair['sampled_plain_whole_ratio'],rs['sampled']['whole_ops_s']/rs['plain']['whole_ops_s'])
    a.equal('paired_peak',pair['sampled_plain_peak_ratio'],rs['sampled']['peak_ops_s']/rs['plain']['peak_ops_s'])
health=a.jread('final-health.json');oracle=a.jread('oracle-checks-1/checks.json')
a.check(health['idle'] and not health['per_session_kernel_faults'] and health['script_sha256']==a.files['capture-health.py'],'final_health')
a.check(oracle['passed'] and oracle['positive_receipts']==2 and len(oracle['rejected'])==18 and
        oracle['script_sha256']==a.files['oracle-checks-1/check_oracles.py'],'negative_checks')
endpoint=a.jread('control/kd-mmap-writer-host-immediate-after.json');before=a.jread('timing-run-1/host-before.json')
tasks=lambda h:sorted(h['qemu'][0]['tasks'],key=lambda t:t['tid'])
a.check(len(tasks(before))==67 and len(tasks(endpoint))==76 and tasks(endpoint)!=tasks(before) and
        health['strict_host_endpoint']['exact_original_threads'] is False,'failed_endpoint_preserved')
with (HERE/'per-repeat.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=list(per_repeat[0]),lineterminator='\n');writer.writeheader();writer.writerows(per_repeat)
report=dict(evidence_consistent=not a.issues,issues=a.issues,checks=sum(a.counts.values()),check_counts=dict(a.counts),
    archives=groups,members=len(a.members),files=len(a.files),symlinks=len(links),correctness_cases=6,timing_validation_sessions=4,
    timing_sessions=12,operations=operations,latency_samples=latency_total,negative_rejections=18,
    strict_host_endpoint=health['strict_host_endpoint'],kd_integration=False,accepted=False,
    archive_manifest_sha256=m.hashfile(RAW/'archives.json'),script_sha256=m.hashfile(Path(__file__)),helper_sha256=m.hashfile(HELPER))
(HERE/'offline-review.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
for name,member in [('final-health.json','final-health.json'),('timing-summary.json','timing-run-1/summary.json'),('oracle-checks.json','oracle-checks-1/checks.json'),('live-3-result.json','live-3/result.json')]:
    (HERE/name).write_bytes(data(member))
(HERE/'archives.json').write_bytes((RAW/'archives.json').read_bytes())
print(json.dumps({k:report[k] for k in ('evidence_consistent','issues','checks','operations','latency_samples')}))
raise SystemExit(bool(a.issues))
