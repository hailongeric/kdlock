#!/usr/bin/env python3
"""Retain attempts and verify final idle after serial Native shared-mm checks."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
sys.dont_write_bytecode=True
ROOT=Path('/root/host_fs/kdlock')
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mmap-writer-native-20261021')
BOOT='b65f0205-c8f9-4385-8b13-039cbce243a6'
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt

def read(p):return json.loads(p.read_text())
def main():
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
    spec=importlib.util.spec_from_file_location('archive',ROOT/'bench/archive_run.py')
    archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive);archive.idle(BASE,rt.idle)
    for p in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:assert p.read_text().strip() not in ('mw_worker','mw_time_worker')
        except FileNotFoundError:pass
    attempts=[];maps={}
    for name in ('live-1','live-2','live-3','timing-prepare-1','timing-run-1'):
        base=BASE/name;r=read(base/'result.json')
        if name in ('live-1','live-2'):
            c=read(base/'cleanup.json')
            assert r['state']=='FAILED' and not r['passed'] and len(r['cases'])==2
            assert c['normal_unload'] and not c['workers'] and c['health_before']=='files=0 mm_refs=0 destroyed=3 release_errors=0'
        else:assert r['passed'] and r['drained'] and r['final_idle'] and r['accepted'] is False
        for filename,root in [('source-sha256.json',base/'source'),('binary-sha256.json',base)]:
            if (base/filename).exists():maps.update({str(root/p):h for p,h in read(base/filename).items()})
        if (base/'inputs.json').exists():maps.update(read(base/'inputs.json')['files'])
        attempts.append(dict(name=name,state=r['state'],passed=r['passed'],source_commit=r['source_commit'],result_sha256=rt.digest(base/'result.json')))
    for path,digest in maps.items():assert rt.digest(Path(path))==digest,path
    live=read(BASE/'live-3/result.json');prep=read(BASE/'timing-prepare-1/result.json');run=read(BASE/'timing-run-1/result.json')
    assert len(live['cases'])==6 and len(prep['sessions'])==4 and len(run['sessions'])==12
    assert all(s['passed'] and s['drained'] and not s['measurement']['delegated'] and s['measurement']['fault_callbacks']==0 for s in prep['sessions']+run['sessions'])
    faults=[]
    for p in BASE.rglob('kernel.log'):
        for line in p.read_text().splitlines():
            if rt.FAULT.search(line):faults.append(dict(path=str(p.relative_to(BASE)),line=line))
    assert not faults
    oracle=read(BASE/'oracle-checks-1/checks.json');assert oracle['passed'] and oracle['positive_receipts']==2 and len(oracle['rejected'])==18
    shutil.copyfile(ROOT/'bench/mmap_writer/check_oracles.py',BASE/'oracle-checks-1/check_oracles.py')
    assert rt.digest(BASE/'oracle-checks-1/check_oracles.py')==oracle['script_sha256']
    elf=BASE/'kernel-elf-1/vmlinux';proof=read(BASE/'kernel-elf-1/writer-elf-capture.json')
    assert rt.digest(elf)==proof['vmlinux_sha256']==live['writer_sites']['vmlinux_sha256']
    for name,digest in proof['outputs'].items():assert rt.digest(BASE/'kernel-elf-1/writer-elf'/name)==digest
    control=BASE/'control';control.mkdir(exist_ok=False)
    for pattern in ('kd-mmap-writer-host-*.json','kd-mmap-writer-*-supervision.log*','kd-mmap-writer-live-*-cleanup.log*'):
        for p in sorted(Path('/tmp').glob(pattern)):shutil.copyfile(p,control/p.name)
    endpoint=read(control/'kd-mmap-writer-host-immediate-after.json')
    original=read(Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2/matrix/host-state.json'))
    before=read(BASE/'timing-run-1/host-before.json');tasks=lambda h:sorted(h['qemu'][0]['tasks'],key=lambda t:t['tid'])
    assert tasks(before)==tasks(original) and len(tasks(before))==67
    config={k:endpoint[k]==original[k] for k in ('cpufreq','numa','recovery_snapshot')}
    config.update({k:endpoint['qemu'][0][k]==original['qemu'][0][k] for k in ('pid','args')})
    endpoint_summary=dict(captured_utc=endpoint['captured_utc'],threads=len(tasks(endpoint)),original_threads=67,
        exact_original_threads=tasks(endpoint)==tasks(original),configuration_checks=config,
        pins_verified=endpoint['pins_verified'],snapshot_listed=endpoint['snapshot_listed'])
    shutil.copyfile(__file__,BASE/'capture-health.py');archive.idle(BASE,rt.idle)
    health=dict(idle=True,boot_id=BOOT,kernel_release=os.uname().release,finished_ns=time.time_ns(),accepted=False,
        attempts=attempts,verified_hashes=len(maps),per_session_kernel_faults=faults,correctness_cases=6,
        timing_validation_sessions=4,timing_sessions=12,oracle_rejections=18,strict_host_endpoint=endpoint_summary,
        kernel_modified=False,kd_integration=False,script_sha256=rt.digest(Path(__file__)))
    with (BASE/'final-health.json').open('x') as f:json.dump(health,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(health))

if __name__=='__main__':main()
