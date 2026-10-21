#!/usr/bin/env python3
"""Focused Native shared-mm mmap writer correctness in the existing recovery VM."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('mw_common',ROOT/'bench/mmap_fault/timing.py')
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
rt=common.rt


def validate(rows,mode,n,iterations):
    identity=rows[0];last=rows[-1]
    rt.require(identity['event']=='identity' and identity['mm'] and identity['mmap_lock'] and identity['object'] and
               identity['tid']==identity['tgid'],'controller exact mm identity differs')
    rt.require(last['event']=='complete' and last['mode']==mode and last['passed'],'client completion missing')
    observations=[r for r in rows if r['event'] in ('scope_after','before_exit','before','after')]
    for row in observations:
        rt.require(row['object']==identity['object'] and row['faults']==row['context_errors']==0 and
                   row['maps']+row['clones']==row['closes']+row['vmas'] and row['observe']==1,
                   'VMA/fault/context accounting differs')
    if mode=='scope':
        s=observations[0]
        rt.require(len(rows)==3 and s['maps']==s['clones']==1 and s['closes']==s['foreign_rejects']==2 and not s['vmas'],
                   'foreign-mm rejection or split/unmap scope differs')
    elif mode=='exit':
        s=observations[0]
        rt.require(len(rows)==3 and s['maps']==s['vmas']==1 and s['clones']==s['closes']==s['foreign_rejects']==0,
                   'exit VMA-only setup differs')
    else:
        rt.require(last['joined']==len(last['workers'])==n and last['completed']==n*iterations and
                   len({w['tid'] for w in last['workers']})==n,'exact worker joins differ')
        for i,w in enumerate(last['workers']):
            rt.require(w['cpu']==i and w['tid']!=identity['tid'] and w['completed']==iterations and not w['errors'] and
                       all(w[k]==identity[k] for k in ('object','mm','mmap_lock','tgid')),
                       'workers did not share the exact native mm/mmap_lock')
        before=observations[0]
        rt.require(before['maps']==before['vmas']==(n if mode=='lifetime' else 0) and
                   not before['closes'] and not before['clones'] and not before['foreign_rejects'],'start state differs')
        if mode=='cycle':
            after=observations[1]
            rt.require(len(rows)==(5 if n>1 else 4) and after['maps']==after['closes']==n*iterations and
                       after['clones']==after['vmas']==after['foreign_rejects']==0 and
                       (n==1 or after['contended_mmaps']>0),'native writer contention or final VMA state differs')
            if n>1:
                stacks=[r for r in rows if r['event']=='writer_stack']
                rt.require(len(stacks)==1 and stacks[0]['tid'] in {w['tid'] for w in last['workers']} and
                           stacks[0]['mm']==identity['mm'] and stacks[0]['mmap_lock']==identity['mmap_lock'] and
                           stacks[0]['blocked']=='rwsem_down_write_slowpath' and
                           stacks[0]['acquire']=='down_write_killable' and
                           stacks[0]['caller'] in ('vm_mmap_pgoff','__vm_munmap'),
                           'actual same-mm Native writer wait was not observed')
                functions=re.findall(r'\] ([A-Za-z0-9_]+)\+',stacks[0]['raw_stack'])
                rt.require('rwsem_down_write_slowpath' in functions and
                           functions[functions.index('down_write_killable')+1]==stacks[0]['caller'],
                           'raw wait stack does not bind the immediate Native mmap-lock caller')
        else:rt.require(mode=='lifetime' and len(rows)==3 and iterations==1,'VMA-only lifetime differs')
    return dict(mode=mode,threads=n,iterations=iterations,passed=True,identity=identity,
                observations=observations,completion=last,protocol='NATIVE_MMAP_LOCK',delegated=False)


def idle(base):
    common.idle(base)
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:rt.require(path.read_text().strip()!='mw_worker','existing shared-mm worker')
        except FileNotFoundError:pass


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--source-manifest',type=Path,required=True)
    p.add_argument('--host-state',type=Path,required=True);common.kernel_identity.arguments(p);a=p.parse_args()
    common.guest();out=a.output.resolve();rt.require(not out.exists() and not out.is_relative_to(ROOT),'new evidence directory required')
    idle(out.parent);out.mkdir(parents=True)
    result=dict(state='PREPARATION',passed=False,drained=False,accepted=False,cases=[],kernel_modified=False,
                protocol='NATIVE_MMAP_LOCK',kd_integration=False,full_suite=False,boot_id=common.BOOT)
    rt.write_json(out/'result.json',result)
    fd=None;messages=''
    def logs():
        nonlocal messages
        if fd is None:return
        while True:
            try:messages+=os.read(fd,1<<20).decode(errors='replace')+'\n'
            except BlockingIOError:break
        (out/'kernel.log').write_text(messages)
        rt.require(not rt.FAULT.search(messages),'kernel fault; retain module','KERNEL_FAULT')
    try:
        common.host_check(a.host_state,out,False)
        result['kernel_identity']=common.kernel_identity.capture(a,out,rt.command)
        manifest=json.loads(a.source_manifest.read_text());source=out/'source'
        dirs=('workload_modules/mmap_writer/','bench/mmap_writer/','tests/kernel/mmap_writer/',
              'bench/mmap_fault/','bench/spin_cacheline/','tests/protocols/','disassem/','kernel_baseline/',
              'tests/unit/','include/','daemon/')
        hashes={k:h for k,h in manifest['files'].items() if k.startswith(dirs) or k in ('bench/archive_run.py','bench/mutex_api_compare/run.py')}
        for name,h in hashes.items():
            rt.require(rt.digest(ROOT/name)==h,'committed source changed: '+name)
            dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(a.source_manifest,out/'committed-source.json');rt.write_json(out/'source-sha256.json',hashes)
        result.update(source_commit=manifest['commit'],source_manifest_sha256=rt.digest(a.source_manifest),source_files=len(hashes),script_sha256=rt.digest(Path(__file__)))
        def verify():
            for name,h in hashes.items():rt.require(rt.digest(ROOT/name)==rt.digest(source/name)==h,'source changed: '+name)
        rt.command([sys.executable,'-m','pip','check'],out/'dependencies.log',timeout=60)
        rt.command(['make','-C',source/'tests/unit','run','PYTHON='+sys.executable,'PY_TESTS='],out/'basic.log',timeout=180)
        payload=source/'workload_modules/mmap_writer/kd_mmap_writer_native.ko'
        rt.command(['make','-C',payload.parent,'KDIR='+str(a.kernel_source),'W=1','UBSAN_SANITIZE=n'],out/'build-payload.log',timeout=180)
        imports=rt.command(['nm','-u',payload],out/'payload-imports.txt')
        rt.require(not re.search(r'\b(?:kd_|komb_)',imports),'Native baseline imported another protocol')
        client=out/'client'
        rt.command(['gcc','-O2','-g','-Wall','-Wextra','-Werror','-pthread','-I'+str(payload.parent),source/'bench/mmap_writer/client.c','-o',client],out/'build-client.log',timeout=60)
        binaries={str(p.relative_to(out)):rt.digest(p) for p in (payload,client)};rt.write_json(out/'binary-sha256.json',binaries)
        verify();idle(out.parent)
        fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK);os.lseek(fd,0,os.SEEK_END)
        rt.command(['insmod',payload,'observe=1'],out/'load-payload.log')
        result['state']='RUNNING';rt.write_json(out/'result.json',result)
        plan=[('scope',1,1),('cycle',1,1000),('cycle',16,5000),('lifetime',1,1),('lifetime',16,1),('exit',1,1)]
        for i,(mode,n,iterations) in enumerate(plan):
            name=f'{i:02d}-{mode}-{n}';print('START',name,flush=True)
            data=rt.command([client,mode,str(n),str(iterations)],out/(name+'.jsonl'),timeout=120)
            logs();case=validate([json.loads(line) for line in data.splitlines()],mode,n,iterations)
            health=Path('/sys/module/kd_mmap_writer_native/parameters/health').read_text().strip()
            rt.require(health==f'files=0 mm_refs=0 destroyed={i+1} release_errors=0','VFS/mm descriptor teardown differs')
            case.update(name=name,health=health);result['cases'].append(case);rt.write_json(out/'result.json',result)
            print('FINISH',name,'PASS',flush=True)
        rt.command(['rmmod','kd_mmap_writer_native'],out/'unload-payload.log')
        logs();verify();idle(out.parent)
        rt.require(all(rt.digest(out/name)==h for name,h in binaries.items()),'binary changed')
        result.update(state='COMPLETE',passed=True,drained=True,final_idle=True,source_unchanged=True,basic_programs=2,binaries=binaries)
    except BaseException as error:result.update(state='FAILED',error=repr(error));raise
    finally:
        rt.write_json(out/'result.json',result)
        if fd is not None:
            try:logs()
            finally:os.close(fd)
    print(json.dumps({k:result[k] for k in ('state','passed','drained','source_commit','basic_programs')}))


if __name__=='__main__':main()
