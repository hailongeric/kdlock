#!/usr/bin/env python3
"""Serial recovery-VM correctness for opt-in backing-state mmap/fault locking."""
import argparse
import datetime
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity

DIRECTORIES = ('include','kernel_module','daemon','tclock_backend','workload_modules/mmap_fault',
               'bench/mmap_fault','tests/kernel/mmap_fault','tests/unit','disassem',
               'tests/protocols','kernel_baseline','bench/spin_cacheline',
               'bench/tclock_compare/allocator_guard')


def validate(rows, backend):
    rt.require(rows and rows[-1]['event']=='complete' and rows[-1]['passed'] and
               rows[-1]['backend']==backend, 'missing successful client receipt')
    probes=[r for r in rows if r['event']=='probe']
    rt.require([r['action'] for r in probes]==list(range(5)), 'missing fault outcome')
    expected=[(0,1,1,0,0,0,0,0),(0,2,2,1,0,0,1,0),
              (-11,1,1,0,1,0,0,0),(0,1,1,0,0,1,0,0),(-116,1,2,1,0,0,0,1)]
    fields=('result','attempts','acquisitions','retries','nowait','completed','revalidated','stale')
    for row, values in zip(probes,expected):
        rt.require(tuple(row[k] for k in fields)==values and row['callbacks']==row['attempts']
                   and row['releases']==row['acquisitions'] and
                   row['pause_timeout']==row['final_held']==0, 'fault ownership outcome differs')
    denied=[r for r in rows if r['event']=='rejected_mode']
    rt.require(len(denied)==1 and denied[0]==dict(event='rejected_mode',action=0,
        result=-116,attempts=0,acquisitions=1,releases=1,callbacks=0,retries=0,
        nowait=0,completed=0,revalidated=0,stale=1,pause_timeout=0,final_held=0),
        'inaccessible VMA must be refused before handle_mm_fault')
    joined=[r for r in rows if r['event']=='joined']
    rt.require(len(joined)==1,'missing joined state')
    s=joined[0]
    rt.require(s['backend']==backend and s['vmas']==s['errors']==0 and
               s['reads']==s['read_ends'] and s['writes']==s['write_ends'] and
               s['scopes']==s['scope_ends']==6 and s['faults']>=408 and
               s['epoch']==(1000 if backend==2 else 1001) and
               s['downgrades']==(0 if backend==2 else 1), 'joined object state differs')
    created=[r for r in rows if r['event']=='create']
    selected=[backend,0,backend]+([0] if backend==2 else [])
    fallback=[0,int(backend!=0),0]+([1] if backend==2 else [])
    rt.require([r['selected'] for r in created]==selected and
               [r['fallback'] for r in created]==fallback and
               all(r['requested']==backend for r in created), 'backend/fallback identity differs')
    return dict(backend=backend,passed=True,probes=probes,rejected_mode=denied[0],joined=s,created=created,
                checks=rows[-1]['checks'],fault_execution='ORIGIN_TASK',
                backing_execution='TCLOCK_SHORT' if backend==2 else 'ORDINARY_LOCAL')


def validate_split(rows, backend, mode, workers, iterations):
    before, ready, *tail = rows
    last = tail[-1]
    rt.require(before['event']=='before' and ready['event']=='ready' and
               ready['mode']==mode and ready['workers']==workers and
               len(set(ready['pids']))==workers and
               ready['vma_only']==(mode=='lifetime'), 'split start receipt differs')
    rt.require(before['backend']==backend and before['features']==0 and
               all(before[k]==0 for k in ('active_probe','epoch','faults','reads','read_ends',
                   'writes','write_ends','context_errors','data_errors','scopes','scope_ends','fallback')) and
               before['vmas']==(0 if mode=='mmap' else workers-(mode=='concurrent')),
               'setup must not trigger a fault or a backing acquisition')
    rt.require(last['event']=='complete' and last['passed'] and last['backend']==backend and
               last['mode']==mode and last['iterations']==iterations and last['joined']==workers and
               last['completed']==iterations*workers and len(last['workers'])==workers,
               'split completion differs')
    rt.require(all(row==dict(worker=i,pid=ready['pids'][i],cpu=i,completed=iterations,errors=0)
                   for i,row in enumerate(last['workers'])), 'split worker receipt differs')
    after=None
    if mode=='lifetime':
        rt.require(len(tail)==1, 'VMA-only final object cannot be queried after destruction')
    else:
        rt.require(len(tail)==2 and tail[0]['event']=='after', 'missing joined object')
        after=tail[0]
        faults=0 if mode=='mmap' else iterations*(workers-(mode=='concurrent'))
        writes=iterations if mode=='concurrent' else 0
        rt.require(after['backend']==backend and after['features']==0 and
                   all(after[k]==0 for k in ('vmas','active_probe','context_errors','data_errors',
                                            'scopes','scope_ends','fallback')) and
                   after['faults']==after['reads']==after['read_ends']==faults and
                   after['epoch']==after['writes']==after['write_ends']==writes,
                   'mmap/fault separation or shared-reader accounting differs')
    return dict(backend=backend,mode=mode,workers=workers,iterations=iterations,
                passed=True,before=before,after=after,completion=last,
                execution='NATIVE_MMAP_ONLY' if mode=='mmap' else 'ORIGIN_FAULT_LOCAL_READER',
                delegated_reader=False,independent_native_mm=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-manifest',type=Path,required=True)
    parser.add_argument('--host-state',type=Path,required=True)
    parser.add_argument('--backends',default='0,1',choices=('0,1','2'))
    parser.add_argument('--native-kd-result',type=Path,
                        help='required successful same-revision result before TCLock')
    parser.add_argument('--split',action='store_true',
                        help='also validate mmap without faults and separate CPU-fault workloads')
    kernel_identity.arguments(parser)
    args=parser.parse_args()
    rt.require(os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2' and
               str(ROOT)=='/root/host_fs/kdlock' and
               Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='b65f0205-c8f9-4385-8b13-039cbce243a6' and
               os.environ.get('KDLOCK_RECOVERY_CONFIRMED')=='1' and
               os.environ.get('KDLOCK_SNAPSHOT_TAG')=='before-mutex-kdonly-20261017T140354Z',
               'same confirmed recovery VM required')
    rt.require(sys.executable=='/root/kdlock-translation-venv-20261019/bin/python3' and
               shutil.which('python3')==sys.executable,'pinned Python required')
    spec=importlib.util.spec_from_file_location('mmap_archive',ROOT/'bench/archive_run.py')
    archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)
    out=args.output.resolve();rt.require(not out.exists() and not out.is_relative_to(ROOT),'new evidence output required')
    archive.idle(out.parent,rt.idle)
    host=json.loads(args.host_state.read_text())
    age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(host['captured_utc'])).total_seconds()
    rt.require(0<=age<=300 and host['snapshot_listed'] and host['pins_verified'] and
               host['recovery_snapshot']==os.environ['KDLOCK_SNAPSHOT_TAG'] and
               len(host['qemu'])==1 and host['qemu'][0]['pid']==257489,
               'fresh evidence for the same host and recovery snapshot required')
    manifest=json.loads(args.source_manifest.read_text())
    tc_run=args.backends=='2'
    prerequisite=None
    if tc_run:
        rt.require(args.native_kd_result is not None,'Native/KD result required first')
        prior=json.loads(args.native_kd_result.read_text())
        rt.require(prior['passed'] and prior['drained'] and prior['final_idle'] and
                   prior['backends']=='0,1' and [c['backend'] for c in prior['cases']]==[0,1] and
                   prior['source_commit']==manifest['commit'] and
                   prior['source_manifest_sha256']==rt.digest(args.source_manifest),
                   'same-revision Native/KD correctness prerequisite differs')
        prerequisite=dict(path=str(args.native_kd_result),sha256=rt.digest(args.native_kd_result))
    hashes={p:h for p,h in manifest['files'].items()
            if p=='bench/archive_run.py' or any(p.startswith(d+'/') for d in DIRECTORIES)}
    rt.require(hashes and len(manifest['commit'])==40,'committed source identities required')
    for name,digest in hashes.items():rt.require(rt.digest(ROOT/name)==digest,'source differs: '+name)
    out.mkdir(parents=True);source=out/'source'
    for name,digest in hashes.items():
        dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        rt.require(rt.digest(dest)==digest,'snapshot differs: '+name)
    shutil.copyfile(args.source_manifest,out/'committed-source.json')
    shutil.copyfile(args.host_state,out/'host-before.json')
    rt.write_json(out/'source-sha256.json',hashes)
    result=dict(state='STARTING',passed=False,drained=False,source_commit=manifest['commit'],
                source_manifest_sha256=rt.digest(args.source_manifest),source_files=len(hashes),
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                snapshot=os.environ['KDLOCK_SNAPSHOT_TAG'],backends=args.backends,
                production_protocol_changed=False,kernel_modified=False,full_suite=False,
                accepted=False,cases=[],split_cases=[],split=args.split,native_kd_prerequisite=prerequisite,
                provider='tclock' if tc_run else 'kdlock',script_sha256=rt.digest(Path(__file__)))
    rt.write_json(out/'result.json',result)
    fd=None;messages=''
    def logs():
        nonlocal messages
        if fd is None:return
        while True:
            try:messages+=os.read(fd,1<<20).decode(errors='replace')+'\n'
            except BlockingIOError:break
        (out/'kernel.log').write_text(messages)
        rt.require(not rt.FAULT.search(messages),'kernel fault; retain all modules','KERNEL_FAULT')
    def verify():
        for p,h in hashes.items():
            rt.require(rt.digest(ROOT/p)==rt.digest(source/p)==h,'source changed: '+p)
        for p,h in prepared.items():
            rt.require(rt.digest(out/'build/provider'/p)==h,'prepared provider changed: '+p)
    prepared={}
    try:
        result['kernel_identity']=kernel_identity.capture(args,out,rt.command)
        rt.command([sys.executable,'-m','pip','check'],out/'dependencies.log',timeout=60)
        packages={p:importlib.metadata.version(p) for p in ('miasm','future','pyparsing','pyelftools')}
        rt.require(packages==dict(miasm='0.1.5',future='1.0.0',pyparsing='2.4.7',pyelftools='0.27'),'dependency versions differ')
        topology=rt.capture_topology([0,1,2,3,4,63])
        rt.require(topology['online_cpus']==list(range(64)) and topology['role_nodes']==[0,0,0,0,0,1],'guest topology differs')
        rt.write_json(out/'environment.json',dict(packages=packages,topology=topology,
            python=sys.executable,cmdline=Path('/proc/cmdline').read_text(),argv=sys.argv))
        rt.command(['make','-C',source/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],out/'basic.log',timeout=180)
        if tc_run:
            provider=source/'tclock_backend/tclock_rwlock_backend_km.ko'
            build=['TCLOCK_RWLOCK=1','TCLOCK_NUMA=1']
        else:
            spec=importlib.util.spec_from_file_location('mmap_prepare',source/'bench/spin_cacheline/provider/prepare.py')
            preparation=importlib.util.module_from_spec(spec);spec.loader.exec_module(preparation)
            prepared=preparation.prepare(out/'build/provider',source)['prepared']
            rt.write_json(out/'prepared-source-sha256.json',prepared)
            provider=out/'build/provider/kernel_module/kdlock_km.ko'
            build=['W=1','KDLOCK_SELFTEST=0','KDLOCK_NUMA=1','KDLOCK_SPIN_BATCH=1024','UBSAN_SANITIZE=n']
        payload=source/'workload_modules/mmap_fault/kd_mmap_fault.ko'
        guard=source/'bench/tclock_compare/allocator_guard/tc_allocator_guard.ko'
        rt.command(['make','-C',guard.parent,'KDIR='+str(args.kernel_source)],out/'build-guard.log',timeout=180)
        rt.command(['make','-C',provider.parent,'KDIR='+str(args.kernel_source),*build],out/'build-provider.log',timeout=180)
        rt.command(['make','-C',payload.parent,'KDIR='+str(args.kernel_source),
            'KDLOCK_INCLUDE='+str(source/'include'),'TCLOCK_INCLUDE='+str(source/'tclock_backend/include'),
            'MF_TC_BUILD='+str(int(tc_run)),
            'KBUILD_EXTRA_SYMBOLS='+str(provider.parent/'Module.symvers')],out/'build-payload.log',timeout=180)
        mode=rt.command(['modinfo','-F','mmap_provider',payload],out/'payload-mode.txt').strip()
        rt.require(mode==result['provider'],'compiled payload mode differs')
        imports=set(rt.command(['nm','-u',payload],out/'payload-imports.txt').split())
        rt.require(('komb_read_lock' in imports)==tc_run and
                   ('kd_down_read' in imports)==(not tc_run) and
                   not any(n.startswith('kd_') if tc_run else n.startswith('komb_') for n in imports),
                   'payload imports an unavailable provider')
        client=out/'client'
        rt.command(['gcc','-O2','-g','-Wall','-Wextra','-Werror','-pthread',
            '-I'+str(payload.parent),source/'bench/mmap_fault/client.c','-o',client],out/'build-client.log',timeout=60)
        binaries={str(p.relative_to(out)):rt.digest(p) for p in (provider,payload,client,guard)}
        split_client=out/'split-client'
        if args.split:
            rt.command(['gcc','-O2','-g','-Wall','-Wextra','-Werror',
                '-I'+str(payload.parent),source/'bench/mmap_fault/split_client.c','-o',split_client],
                out/'build-split-client.log',timeout=60)
            binaries[str(split_client.relative_to(out))]=rt.digest(split_client)
        rt.write_json(out/'binary-sha256.json',binaries)
        verify();archive.idle(out.parent,rt.idle)
        fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK);os.lseek(fd,0,os.SEEK_END)
        result['state']='RUNNING';rt.write_json(out/'result.json',result)
        rt.command(['insmod',guard],out/'load-guard.log')
        rt.command(['rmmod','tc_allocator_guard'],out/'unload-guard.log')
        parameters=['komb_batch_size=1024'] if tc_run else ['bench_quiet=1','bench_complete_probe=1','jit_timing=0']
        rt.command(['insmod',provider,*parameters],out/'load-provider.log')
        if not tc_run:
            params=rt.parameters();rt.write_json(out/'provider-parameters.json',params)
            rt.require(params['bench_quiet']==params['bench_complete_probe']=='Y' and params['jit_timing']=='N','provider observation settings differ')
        rt.command(['insmod',payload],out/'load-payload.log')
        for backend in map(int,args.backends.split(',')):
            print('START mmap/fault backend',backend,flush=True)
            data=rt.command([client,str(backend)],out/f'client-{backend}.jsonl',timeout=120)
            logs()
            case=validate([json.loads(line) for line in data.splitlines()],backend)
            case['health']=Path('/sys/module/kd_mmap_fault/parameters/health').read_text().strip()
            rt.require(re.fullmatch(r'files=0 destroyed=\d+ release_errors=0',case['health']) is not None,'callback/file storage did not drain')
            result['cases'].append(case);rt.write_json(out/'result.json',result)
            print('FINISH mmap/fault backend',backend,'PASS',flush=True)
            if args.split:
                for mode,workers,iterations in (('mmap',1,1000),('mmap',16,1000),
                        ('fault',1,5000),('fault',16,5000),('concurrent',16,1000),('lifetime',16,1000)):
                    print('START split',backend,mode,workers,flush=True)
                    name=f'split-{backend}-{mode}-{workers}'
                    data=rt.command([split_client,str(backend),mode,str(workers),str(iterations)],
                                    out/(name+'.jsonl'),timeout=120)
                    logs()
                    split_case=validate_split([json.loads(line) for line in data.splitlines()],
                                              backend,mode,workers,iterations)
                    health=Path('/sys/module/kd_mmap_fault/parameters/health').read_text().strip()
                    rt.require(re.fullmatch(r'files=0 destroyed=\d+ release_errors=0',health) is not None,
                               'split callback/file storage did not drain')
                    split_case['health']=health
                    result['split_cases'].append(split_case);rt.write_json(out/'result.json',result)
                    print('FINISH split',backend,mode,workers,'PASS',flush=True)
        result['jit_counts_observed']=not tc_run
        if tc_run:
            rt.require(not Path('/sys/module/kdlock_km').exists(),'unexpected KD provider')
            rt.require(Path('/sys/module/tclock_rwlock_backend_km/parameters/quiescent').read_text().strip()=='1','TCLock contexts not idle')
            result.update(tclock_quiescent=True,jit_bodies=None,jit_completions=None)
        else:
            rt.require(not Path('/sys/module/tclock_rwlock_backend_km').exists(),'unexpected TCLock provider')
            counts=Path('/sys/module/kdlock_km/parameters')
            result['jit_bodies']=int((counts/'bench_jit_bodies').read_text())
            result['jit_completions']=int((counts/'bench_jit_completions').read_text())
            rt.require(result['jit_bodies']==result['jit_completions']==0,'unexpected generated execution')
        rt.command(['rmmod','kd_mmap_fault'],out/'unload-payload.log')
        retired=None
        if not tc_run:
            retired=json.loads(rt.command([sys.executable,source/'disassem/device_session.py','retire'],out/'retire.json'))
            rt.require(retired==dict(state=2,modules=0,writers=0,frames=0),'exact source retirement differs')
        rt.command(['rmmod','tclock_rwlock_backend_km' if tc_run else 'kdlock_km'],out/'unload-provider.log')
        logs();verify();archive.idle(out.parent,rt.idle)
        rt.require(all(rt.digest(out/p)==h for p,h in binaries.items()),'binary changed')
        result.update(state='COMPLETE',passed=True,drained=True,retired=retired,final_idle=True,
                      source_unchanged=True,binaries=binaries,basic_programs=2)
    except BaseException as error:
        result.update(state='FAILED',error=repr(error))
        raise
    finally:
        rt.write_json(out/'result.json',result)
        if fd is not None:
            try:logs()
            finally:os.close(fd)
    print(json.dumps(result))


if __name__=='__main__':
    main()
