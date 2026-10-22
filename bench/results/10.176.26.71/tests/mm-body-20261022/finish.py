#!/usr/bin/env python3
"""Preserve build failures and final recovery health after serial MM checks."""
import json
import os
from pathlib import Path
import runpy
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/tests/mm-body-20261022')
OUT = Path('/root/kdlock-kernel-work/mm-body-20261022/candidate-1')
BUNDLE = Path('/root/kdlock-kernel-baselines/mmap-kdmm2-20261022')
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt


def main():
    assert os.geteuid() == 0 and os.uname().release == '6.1.159-kdclobber2'
    transition = runpy.run_path(str(BASE / 'control/transition.py'))
    transition['idle']()
    recovery = json.loads((BASE / 'recovery-1/transition/result.json').read_text())
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert recovery['passed'] and recovery['idle'] and recovery['boot_id'] == boot
    assert recovery['build_id'] == '5ca28058e156f34a2c7fe91e8e0fbf92f4e51960'
    preserved = transition['preserved']()
    modules = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    assert modules == recovery['modules']
    verifier = runpy.run_path(str(ROOT / 'kernel_baseline/verify.py'))['verify']
    verified = verifier(BUNDLE, OUT / 'linux', build=True)
    evidence = BASE / 'build-evidence'
    evidence.mkdir()
    for path in OUT.iterdir():
        if path.is_file() and path.suffix in ('.json', '.log', '.symvers'):
            shutil.copyfile(path, evidence / path.name)
    shutil.copytree(OUT / 'failed-attempt-1', evidence / 'failed-attempt-1')
    shutil.copytree(BUNDLE, evidence / 'baseline')
    shutil.copytree(BUNDLE.with_name(BUNDLE.name + '-capture-failed-1'), evidence / 'failed-capture-1')
    manifest = json.loads((BUNDLE / 'manifest.json').read_text())
    for name, digest in manifest['source_files'].items():
        target = evidence / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OUT / 'linux' / name, target)
        assert rt.digest(target) == digest
    rows = []
    for mode, tasks in [('native', ('api', 'mmap', 'page-fault', 'completed-fault')),
                        ('kd', ('api', 'body', 'body-cancellation', 'mmap', 'page-fault', 'completed-fault'))]:
        for task in tasks:
            path = BASE / (mode + '-1') / task / 'result.json'
            row = json.loads(path.read_text())
            assert row['passed'] and row['drained']
            rows.append(dict(mode=mode, task=task, receipt=str(path), sha256=rt.digest(path),
                             boot_id=row['boot_id']))
    messages = rt.command(['dmesg'], BASE / 'final-recovery-dmesg.log')
    assert not rt.FAULT.search(messages)
    transition['idle']()
    result = dict(passed=True, idle=True, release=os.uname().release, boot_id=boot,
                  build_id=recovery['build_id'], modules=modules, sessions=rows,
                  recovery_preservation=preserved, candidate_verification=verified,
                  candidate_manifest_sha256=rt.digest(BUNDLE / 'manifest.json'),
                  new_faults_in_retained_dmesg=[], timing_started=False,
                  performance_accepted=False, seven_mutex_causes='UNRESOLVED', p95='DEFERRED',
                  driver_sha256=rt.digest(Path(__file__)))
    rt.write_json(BASE / 'final-health.json', result)
    print(json.dumps(dict(passed=True, idle=True, boot_id=boot, sessions=len(rows), modules=len(modules))))


if __name__ == '__main__':
    main()
