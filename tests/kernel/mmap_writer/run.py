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
sys.path.insert(0,str(ROOT/'bench/mmap_lock'))
import eligibility
spec=importlib.util.spec_from_file_location('mw_common',ROOT/'bench/mmap_fault/timing.py')
common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
rt=common.rt
sites_check=common.module('linux70_writer_sites',ROOT/'bench/mmap_writer/sites.py')
# Historical fixed receipts keep their original default verifier. New live
# runs below require a reviewed, re-derived Linux 7 ELF receipt explicitly.
WRITER_SITES=json.loads(Path(__file__).with_name('writer_sites.json').read_text())


def validate(rows,mode,n,iterations,writer_proof=None,eligibility_policy=eligibility.STRICT):
    raw=[r for r in rows if r['event']=='stack_observation']
    rt.require(len(raw)<=4*n and all(r['raw_stack'] for r in raw),'invalid diagnostic stack observations')
    rows=[r for r in rows if r['event']!='stack_observation']
    identity=rows[0];last=rows[-1]
    rt.require(eligibility.policy(last)==eligibility_policy,'fixed completion eligibility differs')
    observed=True
    if eligibility_policy==eligibility.FUNCTIONAL:
        rt.require(mode=='cycle' and n>1 and last.get('functional_complete') is True and last.get('passed') is True,
                   'functional cycle completion required')
        observed=eligibility.observation(last)=='observed'
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
            rt.require(len(rows)==(5 if n>1 and observed else 4) and after['maps']==after['closes']==n*iterations and
                       after['clones']==after['vmas']==after['foreign_rejects']==0 and
                       (n==1 or after['contended_mmaps']>0),'native writer contention or final VMA state differs')
            if n>1 and observed:
                stacks=[r for r in rows if r['event']=='writer_stack']
                rt.require(len(stacks)==1 and stacks[0]['tid'] in {w['tid'] for w in last['workers']} and
                           stacks[0]['mm']==identity['mm'] and stacks[0]['mmap_lock']==identity['mmap_lock'],
                           'actual same-mm writer wait identity was not observed')
                if writer_proof is not None:
                    # A different kernel must supply its own exact ELF chain
                    # verifier. Business, identity and teardown checks stay
                    # shared; the recovery default below remains unchanged.
                    writer_proof(stacks[0])
                else:
                    rt.require(stacks[0]['proof']=='FILTERED_SCHED_RETURN_SITE' and
                           stacks[0]['acquire']=='down_write_killable' and
                           stacks[0]['caller'] in ('vm_mmap_pgoff','__vm_munmap'),
                           'actual same-mm Native writer wait was not observed')
                    stack=stacks[0];site=WRITER_SITES['sites'][stack['caller']]
                    frames=re.findall(r'\] ([A-Za-z0-9_]+)\+0x([0-9a-f]+)/',stack['raw_stack'])
                    rt.require(frames and frames[0][0]==stack['caller'] and
                           int(frames[0][1],16)==stack['return_offset']==site['return_offset'] and
                           stack['state_before']==stack['state_after']=='D' and
                           stack['wchan_before']==stack['wchan_after']==stack['caller'] and
                           stack['schedstat_before']==stack['schedstat_after'] and
                           len(stack['schedstat_before'].split())==3 and
                           all(v.isdigit() for v in stack['schedstat_before'].split()),
                           'raw stack/ELF return site or sleeping task bracket differs')
        else:rt.require(mode=='lifetime' and len(rows)==3 and iterations==1,'VMA-only lifetime differs')
    result=dict(mode=mode,threads=n,iterations=iterations,passed=True,identity=identity,
                observations=observations,completion=last,protocol='NATIVE_MMAP_LOCK',delegated=False,
                **eligibility.fields(eligibility_policy))
    if eligibility_policy==eligibility.FUNCTIONAL:
        rt.require(sum(r['event']=='writer_stack' for r in rows)==int(observed),
                   'observation status differs from witness')
        result['writer_observation']=eligibility.observation(last)
    return result


def idle(base):
    common.idle(base)
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:rt.require(path.read_text().strip() not in ('mw_worker','mw_time_worker'),'existing shared-mm worker')
        except FileNotFoundError:pass


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--source-manifest',type=Path,required=True)
    p.add_argument('--host-state',type=Path,required=True)
    p.add_argument('--writer-sites',type=Path,required=True)
    p.add_argument('--writer-sites-sha256',required=True)
    common.mm_platform.arguments(p);common.kernel_identity.arguments(p);a=p.parse_args()
    common.guest(a.boot_id);out=a.output.resolve();rt.require(not out.exists() and not out.is_relative_to(ROOT),'new evidence directory required')
    idle(out.parent);out.mkdir(parents=True)
    result=dict(state='PREPARATION',passed=False,drained=False,accepted=False,cases=[],kernel_modified=False,
                protocol='NATIVE_MMAP_LOCK',kd_integration=False,full_suite=False,boot_id=a.boot_id)
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
        common.host_check(a.host_state,out,False,a.boot_id,
                          reference=a.host_reference,reference_sha256=a.host_reference_sha256)
        result['kernel_identity']=common.kernel_identity.capture(a,out,rt.command)
        result['kernel_binding']=common.mm_platform.kernel_binding(result['kernel_identity'],a.kernel_source,
                                      a.kernel_baseline,private_backing_locks=False)
        evidence=out/'writer-disassembly';evidence.mkdir()
        writer_sites=sites_check.checked_receipt(a.writer_sites,a.writer_sites_sha256,
                         result['kernel_binding'],a.kernel_source/'vmlinux',evidence,rt.command)
        shutil.copyfile(a.writer_sites,out/'writer-sites.json')
        result.update(writer_sites=writer_sites,writer_sites_sha256=a.writer_sites_sha256)
        manifest=json.loads(a.source_manifest.read_text());source=out/'source'
        dirs=('workload_modules/mmap_writer/','bench/mmap_writer/','tests/kernel/mmap_writer/',
              'bench/mmap_fault/','bench/spin_cacheline/','tests/protocols/','disassem/','kernel_baseline/',
              'tests/unit/','include/','daemon/','kernel_integration/linux70/','bench/basic/')
        hashes={k:h for k,h in manifest['files'].items() if k.startswith(dirs) or k in
                ('bench/archive_run.py','bench/mmap_lock/eligibility.py')}
        for name,h in hashes.items():
            rt.require(rt.digest(ROOT/name)==h,'committed source changed: '+name)
            dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        shutil.copyfile(a.source_manifest,out/'committed-source.json');rt.write_json(out/'source-sha256.json',hashes)
        result.update(source_commit=manifest['commit'],source_manifest_sha256=rt.digest(a.source_manifest),source_files=len(hashes),script_sha256=rt.digest(Path(__file__)))
        def verify():
            rt.require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==a.boot_id and
                       rt.digest(a.writer_sites)==rt.digest(out/'writer-sites.json')==a.writer_sites_sha256,
                       'boot or reviewed writer sites changed')
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
            sites=[str(writer_sites['sites'][name]['return_offset']) for name in ('vm_mmap_pgoff','__vm_munmap')]
            data=rt.command([client,mode,str(n),str(iterations),*sites],out/(name+'.jsonl'),timeout=120)
            logs();case=validate([json.loads(line) for line in data.splitlines()],mode,n,iterations,
                                lambda row:sites_check.validate_witness(row,writer_sites))
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
        common.finish_logs(out,result,logs,fd)
    print(json.dumps({k:result[k] for k in ('state','passed','drained','source_commit','basic_programs')}))


if __name__=='__main__':main()
