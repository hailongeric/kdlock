#!/usr/bin/env python3
"""Verify this recovery boot and emit the existing replay driver's schema."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/tests/actual-mm-plain-20261021')
ORIGINAL = Path('/root/kdlock-evidence/10.176.26.71/bench/mutex-public-20261020-r2')
sys.path.insert(0, str(ROOT/'bench/spin_cacheline'))
import bench_runtime as rt
import kernel_identity


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir()
    transition_path=BASE/'recovery-transition-1/result.json'
    health_path=BASE/'final-health.json'
    rt.require(rt.digest(transition_path)=='f7178c7cdbe7d2b3713d536e1d9493e4d5779e59eef47ea7db9c02e3839fb1d3' and
        rt.digest(health_path)=='4f5500fc7c7472de6328f81484c3fb0b770e6f0158442002599c1741a43629e5' and
        rt.digest(BASE/'transition.py')=='a9304517628c0f63156d98cfa656bd966148f74deb90cf69120b7d579b9ad07b',
        'retained recovery evidence changed')
    transition=json.loads(transition_path.read_text());health=json.loads(health_path.read_text())
    control=runpy.run_path(str(BASE/'transition.py'));control['idle']()
    preserved=control['preserved']()
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    modules=sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    rt.require(transition['passed'] and health['passed'] and transition['boot_id']==health['boot_id']==boot and
        os.uname().release==transition['release']=='6.1.159-kdclobber2' and
        modules==transition['modules']==health['modules'] and len(modules)==73,
        'current recovery boot or modules differ')
    scheduler=runpy.run_path(str(ROOT/'bench/mutex_api_compare/run.py'))
    bindings={}
    for name,digest in scheduler['REPLAY_ENVIRONMENT_SHA256'].items():
        path=ORIGINAL/'matrix'/name;rt.require(rt.digest(path)==digest,'original environment changed')
        bindings[str(path)]=digest
    original=json.loads((ORIGINAL/'matrix/environment.json').read_text())
    previous=os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0,{63});collector=rt.capture_topology([63])
    finally:os.sched_setaffinity(0,previous)
    environment=dict(boot_id=boot,cmdline=Path('/proc/cmdline').read_text().strip(),
        preemption=Path('/sys/kernel/debug/sched/preempt').read_text().strip(),python=sys.executable,
        packages={n:importlib.metadata.version(n) for n in ('miasm','future','pyparsing','pyelftools')},
        snapshot_tag=os.environ['KDLOCK_SNAPSHOT_TAG'],collector_topology=collector)
    rt.require(original['boot_id']=='b65f0205-c8f9-4385-8b13-039cbce243a6' and boot!=original['boot_id'],
        'recorded original/new boot required')
    for key,value in environment.items():
        if key!='boot_id':rt.require(original[key]==value,'original guest control differs: '+key)
    topology=rt.capture_topology(list(range(60)))
    rt.require(topology==json.loads((ORIGINAL/'matrix/topology.json').read_text()),'original topology differs')
    identity=kernel_identity.capture(argparse.Namespace(kernel_source=Path('/root/linux-6.1.159-kdclobber2'),
        kernel_baseline=Path('/root/kdlock-kernel-baselines/mutex-clobber2-20260919')),a.output,rt.command)
    rt.require(identity['running_build_id']=='5ca28058e156f34a2c7fe91e8e0fbf92f4e51960','recovery Build ID differs')
    messages=rt.command(['dmesg'],a.output/'dmesg.log');rt.require(not rt.FAULT.search(messages),'kernel fault')
    control['idle']()
    result=dict(passed=True,idle=True,original_boot_id=original['boot_id'],new_boot_id=boot,
        before_boot_id=transition['before_boot_id'],kernel_release=os.uname().release,
        kernel_build_id=identity['running_build_id'],kernel_identity=identity,modules=modules,
        recovery_preserved=preserved['recovery_preserved'],same_boot=False,environment=environment,
        original_environment_bindings=bindings,topology=topology,driver_sha256=rt.digest(Path(__file__)),
        derivation={str(transition_path):rt.digest(transition_path),str(health_path):rt.digest(health_path)},
        scope='Fresh verification of existing recovery boot; original guest controls unchanged. Host admission remains per session.')
    rt.write_json(a.output/'result.json',result)
    print(json.dumps(dict(passed=True,new_boot_id=boot,sha256=rt.digest(a.output/'result.json'))))


if __name__=='__main__':main()
