#!/usr/bin/env python3
"""Serial recovery-VM correctness for opt-in backing-state mmap/fault locking."""
import argparse
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

DIRECTORIES = ('include','kernel_module','tclock_backend','workload_modules/mmap_fault',
               'bench/mmap_fault','tests/kernel/mmap_fault','tests/unit','disassem',
               'tests/protocols','kernel_baseline','bench/spin_cacheline')


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
    joined=[r for r in rows if r['event']=='joined']
    rt.require(len(joined)==1,'missing joined state')
    s=joined[0]
    rt.require(s['backend']==backend and s['vmas']==s['errors']==0 and
               s['reads']==s['read_ends'] and s['writes']==s['write_ends'] and
               s['scopes']==s['scope_ends']==5 and s['faults']>=408 and
               s['epoch']==(1000 if backend==2 else 1001) and
               s['downgrades']==(0 if backend==2 else 1), 'joined object state differs')
    created=[r for r in rows if r['event']=='create']
    selected=[backend,0,backend]+([0] if backend==2 else [])
    fallback=[0,int(backend!=0),0]+([1] if backend==2 else [])
    rt.require([r['selected'] for r in created]==selected and
               [r['fallback'] for r in created]==fallback and
               all(r['requested']==backend for r in created), 'backend/fallback identity differs')
    return dict(backend=backend,passed=True,probes=probes,joined=s,created=created,
                checks=rows[-1]['checks'],execution='ORIGIN_LOCAL',jit_bodies=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-manifest',type=Path,required=True)
    parser.add_argument('--backends',default='0,1',choices=('0,1','2'))
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
    manifest=json.loads(args.source_manifest.read_text())
    hashes={p:h for p,h in manifest['files'].items() if any(p.startswith(d+'/') for d in DIRECTORIES)}
    rt.require(hashes and len(manifest['commit'])==40,'committed source identities required')
    for name,digest in hashes.items():rt.require(rt.digest(ROOT/name)==digest,'source differs: '+name)
    out.mkdir(parents=True);source=out/'source'
    for name,digest in hashes.items():
        dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        rt.require(rt.digest(dest)==digest,'snapshot differs: '+name)
    shutil.copyfile(args.source_manifest,out/'committed-source.json')
    rt.write_json(out/'source-sha256.json',hashes)
    result=dict(state='STARTING',passed=False,drained=False,source_commit=manifest['commit'],
                source_manifest_sha256=rt.digest(args.source_manifest),source_files=len(hashes),
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                snapshot=os.environ['KDLOCK_SNAPSHOT_TAG'],backends=args.backends,
                production_protocol_changed=False,kernel_modified=False,full_suite=False,
                accepted=False,cases=[],script_sha256=rt.digest(Path(__file__)))
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
    try:
        result['kernel_identity']=kernel_identity.capture(args,out,rt.command)
        rt.command([sys.executable,'-m','pip','check'],out/'dependencies.log',timeout=60)
        rt.command(['make','-C',source/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],out/'basic.log',timeout=180)
        provider=source/'kernel_module/kdlock_km.ko'
        tc=source/'tclock_backend/tclock_rwlock_backend_km.ko'
        payload=source/'workload_modules/mmap_fault/kd_mmap_fault.ko'
        rt.command(['make','-C',provider.parent,'KDIR='+str(args.kernel_source),'W=1','KDLOCK_SELFTEST=0','UBSAN_SANITIZE=n'],out/'build-provider.log',timeout=180)
        rt.command(['make','-C',tc.parent,'KDIR='+str(args.kernel_source),'TCLOCK_RWLOCK=1','TCLOCK_NUMA=1'],out/'build-tclock.log',timeout=180)
        rt.command(['make','-C',payload.parent,'KDIR='+str(args.kernel_source),
            'KDLOCK_INCLUDE='+str(source/'include'),'TCLOCK_INCLUDE='+str(source/'tclock_backend/include'),
            'KBUILD_EXTRA_SYMBOLS='+str(provider.parent/'Module.symvers')+' '+str(tc.parent/'Module.symvers')],out/'build-payload.log',timeout=180)
        client=out/'client'
        rt.command(['gcc','-O2','-g','-Wall','-Wextra','-Werror','-pthread',
            '-I'+str(payload.parent),source/'bench/mmap_fault/client.c','-o',client],out/'build-client.log',timeout=60)
        binaries={str(p.relative_to(out)):rt.digest(p) for p in (provider,tc,payload,client)}
        rt.write_json(out/'binary-sha256.json',binaries)
        verify();archive.idle(out.parent,rt.idle)
        fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK);os.lseek(fd,0,os.SEEK_END)
        result['state']='RUNNING';rt.write_json(out/'result.json',result)
        rt.command(['insmod',provider,'bench_quiet=1','bench_complete_probe=1'],out/'load-provider.log')
        rt.command(['insmod',tc,'komb_batch_size=1024'],out/'load-tclock.log')
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
        counts=Path('/sys/module/kdlock_km/parameters')
        result['jit_bodies']=int((counts/'bench_jit_bodies').read_text())
        result['jit_completions']=int((counts/'bench_jit_completions').read_text())
        rt.require(result['jit_bodies']==result['jit_completions']==0,'unexpected generated execution')
        rt.require(Path('/sys/module/tclock_rwlock_backend_km/parameters/quiescent').read_text().strip()=='1','TCLock contexts not idle')
        rt.command(['rmmod','kd_mmap_fault'],out/'unload-payload.log')
        retired=json.loads(rt.command([sys.executable,source/'disassem/device_session.py','retire'],out/'retire.json'))
        rt.require(retired==dict(state=2,modules=0,writers=0,frames=0),'exact source retirement differs')
        rt.command(['rmmod','tclock_rwlock_backend_km'],out/'unload-tclock.log')
        rt.command(['rmmod','kdlock_km'],out/'unload-provider.log')
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
