#!/usr/bin/env python3
"""Serial split-workload timing with exact callback oracles and retained controls."""
import argparse
import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'bench/mmap_fault'))
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity
from peak import analyze_peak
import mm_platform
RELEASE=mm_platform.RELEASE
BACKENDS={'native':0,'kdlock':1,'tclock':2}


def load(path): return json.loads(path.read_text())
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
archive=module('mf_archive',ROOT/'bench/archive_run.py')



def idle(base):
    archive.idle(base,rt.idle)
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try: rt.require(path.read_text().strip() not in ('mf_time_worker','mf_split_worker'),'existing mmap/fault worker')
        except FileNotFoundError: pass


def guest(boot_id=None):
    return mm_platform.guest(boot_id)


def host_check(path,out,strict,boot_id=None,*,reference=None,reference_sha256=None):
    rt.require(reference is not None, 'new-platform host reference required')
    reference_bytes, original = mm_platform.host_reference(reference, reference_sha256)
    host=load(path);shutil.copyfile(path,out/'host-before.json')
    (out/'host-reference.json').write_bytes(reference_bytes)
    comparison=mm_platform.compare_host(original,host,datetime.datetime.now(datetime.timezone.utc),
                                       os.environ['KDLOCK_SNAPSHOT_TAG'],strict)
    rt.write_json(out/'host-qualification.json',comparison)
    previous=os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0,{63});collector=rt.capture_topology([63])
    finally:os.sched_setaffinity(0,previous)
    environment=dict(boot_id=boot_id,cmdline=Path('/proc/cmdline').read_text().strip(),
        preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],collector_topology=collector,
        **mm_platform.dependency_identity())
    topology=rt.capture_topology(list(range(60)))
    rt.require(topology['online_cpus']==list(range(64)) and topology['role_nodes']==[0]*32+[1]*28,
               '64-vCPU/two-node worker topology differs')
    rt.write_json(out/'environment.json',environment);rt.write_json(out/'topology.json',topology)
    return comparison


def verify_maps(maps):
    for path,digest in maps.items():rt.require(rt.digest(Path(path))==digest,'frozen input changed: '+path)


def finish_logs(out,result,logs,fd):
    """A late kernel-log failure must never leave a reusable PASS receipt."""
    failure=None
    if fd is not None:
        try:logs()
        except BaseException as error:
            failure=error
            result.update(state='FAILED',passed=False,accepted=False,final_log_error=repr(error))
        try:os.close(fd)
        except BaseException as error:
            if failure is None:failure=error
            result.update(state='FAILED',passed=False,accepted=False,final_close_error=repr(error))
    # Proven normal drain is independent of a later observation failure. Keep
    # its existing value; never manufacture drain or unload during finalization.
    rt.write_json(out/'result.json',result)
    if failure is not None:raise failure


def bundle(base, identity):
    r=load(base/'result.json')
    rt.require(r['passed'] and r['drained'] and r['final_idle'] and r['split'] and r['basic_programs']==2,
               'split correctness prerequisite incomplete')
    rt.require(r.get('kernel_binding')==identity, 'correctness kernel identity differs')
    rt.require(r.get('backends') in ('0,1','2'), 'exact split correctness backend set required')
    tc=r['backends']=='2'
    provider='source/tclock_backend/tclock_rwlock_backend_km.ko' if tc else 'build/provider/kernel_module/kdlock_km.ko'
    payload='source/workload_modules/mmap_fault/kd_mmap_fault.ko'
    guard='source/bench/tclock_compare/allocator_guard/tc_allocator_guard.ko'
    files={str(base/'result.json'):rt.digest(base/'result.json')}
    for name,root in [('source-sha256.json',base/'source'),('prepared-source-sha256.json',base/'build/provider'),
                      ('binary-sha256.json',base)]:
        if name=='prepared-source-sha256.json' and tc:
            continue
        rt.require((base/name).is_file(), 'required correctness manifest missing: '+name)
        hashes=load(base/name)
        rt.require(isinstance(hashes,dict) and bool(hashes) and all(
            isinstance(p,str) and not Path(p).is_absolute() and '..' not in Path(p).parts and
            isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h) for p,h in hashes.items()),
            'invalid correctness manifest: '+name)
        if name=='binary-sha256.json':
            rt.require(set(hashes)=={provider,payload,guard,'client','split-client'},
                       'exact validated split binaries required')
        files[str(base/name)]=rt.digest(base/name)
        files.update({str(root/p):h for p,h in hashes.items()})
    verify_maps(files)
    # Reuse the validated binaries; only timing clients/runners are new.
    for path,digest in load(base/'source-sha256.json').items():
        if path.startswith(('include/','kernel_module/','tclock_backend/','workload_modules/mmap_fault/')):
            rt.require(rt.digest(ROOT/path)==digest,'validated provider or payload source changed: '+path)
    return dict(files=files,result=r,provider=str(base/provider),payload=str(base/payload),guard=str(base/guard))


def peak_result(measurement, spec):
    policy = spec.get('peak_policy', 'required')
    rt.require(policy in ('required', 'optional-positive-window'), 'unknown peak policy')
    try:
        return analyze_peak(measurement, spec), None
    except ValueError as error:
        if (policy != 'optional-positive-window' or type(error) is not ValueError or
                str(error) != 'no positive full-cohort peak window'):
            raise
        # Exact operation, callback, worker and progress validation precedes
        # this final availability result. Other malformed samples still fail.
        return None, str(error)


def validate(rows,spec):
    rt.require(len(rows)==2 and rows[0]['event']=='ready','missing start receipt')
    m=rows[1];n=spec['threads'];pids=rows[0]['pids']
    rt.require(m['event']=='measurement' and m['complete'] and m['data_ok'] and m['joined']==n and
        m['backend']==BACKENDS[spec['arm']] and m['threads']==n and m['workload']==spec['workload'] and
        m['observation']==spec['observation'] and len(pids)==len(set(pids))==n and len(m['workers'])==n,
        'measurement identity/join differs')
    ws=m['workers'];completed=sum(w['completed'] for w in ws)
    rt.require(m['completed']==completed>0 and m['worker_cpu_ns']==sum(w['cpu_ns'] for w in ws) and
               m['finished_ns']==max(w['finished_ns'] for w in ws) and
               m['wall_ns']==m['finished_ns']-m['started_ns']>0,'whole-operation accounting differs')
    latency=[]
    for i,w in enumerate(ws):
        rt.require(w['pid']==pids[i] and w['cpu']==w['observed_cpu']==i and not w['error'] and
                   w['completed']>0 and w['cpu_ns']>0,'worker identity/progress differs')
        first=(-i)%64
        expected=max(0,1+(w['completed']-1-first)//64) if spec['observation']=='sampled' else 0
        rt.require(len(w['latency_ns'])==expected and expected<=65536 and
                   all(type(v) is int and v>0 for v in w['latency_ns']),'latency coverage/capacity differs')
        latency.extend(w['latency_ns'])
    before,after=m['before'],m['after']
    quiet=('active_probe','epoch','writes','write_ends','downgrades','context_errors','data_errors','fallback','scopes','scope_ends')
    rt.require(before['backend']==after['backend']==m['backend'] and before['features']==after['features']==0 and
               before['vmas']==(0 if spec['workload']=='mmap' else n) and after['vmas']==0 and
               all(before[k]==after[k]==0 for k in quiet) and before['faults']==before['reads']==before['read_ends']==0 and
               after['faults']==after['reads']==after['read_ends']==(0 if spec['workload']=='mmap' else completed),
               'mmap/fault separation, backing mode or exact callback count differs')
    peak, peak_reason=peak_result(m,spec)
    latency.sort()
    p95=latency[math.ceil(.95*len(latency))-1] if latency else None
    rt.require(bool(latency)==(spec['observation']=='sampled'),'latency mode differs')
    return dict(completed=completed,whole_ops_s=completed*1e9/m['wall_ns'],peak=peak,
        latency_samples=len(latency),completed_operation_p95_ns=p95,
        latency_definition='mmap plus munmap, without access' if spec['workload']=='mmap' else 'MADV_DONTNEED plus checked CPU read; includes PTE reset',
        execution='NATIVE_MMAP_ONLY' if spec['workload']=='mmap' else 'LOCAL_READER',
        delegated=False,errors=0,callback_count=after['faults'],
        peak_status='available' if peak is not None else 'unavailable',
        peak_unavailable_reason=peak_reason)


def session(out,spec,inputs,verify):
    idle(out.parent);verify();out.mkdir()
    result=dict(**spec,state='RUNNING',passed=False,drained=False,accepted=False)
    rt.write_json(out/'result.json',result)
    tc=spec['arm']=='tclock';b=inputs['tclock' if tc else 'kdlock']
    fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK);os.lseek(fd,0,os.SEEK_END);messages=''
    def logs():
        nonlocal messages
        while True:
            try:messages+=os.read(fd,1<<20).decode(errors='replace')+'\n'
            except BlockingIOError:break
        (out/'kernel.log').write_text(messages)
        rt.require(not rt.FAULT.search(messages),'kernel fault; retain modules','KERNEL_FAULT')
    try:
        rt.command(['insmod',b['guard']],out/'load-guard.log');rt.command(['rmmod','tc_allocator_guard'],out/'unload-guard.log')
        params=['komb_batch_size=1024'] if tc else ['bench_quiet=1','bench_complete_probe=1','jit_timing=0','target_process=mf_time_worker']
        rt.command(['insmod',b['provider'],*params],out/'load-provider.log')
        if not tc:rt.write_json(out/'provider-parameters.json',rt.parameters())
        rt.command(['insmod',b['payload']],out/'load-payload.log')
        data=rt.command([inputs['client'],str(BACKENDS[spec['arm']]),spec['workload'],str(spec['threads']),spec['observation']],out/'client.jsonl',timeout=120)
        logs();result['measurement']=validate([json.loads(line) for line in data.splitlines()],spec)
        health=Path('/sys/module/kd_mmap_fault/parameters/health').read_text().strip()
        rt.require(health=='files=0 destroyed=1 release_errors=0','mapping object did not drain')
        result['health']=health
        if tc:
            rt.require(Path('/sys/module/tclock_rwlock_backend_km/parameters/quiescent').read_text().strip()=='1','TCLock contexts not idle')
            result.update(tclock_quiescent=True,retired=None,jit_observation=None)
        else:
            registry=rt.registry();rt.require(not registry,'reader workload unexpectedly registered a JIT image')
            rt.write_json(out/'registry.json',registry)
            result['jit_observation']=dict(registry_empty=True,counters_bound=False,
                reason='Ordinary reader calls; no generated entry or lock-address observation binding')
            retired=json.loads(rt.command([sys.executable,ROOT/'disassem/device_session.py','retire'],out/'retire.json'))
            rt.require(retired==dict(state=2,modules=0,frames=0,writers=0),'exact source retirement differs')
            result['retired']=retired
        rt.command(['rmmod','kd_mmap_fault'],out/'unload-payload.log')
        rt.command(['rmmod','tclock_rwlock_backend_km' if tc else 'kdlock_km'],out/'unload-provider.log')
        logs();verify();idle(out.parent)
        result.update(state='COMPLETE',passed=True,drained=True)
    except BaseException as error:
        result.update(state='FAILED',error=repr(error));raise
    finally:
        finish_logs(out,result,logs,fd)
    return result


def specification(workload,n,arm,observation,repeat):
    return dict(workload=workload,threads=n,arm=arm,observation=observation,repeat=repeat,
        cpus=list(range(n)),collector_cpu=63,collector_shared=False,duration_ms=2000,
        peak_window_ms=300,peak_settle_ms=300,sample_ms=10)


def measurement_plan(single_round=False, workload=None):
    if single_round:
        rt.require(workload in ('mmap', 'fault'), 'select one single-round workload')
        arms = ('native',) if workload == 'mmap' else tuple(BACKENDS)
        return [dict(specification(workload, n, arm, 'plain', 0),
                     peak_policy='optional-positive-window')
                for n in list(range(1, 9)) + list(range(12, 61, 4)) for arm in arms]
    rt.require(workload is None, 'workload selection requires the single-round plan')
    plan = []
    for selected in ('mmap', 'fault'):
        arms = ['native'] if selected == 'mmap' else list(BACKENDS)
        for n in (1, 16):
            for repeat in range(3):
                order = arms[repeat % len(arms):] + arms[:repeat % len(arms)]
                for observation in (('plain', 'sampled') if repeat % 2 == 0 else ('sampled', 'plain')):
                    for arm in order:
                        plan.append(specification(selected, n, arm, observation, repeat))
    rt.require(len(plan) == 48, 'fixed matched plan differs')
    return plan


def distribution(values):
    mean=statistics.mean(values)
    return dict(n=len(values),minimum=min(values),maximum=max(values),median=statistics.median(values),
                cv_pct=100*statistics.pstdev(values)/mean,spread_pct=100*(max(values)-min(values))/statistics.median(values))


def summarize(rows):
    groups={};pairs={}
    for row in rows:
        key=(row['workload'],row['threads'],row['arm'],row['observation'])
        groups.setdefault(key,[]).append(row['measurement'])
        pairs.setdefault(key[:3]+(row['repeat'],),{})[row['observation']]=row['measurement']
    result=[]
    for key,values in groups.items():
        result.append(dict(workload=key[0],threads=key[1],arm=key[2],observation=key[3],
            whole_ops_s=distribution([v['whole_ops_s'] for v in values]),
            peak_ops_s=distribution([v['peak']['throughput_ops_s'] for v in values]),
            completed_operation_p95_ns=distribution([v['completed_operation_p95_ns'] for v in values]) if key[3]=='sampled' else None))
    overhead=[dict(workload=k[0],threads=k[1],arm=k[2],repeat=k[3],
        sampled_plain_whole_ratio=v['sampled']['whole_ops_s']/v['plain']['whole_ops_s'],
        sampled_plain_peak_ratio=v['sampled']['peak']['throughput_ops_s']/v['plain']['peak']['throughput_ops_s']) for k,v in pairs.items()]
    return dict(groups=result,observation_pairs=overhead,accepted=False,
                limits='Whole fault cycles include PTE reset; local readers only; host endpoint pending; seven mutex causes remain unresolved')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','measure'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--host-state',type=Path,required=True);p.add_argument('--source-manifest',type=Path)
    p.add_argument('--correctness-kd',type=Path);p.add_argument('--correctness-tc',type=Path)
    mm_platform.arguments(p)
    p.add_argument('--plain-only', action='store_true', help='prepare the plain client without latency sampling')
    p.add_argument('--single-round-grid', action='store_true', help='new plain 21-count plan, one repetition')
    p.add_argument('--workload', choices=('mmap','fault'))
    p.add_argument('--exploratory-host', action='store_true', help='retain failed strict host qualification explicitly')
    p.add_argument('--inputs',type=Path);kernel_identity.arguments(p);a=p.parse_args()
    rt.require(not a.plain_only or a.action == 'prepare', 'plain-only applies to preparation')
    rt.require(not a.single_round_grid or a.action == 'measure', 'single-round grid applies to measurement')
    rt.require(not a.exploratory_host or a.single_round_grid, 'exploratory host requires the explicit new plan')
    guest(a.boot_id);out=a.output.resolve();rt.require(not out.exists() and not out.is_relative_to(ROOT),'new evidence path required')
    idle(out.parent);out.mkdir(parents=True)
    result=dict(state='PREPARATION',passed=False,drained=False,accepted=False,boot_id=a.boot_id,action=a.action,sessions=[],
                single_round_grid=a.single_round_grid,exploratory_host=a.exploratory_host)
    rt.write_json(out/'result.json',result)
    try:
        host_check(a.host_state,out,a.action=='measure' and not a.exploratory_host,a.boot_id,
                   reference=a.host_reference,reference_sha256=a.host_reference_sha256)
        result['kernel_identity']=kernel_identity.capture(a,out,rt.command)
        result['kernel_binding']=mm_platform.kernel_binding(result['kernel_identity'],a.kernel_source,a.kernel_baseline)
        if a.action=='prepare':
            rt.require(a.source_manifest and a.correctness_kd and a.correctness_tc,'correctness and committed source required')
            manifest=load(a.source_manifest);kd=bundle(a.correctness_kd,result['kernel_binding']);tc=bundle(a.correctness_tc,result['kernel_binding'])
            rt.require(len(kd['result']['split_cases'])==12 and len(tc['result']['split_cases'])==6 and
                       kd['result']['source_commit']==tc['result']['source_commit'],'same-revision eighteen-case prerequisite')
            dirs=('include/','kernel_module/','daemon/','tclock_backend/','workload_modules/mmap_fault/','bench/mmap_fault/',
                  'bench/spin_cacheline/','disassem/','tests/protocols/','tests/unit/','kernel_baseline/',
                  'kernel_integration/linux70/','bench/basic/')
            selected={name:h for name,h in manifest['files'].items() if name.startswith(dirs) or name in
                      ('bench/archive_run.py',)}
            source=out/'source';files={}
            for name,h in selected.items():
                rt.require(rt.digest(ROOT/name)==h,'committed source changed: '+name)
                dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
                files[str(ROOT/name)]=files[str(dest)]=h
            shutil.copyfile(a.source_manifest,out/'committed-source.json')
            rt.command([sys.executable,'-m','pip','check'],out/'dependencies.log',timeout=60)
            rt.command(['make','-C',source/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],out/'basic.log',timeout=180)
            client=out/'timed-client'
            rt.command(['gcc','-O2','-g','-Wall','-Wextra','-Werror','-I'+str(source/'workload_modules/mmap_fault'),
                       source/'bench/mmap_fault/timed_client.c','-o',client],out/'build-client.log',timeout=60)
            files[str(client)]=rt.digest(client)
            for b in (kd,tc):files.update(b['files'])
            inputs=dict(kdlock=kd,tclock=tc,client=str(client),files=files,source_commit=manifest['commit'],
                        correctness_source_commit=kd['result']['source_commit'],kernel_binding=result['kernel_binding'])
            rt.write_json(out/'inputs.json',inputs)
            plan=[specification(w,n,arm,'plain' if a.plain_only else 'sampled',0) for w in ('mmap','fault') for n in (1,16)
                  for arm in (('native',) if w=='mmap' else tuple(BACKENDS))]
        else:
            rt.require(a.inputs is not None,'validated inputs required')
            inputs=load(a.inputs);prior=load(a.inputs.parent/'result.json')
            rt.require(inputs.get('kernel_binding')==prior.get('kernel_binding')==result['kernel_binding'],
                       'timing prerequisite kernel identity differs')
            rt.require(prior['passed'] and prior['drained'] and len(prior['sessions'])==8 and
                       all(r['passed'] and r['drained'] for r in prior['sessions']),'timed client correctness prerequisite incomplete')
            shutil.copyfile(a.inputs,out/'inputs.json')
            plan=measurement_plan(a.single_round_grid,a.workload)
        def verify():
            rt.require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==a.boot_id, 'guest boot changed')
            verify_maps(inputs['files'])
        verify();rt.write_json(out/'plan.json',plan);result.update(state='RUNNING',source_commit=inputs['source_commit'],planned=len(plan))
        for i,spec in enumerate(plan):
            name=f'{i:02d}-{spec["workload"]}-{spec["threads"]}-{spec["arm"]}-{spec["observation"]}-r{spec["repeat"]}'
            print('START',name,flush=True)
            row=session(out/name,spec,inputs,verify);row['name']=name;result['sessions'].append(row)
            rt.write_json(out/'result.json',result);print('FINISH',name,'PASS',flush=True)
        verify();idle(out.parent)
        if a.action=='measure':
            summary = (dict(single_round=True,accepted=False,variability=None,
                            sessions=result['sessions']) if a.single_round_grid else summarize(result['sessions']))
            rt.write_json(out/'summary.json',summary)
        result.update(state='COMPLETE',passed=True,drained=True,final_idle=True,host_endpoint='PENDING',basic_programs=2 if a.action=='prepare' else None)
    except BaseException as error:
        result.update(state='FAILED',error=repr(error));raise
    finally:rt.write_json(out/'result.json',result)
    print(json.dumps({k:result[k] for k in ('state','passed','drained','source_commit','planned')}))


if __name__=='__main__':main()
