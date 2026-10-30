#!/usr/bin/env python3
"""Bounded preservation wrapper around maintained archive_run; no measurement."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/mnt/kdlock-builds/kdlock-evidence/10.176.26.71/tests/kdscope1-api-f7a84065-20261030')
OUT = BASE.with_name(BASE.name+'-archive-control')
ARCHIVES = BASE.with_name(BASE.name+'-archives')
BOOT = '2e0ea0fa-ff34-4416-9175-b4b0ede3f63b'
COMMIT = 'f7a84065e84474380faa37eeadfdf534abd72a68'
PYTHON = '/mnt/kdlock-builds/venvs/kdlock-translation-7.0-20261027/bin/python3'
PHASE_CONTROLLER = Path('/tmp/kdlock-scope-api-step-r3-20261030.py')
PHASE_SHA = '35495b774fd74872cd204140ef76fe4cdcc34b2235cbac051d05999c9101bf6c'
REFERENCE = Path('/tmp/kdlock-scope-f7-pool64-host-reference.json')
REFERENCE_SHA = '95199f8417b1eb8a0e7a406fa1143dec17090aa0973c6db3d0ae828e401ed588'
POLICY_SHA = '52dd632277c8997b8e10c4dee335cfddeb3cea3e029674d66b0b933998070e46'

def require(value, message):
    if not value: raise RuntimeError(message)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''): h.update(chunk)
    return h.hexdigest()

def read(path): return json.loads(Path(path).read_text())

def save(path, value):
    tmp=path.with_name('.'+path.name+'.tmp')
    with tmp.open('w') as f:
        json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
    tmp.replace(path)

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path); result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result); return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--measure-owner-sha256',required=True)
    p.add_argument('--host-after',type=Path,required=True)
    p.add_argument('--host-after-sha256',required=True)
    p.add_argument('--endpoint-result',type=Path,required=True)
    p.add_argument('--endpoint-result-sha256',required=True)
    a=p.parse_args()
    require(os.geteuid()==0 and sys.executable==PYTHON and os.uname().release=='7.0.0-38-kdscope1','expected guest/Python/kernel')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT,'boot differs')
    require([x for x in Path('/proc/cmdline').read_text().split() if x.startswith('kd_mmap=')]==['kd_mmap=off'],'Native MM mode required')
    require(not OUT.exists() and not ARCHIVES.exists(),'fresh archive/control siblings required')
    OUT.mkdir(); shutil.copyfile(__file__,OUT/'controller.py')
    owner=dict(schema=1,completed=False,state='ADMISSION',source_commit=COMMIT,boot_id=BOOT,
               script_sha256=sha(Path(__file__)),performance_accepted=False,idle=False,
               drain_unknown=False,started=time.time(),measure_owner_sha256=a.measure_owner_sha256)
    child=None
    def persist(): save(OUT/'owner.json',owner)
    def interrupted(signum,frame): raise InterruptedError('archive wrapper interrupted; child untouched')
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,interrupted)
    persist()
    try:
        require(sha(PHASE_CONTROLLER)==PHASE_SHA,'reviewed phase validator changed')
        api=module('reviewed_api_phase',PHASE_CONTROLLER)
        measure=BASE/'measure-control/owner.json'
        require(sha(measure)==a.measure_owner_sha256,'actual completed measure owner differs')
        bindings={}
        for phase in ('basic','objects','functional','measure'):
            control=BASE/(phase+'-control');o=read(control/'owner.json');result=BASE/phase/'result.json'
            require(o.get('state')=='COMPLETE' and o.get('completed') is True and
                    o.get('final_idle') is True and o.get('completion_checks_passed') is True and
                    o.get('drain_unknown') is False and o.get('child_returncode')==0 and
                    o.get('source_commit')==COMMIT and o.get('boot_id')==BOOT and
                    o.get('inputs',{}).get('controller.py')==PHASE_SHA and
                    o.get('result_sha256')==sha(result),'phase owner incomplete or differs: '+phase)
            api.verify_phase(read(result),phase,BOOT)
            bindings[str(control/'owner.json')]=sha(control/'owner.json');bindings[str(result)]=sha(result)
        o=read(measure)
        require(o.get('planned_points')==126 and o.get('rounds_per_point')==1,'exact measurement count differs')
        control=measure.parent
        for name in ('source-state.json','source-sha256.json','host-before.json','host-reference.json'):
            require(sha(control/name)==o['inputs'][name],'measurement input differs: '+name)
        state=read(control/'source-state.json');sources=read(control/'source-sha256.json')
        require(state.get('git_head')==COMMIT and not state.get('git_status') and state.get('files')==len(sources),'frozen source state differs')
        def sources_unchanged():
            require(all(sha(ROOT/name)==digest for name,digest in sources.items()),'frozen source bytes changed')
        sources_unchanged()
        require(sha(a.host_after)==a.host_after_sha256 and sha(a.endpoint_result)==a.endpoint_result_sha256 and
                sha(REFERENCE)==REFERENCE_SHA,'endpoint/reference input differs')
        policy=read(a.endpoint_result);host=read(a.host_after)
        require(policy.get('action')=='verify' and policy.get('completed') is True and
                policy.get('mutation_attempted') is False and policy.get('policy_state_unknown') is False and
                policy.get('apply_receipt_sha256')==POLICY_SHA and
                policy.get('final_properties')=={'thread-pool-min':64,'thread-pool-max':64,'aio-max-batch':0} and
                policy['captures']['after']['sha256']==a.host_after_sha256,'endpoint policy incomplete')
        platform=module('maintained_mm_platform',ROOT/'bench/mmap_fault/mm_platform.py')
        now=datetime.datetime.now(datetime.timezone.utc)
        comparison=platform.compare_host(read(REFERENCE),host,now,'linux70-kdlock1-clean-20261027',True)
        platform.compare_host(read(control/'host-before.json'),host,now,'linux70-kdlock1-clean-20261027',True)
        require(comparison['original_threads']==comparison['observed_threads']==131,'expected131-task endpoint')
        for name,src in (('host-after.json',a.host_after),('endpoint-policy.json',a.endpoint_result)):
            with (BASE/name).open('xb') as f:f.write(src.read_bytes())
        endpoint=dict(schema=1,completed=True,source_commit=COMMIT,boot_id=BOOT,
            measure_owner_sha256=a.measure_owner_sha256,host_after_sha256=a.host_after_sha256,
            endpoint_policy_sha256=a.endpoint_result_sha256,reference_sha256=REFERENCE_SHA,
            comparison=comparison,captured_utc=host['captured_utc'],measure_finished=o['finished'],
            performance_accepted=False,scope='Strict endpoint identity only; not uninterrupted isolation or performance acceptance')
        require(not (BASE/'endpoint-receipt.json').exists(),'preserve existing endpoint')
        save(BASE/'endpoint-receipt.json',endpoint)
        sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
        archive=module('maintained_archive_run',ROOT/'bench/archive_run.py')
        from bench_runtime import idle as common_idle
        archive.idle(BASE,common_idle)
        health=dict(schema=1,idle=True,boot_id=BOOT,source_commit=COMMIT,checked=time.time(),
            actual_idle_predicates=['bench/archive_run.py:idle','bench/spin_cacheline/bench_runtime.py:idle'],
            idle_source_sha256=sha(ROOT/'bench/spin_cacheline/bench_runtime.py'),
            archive_source_sha256=sha(ROOT/'bench/archive_run.py'),phase_receipts=bindings,
            endpoint_receipt_sha256=sha(BASE/'endpoint-receipt.json'),performance_accepted=False,
            scope='Actual maintained idle plus retained successful phase checks; no new fault diagnostics')
        require(not (BASE/'final-health.json').exists(),'preserve existing final health')
        save(BASE/'final-health.json',health)
        argv=[PYTHON,str(ROOT/'bench/archive_run.py'),'--base',str(BASE),'--output',str(ARCHIVES),
              '--health',str(BASE/'final-health.json'),'--kernel-variant','kdscope1-native',
              '--kernel-source','/mnt/kdlock-builds/linux-7.0.0-38-kdscope1/build',
              '--kernel-baseline','/root/kdlock-kernel-baselines/linux70-kdscope1-native-20261030',
              '--timeout-seconds','3600']
        for phase in ('basic','objects','functional','measure'):argv+=['--group',phase+'='+phase]
        owner.update(state='ARCHIVING',argv=argv,drain_unknown=True,
                     endpoint_receipt_sha256=sha(BASE/'endpoint-receipt.json'),final_health_sha256=sha(BASE/'final-health.json'))
        persist()
        with (OUT/'archive.log').open('xb') as log:
            child=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                   env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),start_new_session=True)
            owner['pid']=child.pid;persist();code=child.wait(timeout=3660)
        owner['returncode']=code;persist();require(code==0,'maintained archive failed')
        result=read(ARCHIVES/'archives.json')
        require(result.get('completed') is True and result.get('guest_idle') is True and result.get('boot_id')==BOOT and
                result.get('guest_base')==str(BASE) and result.get('kernel_variant')=='kdscope1-native' and
                {r['group'] for r in result['groups']}=={'basic','objects','functional','measure','metadata'},'archive incomplete')
        sources_unchanged();require(all(sha(Path(n))==v for n,v in bindings.items()),'phase receipts changed')
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT,'boot changed')
        archive.idle(BASE,common_idle)
        owner.update(completed=True,state='COMPLETE',idle=True,drain_unknown=False,
                     archives_sha256=sha(ARCHIVES/'archives.json'),finished=time.time())
    except BaseException as error:
        owner.update(state='FAILED',error=repr(error),finished=time.time())
        if child is not None:owner.update(child_returncode=child.poll(),drain_unknown=True)
        raise
    finally:persist()
    print(json.dumps(owner,sort_keys=True))

if __name__=='__main__':main()
