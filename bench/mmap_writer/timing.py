#!/usr/bin/env python3
"""Serial Native shared-mm mmap timing; unchanged VM, exact callbacks and drain."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'bench/mmap_fault'))
import timing as common
rt=common.rt
check=common.module('mw_correctness',ROOT/'tests/kernel/mmap_writer/run.py')


def validate(rows,spec):
    rt.require(len(rows)==2 and rows[0]['event']=='ready','missing identity/start receipt')
    identity=rows[0]['identity'];m=rows[1];n=spec['threads']
    rt.require(identity['object'] and identity['mm'] and identity['mmap_lock'] and identity['tid']==identity['tgid'],
               'invalid controller identity')
    rt.require(m['event']=='measurement' and m['complete'] and m['data_ok'] and m['workload']=='mmap-shared-mm' and
               m['threads']==m['joined']==n and m['observation']==spec['observation'] and len(m['workers'])==n,
               'incomplete/wrong measurement')
    ws=m['workers'];completed=sum(w['completed'] for w in ws)
    rt.require(completed==m['completed']>0 and m['worker_cpu_ns']==sum(w['cpu_ns'] for w in ws) and
               m['finished_ns']==max(w['finished_ns'] for w in ws) and m['wall_ns']==m['finished_ns']-m['started_ns']>0 and
               len({w['identity']['tid'] for w in ws})==n,'whole-operation or thread accounting differs')
    latency=[]
    for i,w in enumerate(ws):
        who=w['identity']
        rt.require(w['cpu']==w['observed_cpu']==i and not w['error'] and w['completed']>0 and w['cpu_ns']>0 and
                   who['tid']!=identity['tid'] and all(who[k]==identity[k] for k in ('object','mm','mmap_lock','tgid')),
                   'worker did not use the exact shared native mm/lock')
        first=(-i)%64;expected=max(0,1+(w['completed']-1-first)//64) if spec['observation']=='sampled' else 0
        rt.require(len(w['latency_ns'])==expected<=65536 and all(type(v) is int and v>0 for v in w['latency_ns']),
                   'latency coverage or capacity differs')
        latency.extend(w['latency_ns'])
    before,after=m['before'],m['after']
    quiet=('clones','vmas','faults','context_errors','foreign_rejects','contended_mmaps','observe')
    rt.require(before['object']==after['object']==identity['object'] and before['maps']==before['closes']==0 and
               after['maps']==after['closes']==completed and all(before[k]==after[k]==0 for k in quiet),
               'exact VMA/fault/observation accounting differs')
    peak=common.analyze_peak(m,spec);latency.sort()
    rt.require(bool(latency)==(spec['observation']=='sampled'),'latency mode differs')
    return dict(completed=completed,whole_ops_s=completed*1e9/m['wall_ns'],peak=peak,
        latency_samples=len(latency),completed_operation_p95_ns=latency[math.ceil(.95*len(latency))-1] if latency else None,
        latency_definition='One shared-mm mmap plus munmap cycle, untouched payload range',
        execution='NATIVE_MMAP_LOCK',delegated=False,errors=0,callback_count=after['maps'],fault_callbacks=0)


def session(out,spec,inputs):
    check.idle(out.parent);common.verify_maps(inputs['files']);out.mkdir()
    result=dict(**spec,state='RUNNING',passed=False,drained=False,accepted=False)
    rt.write_json(out/'result.json',result)
    fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK);os.lseek(fd,0,os.SEEK_END);messages=''
    def logs():
        nonlocal messages
        while True:
            try:messages+=os.read(fd,1<<20).decode(errors='replace')+'\n'
            except BlockingIOError:break
        (out/'kernel.log').write_text(messages);rt.require(not rt.FAULT.search(messages),'kernel fault; retain payload')
    try:
        rt.command(['insmod',inputs['payload'],'observe=0'],out/'load-payload.log')
        data=rt.command([inputs['client'],str(spec['threads']),spec['observation']],out/'client.jsonl',timeout=120)
        logs();result['measurement']=validate([json.loads(line) for line in data.splitlines()],spec)
        health=Path('/sys/module/kd_mmap_writer_native/parameters/health').read_text().strip()
        rt.require(health=='files=0 mm_refs=0 destroyed=1 release_errors=0','VFS/mm references did not drain')
        result['health']=health
        rt.command(['rmmod','kd_mmap_writer_native'],out/'unload-payload.log')
        logs();common.verify_maps(inputs['files']);check.idle(out.parent)
        result.update(state='COMPLETE',passed=True,drained=True)
    except BaseException as error:result.update(state='FAILED',error=repr(error));raise
    finally:
        common.finish_logs(out,result,logs,fd)
    return result


def spec(n,observation,repeat):
    return dict(workload='mmap-shared-mm',threads=n,arm='native',observation=observation,repeat=repeat,
                cpus=list(range(n)),collector_cpu=63,collector_shared=False,duration_ms=2000,
                peak_window_ms=300,peak_settle_ms=300,sample_ms=10,queue_observer=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','measure'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--host-state',type=Path,required=True)
    p.add_argument('--source-manifest',type=Path);p.add_argument('--correctness',type=Path);p.add_argument('--inputs',type=Path)
    common.mm_platform.arguments(p);common.kernel_identity.arguments(p)
    a=p.parse_args();common.guest(a.boot_id);out=a.output.resolve()
    rt.require(not out.exists() and not out.is_relative_to(ROOT),'new evidence directory required');check.idle(out.parent);out.mkdir(parents=True)
    result=dict(state='PREPARATION',passed=False,drained=False,accepted=False,boot_id=a.boot_id,action=a.action,sessions=[],
                kd_integration=False,kernel_modified=False,protocol='NATIVE_MMAP_LOCK')
    try:
        common.host_check(a.host_state,out,a.action=='measure',a.boot_id,
                          reference=a.host_reference,reference_sha256=a.host_reference_sha256)
        result['kernel_identity']=common.kernel_identity.capture(a,out,rt.command)
        result['kernel_binding']=common.mm_platform.kernel_binding(result['kernel_identity'],a.kernel_source,
                                      a.kernel_baseline,private_backing_locks=False)
        if a.action=='prepare':
            rt.require(a.correctness and a.source_manifest,'correctness and committed inputs required')
            prior=common.load(a.correctness/'result.json')
            rt.require(prior.get('kernel_binding')==result['kernel_binding'],
                       'writer correctness kernel identity differs')
            rt.require(prior['passed'] and prior['drained'] and prior['final_idle'] and prior['basic_programs']==2 and
                       len(prior['cases'])==6 and all(v['passed'] for v in prior['cases']), 'focused correctness incomplete')
            files={str(a.correctness/'result.json'):rt.digest(a.correctness/'result.json')}
            for manifest_name,root in [('source-sha256.json',a.correctness/'source'),('binary-sha256.json',a.correctness)]:
                receipt=a.correctness/manifest_name;files[str(receipt)]=rt.digest(receipt)
                files.update({str(root/name):h for name,h in common.load(receipt).items()})
            for name,h in common.load(a.correctness/'source-sha256.json').items():
                if name.startswith('workload_modules/mmap_writer/'):rt.require(rt.digest(ROOT/name)==h,'validated payload source changed')
            manifest=common.load(a.source_manifest);source=out/'source'
            dirs=('bench/mmap_writer/','tests/kernel/mmap_writer/','workload_modules/mmap_writer/', 'bench/mmap_fault/',
                  'bench/spin_cacheline/','tests/unit/','tests/protocols/','include/','daemon/','disassem/','kernel_baseline/',
                  'kernel_integration/linux70/','bench/basic/')
            selected={k:h for k,h in manifest['files'].items() if k.startswith(dirs) or k in
                      ('bench/archive_run.py','bench/mmap_lock/eligibility.py')}
            for name,h in selected.items():
                rt.require(rt.digest(ROOT/name)==h,'committed input changed: '+name)
                dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
                files[str(ROOT/name)]=files[str(dest)]=h
            shutil.copyfile(a.source_manifest,out/'committed-source.json');rt.write_json(out/'source-sha256.json',selected)
            rt.command([sys.executable,'-m','pip','check'],out/'dependencies.log',timeout=60)
            rt.command(['make','-C',source/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],out/'basic.log',timeout=180)
            client=out/'timed-client'
            rt.command(['gcc','-O2','-g','-Wall','-Wextra','-Werror','-pthread','-I'+str(source/'workload_modules/mmap_writer'),
                        source/'bench/mmap_writer/timed_client.c','-o',client],out/'build-client.log',timeout=60)
            files[str(client)]=rt.digest(client)
            inputs=dict(files=files,client=str(client),payload=str(a.correctness/'source/workload_modules/mmap_writer/kd_mmap_writer_native.ko'),
                        source_commit=manifest['commit'],correctness_source_commit=prior['source_commit'],
                        kernel_binding=result['kernel_binding'])
            rt.write_json(out/'inputs.json',inputs);plan=[spec(n,mode,0) for n in (1,16) for mode in ('plain','sampled')]
        else:
            rt.require(a.inputs is not None,'validated timing inputs required');inputs=common.load(a.inputs)
            prior=common.load(a.inputs.parent/'result.json')
            rt.require(inputs.get('kernel_binding')==prior.get('kernel_binding')==result['kernel_binding'],
                       'timing prerequisite kernel identity differs')
            rt.require(prior['passed'] and prior['drained'] and prior['final_idle'] and len(prior['sessions'])==4 and
                       all(v['passed'] and v['drained'] for v in prior['sessions']),'timed client correctness incomplete')
            shutil.copyfile(a.inputs,out/'inputs.json')
            plan=[spec(n,mode,repeat) for n in (1,16) for repeat in range(3)
                  for mode in (('plain','sampled') if repeat%2==0 else ('sampled','plain'))]
        common.verify_maps(inputs['files']);rt.write_json(out/'plan.json',plan)
        result.update(state='RUNNING',source_commit=inputs['source_commit'],planned=len(plan))
        for i,item in enumerate(plan):
            rt.require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==a.boot_id,'guest boot changed')
            name=f'{i:02d}-mmap-shared-mm-{item["threads"]}-{item["observation"]}-r{item["repeat"]}'
            print('START',name,flush=True);row=session(out/name,item,inputs);row['name']=name
            result['sessions'].append(row);rt.write_json(out/'result.json',result);print('FINISH',name,'PASS',flush=True)
        common.verify_maps(inputs['files']);check.idle(out.parent)
        if a.action=='measure':
            summary=common.summarize(result['sessions']);summary['limits']='Native instrumented shared-mm baseline only; endpoint pending; seven mutex causes unresolved'
            rt.write_json(out/'summary.json',summary)
        result.update(state='COMPLETE',passed=True,drained=True,final_idle=True,host_endpoint='PENDING',basic_programs=2 if a.action=='prepare' else None)
    except BaseException as error:result.update(state='FAILED',error=repr(error));raise
    finally:rt.write_json(out/'result.json',result)
    print(json.dumps({k:result[k] for k in ('state','passed','drained','source_commit','planned')}))


if __name__=='__main__':main()
