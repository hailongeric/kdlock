#!/usr/bin/env python3
"""Seal final idle recovery health after the serial actual-MM checks."""
import json
import os
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
ROOT = Path('/root/host_fs/kdlock')
BASE = Path('/root/kdlock-evidence/10.176.26.71/tests/actual-mm-plain-20261021')
sys.path.insert(0, str(ROOT / 'bench/spin_cacheline'))
import bench_runtime as rt


def main():
    transition = runpy.run_path(str(BASE / 'transition.py'))
    transition['idle']()
    prior = json.loads((BASE / 'recovery-transition-1/result.json').read_text())
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    rt.require(prior['passed'] and prior['idle'] and prior['boot_id'] == boot and
               prior['release'] == os.uname().release == '6.1.159-kdclobber2',
               'verified recovery boot required')
    result = transition['preserved']()
    modules = sorted(line.split()[0] for line in Path('/proc/modules').read_text().splitlines())
    rt.require(modules == prior['modules'], 'final runtime module set differs')
    for manifest in ('prepare-1/inputs.json', 'compatibility-1/source-sha256.json'):
        files = json.loads((BASE / manifest).read_text())
        if manifest.endswith('inputs.json'):
            files = files['files']
        rt.require(all(rt.digest(Path(name)) == digest for name, digest in files.items()),
                   'frozen source or binary changed: ' + manifest)
    compatibility = json.loads((BASE / 'compatibility-1/result.json').read_text())
    rt.require(compatibility['passed'] and compatibility['final_idle'] and
               compatibility['modules_loaded'] == 0, 'default builds incomplete')
    messages = rt.command(['dmesg'], BASE / 'final-recovery-dmesg.log')
    faults = rt.FAULT.findall(messages)
    rt.require(not faults, 'final recovery boot contains a kernel fault')
    transition['idle']()
    result.update(passed=True, idle=True, boot_id=boot, release=os.uname().release,
                  build_id=prior['build_id'], modules=modules,
                  new_faults_in_retained_dmesg=faults,
                  boot_io_errors=[line for line in messages.splitlines() if 'I/O error' in line],
                  transition_sha256=rt.digest(BASE / 'recovery-transition-1/result.json'),
                  compatibility_sha256=rt.digest(BASE / 'compatibility-1/result.json'),
                  inputs_sha256=rt.digest(BASE / 'prepare-1/inputs.json'),
                  driver_sha256=rt.digest(Path(__file__)), timing_sessions=0,
                  accepted=False, seven_mutex_causes='UNRESOLVED', p95_status='DEFERRED')
    rt.write_json(BASE / 'final-health.json', result)
    print(json.dumps(dict(passed=True, idle=True, boot_id=boot, modules=len(modules))))


if __name__ == '__main__':
    main()
