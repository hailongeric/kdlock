#!/usr/bin/env python3
"""Retain all split-stage attempts and verify actual idle after the serial runs."""
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
BASE=Path('/root/kdlock-evidence/10.176.26.71/tests/mmap-fault-split-20261021')
BOOT='b65f0205-c8f9-4385-8b13-039cbce243a6'
sys.path.insert(0,str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert os.geteuid()==0 and os.uname().release=='6.1.159-kdclobber2'
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
    spec=importlib.util.spec_from_file_location('archive',ROOT/'bench/archive_run.py')
    archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)
    archive.idle(BASE,rt.idle)
    for path in Path('/proc').glob('[0-9]*/task/[0-9]*/comm'):
        try:assert path.read_text().strip() not in ('mf_split_worker','mf_time_worker')
        except FileNotFoundError:pass
    maps={};attempts=[]
    for name in ('live-1','live-2','timing-prepare-1','timing-prepare-2','timing-run-1'):
        base=BASE/name;r=read(base/'result.json')
        if name=='timing-prepare-1':
            assert r['state']=='FAILED' and not r['passed'] and not r['sessions']
            assert not list(base.rglob('load-provider.log')) and not (base/'build-client.log').exists()
        else:assert r['passed'] and r['drained'] and r['final_idle'] and r['accepted'] is False
        if (base/'committed-source.json').exists():
            manifest=read(base/'committed-source.json')
            maps.update({str(base/'source'/p):h for p,h in manifest['files'].items() if (base/'source'/p).is_file()})
        for filename,root in [('prepared-source-sha256.json',base/'build/provider'),('binary-sha256.json',base)]:
            if (base/filename).exists():maps.update({str(root/p):h for p,h in read(base/filename).items()})
        if (base/'inputs.json').exists():maps.update(read(base/'inputs.json')['files'])
        attempts.append(dict(name=name,state=r['state'],passed=r['passed'],
            source_commit=r.get('source_commit',read(base/'committed-source.json')['commit'] if (base/'committed-source.json').exists() else None),
            result_sha256=sha(base/'result.json')))
    for path,digest in maps.items():assert sha(Path(path))==digest,path
    run=read(BASE/'timing-run-1/result.json');prep=read(BASE/'timing-prepare-2/result.json')
    assert len(run['sessions'])==48 and len(prep['sessions'])==8
    assert all(s['passed'] and s['drained'] and not s['measurement']['delegated'] for s in run['sessions']+prep['sessions'])
    faults=[]
    for path in BASE.rglob('kernel.log'):
        for line in path.read_text().splitlines():
            if rt.FAULT.search(line):faults.append(dict(path=str(path.relative_to(BASE)),line=line))
    assert not faults,faults
    oracle=read(BASE/'oracle-checks/checks.json')
    assert oracle['passed'] and oracle['positive_receipts']==1 and len(oracle['rejected'])==9
    control=BASE/'control';control.mkdir(exist_ok=False)
    for path in sorted(Path('/tmp').glob('kd-mf-*-host-*.json')):
        shutil.copyfile(path,control/path.name)
    for pattern in ('kd-mf-split-live-*-supervision.log*','kd-mf-time-*-supervision.log*'):
        for path in sorted(Path('/tmp').glob(pattern)):
            shutil.copyfile(path,control/path.name)
    # The source-host capture was taken immediately after the timing command,
    # before evidence copying. It cannot be replaced by a later settled state.
    endpoint=read(control/'kd-mf-time-host-immediate-after.json')
    original=read(Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2/matrix/host-state.json'))
    before=read(BASE/'timing-run-1/host-before.json')
    tasks=lambda h:sorted(h['qemu'][0]['tasks'],key=lambda t:t['tid'])
    assert tasks(before)==tasks(original) and len(tasks(before))==67
    config={k:endpoint[k]==original[k] for k in ('cpufreq','numa','recovery_snapshot')}
    config.update({k:endpoint['qemu'][0][k]==original['qemu'][0][k] for k in ('pid','args')})
    endpoint_summary=dict(captured_utc=endpoint['captured_utc'],threads=len(tasks(endpoint)),
        exact_original_threads=tasks(endpoint)==tasks(original),configuration_checks=config,
        pins_verified=endpoint['pins_verified'],snapshot_listed=endpoint['snapshot_listed'],
        original_threads=67)
    shutil.copyfile(__file__,BASE/'capture-health.py')
    archive.idle(BASE,rt.idle)
    health=dict(idle=True,boot_id=BOOT,kernel_release=os.uname().release,finished_ns=time.time_ns(),
        accepted=False,attempts=attempts,verified_hashes=len(maps),per_session_kernel_faults=faults,
        correctness_split_cases=18,timing_validation_sessions=8,timing_sessions=48,
        oracle_rejections=9,strict_host_endpoint=endpoint_summary,
        script_sha256=sha(Path(__file__)))
    with (BASE/'final-health.json').open('x') as f:json.dump(health,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(health))


if __name__=='__main__':main()
